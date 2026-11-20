"""Build the isolated local-view candidate directly from committed Git blobs."""

import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import tomllib
import zipfile


HERE = Path(__file__).resolve().parent
VERIFICATION = HERE.parents[1]
ROOT = VERIFICATION.parent
EXTERNAL = Path('D:/he_m4_cross_scale_local_first_view_001/install')
PYTHON = Path('D:/he_anchor_001/venv/Scripts/python.exe')
BASE = '08a5f3b29283270c97b6d9d6e217bbee6ca7bfc1'
BASE_SOURCE = '0d75c8f7f3522c4c7f2a5807f51f86fc4f2bec49efa9a215bf090775787ab91b'
BASE_BINDING = VERIFICATION / 'm4_live_assembly_relation_task_001/PRODUCT_RUN_BINDING.json'
BASE_BINDING_SHA = 'eb0ecece262ce0fbbe2b01f041b9e6eab77f0c4810030094c2f590850f51b2e0'
BASE_WHEEL = (VERIFICATION / 'm1_source_region_facts_first_001/build_B'
              / 'human_eye_spatial_plugin-9.7.2+m1.source.region.facts.first.001.b-py3-none-any.whl')
BASE_TOOLS = Path('D:/he_m4_cross_scale_brief_entry_001/slots/P1/INSTALLED_TOOLS.json')
BOOTSTRAP = VERIFICATION / 'm4_live_source_region_task_003/harness/reused/verified_bootstrap.py'
WHEEL_BUILDER = 'verification/build_candidate_release.py'
VERSION = '9.7.2+m4.cross.scale.local.first.view.001'
PACKAGES = ('human_eye_plugin', 'human_eye_module1_operators')
PACKAGE_DATA = ('human_eye_plugin/plugin.json', 'human_eye_plugin/mcp_config.json')
CHANGED = ('human_eye_plugin/active_observation.py', 'human_eye_plugin/active_observation_region_task.py')
PUBLIC_TOOL = 'human_eye_scene_observe'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def file_pin(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': digest(raw)}


def read(path):
    return path.read_bytes()


def write(path, raw):
    with path.open('xb') as stream:
        stream.write(raw)


def save(path, value):
    write(path, (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + '\n').encode())


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(*arguments, input=None):
    return subprocess.check_output(['git', *arguments], input=input, cwd=ROOT)


def git_blobs(commit, paths):
    names = tuple(paths)
    queries = ''.join(f'{commit}:{path}\n' for path in names).encode()
    source = io.BytesIO(git('cat-file', '--batch', input=queries))
    blobs = {}
    for name in names:
        header = source.readline().split()
        if (len(header) != 3 or header[1] != b'blob'
                or not header[2].isdigit() or name in blobs):
            raise ValueError('missing or repeated tracked blob/' + name)
        length = int(header[2])
        raw = source.read(length)
        if len(raw) != length or source.read(1) != b'\n':
            raise ValueError('incomplete tracked blob/' + name)
        blobs[name] = raw
    if source.read(1):
        raise ValueError('unexpected bytes after tracked blobs')
    return blobs


def python_paths(commit, project):
    packages = tuple(project['tool']['setuptools']['packages'])
    if packages != PACKAGES:
        raise ValueError('runtime package domain changed')
    packaged = [module + '.py' for module in project['tool']['setuptools']['py-modules']]
    for name in git('ls-tree', '-r', '-z', '--name-only', commit, '--', *packages).decode().split('\0'):
        if name.endswith('.py') and name.count('/') == 1:
            packaged.append(name)
    return sorted(packaged)


def verify_baseline(helper):
    old = json.loads(read(BASE_BINDING))
    wheel = read(BASE_WHEEL)
    if (digest(read(BASE_BINDING)) != BASE_BINDING_SHA or old['preparation_git'] != BASE
            or old['source_sha256'] != BASE_SOURCE or digest(wheel) != old['wheel_sha256']):
        raise ValueError('historical binding or wheel changed')
    proof = helper.verify_wheel(wheel)
    manifest = old['source_manifest']
    paths = [row['path'] for row in manifest]
    blobs = git_blobs(BASE, (*paths, *PACKAGE_DATA, 'pyproject.toml', WHEEL_BUILDER))
    project = tomllib.loads(blobs['pyproject.toml'].decode())
    if len(paths) != 143 or paths != python_paths(BASE, project) or len(set(paths)) != len(paths):
        raise ValueError('original manifest is not the 143 runtime sources of the Git baseline')
    installed = Path(old['install_root'])
    if sorted(path.relative_to(installed).as_posix() for path in installed.rglob('*.py')) != paths:
        raise ValueError('historical installed file set changed')
    with zipfile.ZipFile(io.BytesIO(wheel)) as archive:
        archived_sources = sorted(name for name in archive.namelist() if name.endswith('.py'))
        manifest_name = next(name for name in archive.namelist() if name.endswith('/runtime_sources.json'))
        if archived_sources != paths or json.loads(archive.read(manifest_name)) != manifest:
            raise ValueError('historical wheel file set or runtime manifest changed')
        for row in manifest:
            name = row['path']
            if (digest(blobs[name]) != row['sha256'] or archive.read(name) != blobs[name]
                    or read(installed / name) != blobs[name]):
                raise ValueError('historical Git, wheel, installed source mismatch/' + name)
        for name in PACKAGE_DATA:
            if archive.read(name) != blobs[name] or read(installed / name) != blobs[name]:
                raise ValueError('historical package data differs from the Git baseline/' + name)
    runtime_key = {key: old[key] for key in ('base_version', 'implementation_revision')}
    encoded = json.dumps({**runtime_key, 'files': manifest}, sort_keys=True, separators=(',', ':')).encode()
    if digest(encoded) != BASE_SOURCE:
        raise ValueError('independent historical Git source identity mismatch')
    return old, blobs, proof


def inspect(binding_path):
    binding = json.loads(read(binding_path))
    sys.path.insert(0, binding['dependency_root'])
    guard = load('_local_view_installed_bootstrap', BOOTSTRAP).bootstrap(binding)
    from human_eye_plugin import active_observation, active_observation_region_task, live_spatial_mcp
    from human_eye_plugin.runtime_identity import check_source_drift, runtime_identity

    identity = runtime_identity()
    identity_keys = ('base_version', 'build_id', 'distribution_version', 'implementation_revision',
                     'protocol_version', 'source_sha256')
    loaded = (active_observation, active_observation_region_task, live_spatial_mcp)
    files = [file_pin(module.__file__) for module in loaded]
    expected = {row['path']: row['sha256'] for row in binding['source_manifest']}
    runtime_root = Path(binding['install_root']).resolve()
    if (identity['source_kind'] != 'installed_distribution'
            or any(binding[key] != identity[key] for key in identity_keys)
            or identity['source_files'] != binding['source_manifest']
            or any(expected[Path(row['path']).relative_to(runtime_root).as_posix()] != row['sha256']
                   for row in files)
            or not check_source_drift()['compatible']):
        raise ValueError('imported control or candidate identity differs from its binding')
    server = live_spatial_mcp.LiveSpatialMCPServer(object(), default_session_id='offline-schema')
    request = {'jsonrpc': '2.0', 'method': 'tools/list', 'id': 'schema'}
    tools = server.handle_jsonrpc_message(request)['result']['tools']
    if tools != json.loads(read(BASE_TOOLS)):
        raise ValueError('actual installed tools/list differs from the historical arm')
    guard.verify_loaded()
    print(json.dumps({'identity': {key: identity[key] for key in (*identity_keys, 'source_kind')},
                      'tools': tools, 'source_files_executed': files}))


def probe(binding, name):
    command = [str(PYTHON), '-I', '-B', str(Path(__file__).resolve()), '--inspect', str(binding)]
    result = subprocess.run(command, capture_output=True, timeout=60)
    write(EXTERNAL / (name + '_STDOUT.bin'), result.stdout)
    write(EXTERNAL / (name + '_STDERR.bin'), result.stderr)
    result.check_returncode()
    return command, json.loads(result.stdout)


def build(candidate):
    started = time.perf_counter_ns()
    if not re.fullmatch('[0-9a-f]{40}', candidate):
        raise ValueError('one exact candidate commit is required')
    if BASE.encode() not in git('rev-list', '--first-parent', candidate).splitlines():
        raise ValueError('candidate must descend directly along the baseline branch')
    scope = tuple(git('diff', '--name-only', '-z', BASE, candidate).decode().rstrip('\0').split('\0'))
    if scope != CHANGED:
        raise ValueError('candidate commit changed files outside the two registered product sources')
    helper_path = VERIFICATION / 'build_candidate_release.py'
    if read(helper_path) != git_blobs(candidate, (WHEEL_BUILDER,))[WHEEL_BUILDER]:
        raise ValueError('runtime wheel builder must match the exact candidate Git blob')
    helper = load('_local_view_wheel_builder', helper_path)
    historical, baseline_blobs, baseline_proof = verify_baseline(helper)
    candidate_blobs = git_blobs(candidate, baseline_blobs)
    if tuple(name for name in baseline_blobs if baseline_blobs[name] != candidate_blobs[name]) != CHANGED:
        raise ValueError('candidate raw source diff is outside the two registered modules')
    manifest = [dict(path=row['path'], sha256=digest(candidate_blobs[row['path']]))
                for row in historical['source_manifest']]
    project = tomllib.loads(candidate_blobs['pyproject.toml'].decode())
    paths = [row['path'] for row in manifest]
    if paths != python_paths(candidate, project):
        raise ValueError('candidate runtime source domain changed')
    outputs = ('BUILD_INSTALL.json', 'PRODUCT_RUN_BINDING.json', 'TOOLS_SCHEMA.json', 'PRODUCT_SCHEMA.json')
    if any((HERE / name).exists() for name in outputs):
        raise FileExistsError('the single candidate installation already has sealed outputs')
    EXTERNAL.mkdir(parents=True, exist_ok=False)
    stage = EXTERNAL / 'git_source'
    for name, raw in candidate_blobs.items():
        target = stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        write(target, raw)
    wheel_name, raw_wheel = helper.wheel_bytes(stage, manifest, project['project'], VERSION)
    wheel_proof = helper.verify_wheel(raw_wheel)
    wheel = EXTERNAL / wheel_name
    installed = EXTERNAL / 'product'
    write(wheel, raw_wheel)
    command = [str(PYTHON), '-I', '-B', '-m', 'pip', '--isolated', '--disable-pip-version-check', 'install',
               '--no-index', '--no-deps', '--no-compile', '--target', str(installed), str(wheel)]
    pip = subprocess.run(command, capture_output=True, timeout=90)
    write(EXTERNAL / 'PIP_STDOUT.bin', pip.stdout)
    write(EXTERNAL / 'PIP_STDERR.bin', pip.stderr)
    pip.check_returncode()
    with zipfile.ZipFile(io.BytesIO(raw_wheel)) as archive:
        if sorted(name for name in archive.namelist() if name.endswith('.py')) != paths:
            raise ValueError('candidate wheel source set changed')
        for name in archive.namelist():
            # Installation tracks entry points and its own paths in a new RECORD.
            if not name.endswith('/RECORD') and archive.read(name) != read(installed / name):
                raise ValueError('installed bytes differ from the verified wheel/' + name)
        for name in (*paths, *PACKAGE_DATA):
            if archive.read(name) != candidate_blobs[name]:
                raise ValueError('wheel bytes differ from exact candidate Git/' + name)
    if sorted(path.relative_to(installed).as_posix() for path in installed.rglob('*.py')) != paths:
        raise ValueError('candidate installed source set changed')
    pin_paths = [path for path in sorted(installed.rglob('*')) if path.is_file()]
    installed_pins = [file_pin(path) for path in pin_paths]
    # Runtime identity's canonical source digest covers the actual file generation.
    identity = {key: historical[key] for key in ('base_version', 'implementation_revision')}
    signed = json.dumps({**identity, 'files': manifest}, sort_keys=True, separators=(',', ':')).encode()
    source_sha = digest(signed)
    binding = {**identity, 'build_id': 'sha256:' + source_sha, 'source_sha256': source_sha,
               'source_manifest': manifest, 'distribution_version': VERSION,
               'install_root': str(installed.resolve()), 'dependency_root': historical['dependency_root'],
               'preparation_git': candidate, 'protocol_version': historical['protocol_version'],
               'wheel_path': str(wheel.resolve()), 'wheel_sha256': digest(raw_wheel),
               'historical_preparation_git': BASE, 'historical_source_sha256': BASE_SOURCE,
               'changed_product_sources': list(CHANGED), 'unchanged_product_sources': len(manifest) - len(CHANGED)}
    draft = EXTERNAL / 'INSTALL_DRAFT.json'
    save(draft, binding)
    baseline_command, baseline_actual = probe(BASE_BINDING, 'BASELINE_PROBE')
    probe_command, candidate_actual = probe(draft, 'CANDIDATE_PROBE')
    tools_path, schema_path = HERE / 'TOOLS_SCHEMA.json', HERE / 'PRODUCT_SCHEMA.json'
    tools = candidate_actual['tools']
    if baseline_actual['tools'] != tools:
        raise ValueError('candidate and baseline installed tools differ')
    save(tools_path, tools)
    save(schema_path, next(tool for tool in tools if tool['name'] == PUBLIC_TOOL))
    dependencies = [file_pin(path) for path in (
        Path(__file__).resolve(), BASE_BINDING, BASE_WHEEL, BASE_TOOLS, BOOTSTRAP, helper_path, PYTHON,
        wheel, draft, tools_path, schema_path)]
    historical_pins = [file_pin(Path(historical['install_root']) / name) for name in (*paths, *PACKAGE_DATA)]
    staged_pins = [file_pin(stage / name) for name in candidate_blobs]
    receipt = {'passed': True, 'started_ns': started, 'completed_ns': time.perf_counter_ns(),
               'binding': binding, 'direct_git_source': True,
               'historical_git_wheel_install_sources_verified': len(manifest),
               'historical_wheel_record_verified': baseline_proof['all_hashes_verified'],
               'historical_installed_files': historical_pins,
               'staged_candidate_git_files': staged_pins,
               'candidate_runtime_probe': candidate_actual['identity'],
               'baseline_runtime_probe': baseline_actual['identity'],
               'actual_loaded_sources': candidate_actual['source_files_executed'],
               'baseline_loaded_sources': baseline_actual['source_files_executed'],
               'wheel_RECORD_verified': wheel_proof['all_hashes_verified'], 'wheel_members': wheel_proof['files'],
               'wheel': file_pin(wheel), 'install_command': command, 'offline_probe_command': probe_command,
               'baseline_offline_probe_command': baseline_command,
               'installed_files': installed_pins, 'execution_and_input_pins': dependencies,
               'tool_schema_matches_historical_actual_directory': True, 'actual_tool_count': len(tools),
               'actual_candidate_wheels': 1, 'actual_installed_subprocesses': 1,
               'new_qualification_Blender': 0, 'models': 0, 'asset_builds': 0}
    save(HERE / 'BUILD_INSTALL.json', receipt)
    save(HERE / 'PRODUCT_RUN_BINDING.json', binding)
    print(json.dumps({'candidate_commit': candidate, 'source_sha256': source_sha, 'wheel_sha256': binding['wheel_sha256'],
                      'install_root': binding['install_root'], 'baseline_sources_verified': len(manifest)}))


if __name__ == '__main__':
    if not sys.flags.isolated or not sys.dont_write_bytecode or Path(sys.executable).resolve() != PYTHON.resolve():
        raise ValueError('use the fixed local build interpreter with -I -B')
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--candidate')
    action.add_argument('--inspect', type=Path)
    action.add_argument('--verify-baseline', action='store_true')
    args = parser.parse_args()
    if args.candidate:
        build(args.candidate)
    elif args.inspect:
        inspect(args.inspect)
    else:
        helper = load('_local_view_baseline_wheel_helpers', VERIFICATION / 'build_candidate_release.py')
        original, _, _ = verify_baseline(helper)
        print(f"Verified {len(original['source_manifest'])} baseline Git, wheel, installed sources")
