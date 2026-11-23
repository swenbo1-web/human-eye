"""Build and verify the single isolated selective-transport wheel from the fixed Git blobs."""

import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys
import time
import tomllib
import zipfile


HERE = Path(__file__).resolve().parent
V = HERE.parent
OLD = run_path(str(V/'m2_source_region_shared_normalization_live_001/experiment.py'))
read, write, pin, require, git = (OLD[k] for k in ('read', 'write', 'pin', 'require', 'git'))
ROOT = Path('D:/he_m2_source_region_cold_selective_transport_001')
PYTHON_SHA = '50f885251e42eb8cd1fbf5d4fbcc01efdbe8b9f4d4379e16664d4d0f3d4a9869'
BASE = 'e800667077a6c390dbc1f49aa46ba9a01b153de5'
CANDIDATE = 'a383f953c28413ccdc010869d9a7b35257416632'
BASE_BINDING = V/'m1_source_region_image_evidence_001/install/PRODUCT_RUN_BINDING.json'
BUILDER = V/'build_candidate_release.py'
BLOBS = V/'m4_cross_scale_local_first_view_001/install/build_install.py'
CHANGES = ('human_eye_plugin/blender_host.py', 'human_eye_plugin/blender_mcp_host.py',
           'human_eye_plugin/live_service.py', 'human_eye_plugin/source_region.py')
DATA = ('human_eye_plugin/plugin.json', 'human_eye_plugin/mcp_config.json')
VERSION = '9.7.2+m2.source.region.cold.selective.transport.001'


def build():
    require(sys.flags.isolated and sys.dont_write_bytecode and pin(sys.executable)['sha256'] == PYTHON_SHA,
            'fixed_isolated_interpreter_required')
    start = time.perf_counter_ns()
    require(git('rev-parse', CANDIDATE + '^').decode().strip() == BASE and
            git('diff', '--name-only', BASE, CANDIDATE).decode().splitlines() == list(CHANGES),
            'only_the_four_selective_transport_source_changes_are_admitted')
    base = read(BASE_BINDING)
    require(base['preparation_git'] == BASE and len(base['source_manifest']) == 143,
            'baseline_install_not_the_fixed_product')
    names = [item['path'] for item in base['source_manifest']]
    files = [*names, *DATA, 'pyproject.toml']
    blobs = run_path(str(BLOBS))['git_blobs']
    before, after = blobs(BASE, files), blobs(CANDIDATE, files)
    require(tuple(name for name in files if before[name] != after[name]) == CHANGES,
            'binary_scope_changed')
    tools = run_path(str(BUILDER))
    digest = tools['digest']
    old_wheel = Path(base['wheel_path'])
    require(pin(old_wheel)['sha256'] == base['wheel_sha256'], 'baseline_wheel_sha')
    tools['verify_wheel'](old_wheel.read_bytes())
    with zipfile.ZipFile(old_wheel) as archive:
        require(all(archive.read(name) == before[name] == (Path(base['install_root'])/name).read_bytes()
                    for name in [*names, *DATA]), 'base_Git_wheel_runtime_identity_mismatch')

    root = ROOT/'candidate_install'
    root.mkdir(parents=True, exist_ok=False)
    staging = root/'git_source'
    for name, raw in after.items():
        target = staging/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    manifest = [{'path': name, 'sha256': digest(after[name])} for name in names]
    name, raw = tools['wheel_bytes'](staging, manifest, tomllib.loads(after['pyproject.toml'].decode())['project'], VERSION)
    wheel = root/name
    wheel.write_bytes(raw)
    verified = tools['verify_wheel'](raw)
    installed = root/'product'
    command = [sys.executable, '-IB', '-m', 'pip', '--isolated', '--disable-pip-version-check', 'install', '--no-index',
               '--no-deps', '--no-compile', '--target', str(installed), str(wheel)]
    result = subprocess.run(command, capture_output=True, timeout=90)
    (root/'PIP_STDOUT.bin').write_bytes(result.stdout)
    (root/'PIP_STDERR.bin').write_bytes(result.stderr)
    result.check_returncode()
    with zipfile.ZipFile(wheel) as pack:
        require(sorted(name for name in pack.namelist() if name.endswith('.py')) == names and
                all(pack.read(name) == (installed/name).read_bytes() for name in pack.namelist()
                    if not name.endswith('/RECORD')), 'candidate_installed_file_bytes_mismatch')
    require(sorted(path.relative_to(installed).as_posix() for path in installed.rglob('*.py')) == names,
            'unexpected_candidate_runtime_file_set')
    identity = {k: base[k] for k in ('base_version', 'implementation_revision')}
    source_hash = digest(json.dumps({**identity, 'files': manifest}, sort_keys=True, separators=(',', ':')).encode())
    binding = {**identity, 'build_id': 'sha256:' + source_hash, 'source_sha256': source_hash,
               'source_manifest': manifest, 'distribution_version': VERSION, 'install_root': str(installed),
               'dependency_root': base['dependency_root'], 'preparation_git': CANDIDATE,
               'protocol_version': base['protocol_version'], 'wheel_path': str(wheel), 'wheel_sha256': digest(raw),
               'historical_preparation_git': BASE, 'historical_source_sha256': base['source_sha256'],
               'changed_product_sources': list(CHANGES), 'unchanged_product_sources': 143-len(CHANGES)}
    write(HERE/'install/PRODUCT_RUN_BINDING.json', binding)
    write(HERE/'install/BUILD_INSTALL.json', {'passed': True, 'binding': binding, 'wheel': pin(wheel),
          'verified_wheel_RECORD': verified, 'command': command, 'actual_candidate_wheels': 1,
          'actual_candidate_installs': 1, 'elapsed_ns': time.perf_counter_ns()-start})
    print({key: binding[key] for key in ('preparation_git', 'source_sha256', 'wheel_sha256')}, flush=True)


if __name__ == '__main__':
    build()
