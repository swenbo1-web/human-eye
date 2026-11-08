"""Prepare frozen bytes, then one owned T04 QA with two captures and one close.

Preparation imports no product and starts no session. Only the explicitly
selected run command can launch the original controlled stdio/NativeSession.
"""
import argparse
import ast
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import traceback
import types

FOLDER = Path(__file__).resolve().parent
ROOT = FOLDER.parents[1]
OUT = FOLDER / 'qa_01'
TOKEN = 'DEGENERATE-SURFACE-001-20261108T110651Z-QA-ONLY'
COORD = Path('D:/hefe/verification/fixes/20261107_nearest_contract')
STATE = Path('D:/hefe/verification/fixes/20261106_parallel_coordination/STATE.json')
ASSIGNMENT = COORD / 'DEGENERATE_SURFACE_ASSIGNMENT.md'
ASSIGNMENT_SHA = '190423ab17b28f1655ead3c816d3f7bde822db6a30eefe6c08edf8cde9db339b'
OLD = ROOT / 'verification/surface_nearest_entry_001/qa_prepare'
HELPER = ROOT / 'verification/consumption_run_001/materials/admin/visual004_native.py'
HELPER_SHA = '5bc1152aeafab89220c93edeec51cbe32ace458cc07d3e7d0507b6412b816fb3'
BOOTSTRAP_SHA = '45363af4e6763589dee638ba3a0bc1ee6a9cc00eca9da950736b2ae6fabe39a6'
BLENDER = Path('D:/Tools/blender5.2/blender.exe')
BLENDER_SHA = '284f4041f98e113f3dc10654a7193ffaaa9bfdfec8b87fa116620a48b5f6d4cb'
MATERIALS = ROOT / 'verification/consumption_run_001/materials'
MATERIAL_SHA = '0fb8fdacb5bdd2fc1b6f42e6c09763e2811b4c2fb5f1421af84ecde5871189df'
ASSET_SHA = '5638452c2e287803b2d722f5dc8cc845bb687fac0ff7531c7b1cdd69c17ff94d'
PYTHON = ROOT / 'verification/fixes/surface_facts_001/engineering_b/venv/Scripts/python.exe'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_bytes((json.dumps(value, indent=2, allow_nan=False) + '\n').encode('utf8'))


def error_info(error):
    return dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc())


def window():
    value = json.loads(STATE.read_bytes())['performance_window']
    assert value['token'] == TOKEN and value['owner'] == 'W-ENTRY'
    assert value['max_sessions'] == 1 and value['max_RPC'] == 3 and value['model_answers'] == 0
    assert str(value['status']).startswith('granted')
    end = datetime.fromisoformat(value.get('expires_utc', value.get('deadline_utc')).replace('Z', '+00:00'))
    assert datetime.now(timezone.utc) < end - timedelta(seconds=660), 'leave_original_600s_plus_cleanup'
    return value


def declared_identity(value):
    value = value.get('identity', value)
    return value.get('runtime_source_sha256', value.get('candidate_source_sha256', value.get('source_sha256')))


def check_sources(plan):
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == plan['candidate_commit']
    for row in plan['product_manifest']:
        assert sha(ROOT / row['path']) == sha(Path(plan['source_root']) / row['path']) == row['sha256'], row['path']
    assert sha(HELPER) == HELPER_SHA and sha(plan['asset']) == ASSET_SHA and sha(BLENDER) == BLENDER_SHA
    assert sha(ASSIGNMENT) == ASSIGNMENT_SHA and sha(MATERIALS / 'MATERIAL_MANIFEST.json') == MATERIAL_SHA
    assert Path(sys.executable).resolve() == PYTHON.resolve(), 'existing_interpreter_required'


def proof(record):
    path = Path(record['path']).resolve()
    assert sha(path) == record['sha256'], str(path)
    return json.loads(path.read_bytes()), dict(path=str(path), sha256=record['sha256'])


