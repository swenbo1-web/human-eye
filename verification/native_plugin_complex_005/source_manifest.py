"""COMPLEX-005: read actual historical/current releases and static catalogues.

Only the controlled entry's identity role and fresh static tools/list imports
execute. No serve/configuration/host/model is started; releases stay read-only.
The historical installation is bound to its recorded deployment, never HEAD.
"""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RELEASES = Path('D:/hefe/.human-eye/releases')
DEPENDENCY_PYTHON = RELEASES/'9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe'
UPGRADE = Path('D:/hefe/verification/fixes/20261110_local_upgrade')
ROOT_MODULES = ('human_eye_hook.py', 'human_eye_foveated_renderer.py', 'native_3d_spatial_scratchpad.py',
    'module_2_low_token_mcp_scene_bridge.py', 'module_3_1_mcp_protocol_ipc_engine.py',
    'module_3_2_vlm_grounding_closed_loop_agent.py', 'module_3_3_closed_loop_control_engine.py')
VERSIONS = {
    'H': {'release': '9.7.2+20261103.scene.trace.r1', 'count': 125,
        'commit': '001743bb4700719bda1448a49fbb4601bbde24b2',
        'canonical': 'a045a800256f4767271308d239c735177f992ce3408d927d42bde5f1d4b60d8f',
        'entry_sha256': 'dcdbb83011bdb80ba75dd2e442ff8e8ca334443424646dc999563b76a11a93ae',
        'binding_sha256': '3f4671ae4cc9c22a3e1d152b44f1ec3647db2ebea0dd5b0bad866cd8a3199d3e',
        'admin_sha256': 'b09c84eff94e389d37869142952de1fd3097a5778ea84d591d695690c8de65e7'},
    'C': {'release': '9.7.2+20261110.scale.opt.r1', 'count': 137,
        'commit': 'df016079b0265ee327f884c90dd4815c392016b6',
        'canonical': '3fc2651e108ad7ac252394871d78e1abaee1200c92a018125984b2fc240193bd',
        'entry_sha256': 'e8f710dd283be03acf01a29f3b811a41ef767fd12b2fb6372fa8b628269617d2',
        'binding_sha256': 'f4edea08d013259fcd07c6606bc1b361dd5082b81528d1028774e9fd486bb676',
        'admin_sha256': 'cdbba842fab87386111daa09af15e97d58b55f6a51c18fa3aeba72d315baf0f1'},
}

SCHEMA_PROBE = r'''
import importlib.util,json,pathlib,sys
forbidden=[]
def audit(event,args):
    if event in ('socket.connect','socket.connect_ex','socket.bind','subprocess.Popen','os.system'):
        forbidden.append(event);raise RuntimeError('source_preflight_forbids_'+event)
sys.addaudithook(audit)
entry=pathlib.Path(sys.argv[1]).resolve()
spec=importlib.util.spec_from_file_location('_complex005_fixed_target',entry)
boot=importlib.util.module_from_spec(spec);sys.modules[spec.name]=boot;spec.loader.exec_module(boot)
proof=boot.validate_binding(expected_python=sys.executable)
sys.path.insert(0,proof['module_root']);identity,origins=boot.verify_imported_runtime(proof)
import numpy,PIL
from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer
server=LiveSpatialMCPServer(object(),default_session_id='complex005-source-only')
response=server.handle_jsonrpc_message({'jsonrpc':'2.0','id':1,'method':'tools/list','params':{}})
identity,origins=boot.verify_imported_runtime(proof)
print(json.dumps({'isolated':bool(sys.flags.isolated),'dont_write_bytecode':sys.dont_write_bytecode,
    'python':sys.executable,'prefix':sys.prefix,'python_version':sys.version,
    'numpy_version':numpy.__version__,'numpy_file':numpy.__file__,
    'pillow_version':PIL.__version__,'pillow_file':PIL.__file__,
    'identity':identity,'module_origins':origins,'launcher':proof,'tools_list':response,
    'spatial_task_only_attribute_present':hasattr(server,'spatial_task_only'),
    'spatial_task_only':getattr(server,'spatial_task_only',None),
    'constructor_arguments':{'service':'opaque object only','default_session_id':'complex005-source-only'},
    'service_constructed':False,'configuration_read':False,'host_calls':0,'forbidden_audit_events':forbidden}))
'''


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('utf8')


def load(path):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError('duplicate_json_key:'+key)
            value[key] = item
        return value
    return json.loads(Path(path).read_bytes(), object_pairs_hook=unique,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite_json:'+value)))


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n',
        encoding='utf8', newline='\n')


