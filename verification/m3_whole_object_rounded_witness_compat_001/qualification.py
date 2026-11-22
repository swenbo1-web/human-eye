"""Freeze, build and seal the closed-solid point publication correction."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
from subprocess import check_output, run
import sys
import time
import tomllib
from zipfile import ZIP_DEFLATED, ZipFile

NS = Path(__file__).resolve().parent
V = NS.parent
ROOT = Path('D:/he_m3_whole_object_rounded_witness_compat_001')
OLD = V / 'm3_whole_object_witness_triangle_001/install/PRODUCT_RUN_BINDING.json'
PRIOR = V / 'm3_whole_object_rounded_witness_001'
PARENT_BINDING = PRIOR / 'install/PRODUCT_RUN_BINDING.json'
PLAN_GIT = '07c7122227d85518ed80d348f148cd8f27e91884'
PLAN = 'docs/M3_WHOLE_OBJECT_ROUNDED_WITNESS_COMPAT_001_PLAN.md'
A0 = '5c77f71a04e580e1e1810d4d72ff6a955cb27a0c'
A1 = 'ae14344ea3aa654c710f2329bd4aa4423f7af9c4'
B = 'cee6fe78a65c1534361228641743aa83d6d72b61'
DELTA = 'human_eye_plugin/surface_proximity.py'
DATA = ('human_eye_plugin/plugin.json', 'human_eye_plugin/mcp_config.json')
PYTHON = Path('D:/he_anchor_001/venv/Scripts/python.exe')
BUILDER = V / 'build_candidate_release.py'
BLOBS = V / 'm4_cross_scale_local_first_view_001/install/build_install.py'


def git(*args):
    return check_output(['git', '-C', str(V.parent), *args])


def read(path):
    return json.loads(path.read_bytes())


def write(path, data):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        stream.write(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def digest(data):
    return {'bytes': len(data), 'sha256': sha256(data).hexdigest()}


def pin(path):
    path = path.resolve(strict=True)
    return {'path': str(path), **digest(path.read_bytes())}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def freeze(preflight):
    require(not (ROOT / 'candidate_install').exists(), 'candidate build already exists')
    require((NS / 'PLAN.md').read_bytes() == git('show', f'{PLAN_GIT}:{PLAN}'), 'plan changed')
    require(git('rev-list', '--parents', '-n', '1', B).decode().split() == [B, A1]
            and git('diff', '--name-only', A1, B).decode().splitlines() == [DELTA],
            'expected a single direct product change')
    for arm, git_id, failed_subtests in (('A0', A0, 0), ('A1', A1, 5)):
        receipt = read(ROOT / 'regression' / arm / 'RESULT.json')
        require(receipt['preparation_git'] == git_id and receipt['passed_expected_outcome']
                and len(receipt['failing_subtests']) == failed_subtests, f'direct regression admission failed: {arm}')
    require(read(ROOT / 'WITNESS_PREFLIGHT.json')['passed'], 'sealed witness preflight failed')
    shadow = read(ROOT / 'relations/SHADOW.json')
    require(shadow['passed'] and not shadow['candidate_scored']
            and shadow['observations_passed'] == 40 and shadow['shadow_malformed_body_count'] == 16
            and shadow['shadow_malformed_fact_count'] == 20, 'published relation repro failed')
    dependencies = [Path(__file__), NS / 'PLAN.md', OLD, PARENT_BINDING, BUILDER, BLOBS,
                    PRIOR / 'FROZEN.json', PRIOR / 'RAW_INDEX.json', PRIOR / 'ORIGINAL_RUNTIME.zip',
                    V / 'test_concave_geometry.py', V / 'test_task_complete_001.py',
                    *preflight]
    for folder in ('regression', 'relations', 'witness'):
        scripts = [p for p in (NS / folder).rglob('*') if p.suffix in ('.py', '.md', '.json')]
        require(any(p.suffix == '.py' for p in scripts), f'qualification missing: {folder}')
        dependencies.extend(scripts)
    for folder in ('harness', 'checks'):
        dependencies.extend((PRIOR / folder).glob('*.py'))
    for entry in read(PRIOR / 'FROZEN.json')['source_inputs']:
        retained = Path(entry['path'])
        require(pin(retained) == entry, f'prior frozen source changed: {retained}')
        dependencies.append(retained)
    for binding_path, expected in ((OLD, A0), (PARENT_BINDING, A1)):
        bound = read(binding_path)
        require(bound['preparation_git'] == expected and len(bound['source_manifest']) == 143,
                f'expected fixed install: {expected}')
        wheel = Path(bound['wheel_path'])
        require(pin(wheel)['sha256'] == bound['wheel_sha256'], f'wheel changed: {expected}')
        dependencies.append(wheel)
        for row in bound['source_manifest']:
            installed = Path(bound['install_root']) / row['path']
            require(pin(installed)['sha256'] == row['sha256'], f'installed module changed: {installed}')
            dependencies.append(installed)
    paths = sorted({p.resolve(strict=True) for p in dependencies})
    write(NS / 'FROZEN.json', {
        'plan_git': PLAN_GIT, 'baseline_git': A0, 'regressed_git': A1, 'candidate_git': B,
        'changed_runtime_source': DELTA, 'preflight': [pin(p) for p in preflight],
        'source_inputs': [pin(p) for p in paths],
        'expected_point_m': [1.0, 0.4375, 0.25], 'expected_triangle_indices': [6, 4],
        'expected_positive_fact_combinations': 4,
        'expected_pairs': {'all': 210, 'strict': 202, 'exact': 8},
        'builds_and_installs_max_each': 1, 'new_Blender_models_rasters_each': 0,
    })
    print(pin(NS / 'FROZEN.json'))


def verify_frozen():
    info = read(NS / 'FROZEN.json')
    require(info['candidate_git'] == B and all(pin(Path(row['path'])) == row for row in info['source_inputs']),
            'frozen candidate or input changed')


def build():
    require(sys.flags.isolated and sys.dont_write_bytecode and Path(sys.executable).resolve() == PYTHON.resolve(),
            'use the pinned installer interpreter')
    verify_frozen()
    started = time.perf_counter_ns()
    parent = read(PARENT_BINDING)
    names = [row['path'] for row in parent['source_manifest']]
    files = [*names, *DATA, 'pyproject.toml']
    blobs = run_path(str(BLOBS))['git_blobs']
    previous, candidate = blobs(A1, files), blobs(B, files)
    require([name for name in files if previous[name] != candidate[name]] == [DELTA],
            'candidate package diff exceeded scope')
    helper = run_path(str(BUILDER))
    for path, revision in ((OLD, A0), (PARENT_BINDING, A1)):
        binding = read(path)
        source = blobs(revision, [*names, *DATA])
        wheel = Path(binding['wheel_path'])
        helper['verify_wheel'](wheel.read_bytes())
        with ZipFile(wheel) as package:
            require(all(source[name] == package.read(name) == (Path(binding['install_root']) / name).read_bytes()
                        for name in [*names, *DATA]), f'Git/wheel/install mismatch: {revision}')
    target = ROOT / 'candidate_install'
    target.mkdir(parents=True, exist_ok=False)
    staging = target / 'git_source'
    for name, raw in candidate.items():
        path = staging / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    manifest = [{'path': name, 'sha256': digest(candidate[name])['sha256']} for name in names]
    version = '9.7.2+m3.whole.object.rounded.witness.compat.001'
    project = tomllib.loads(candidate['pyproject.toml'].decode())['project']
    wheel_name, raw = helper['wheel_bytes'](staging, manifest, project, version)
    wheel = target / wheel_name
    wheel.write_bytes(raw)
    checked = helper['verify_wheel'](raw)
    installed = target / 'product'
    command = [str(PYTHON), '-IB', '-m', 'pip', '--isolated', '--disable-pip-version-check',
               'install', '--no-index', '--no-deps', '--no-compile', '--target', str(installed), str(wheel)]
    result = run(command, capture_output=True, timeout=90)
    (target / 'PIP_STDOUT.bin').write_bytes(result.stdout)
    (target / 'PIP_STDERR.bin').write_bytes(result.stderr)
    result.check_returncode()
    with ZipFile(wheel) as package:
        require(all(package.read(name) == (installed / name).read_bytes()
                    for name in package.namelist() if not name.endswith('/RECORD')), 'installed content mismatch')
    require(sorted(path.relative_to(installed).as_posix() for path in installed.rglob('*.py')) == names,
            'installed runtime source set changed')
    identity = {key: parent[key] for key in ('base_version', 'implementation_revision')}
    canonical = json.dumps({**identity, 'files': manifest}, sort_keys=True, separators=(',', ':')).encode()
    source_hash = digest(canonical)['sha256']
    binding = {
        **identity, 'build_id': 'sha256:' + source_hash, 'source_sha256': source_hash, 'source_manifest': manifest,
        'distribution_version': version, 'install_root': str(installed), 'dependency_root': parent['dependency_root'],
        'preparation_git': B, 'protocol_version': parent['protocol_version'], 'wheel_path': str(wheel),
        'wheel_sha256': digest(raw)['sha256'], 'historical_preparation_git': A1,
        'historical_source_sha256': parent['source_sha256'], 'changed_product_sources': [DELTA],
        'unchanged_product_sources': 142,
    }
    write(NS / 'install/PRODUCT_RUN_BINDING.json', binding)
    write(NS / 'install/BUILD_INSTALL.json', {
        'passed': True, 'binding': binding, 'old_install_sources_verified_each': len(names), 'wheel_RECORD': checked,
        'wheel': pin(wheel), 'installed_files': [pin(p) for p in sorted(installed.rglob('*')) if p.is_file()],
        'command': command, 'actual_candidate_wheels': 1, 'actual_candidate_installs': 1,
        'elapsed_ns': time.perf_counter_ns() - started,
    })
    print(json.dumps({k: binding[k] for k in ('preparation_git', 'source_sha256', 'wheel_sha256', 'install_root')}))


def archive():
    verify_frozen()
    check = run_path(str(V / 'perf050_dense_micro_surface_holdout_recovery_001/archive_evidence.py'))['check_named_bytes']
    binding = read(NS / 'install/PRODUCT_RUN_BINDING.json')
    build_root = ROOT / 'candidate_install'
    build_members = {Path(binding['wheel_path']), build_root / 'PIP_STDOUT.bin', build_root / 'PIP_STDERR.bin'}
    files = sorted(p for p in ROOT.rglob('*')
                   if p.is_file() and (build_root not in p.parents or p in build_members))
    index = {}
    path = NS / 'ORIGINAL_RUNTIME.zip'
    with ZipFile(path, 'x', compression=ZIP_DEFLATED, compresslevel=6) as bundle:
        for source in files:
            name = source.relative_to(ROOT).as_posix()
            data = source.read_bytes()
            check(name, data)
            bundle.writestr(name, data)
            index[name] = digest(data)
    with ZipFile(path) as bundle:
        require(len(bundle.namelist()) == len(index) and set(bundle.namelist()) == index.keys()
                and all(digest(bundle.read(name)) == row for name, row in index.items()), 'archived bytes changed')
    write(NS / 'RAW_INDEX.json', {
        'freeze_sha256': pin(NS / 'FROZEN.json')['sha256'],
        'archive': {'name': path.name, **digest(path.read_bytes())},
        'member_count': len(index), 'members': index,
    })
    print(f'{len(index)} members, {path.stat().st_size} bytes, {pin(path)["sha256"]}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('freeze', 'build', 'archive'))
    parser.add_argument('--preflight', type=Path, nargs='+')
    arguments = parser.parse_args()
    if arguments.action == 'freeze':
        require(arguments.preflight, 'record the shadow reproductions before building')
        freeze(arguments.preflight)
    elif arguments.action == 'build':
        build()
    else:
        archive()
