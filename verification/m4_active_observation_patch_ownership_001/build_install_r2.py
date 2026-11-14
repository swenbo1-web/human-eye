"""Build a deterministic manifest wheel and install into this task's isolated root."""

import argparse
import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import time
import zipfile


VERSION = '9.7.2+m4.active.patch.ownership.r2'
OLD_VERSION = '9.7.2+m4.active.brief.delivery.r1'
OLD_WHEEL_SHA = '67aaa5acfa8b7009d9d3f83bab743328c7d5686208458207fd453cc57f517334'


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def save(path, value):
    with path.open('xb') as stream:
        stream.write((json.dumps(value, sort_keys=True, indent=2) + '\n').encode())


def wheel_bytes(members):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, blob in sorted(members.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o644 << 16
            archive.writestr(info, blob)
    return buffer.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--external-root', type=Path, required=True)
    parser.add_argument('--freeze', type=Path, required=True)
    parser.add_argument('--preparation-git', required=True)
    args = parser.parse_args()
    root = args.repo.resolve()
    output = args.output.resolve()
    external = args.external_root.resolve()
    output.mkdir(exist_ok=False)
    started = time.perf_counter_ns()
    frozen = json.loads(args.freeze.read_bytes())
    manifest = frozen['runtime_manifest']
    for row in manifest:
        assert digest((root / row['path']).read_bytes()) == row['sha256']

    old = root / 'verification/m4_active_observation_brief_delivery_001/build'
    old_wheel = next(old.glob('*.whl'))
    assert digest(old_wheel.read_bytes()) == OLD_WHEEL_SHA
    members = {}
    source_paths = {row['path'] for row in manifest}
    wheel_started = time.perf_counter_ns()
    with zipfile.ZipFile(old_wheel) as archive:
        for name in archive.namelist():
            renamed = name.replace(OLD_VERSION, VERSION)
            blob = archive.read(name)
            if name.endswith('RECORD'):
                continue
            if name in source_paths:
                blob = (root / name).read_bytes()
            elif name.endswith('METADATA'):
                blob = blob.replace(('Version: ' + OLD_VERSION).encode(),
                                    ('Version: ' + VERSION).encode())
            elif name.endswith('runtime_sources.json'):
                blob = (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode()
            members[renamed] = blob
    record_path = 'human_eye_spatial_plugin-' + VERSION + '.dist-info/RECORD'
    record = io.StringIO(newline='')
    writer = csv.writer(record, lineterminator='\n')
    for name, blob in sorted(members.items()):
        encoded = base64.urlsafe_b64encode(hashlib.sha256(blob).digest()).rstrip(b'=').decode()
        writer.writerow([name, 'sha256=' + encoded, len(blob)])
    writer.writerow([record_path, '', ''])
    members[record_path] = record.getvalue().encode()
    wheel = wheel_bytes(members)
    assert wheel == wheel_bytes(members)
    path = output / ('human_eye_spatial_plugin-' + VERSION + '-py3-none-any.whl')
    with path.open('xb') as stream:
        stream.write(wheel)
    with zipfile.ZipFile(path) as archive:
        for name, encoded, size in csv.reader(io.StringIO(archive.read(record_path).decode())):
            if name == record_path:
                continue
            blob = archive.read(name)
            assert len(blob) == int(size)
            assert encoded == 'sha256=' + base64.urlsafe_b64encode(
                hashlib.sha256(blob).digest()).rstrip(b'=').decode()
    wheel_closed = time.perf_counter_ns()

    product = external / 'product_r2'
    assert not product.exists()
    command = [str(external / 'venv/Scripts/python.exe'), '-I', '-B', '-m', 'pip',
               'install', '--no-index', '--no-deps', '--no-compile', '--target',
               str(product), str(path)]
    install_started = time.perf_counter_ns()
    installed = subprocess.run(command, capture_output=True)
    install_closed = time.perf_counter_ns()
    (output / 'PIP_STDOUT.txt').write_bytes(installed.stdout)
    (output / 'PIP_STDERR.txt').write_bytes(installed.stderr)
    assert installed.returncode == 0
    for row in manifest:
        assert digest((product / row['path']).read_bytes()) == row['sha256']
    identity_input = {'base_version': '9.7.2',
                      'implementation_revision': 'v26-surface-scan-pair-cache-20261112',
                      'files': manifest}
    source_hash = digest(json.dumps(identity_input, sort_keys=True,
        separators=(',', ':'), ensure_ascii=True).encode())
    binding = {'base_version': identity_input['base_version'],
               'implementation_revision': identity_input['implementation_revision'],
               'protocol_version': '2025-03-26', 'build_id': 'sha256:' + source_hash,
               'source_sha256': source_hash, 'source_manifest': manifest,
               'distribution_version': VERSION, 'install_root': str(product),
               'dependency_root': str(external / 'venv/Lib/site-packages'),
               'preparation_git': args.preparation_git,
               'source_freeze_sha256': digest(args.freeze.read_bytes()),
               'wheel_sha256': digest(wheel)}
    save(output / 'RUN_BINDING.json', binding)
    save(output / 'BUILD_INSTALL.json', {'started_ns': started,
        'wheel_started_ns': wheel_started, 'wheel_closed_ns': wheel_closed,
        'install_started_ns': install_started, 'install_closed_ns': install_closed,
        'closed_before_publication_ns': time.perf_counter_ns(),
        'command': command, 'pip_exit_code': installed.returncode,
        'wheel': {'file': str(path), 'sha256': digest(wheel), 'bytes': len(wheel),
                  'members': len(members), 'RECORD_verified': True, 'deterministic': True},
        'installed_source_files': len(manifest), 'binding': binding,
        'new_Blender_rasters_core_model_calls': 0})
    print(json.dumps({'source_sha256': source_hash, 'wheel_sha256': digest(wheel),
                      'installed_source_files': len(manifest)}))


if __name__ == '__main__':
    main()