def manifest(site, count):
    names = set(ROOT_MODULES)
    for package in ('human_eye_plugin', 'human_eye_module1_operators'):
        names.update(package+'/'+p.name for p in (site/package).glob('*.py'))
    if len(names) != count:
        raise ValueError('independent_runtime_source_count:'+str(len(names)))
    rows = []
    for name in sorted(names):
        path = site/name
        if path.resolve() != path or not path.resolve().is_relative_to(site):
            raise ValueError('source_path_outside_install:'+name)
        rows.append({'path': name, 'sha256': sha(path)})
    return rows


def git_manifest(commit, names):
    raw = subprocess.check_output(['git', 'archive', '--format=tar', commit, *names], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as archive:
        rows = [{'path': member.name, 'sha256': hashlib.sha256(archive.extractfile(member).read()).hexdigest()}
            for member in archive.getmembers() if member.isfile()]
    if len(rows) != len(names) or {row['path'] for row in rows} != set(names):
        raise ValueError('fixed_commit_source_members_mismatch')
    return sorted(rows, key=lambda row: row['path'])


def run(label, argv):
    out, err = HERE/(label+'.stdout.json'), HERE/(label+'.stderr.txt')
    if out.exists() or err.exists():
        raise FileExistsError('source_probe_output_already_exists:'+label)
    env = dict(os.environ)
    for key in ('PYTHONPATH', 'PYTHONHOME'):
        env.pop(key, None)
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    started = time.perf_counter_ns()
    proc = subprocess.run([str(a) for a in argv], cwd=HERE, env=env,
        capture_output=True, timeout=45, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    out.write_bytes(proc.stdout)
    err.write_bytes(proc.stderr)
    receipt = {'argv': [str(a) for a in argv], 'exit_code': proc.returncode,
        'started_ns': started, 'elapsed_ns': time.perf_counter_ns()-started,
        'stdout': str(out), 'stdout_sha256': sha(out), 'stderr': str(err), 'stderr_sha256': sha(err)}
    save(HERE/(label+'.COMMAND.json'), receipt)
    if proc.returncode:
        raise RuntimeError(label+'_failed:'+str(proc.returncode)+':'+str(err))
    return load(out), receipt


def historical_binding(fixed, entry, binding):
    prepare = UPGRADE/'PREPARE.md'
    doctor_path = UPGRADE/'OLD_DOCTOR_BEFORE.json'
    stdout_path = UPGRADE/'OLD_DOCTOR_BEFORE.stdout.json'
    plan_path = UPGRADE/'PLAN_BEFORE.json'
    root_review_path = Path('D:/hefe/verification/fixes/20261110_native_plugin_compare_005/INSTALLED_BASELINE_REVIEW.json')
    prepare_text = prepare.read_text(encoding='utf8')
    if any(value not in prepare_text for value in (fixed['release'], fixed['canonical'], fixed['entry_sha256'],
            fixed['binding_sha256'], fixed['admin_sha256'])):
        raise ValueError('historical_prepare_identity_mismatch')
    doctor = load(doctor_path)
    result = doctor['result']
    runtime = result['target_runtime']
    historical = runtime['identity']
    launcher = runtime['launcher']
    if doctor['returncode'] != 0 or not result.get('ready_to_apply') or result['changes'] or result['applied']:
        raise ValueError('historical_doctor_not_successful_readonly')
    if load(stdout_path) != result:
        raise ValueError('historical_doctor_raw_stdout_differs')
    if Path(result['engine_root']).resolve() != entry.parent.parent/'site-packages':
        raise ValueError('historical_doctor_install_root_mismatch')
    if (historical['source_sha256'] != fixed['canonical'] or historical['distribution_version'] != fixed['release']
            or historical['source_file_count'] != fixed['count'] or historical['source_kind'] != 'installed_distribution'):
        raise ValueError('historical_doctor_source_identity_mismatch')
    for key in ('launcher_sha256', 'binding_sha256', 'admin_sha256'):
        if launcher[key] != fixed['entry_sha256' if key == 'launcher_sha256' else key]:
            raise ValueError('historical_doctor_launcher_receipt_mismatch:'+key)
    if launcher['identity'] != binding['identity'] or Path(launcher['entry']).resolve() != entry:
        raise ValueError('historical_entry_identity_mismatch')
    plan = load(plan_path)
    prior = plan['argv'].index('--prior-launcher')
    if (Path(plan['argv'][prior+1]).resolve() != entry or plan['argv'][prior+2] != fixed['entry_sha256']
            or plan['argv'][prior+3] != 'sha256:'+fixed['canonical']):
        raise ValueError('upgrade_prior_launcher_not_historical_install')
    root_review = load(root_review_path)
    baseline = root_review['baseline']
    if (root_review['status'] != 'passed' or baseline['git_commit'] != fixed['commit']
            or baseline['canonical_source_sha256'] != fixed['canonical']
            or baseline['manifest'] != binding['source_files'] or baseline['git_source_byte_mismatches']):
        raise ValueError('independent_root_historical_source_review_mismatch')
    if git_manifest(fixed['commit'], [row['path'] for row in binding['source_files']]) != binding['source_files']:
        raise ValueError('historical_fixed_commit_bytes_differ_from_actual_install')
    return {'basis': 'original pre-upgrade doctor and migration plan, independently matched with unchanged installed release',
        'historical_git_commit': fixed['commit'], 'HEAD_used_as_historical_source': False,
        'source_git_install_equal': True,
        'historical_runtime_identity': historical,
        'historical_connection_scope': result.get('current_connection'),
        'historical_desktop_loaded_identity_inferred': False,
        'records': [{'path': str(p), 'sha256': sha(p)} for p in (prepare, doctor_path, stdout_path, plan_path, root_review_path)]}


def current_binding(fixed, entry, rows):
    receipt_path = UPGRADE/'INSTALL/ISOLATED_INSTALL.json'
    receipt = load(receipt_path)
    previous_path = HERE.parent/'native_plugin_complex_004/SOURCE_PREFLIGHT.json'
    previous = load(previous_path)['versions']['C']
    if (receipt['status'] != 'passed' or receipt['fixed_commit'] != fixed['commit']
            or receipt['source_sha256'] != fixed['canonical'] or receipt['source_count'] != fixed['count']
            or not receipt['source_commit_wheel_install_equal']
            or Path(receipt['entry']).resolve() != entry or previous['runtime_sources'] != rows
            or previous['source_sha256'] != fixed['canonical'] or previous['commit'] != fixed['commit']):
        raise ValueError('current_fixed_deployment_evidence_mismatch')
    if git_manifest(fixed['commit'], [row['path'] for row in rows]) != rows:
        raise ValueError('current_fixed_commit_bytes_differ_from_install')
    return {'basis': 'actual current installed release, fixed df016079 Git archive, original deployment receipt and sealed 004 current-version preflight',
        'fixed_commit': fixed['commit'], 'source_git_install_equal': True,
        'records': [{'path': str(p), 'sha256': sha(p)} for p in (receipt_path, previous_path)]}


def qualify(group):
    started = time.perf_counter_ns()
    fixed = VERSIONS[group]
    release = (RELEASES/fixed['release']).resolve()
    entry = release/'admin/target_runtime_entry.py'
    binding_path = entry.with_name('RUNTIME_BINDING.json')
    binding = load(binding_path)
    site = release/'site-packages'
    if (sha(entry) != fixed['entry_sha256'] or sha(binding_path) != fixed['binding_sha256']
            or sha(entry.with_name('installed_release.py')) != fixed['admin_sha256']
            or binding['launcher_sha256'] != fixed['entry_sha256'] or binding['admin_sha256'] != fixed['admin_sha256']
            or Path(binding['dependency_python']).resolve() != DEPENDENCY_PYTHON.resolve()):
        raise ValueError('actual_controlled_entry_or_binding_mismatch:'+group)
    rows = manifest(site, fixed['count'])
    canonical = hashlib.sha256(encoded({'base_version': binding['identity']['base_version'],
        'implementation_revision': binding['identity']['implementation_revision'], 'files': rows})).hexdigest()
    if rows != binding['source_files'] or canonical != fixed['canonical']:
        raise ValueError('independent_actual_source_manifest_mismatch:'+group)
    origin = historical_binding(fixed, entry, binding) if group == 'H' else current_binding(fixed, entry, rows)
    raw, identity_command = run(group+'_identity', [DEPENDENCY_PYTHON, '-I', '-B', entry, 'identity'])
    identity = raw['runtime_identity']
    if (identity['source_files'] != rows or identity['source_sha256'] != canonical
            or identity['distribution_version'] != fixed['release'] or identity['source_kind'] != 'installed_distribution'):
        raise ValueError('actual_entry_identity_differs:'+group)
    schema, schema_command = run(group+'_schemas', [DEPENDENCY_PYTHON, '-I', '-B', '-X', 'utf8', '-c', SCHEMA_PROBE, entry])
    if (schema['identity'] != identity or not schema['isolated'] or not schema['dont_write_bytecode']
            or schema['forbidden_audit_events'] or schema['host_calls'] != 0 or schema['configuration_read']
            or schema['service_constructed']):
        raise ValueError('static_ordinary_catalogue_source_or_scope_mismatch:'+group)
    if schema['numpy_version'] != '2.3.5' or schema['pillow_version'] != '12.3.0':
        raise ValueError('unexpected_dependency_versions:'+group)
    tools = schema['tools_list']['result']['tools']
    names = [tool['name'] for tool in tools]
    if len(names) != len(set(names)) or names.count('human_eye_scene_observe') != 1:
        raise ValueError('unexpected_ordinary_catalogue:'+group)
    observe = next(tool for tool in tools if tool['name'] == 'human_eye_scene_observe')
    modes = observe['inputSchema']['properties']['query']['properties']['mode']['enum']
    save(HERE/(group+'_TOOLS_CATALOGUE.json'), {'group': group, 'tools_list': schema['tools_list'],
        'original_definitions_unchanged': True, 'source_sha256': canonical})
    return {'commit': fixed['commit'], 'entry': str(entry), 'entry_sha256': sha(entry),
        'source_sha256': canonical, 'installed_root': str(site), 'identity': identity,
        'dependency_python': str(DEPENDENCY_PYTHON), 'distribution_version': fixed['release'],
        'runtime_sources': rows, 'source_count': len(rows), 'binding': str(binding_path),
        'binding_sha256': sha(binding_path), 'admin_sha256': sha(entry.with_name('installed_release.py')),
        'source_origin': origin, 'ordinary_tools_sha256': hashlib.sha256(encoded(tools)).hexdigest(),
        'ordinary_tool_names': names, 'ordinary_query_modes': modes,
        'identity_command': identity_command, 'schema_command': schema_command,
        'schema_probe': {key: schema[key] for key in ('numpy_version', 'pillow_version', 'numpy_file',
            'pillow_file', 'python_version', 'host_calls', 'service_constructed', 'configuration_read',
            'spatial_task_only_attribute_present', 'spatial_task_only')},
        'ordinary_serve_argv_prefix': [str(DEPENDENCY_PYTHON), '-I', '-B', str(entry), 'serve'],
        'ordinary_serve_required_suffix': ['--config', '<owned-isolated-config>'],
        'proposed_public_tools': ['human_eye_scene_observe', 'human_eye_connection_status'],
        'public_tool_selection_status': 'root confirmed original observe/status only; no schema normalization or capability backport',
        'qualification_started_ns': started, 'qualification_elapsed_ns': time.perf_counter_ns()-started}


def main():
    HERE.mkdir(exist_ok=True)
    out = HERE/'SOURCE_PREFLIGHT.json'
    if out.exists():
        raise FileExistsError('source_preflight_already_recorded')
    started = time.perf_counter_ns()
    result = {'schema': 'complex-005-source-preflight-v1', 'task': 'COMPLEX-005', 'scope': 'PREP_ONLY',
        'passed': False, 'dependency_python': str(DEPENDENCY_PYTHON), 'versions': {},
        'model_calls': 0, 'Blender_started': 0, 'performance_runs': 0, 'serve_processes_started': 0,
        'default_or_formal_configuration_writes': 0, 'new_builds': 0, 'new_installs': 0,
        'learning_task_sync': 'pending; no legal bound context; no borrowed handle'}
    try:
        for group in ('H', 'C'):
            result['versions'][group] = qualify(group)
        h, c = (result['versions'][g] for g in ('H', 'C'))
        result['ordinary_schema_equal'] = h['ordinary_tools_sha256'] == c['ordinary_tools_sha256']
        result['catalogue_comparison'] = {'H_names': h['ordinary_tool_names'], 'C_names': c['ordinary_tool_names'],
            'H_query_modes': h['ordinary_query_modes'], 'C_query_modes': c['ordinary_query_modes'],
            'definition_difference_policy': 'Each version retains its actual original schema and supported interface; differences are facts, not a preflight failure.'}
        result['passed'] = True
    except BaseException as exc:
        result['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
        raise
    finally:
        result['started_ns'] = started
        result['elapsed_ns'] = time.perf_counter_ns()-started
        result['script_sha256'] = sha(__file__)
        save(out, result)
        print(json.dumps({'passed': result['passed'], 'output': str(out),
            'versions': {g: v['source_sha256'] for g, v in result['versions'].items()}}))


if __name__ == '__main__':
    main()
