"""Build a source-pinned candidate using the accepted wheel's fixed metadata."""

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


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EXTERNAL = Path('D:/he_m5_observe_measure_001')


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def save(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')


def wheel_bytes(members):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, blob in sorted(members.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o644 << 16
            archive.writestr(info, blob)
    return output.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=('initial', 'final'), required=True)
    parser.add_argument('--freeze', type=Path, required=True)
    parser.add_argument('--preparation-git', required=True)
    args = parser.parse_args()
    started = time.perf_counter_ns()
    output = HERE / ('build_' + args.phase)
    install = EXTERNAL / ('B_initial' if args.phase == 'initial' else 'B') / 'product'
    if output.exists() or install.exists():
        raise FileExistsError('candidate_build_is_write_once')
    frozen = read(args.freeze)
    manifest = frozen['runtime_manifest']
    if not manifest or len({row['path'] for row in manifest}) != len(manifest):
        raise ValueError('unique_frozen_runtime_sources_required')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip()
    if head != args.preparation_git:
        raise ValueError('candidate_preparation_commit_changed')
    for row in manifest:
        blob = (ROOT / row['path']).read_bytes()
        committed = subprocess.check_output(['git', 'show', head + ':' + row['path']], cwd=ROOT)
        if digest(blob) != row['sha256'] or committed != blob:
            raise ValueError('candidate_source_commit_or_freeze_mismatch')
    baseline = read(HERE / 'A_RUN_BINDING.json')
    templates = list((HERE.parent / 'm4_target_acquisition_002/build_B').glob('*.whl'))
    if len(templates) != 1 or digest(templates[0].read_bytes()) != baseline['wheel_sha256']:
        raise ValueError('accepted_wheel_template_changed')
    old_version = baseline['distribution_version']
    version = '9.7.2+m5.observe.measure.001.' + ('r0' if args.phase == 'initial' else 'r1')
    members = {}
    old_sources = {row['path'] for row in baseline['source_manifest']}
    wheel_started = time.perf_counter_ns()
    with zipfile.ZipFile(templates[0]) as archive:
        for name in archive.namelist():
            if name.endswith('RECORD') or name in old_sources:
                continue
            blob = archive.read(name)
            if name.endswith('METADATA'):
                blob = blob.replace(('Version: ' + old_version).encode(), ('Version: ' + version).encode())
            if name.endswith('runtime_sources.json'):
                blob = (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode()
            members[name.replace(old_version, version)] = blob
    for row in manifest:
        members[row['path']] = (ROOT / row['path']).read_bytes()
    record_name = 'human_eye_spatial_plugin-' + version + '.dist-info/RECORD'
    record = io.StringIO(newline='')
    writer = csv.writer(record, lineterminator='\n')
    for name, blob in sorted(members.items()):
        encoded = base64.urlsafe_b64encode(hashlib.sha256(blob).digest()).rstrip(b'=').decode()
        writer.writerow([name, 'sha256=' + encoded, len(blob)])
    writer.writerow([record_name, '', ''])
    members[record_name] = record.getvalue().encode()
    wheel = wheel_bytes(members)
    if wheel != wheel_bytes(members):
        raise ValueError('wheel_nondeterministic')
    output.mkdir()
    path = output / ('human_eye_spatial_plugin-' + version + '-py3-none-any.whl')
    with path.open('xb') as stream:
        stream.write(wheel)
    with zipfile.ZipFile(path) as archive:
        for name, encoded, size in csv.reader(io.StringIO(archive.read(record_name).decode())):
            if name == record_name:
                continue
            blob = archive.read(name)
            expected = 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(blob).digest()).rstrip(b'=').decode()
            if encoded != expected or len(blob) != int(size):
                raise ValueError('wheel_record_verification')
    wheel_closed = time.perf_counter_ns()
    command = ['D:/he_anchor_001/venv/Scripts/python.exe', '-I', '-B', '-m', 'pip', 'install',
               '--no-index', '--no-deps', '--no-compile', '--target', str(install), str(path)]
    install_started = time.perf_counter_ns()
    process = subprocess.run(command, capture_output=True)
    install_closed = time.perf_counter_ns()
    (output / 'PIP_STDOUT.txt').write_bytes(process.stdout)
    (output / 'PIP_STDERR.txt').write_bytes(process.stderr)
    if process.returncode:
        raise ValueError('isolated_install_failed')
    for row in manifest:
        if digest((install / row['path']).read_bytes()) != row['sha256']:
            raise ValueError('installed_source_mismatch')
    identity = {key: baseline[key] for key in ('base_version', 'implementation_revision')}
    source_hash = digest(json.dumps(dict(identity, files=manifest), sort_keys=True,
                                   separators=(',', ':'), ensure_ascii=True).encode())
    binding = dict(identity, protocol_version=baseline['protocol_version'],
        build_id='sha256:' + source_hash, source_sha256=source_hash, source_manifest=manifest,
        distribution_version=version, install_root=str(install), dependency_root=baseline['dependency_root'],
        preparation_git=head, source_freeze_sha256=digest(args.freeze.read_bytes()), wheel_sha256=digest(wheel))
    save(output / 'RUN_BINDING.json', binding)
    save(output / 'BUILD_INSTALL.json', dict(started_ns=started, wheel_started_ns=wheel_started,
        wheel_closed_ns=wheel_closed, install_started_ns=install_started, install_closed_ns=install_closed,
        closed_before_publication_ns=time.perf_counter_ns(), command=command, pip_exit_code=process.returncode,
        wheel=dict(path=str(path), sha256=digest(wheel), bytes=len(wheel), members=len(members),
                   RECORD_verified=True, deterministic=True), binding=binding,
        new_Blender_rasters_model_paid_calls=0))
    print(json.dumps(dict(phase=args.phase, source_sha256=source_hash,
                         wheel_sha256=digest(wheel), installed_source_files=len(manifest))))


if __name__ == '__main__':
    main()