def prepare(args):
    begun = time.perf_counter_ns()
    assert not OUT.exists(), 'fresh_bounded_QA_directory_required'
    assert args.candidate_freeze is not None, 'candidate_freeze_required'
    frozen_path = args.candidate_freeze.resolve()
    frozen = json.loads(frozen_path.read_bytes())
    commit, source_sha = frozen['candidate_commit'], frozen['source_sha256']
    assert re.fullmatch('[0-9a-f]{40}', commit) and re.fullmatch('[0-9a-f]{64}', source_sha)
    manifest = sorted([dict(path=row['path'], sha256=row['sha256'])
                       for row in frozen['product_manifest']], key=lambda row: row['path'])
    assert len(manifest) == len({row['path'] for row in manifest}) == 131
    source_root = Path(frozen['source_root']).resolve()
    assert source_root.is_relative_to(FOLDER), 'current_batch_source_snapshot_required'
    offline, offline_proof = proof(frozen['offline_proof'])
    identity_record, identity_proof = proof(frozen['identity_proof'])
    identity = identity_record.get('identity', identity_record)
    assert offline.get('passed') is True, 'offline_pass_required'
    assert declared_identity(offline) == declared_identity(identity_record) == source_sha
    identity_manifest = identity.get('product_manifest', identity.get('manifest', identity.get('source_files', identity.get('files', []))))
    assert sorted([dict(path=r['path'], sha256=r['sha256']) for r in identity_manifest], key=lambda r:r['path']) == manifest
    guard = offline.get('loader_guard', {})
    assert (identity_record.get('guard_verify_loaded') is True or identity.get('guard_verify_loaded') is True
            or type(guard) is dict and guard.get('verify_loaded') is True), 'original_verified_loader_execution_required'
    if type(guard) is dict and 'every_loaded_module_has_execution_or_namespace_witness' in guard:
        assert guard['every_loaded_module_has_execution_or_namespace_witness'] is True
    expected = frozen['expected_t04']
    assert type(expected['distance_m']) in (int, float) and math.isfinite(expected['distance_m']) and expected['distance_m'] >= 0
    assert type(expected['nearest_names']) is list and expected['nearest_names']
    assert all(type(name) is str and name for name in expected['nearest_names'])
    assert len(expected['nearest_names']) == len(set(expected['nearest_names']))
    assert type(expected['targets_excluding_focal']) is int and expected['targets_excluding_focal'] == 4
    material_manifest = MATERIALS / 'MATERIAL_MANIFEST.json'
    assert sha(material_manifest) == MATERIAL_SHA
    task = next(row for row in json.loads(material_manifest.read_bytes())['tasks'] if row['task_id'] == 'T04')
    assert task['asset_sha256'] == ASSET_SHA
    prompt_path = MATERIALS / task['prompt_path']
    assert sha(prompt_path) == task['prompt_utf8_sha256']
    focal = re.search(r'以 ([A-Za-z0-9_]+) 为焦点', prompt_path.read_text(encoding='utf8'))
    assert focal and focal.group(1) == 'M4_Focal'
    plan = dict(candidate_commit=commit, source_sha256=source_sha, product_manifest=manifest,
        source_root=str(source_root), run_root=str(OUT), native_workspace=str(OUT / 'owned'),
        blender=str(BLENDER), blender_sha256=BLENDER_SHA, asset=task['source_asset_path'], asset_sha256=ASSET_SHA,
        helper=str(HELPER), helper_sha256=HELPER_SHA, max_sessions=1, max_total_RPC=3,
        max_execute_RPC=2, max_close_RPC=1, model_consumers=0, retries=0,
        request_budget_s=20., native_visual_timeout_s=10., original_worker_seconds=600,
        candidate_freeze=dict(path=str(frozen_path), sha256=sha(frozen_path)),
        offline_proof=offline_proof, identity_proof=identity_proof,
        prompt_proof=dict(path=str(prompt_path),sha256=sha(prompt_path)),
        focal_name=focal.group(1), expected_t04=expected, window=window())
    check_sources(plan)
    blobs = {}
    for row in manifest:
        path = (ROOT / row['path']).resolve()
        assert path.is_relative_to(ROOT) and path.suffix == '.py'
        data = path.read_bytes()
        assert subprocess.check_output(['git', 'cat-file', 'blob', commit + ':' + row['path']], cwd=ROOT) == data
        blobs[row['path']] = data
    constants = {}
    for node in ast.parse(blobs['human_eye_plugin/runtime_identity.py']).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ('BASE_VERSION', 'IMPLEMENTATION_REVISION'):
                    constants[target.id] = ast.literal_eval(node.value)
    canonical = dict(base_version=constants['BASE_VERSION'], implementation_revision=constants['IMPLEMENTATION_REVISION'], files=manifest)
    assert hashlib.sha256(json.dumps(canonical,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest() == source_sha
    assert sha(OLD / 'stdio_bootstrap.py') == BOOTSTRAP_SHA
    plan['host_sha256'] = next(row['sha256'] for row in manifest if row['path'] == 'human_eye_plugin/blender_host.py')
    OUT.mkdir()
    (OUT / 'stdio_bootstrap.py').write_bytes((OLD / 'stdio_bootstrap.py').read_bytes())
    plan.update(prepared_utc=datetime.now(timezone.utc).isoformat(), prepare_elapsed_ns=time.perf_counter_ns()-begun)
    save(OUT / 'PLAN.json', plan)
    paths = (Path(__file__), HELPER, OLD / 'controller.py', OUT / 'stdio_bootstrap.py',
             frozen_path, Path(identity_proof['path']), Path(offline_proof['path']), material_manifest, prompt_path)
    save(OUT / 'FREEZE.json', dict(plan_sha256=sha(OUT / 'PLAN.json'), no_session_started=True,
        controllers=[dict(path=str(path), sha256=sha(path)) for path in paths]))
    print(json.dumps(dict(status='prepared_no_session', source_sha256=source_sha, candidate_commit=commit,
                          plan_sha256=sha(OUT / 'PLAN.json'), max_total_RPC=3)))


def existing_helpers():
    """Load old controller definitions only; its guarded main is not run."""
    path = OLD / 'controller.py'
    spec = importlib.util.spec_from_file_location('_degenerate_existing_entry_QA_controller', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.OUT = OUT
    module.FOLDER = OUT
    return module


def semantic(value):
    fields = ('result_kind','status','scope','focal','nearest_objects','best_known_objects',
              'distance_m','best_known_distance_m','unit','coverage','unresolved','execution_authority')
    return {key:value.get(key) for key in fields}


def check_t04(value, plan):
    assert value['result_kind'] == 'surface_nearest' and value['status'] == 'complete'
    assert value['execution_authority'] is False and value['unit'] == 'm'
    assert value['focal']['name'] == plan['focal_name']
    assert value['binding']['runtime_source_sha256'] == plan['source_sha256']
    assert value['distance_m'] == plan['expected_t04']['distance_m']
    assert sorted(row['name'] for row in value['nearest_objects']) == sorted(plan['expected_t04']['nearest_names'])
    assert not value['unresolved']
    coverage = value['coverage']
    assert coverage['targets_excluding_focal'] == plan['expected_t04']['targets_excluding_focal']
    assert coverage['unresolved'] == 0
    assert coverage['distance_valid'] + coverage['strictly_excluded'] == coverage['targets_excluding_focal']
    assert '_exact_distance_sq' not in json.dumps(value) and 'vertices' not in json.dumps(value)


def run():
    plan = json.loads((OUT / 'PLAN.json').read_bytes())
    freeze = json.loads((OUT / 'FREEZE.json').read_bytes())
    assert sha(OUT / 'PLAN.json') == freeze['plan_sha256']
    for row in freeze['controllers']:
        assert sha(row['path']) == row['sha256']
    for key in ('offline_proof', 'identity_proof', 'candidate_freeze', 'prompt_proof'):
        assert sha(plan[key]['path']) == plan[key]['sha256']
    check_sources(plan)
    active_window = window()
    assert active_window['token'] == plan['window']['token']
    assert not (OUT / 'STARTED.json').exists(), 'no_second_session_or_retry'
    helpers = existing_helpers()
    native = types.ModuleType('_degenerate_owned_native')
    native.__file__ = str(HELPER)
    sys.modules[native.__name__] = native
    exec(compile(HELPER.read_bytes(), str(HELPER), 'exec', dont_inherit=True), native.__dict__)
    begun = time.perf_counter_ns()
    plan['deadline_ns'] = begun + 600_000_000_000
    record = dict(started_utc=datetime.now(timezone.utc).isoformat(), original_deadline_ns=plan['deadline_ns'],
        candidate_commit=plan['candidate_commit'], source_sha256=plan['source_sha256'], controller_pid=os.getpid(),
        primary_error=None, owned_sessions_attempted=0, control_RPC_attempts=0, product_attempts=0,
        public_calls=[], retries=0, model_consumers=0, actual_external_API=0, original_asset_write=False,
        profile_setup_RPC=0, expected_t04=plan['expected_t04'])
    with (OUT / 'STARTED.json').open('xb') as stream:
        stream.write((json.dumps(dict(started_utc=record['started_utc'], started_ns=begun,
            argv=sys.argv, python=sys.executable, controller_pid=os.getpid(),
            freeze_sha256=sha(OUT / 'FREEZE.json'), window=active_window), indent=2) + '\n').encode())
    owner = None
    stdio = None

    def sockets_count():
        return len(list((OUT / 'stdio').glob('socket_*')))

    def transaction(label, call):
        assert record['control_RPC_attempts'] + sockets_count() < 3, 'physical_RPC_cap'
        folder = OUT / label
        folder.mkdir()
        meter = dict(send_attempted_bytes=0, send_completed_bytes=0, received_bytes=0)
        original = native.socket.create_connection
        def connect(*args, **kwargs):
            return helpers.MeterSocket(original(*args, **kwargs), folder, meter)
        native.socket.create_connection = connect
        record['control_RPC_attempts'] += 1
        start = time.perf_counter_ns()
        try:
            response = call()
            save(folder / 'RESPONSE.json', response)
            return response
        finally:
            native.socket.create_connection = original
            save(folder / 'METER.json', dict(**meter, elapsed_ns=time.perf_counter_ns()-start))

    def observe(label, arguments):
        before = sockets_count()
        assert record['product_attempts'] < 2 and record['control_RPC_attempts'] + before < 2, 'reserve_close_RPC'
        row = dict(label=label, started_ns=time.perf_counter_ns(), arguments=arguments)
        record['public_calls'].append(row)
        record['product_attempts'] += 1
        try:
            response = stdio.call('tools/call', dict(name='human_eye_scene_observe', arguments=arguments))
            row['response'] = response
            assert sockets_count()-before == 1, 'one_physical_capture_per_public_request'
            return response
        finally:
            row['elapsed_ns'] = time.perf_counter_ns()-row['started_ns']
            row['physical_RPC_delta'] = sockets_count()-before

    try:
        record['owned_sessions_attempted'] = 1
        start = time.perf_counter_ns()
        owner = native.NativeSession.start(blender=plan['blender'], asset=plan['asset'], workspace=OUT / 'owned',
            deadline_ns=plan['deadline_ns'], condition='N', expected_asset_sha256=ASSET_SHA, max_calls=2)
        record['native_startup_ns'] = time.perf_counter_ns()-start
        record['ready'] = owner.ready
        assert owner.ready['pid'] == owner.process.pid and owner.ready['helper_sha256'] == HELPER_SHA
        save(OUT / 'NATIVE_COMMAND.json', dict(pid=owner.process.pid, argv=[plan['blender'], '--factory-startup',
            '--disable-autoexec', '--background', str(OUT / 'owned/input.blend'), '--python-exit-code', '1',
            '--python', str(HELPER), '--', '--worker', str(OUT / 'owned/CONFIG.json')]))
        plan['endpoint'] = dict(host=owner.host, port=owner.port)
        plan['config_path'] = str(OUT / 'live-connector.json')
        save(plan['config_path'], dict(schema_version='1.0', enabled=True, observe_on_prompt=False,
            project_root=plan['source_root'], state_file=str(OUT / 'state.json'), audit_file=str(OUT / 'audit.jsonl'),
            expected_identity=dict(source_sha256=plan['source_sha256']),
            blender=dict(host=owner.host, port=owner.port, timeout_s=10), request_budget_s=20., native_visual_timeout_s=10.))
        save(OUT / 'RUNTIME_PLAN.json', plan)
        save(OUT / 'ENDPOINT_FREEZE.json', dict(runtime_plan_sha256=sha(OUT / 'RUNTIME_PLAN.json'),
            config_sha256=sha(plan['config_path']), ready=owner.ready))
        stdio = helpers.Stdio(plan)
        save(OUT / 'STDIO_PROCESS.json', dict(pid=stdio.process.pid, owner='controller Popen',
            command=json.loads((OUT / 'STDIO_COMMAND.json').read_bytes())))
        assert 'result' in stdio.call('initialize', dict(protocolVersion='2024-11-05', capabilities={},
            clientInfo=dict(name='degenerate-surface-QA', version='1')))
        stdio.call('notifications/initialized', {}, notification=True)
        tools = stdio.call('tools/list', {})
        assert any(tool['name'] == 'human_eye_scene_observe' for tool in tools['result']['tools'])
        assert sockets_count() == 0, 'initialize_and_list_must_not_capture'
        first = helpers.public_result(observe('direct_name', dict(session_id='degenerate-direct-read',
            include_image=False, query=dict(mode='surface_nearest', objects=[dict(name=plan['focal_name'])]))))
        check_t04(first, plan)
        focal = first['focal']['id']
        assert type(focal) is str and focal
        legacy = helpers.public_result(observe('legacy_id', dict(session_id='degenerate-legacy-read', focal_id=focal,
            include_image=False, query=dict(mode='surface_nearest'))))
        check_t04(legacy, plan)
        assert semantic(first) == semantic(legacy), 'direct_name_legacy_ID_mismatch'
        record['entry_assertions_passed'] = True
    except BaseException as error:
        record['primary_error'] = error_info(error)
    finally:
        if stdio is not None:
            try:
                record['stdio_cleanup'] = stdio.close()
            except BaseException as error:
                record['stdio_cleanup_error'] = error_info(error)
        if owner is not None:
            try:
                record['native_cleanup'] = transaction('rpc_close', owner.close)
            except BaseException as error:
                record['native_cleanup_error'] = error_info(error)
                owner._kill()
            record['owned_process_reaped'] = owner.process.poll() is not None
            record['owned_exit_code'] = owner.process.poll()
            closed = OUT / 'owned/WORKER_CLOSED.json'
            if closed.exists():
                record['worker_closed'] = json.loads(closed.read_bytes())
                record['worker_closed_sha256'] = sha(closed)
        bootstrap_path = OUT / 'stdio/BOOTSTRAP_RESULT.json'
        if bootstrap_path.exists():
            record['bootstrap'] = json.loads(bootstrap_path.read_bytes())
        record['product_socket_count'] = sockets_count()
        record['total_RPC_attempts'] = record['control_RPC_attempts'] + sockets_count()
        record['asset_sha256_after'] = sha(plan['asset'])
        record['helper_sha256_after'] = sha(HELPER)
        record['source_drift'] = [row['path'] for row in plan['product_manifest']
            if sha(ROOT / row['path']) != row['sha256'] or sha(Path(plan['source_root']) / row['path']) != row['sha256']]
        record['whole_controller_ns'] = time.perf_counter_ns()-begun
        record['ended_utc'] = datetime.now(timezone.utc).isoformat()
        bootstrap = record.get('bootstrap', {})
        witness = bootstrap.get('execution_witness', {})
        cleanup = record.get('native_cleanup', {})
        cleanup_response = cleanup.get('response')
        cleanup_response = cleanup_response if type(cleanup_response) is dict else {}
        bound_generation = witness.get('bound_generation')
        bound_generation = bound_generation if type(bound_generation) is dict else {}
        controls = [json.loads(path.read_bytes()) for path in OUT.glob('rpc_*/METER.json')]
        sockets = bootstrap.get('sockets', [])
        record['boundary_totals'] = dict(control_TX_attempted_bytes=sum(row['send_attempted_bytes'] for row in controls),
            control_TX_completed_bytes=sum(row['send_completed_bytes'] for row in controls), control_RX_bytes=sum(row['received_bytes'] for row in controls),
            product_TX_attempted_bytes=sum(row['send_attempted_bytes'] for row in sockets),
            product_TX_completed_bytes=sum(row['send_completed_bytes'] for row in sockets), product_RX_bytes=sum(row['received_bytes'] for row in sockets),
            complete_stdio_TX_bytes=record.get('stdio_cleanup', {}).get('complete_TX_bytes'),
            complete_stdio_RX_bytes=record.get('stdio_cleanup', {}).get('complete_RX_bytes'))
        record['timing_note'] = 'Preparation, startup, product requests, close and whole controller are nested; no cold/warm model-benefit inference or free-overhead subtraction.'
        record['cache_proof_scope'] = 'Offline verified-loader execution counts are authoritative; actual stdio profile observations are retained without cold/warm inference.'
        record['passed'] = bool(record['primary_error'] is None and record.get('entry_assertions_passed')
            and record['owned_sessions_attempted'] == 1 and record['product_attempts'] == 2
            and record['product_socket_count'] == 2 and record['total_RPC_attempts'] == 3
            and witness.get('guard_verified') and bound_generation.get('compatible')
            and witness.get('every_loaded_module_has_execution_or_namespace_witness')
            and record.get('stdio_cleanup', {}).get('exit_code') == 0
            and record.get('stdio_cleanup', {}).get('process_reaped') is True
            and record.get('stdio_cleanup', {}).get('extra_rx_bytes') == 0
            and record.get('owned_process_reaped') and record.get('owned_exit_code') == 0
            and cleanup_response.get('status') == 'closed' and cleanup.get('error') is None
            and cleanup.get('original_deadline_ns') == plan['deadline_ns']
            and cleanup_response.get('deadline_ns') == plan['deadline_ns']
            and cleanup.get('source_file_unchanged') and cleanup.get('protected_files_unchanged')
            and record.get('worker_closed', {}).get('poisoned') is False
            and record.get('worker_closed', {}).get('original_deadline_ns') == plan['deadline_ns']
            and record.get('worker_closed', {}).get('initial_geometry_fingerprint') == record.get('worker_closed', {}).get('final_geometry_fingerprint') == record.get('ready', {}).get('initial_fingerprint')
            and record['asset_sha256_after'] == ASSET_SHA and record['helper_sha256_after'] == HELPER_SHA
            and not record['source_drift'])
        record['status'] = 'bounded_real_degenerate_surface_complete' if record['passed'] else 'incomplete_no_replay'
        save(OUT / 'RESULTS.json', record)
        print(json.dumps(dict(status=record['status'], passed=record['passed'], total_RPC_attempts=record['total_RPC_attempts'], result=str(OUT / 'RESULTS.json'))))
    if not record['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('prepare', 'run'))
    parser.add_argument('--candidate-freeze', type=Path)
    args = parser.parse_args()
    try:
        {'prepare':lambda:prepare(args), 'run':run}[args.command]()
    except BaseException as error:
        if not (OUT / 'STARTED.json').exists():
            failures = FOLDER / 'qa_prepare_failures'
            failures.mkdir(exist_ok=True)
            save(failures / (str(time.time_ns()) + '.json'), error_info(error))
        raise
