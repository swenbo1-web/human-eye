"""Build a frozen source patch into a disposable, fully offline installation."""

import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import time
import zipfile


NS = Path(__file__).resolve().parent
ROOT = NS.parent.parent
BASELINE = '08a5f3b29283270c97b6d9d6e217bbee6ca7bfc1'
A_BINDING = NS.parent / 'm4_live_assembly_relation_task_001/PRODUCT_RUN_BINDING.json'
A_BINDING_SHA = 'eb0ecece262ce0fbbe2b01f041b9e6eab77f0c4810030094c2f590850f51b2e0'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def check(condition, reason):
    if not condition:
        raise ValueError(reason)


def dumped(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf8', newline='\n')


def runtime_identity(install_root, dependency_root):
    command = [sys.executable, '-I', '-B', '-c',
               'import json,sys;sys.path[:0]=sys.argv[1:];'
               'from human_eye_plugin.runtime_identity import runtime_identity;'
               'print(json.dumps(runtime_identity()))', str(install_root), str(dependency_root)]
    return json.loads(subprocess.check_output(command, cwd=install_root))


def manifest_paths(path, package_only=False):
    files = sorted(file.relative_to(path).as_posix() for file in path.rglob('*.py') if file.is_file())
    if package_only:
        return [name for name in files if name.count('/') <= 1 and (name.startswith(
            ('human_eye_plugin/', 'human_eye_module1_operators/')) or '/' not in name)]
    return files


def prepare(label, output, patch):
    started = time.perf_counter_ns()
    baseline_raw = A_BINDING.read_bytes()
    check(sha(baseline_raw) == A_BINDING_SHA, 'A binding hash mismatch')
    baseline = json.loads(baseline_raw)
    dependency_root = Path(baseline['dependency_root']).resolve(strict=True)
    baseline_root = Path(baseline['install_root']).resolve(strict=True)
    a_identity = runtime_identity(baseline_root, dependency_root)
    check(a_identity['source_files'] == baseline['source_manifest'] and
          a_identity['source_sha256'] == baseline['source_sha256'] and
          a_identity['source_kind'] == 'installed_distribution', 'original A installation drifted')
    output.mkdir(parents=True, exist_ok=False)
    source = output / 'src'
    source.mkdir()
    source_paths = ['.gitattributes', 'pyproject.toml', 'README.md', 'human_eye_plugin', 'human_eye_module1_operators']
    source_paths += [entry['path'] for entry in baseline['source_manifest'] if '/' not in entry['path']]
    archive = subprocess.check_output(['git', 'archive', '--format=zip', BASELINE, '--', *source_paths], cwd=ROOT)
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        bundle.extractall(source)
    check(manifest_paths(source) == [row['path'] for row in baseline['source_manifest']],
          'Git source archive does not match the installed A source roster')
    for row in baseline['source_manifest']:
        check(sha((source / row['path']).read_bytes()) == row['sha256'], 'A source hash mismatch ' + row['path'])
    frozen_patch = output / 'SOURCE.patch'
    frozen_patch.write_bytes(patch.read_bytes())
    # The archive is independent of the working tree's destination and index.
    patch_command = ['git', '-c', 'core.autocrlf=false', 'apply']
    subprocess.run([*patch_command, '--check', str(frozen_patch)], cwd=source, check=True)
    subprocess.run([*patch_command, str(frozen_patch)], cwd=source, check=True)
    changed = [row['path'] for row in baseline['source_manifest']
               if sha((source / row['path']).read_bytes()) != row['sha256']]
    check(changed and all(name.startswith('human_eye_plugin/') for name in changed), 'invalid candidate scope')
    check(manifest_paths(source) == [row['path'] for row in baseline['source_manifest']],
          'candidate unexpectedly changed source roster')
    project = source / 'pyproject.toml'
    spec = project.read_bytes()
    check(spec.count(b'version = "9.7.2"') == 1, 'version pin mismatch')
    version = '9.7.2+m4.assembly.evidence.first.1.' + label
    project.write_bytes(spec.replace(b'version = "9.7.2"', f'version = "{version}"'.encode()))
    wheel_dir = output / 'wheel'
    install = output / 'product'
    wheel_dir.mkdir()
    pip = [sys.executable, '-I', '-B', '-m', 'pip', '--isolated', '--disable-pip-version-check']
    with (output / 'BUILD.log').open('wb') as log:
        subprocess.run([*pip, 'wheel', '--no-index', '--no-deps', '--no-build-isolation',
                        '--wheel-dir', str(wheel_dir), str(source)], cwd=output, stdout=log,
                       stderr=subprocess.STDOUT, check=True)
        wheel, = wheel_dir.glob('*.whl')
        subprocess.run([*pip, 'install', '--no-index', '--no-deps', '--no-compile', '--target', str(install),
                        str(wheel)], cwd=output, stdout=log, stderr=subprocess.STDOUT, check=True)
    identity = runtime_identity(install, dependency_root)
    check(identity['source_kind'] == 'installed_distribution' and identity['distribution_version'] == version,
          'candidate distribution identity mismatch')
    manifest = identity.pop('source_files')
    check([entry['path'] for entry in manifest] == manifest_paths(install, package_only=True),
          'candidate installed source roster mismatch')
    with zipfile.ZipFile(wheel) as bundle:
        for entry in manifest:
            path = entry['path']
            raw = (source / path).read_bytes()
            check(raw == bundle.read(path) == (install / path).read_bytes() and sha(raw) == entry['sha256'],
                  'source, wheel, install mismatch ' + path)
    binding = {**identity, 'source_manifest': manifest, 'install_root': str(install),
               'dependency_root': str(dependency_root), 'preparation_git': BASELINE,
               'patch_sha256': sha(frozen_patch.read_bytes()), 'wheel_sha256': sha(wheel.read_bytes()),
               'changed_runtime_paths': changed, 'preparation_ns': time.perf_counter_ns() - started}
    dumped(output / 'BINDING.json', binding)
    print(label, binding['source_sha256'], str(output / 'BINDING.json'))


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('label', choices=['first', 'optimized'])
    cli.add_argument('output', type=Path)
    cli.add_argument('patch', type=Path)
    args = cli.parse_args()
    prepare(args.label, args.output.resolve(), args.patch.resolve(strict=True))
