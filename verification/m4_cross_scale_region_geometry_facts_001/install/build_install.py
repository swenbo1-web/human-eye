"""Build the one isolated geometry candidate from the historical wheel and Git patch."""

import argparse
import base64
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import zipfile


HERE = Path(__file__).resolve().parent
V = HERE.parents[1]
ROOT = V.parent
EXTERNAL = Path('D:/he_m4_cross_scale_region_geometry_facts_001/install')
PYTHON = Path('D:/he_anchor_001/venv/Scripts/python.exe')
OLD_BINDING = V / 'm4_live_assembly_relation_task_001/PRODUCT_RUN_BINDING.json'
OLD_WHEEL = (V / 'm1_source_region_facts_first_001/build_B'
             / 'human_eye_spatial_plugin-9.7.2+m1.source.region.facts.first.001.b-py3-none-any.whl')
OLD_TOOLS = Path('D:/he_m4_cross_scale_brief_entry_001/slots/P1/INSTALLED_TOOLS.json')
WHEEL_HELPER = V / 'build_candidate_release.py'
BOOTSTRAP = V / 'm4_live_source_region_task_003/harness/reused/verified_bootstrap.py'
BASELINE = '108c01fea0f188d587a14c690a4e6f5fd69a0c7b'
OLD_PREPARATION = '08a5f3b29283270c97b6d9d6e217bbee6ca7bfc1'
OLD_BINDING_SHA = 'eb0ecece262ce0fbbe2b01f041b9e6eab77f0c4810030094c2f590850f51b2e0'
OLD_SOURCE_SHA = '0d75c8f7f3522c4c7f2a5807f51f86fc4f2bec49efa9a215bf090775787ab91b'
SOURCE = 'human_eye_plugin/live_spatial_mcp.py'
VERSION = '9.7.2+m4.cross.scale.region.geometry.facts.001'
PUBLIC_TOOL = 'human_eye_scene_observe'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def file_pin(path):
    raw = path.read_bytes()
    return {'path': str(path.resolve()), 'bytes': len(raw), 'sha256': digest(raw)}


def read(path):
    return json.loads(path.read_bytes())


def save(path, value):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, allow_nan=False, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')


def write(path, raw):
    with path.open('xb') as stream:
        stream.write(raw)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(*arguments, cwd=ROOT, input=None):
    return subprocess.check_output(
        ['git', '-c', 'core.autocrlf=false', '-c', 'core.eol=lf', *arguments], cwd=cwd, input=input)


def old_source(archive, binding):
    manifest = binding['source_manifest']
    paths = [row['path'] for row in manifest]
    if (len(paths) != 143 or paths != sorted(set(paths))
            or [name for name in sorted(archive.namelist()) if name.endswith('.py')] != paths):
        raise ValueError('the original wheel must contain exactly the registered 143 sources')
    src_root = Path(binding['install_root']).resolve()
    for row in manifest:
        relative = row['path']
        raw = archive.read(relative)
        if digest(raw) != row['sha256'] or (src_root / relative).read_bytes() != raw:
            raise ValueError('original installed wheel source diverges/' + relative)
    recorded = next(name for name in archive.namelist() if name.endswith('/runtime_sources.json'))
    if json.loads(archive.read(recorded)) != manifest:
        raise ValueError('original wheel runtime manifest differs from the retained installation')
    return manifest


def transplant(candidate, stage, original):
    if git('merge-base', '--is-ancestor', BASELINE, candidate):
        raise ValueError('unexpected candidate ancestry output')
    git_source = git('show', f'{candidate}:{SOURCE}')
    if git_source != (ROOT / SOURCE).read_bytes():
        raise ValueError('the candidate geometry source has uncommitted changes')
    if git('diff', '--name-only', BASELINE, candidate, '--', 'human_eye_plugin', 'human_eye_module1_operators',
           ':(glob)*.py', 'pyproject.toml').decode().splitlines() != [SOURCE]:
        raise ValueError('only the region brief projection product module may change')
    patch = git('diff', '--no-ext-diff', '--binary', BASELINE, candidate, '--', SOURCE)
    if not patch or git('show', f'{OLD_PREPARATION}:{SOURCE}') != original:
        raise ValueError('a nonempty feature patch and exact historical source are required')
    path = stage / SOURCE
    path.parent.mkdir(parents=True)
    write(path, original)
    git('apply', '--check', '--whitespace=nowarn', cwd=stage, input=patch)
    git('apply', '--whitespace=nowarn', cwd=stage, input=patch)
    translated = path.read_bytes()
    git('apply', '--reverse', '--whitespace=nowarn', cwd=stage, input=patch)
    if translated == original or path.read_bytes() != original:
        raise ValueError('the translated source must reverse exactly to the historical bytes')
    accepted = stage / 'candidate' / SOURCE
    accepted.parent.mkdir(parents=True)
    write(accepted, translated)
    write(HERE / 'SOURCE_PATCH.diff', patch)
    return accepted, digest(git_source)


def wheel_members(archive, previous_version, manifest, candidate_source):
    members = {}
    for name in archive.namelist():
        if name.endswith('/RECORD'):
            continue
        raw = candidate_source if name == SOURCE else archive.read(name)
        if name.endswith('/METADATA'):
            old = ('\nVersion: ' + previous_version + '\n').encode()
            if raw.count(old) != 1:
                raise ValueError('the historical wheel metadata version must identify one entry')
            raw = raw.replace(old, ('\nVersion: ' + VERSION + '\n').encode())
        elif name.endswith('/runtime_sources.json'):
            raw = (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode()
        members[name.replace(previous_version, VERSION)] = raw
    record = 'human_eye_spatial_plugin-' + VERSION + '.dist-info/RECORD'
    buffer = io.StringIO(newline='')
    writer = csv.writer(buffer, lineterminator='\n')
    for name, raw in sorted(members.items()):
        checksum = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b'=').decode()
        writer.writerow([name, 'sha256=' + checksum, len(raw)])
    writer.writerow([record, '', ''])
    return dict(sorted({**members, record: buffer.getvalue().encode()}.items()))


def inspect(binding_path):
    binding = read(binding_path)
    sys.path.insert(0, binding['dependency_root'])
    guard = load('_candidate_install_bootstrap', BOOTSTRAP).bootstrap(binding)
    from human_eye_plugin import live_spatial_mcp
    from human_eye_plugin.runtime_identity import check_source_drift, runtime_identity

    identity = runtime_identity()
    identity_fields = ('base_version', 'build_id', 'distribution_version',
                       'implementation_revision', 'protocol_version', 'source_sha256')
    module_path = Path(live_spatial_mcp.__file__).resolve()
    if (identity['source_kind'] != 'installed_distribution'
            or any(binding[key] != identity[key] for key in identity_fields)
            or identity['source_files'] != binding['source_manifest']
            or module_path != (Path(binding['install_root']) / SOURCE).resolve()
            or not check_source_drift()['compatible']):
        raise ValueError('actual imported wheel identity does not match the candidate binding')
    server = live_spatial_mcp.LiveSpatialMCPServer(object(), default_session_id='offline-schema')
    request = {'jsonrpc': '2.0', 'method': 'tools/list', 'id': 'schema'}
    tools = server.handle_jsonrpc_message(request)['result']['tools']
    if tools != read(OLD_TOOLS):
        raise ValueError('the installed public tool directory differs from the historical arm')
    public = next(tool for tool in tools if tool['name'] == PUBLIC_TOOL)
    guard.verify_loaded()
    print(json.dumps({'identity': identity, 'tools': tools, 'public': public, 'module': file_pin(module_path)}))


def build(candidate):
    started = time.perf_counter_ns()
    require_python()
    if not re.fullmatch('[0-9a-f]{40}', candidate):
        raise ValueError('one exact candidate commit is required')
    prior_preflight = EXTERNAL / 'transplant_crlf_preflight'
    previous = [prior_preflight] if prior_preflight.is_dir() else []
    if ((EXTERNAL.exists() and sorted(EXTERNAL.iterdir()) != previous) or any((HERE / name).exists() for name in (
            'PRODUCT_RUN_BINDING.json', 'BUILD_INSTALL.json', 'SOURCE_PATCH.diff', 'TOOLS_SCHEMA.json',
            'PRODUCT_SCHEMA.json'))):
        raise FileExistsError('the single candidate installation is already initialized')
    binding_raw, wheel_raw = OLD_BINDING.read_bytes(), OLD_WHEEL.read_bytes()
    old = json.loads(binding_raw)
    if (digest(binding_raw) != OLD_BINDING_SHA or old['preparation_git'] != OLD_PREPARATION
            or old['source_sha256'] != OLD_SOURCE_SHA or digest(wheel_raw) != old['wheel_sha256']):
        raise ValueError('historical wheel or binding changed')
    helper = load('_geometry_wheel_helpers', WHEEL_HELPER)
    helper.verify_wheel(wheel_raw)
    EXTERNAL.mkdir(parents=True, exist_ok=bool(previous))
    with zipfile.ZipFile(io.BytesIO(wheel_raw)) as archive:
        old_manifest = old_source(archive, old)
        old_source_bytes = archive.read(SOURCE)
        translated, committed_sha = transplant(candidate, EXTERNAL / 'patch', old_source_bytes)
        new_source = translated.read_bytes()
        manifest = [dict(row, sha256=digest(new_source)) if row['path'] == SOURCE else row
                    for row in old_manifest]
        members = wheel_members(archive, old['distribution_version'], manifest, new_source)
    wheel_raw = helper.archive_bytes(members)
    verification = helper.verify_wheel(wheel_raw)
    changed = [before['path'] for before, after in zip(old_manifest, manifest, strict=True) if before != after]
    if changed != [SOURCE]:
        raise ValueError('exactly the geometry formatter module may differ from the historical installation')
    wheel = EXTERNAL / ('human_eye_spatial_plugin-' + VERSION + '-py3-none-any.whl')
    write(wheel, wheel_raw)
    target = EXTERNAL / 'product'
    command = [str(PYTHON), '-I', '-B', '-m', 'pip', '--isolated', '--disable-pip-version-check', 'install',
               '--no-index', '--no-deps', '--no-compile', '--target', str(target), str(wheel)]
    installed = subprocess.run(command, capture_output=True, timeout=90)
    write(EXTERNAL / 'PIP_STDOUT.bin', installed.stdout)
    write(EXTERNAL / 'PIP_STDERR.bin', installed.stderr)
    installed.check_returncode()
    record_paths = [row['path'] for row in manifest]
    if sorted(path.relative_to(target).as_posix() for path in target.rglob('*.py')) != record_paths:
        raise ValueError('installed Python file set differs from recorded wheel sources')
    installed_pins = []
    for row in manifest:
        pin = file_pin(target / row['path'])
        if pin['sha256'] != row['sha256']:
            raise ValueError('installed source hash mismatch/' + row['path'])
        installed_pins.append(pin)
    for name in ('human_eye_plugin/plugin.json', 'human_eye_plugin/mcp_config.json'):
        if (target / name).read_bytes() != members[name]:
            raise ValueError('installed package data changed/' + name)
        installed_pins.append(file_pin(target / name))
    for path in sorted(next(target.glob('*.dist-info')).iterdir()):
        if path.is_file():
            installed_pins.append(file_pin(path))
    identity = {key: old[key] for key in ('base_version', 'implementation_revision')}
    signed = {**identity, 'files': manifest}
    source_sha = digest(json.dumps(signed, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode())
    binding = {**identity, 'build_id': 'sha256:' + source_sha, 'source_sha256': source_sha,
               'source_manifest': manifest, 'distribution_version': VERSION,
               'install_root': str(target.resolve()), 'dependency_root': old['dependency_root'],
               'preparation_git': candidate, 'protocol_version': old['protocol_version'],
               'wheel_path': str(wheel.resolve()), 'wheel_sha256': digest(wheel_raw),
               'historical_preparation_git': OLD_PREPARATION, 'historical_source_sha256': OLD_SOURCE_SHA,
               'product_patch_baseline_git': BASELINE, 'product_patch_sha256': file_pin(HERE / 'SOURCE_PATCH.diff')['sha256'],
               'product_patch_committed_source_sha256': committed_sha,
               'changed_product_sources': changed, 'unchanged_product_sources': len(manifest) - len(changed)}
    draft = EXTERNAL / 'INSTALL_DRAFT.json'
    save(draft, binding)
    probe_command = [str(PYTHON), '-I', '-B', str(Path(__file__).resolve()), '--inspect', str(draft)]
    probe = subprocess.run(probe_command, capture_output=True, timeout=60)
    write(EXTERNAL / 'PROBE_STDOUT.bin', probe.stdout)
    write(EXTERNAL / 'PROBE_STDERR.bin', probe.stderr)
    probe.check_returncode()
    actual = json.loads(probe.stdout)
    tools_path, schema_path = HERE / 'TOOLS_SCHEMA.json', HERE / 'PRODUCT_SCHEMA.json'
    save(tools_path, actual['tools'])
    save(schema_path, actual['public'])
    dependencies = [file_pin(path) for path in (
        Path(__file__).resolve(), OLD_BINDING, OLD_WHEEL, OLD_TOOLS, WHEEL_HELPER, BOOTSTRAP,
        PYTHON, HERE / 'SOURCE_PATCH.diff', translated, wheel, tools_path, schema_path)]
    initial_preflight = None
    if previous:
        old_stage = prior_preflight / SOURCE
        if (old_stage.read_bytes().replace(b'\r\n', b'\n') != old_source_bytes
                or old_stage.read_bytes() == old_source_bytes):
            raise ValueError('retained preflight must be the exact CRLF rendering of the old source')
        initial_preflight = {'reason': 'ambient_git_ignored_LF_preservation_before_wheel_creation',
                             'same_normalized_old_bytes': True, 'retained_stage': file_pin(old_stage),
                             'wheel_builds': 0, 'installations': 0}
    receipt = {'passed': True, 'started_ns': started, 'completed_ns': time.perf_counter_ns(),
               'binding': binding, 'actual_loaded_module': actual['module'],
               'wheel_RECORD_verified': verification['all_hashes_verified'], 'wheel_members': verification['files'],
               'wheel': file_pin(wheel), 'install_command': command, 'offline_probe_command': probe_command,
               'installed_files': installed_pins, 'execution_and_input_pins': dependencies,
               'tool_schema_matches_historical_actual_directory': True, 'actual_tool_count': len(actual['tools']),
               'actual_installed_subprocesses': 1, 'new_qualification_Blender': 0, 'models': 0, 'asset_builds': 0,
               'initial_transplant_preflight': initial_preflight}
    save(HERE / 'BUILD_INSTALL.json', receipt)
    save(HERE / 'PRODUCT_RUN_BINDING.json', binding)
    print(json.dumps({'prepared': candidate, 'source_sha256': source_sha, 'wheel_sha256': binding['wheel_sha256'],
                      'install_root': binding['install_root'], 'bindings': str(HERE / 'PRODUCT_RUN_BINDING.json')}))


def require_python():
    if not sys.flags.isolated or not sys.dont_write_bytecode or Path(sys.executable).resolve() != PYTHON.resolve():
        raise ValueError('use the fixed local build interpreter with -I -B')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--candidate')
    mode.add_argument('--inspect', type=Path)
    request = parser.parse_args()
    if request.candidate:
        build(request.candidate)
    else:
        require_python()
        inspect(request.inspect)
