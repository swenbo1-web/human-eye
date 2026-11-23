"""One registered Blender read window with a sealed loopback preflight."""

import argparse
import base64
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from time import perf_counter_ns, sleep
import traceback
from uuid import uuid4

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from replay_rna import archive_as_bpy

VERIFY = HERE.parent
NATIVE_ROOT = VERIFY / 'm4_global_local_qualification_001/harness/reused'
CAPTURE = VERIFY / 'm4_live_source_region_task_003/harness/device_capture.py'
BUDGET = VERIFY / 'm4_live_source_region_task_003/harness/budget.py'
PRODUCT_BINDING = VERIFY / 'm1_m2_source_region_scoped_measurement_001/install/PRODUCT_RUN_BINDING.json'
ROOT = Path('D:/he_m4_source_region_live_bounds_qualification_001').resolve()
PRODUCT = Path('D:/he_m1_m2_source_region_scoped_measurement_001/candidate_install/product').resolve()
BLENDER = Path('D:/Tools/blender5.2/blender.exe').resolve()
PYTHON = Path('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe').resolve()
PYTHON_SHA = '50f885251e42eb8cd1fbf5d4fbcc01efdbe8b9f4d4379e16664d4d0f3d4a9869'
BLENDER_SHA = '284f4041f98e113f3dc10654a7193ffaaa9bfdfec8b87fa116620a48b5f6d4cb'
PRODUCT_COMMIT = 'ba79e2f1ca79f4651a3acaef90988fef9a1a9fc6'
SOURCE_SHA = '4a51c48524b66895819b69a30d2bd8eb020ce840028f0612f8d6e887c0423f09'
WHEEL_SHA = '7ff84ab1349d93a0810c687c8e3b0cea10d311c512380b5a9077305f35d5685d'
LABELS = ('RAIL', 'ASSEMBLY')
PREFIX = 'M4_LIVE_BOUNDS:'
CAPTURE_PREFIX = 'M4_LIVE_SOURCE_CAPTURE:'
SLOT_NS = 120 * 10**9
RUNTIME_FILES = (
    'human_eye_plugin/blender_mcp_host.py', 'human_eye_plugin/blender_host.py',
    'human_eye_plugin/scene_residency.py', 'human_eye_plugin/rig_pose.py',
    'human_eye_plugin/arm_twist_weights.py', 'human_eye_plugin/arm_twist_expert.py',
    'human_eye_plugin/arm_twist_source.py',
)


def import_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[name]
        raise
    return module


native = import_file('live_bounds_native', NATIVE_ROOT / 'owned_native.py')
meter = import_file('live_bounds_meter', NATIVE_ROOT / 'wire_meter.py')
encoded, load, save, sha, check = native.encoded, native.load, native.save, native.sha, native.check


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(path):
    path = Path(path).resolve(strict=True)
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}


def check_identity(pin):
    require(identity(pin['path']) == pin, 'changed_input:' + str(pin['path']))


def require_interpreter():
    require(Path(sys.executable).resolve() == PYTHON and sha(PYTHON) == PYTHON_SHA,
            'unbound_isolated_python')
    require(sys.flags.isolated and sys.flags.dont_write_bytecode and sys.flags.utf8_mode,
            'isolated_python_flags_required')


def inputs():
    data = load(ROOT / 'REQUESTS.json')
    require(data['schema'] == 'human-eye-m4-live-bounds-requests-v1' and
            data['order'] == list(LABELS) and set(data['cases']) == set(LABELS), 'requests_contract')
    for label in LABELS:
        case = data['cases'][label]
        require(case['label'] == label and len(case['queries']) == 2, 'registered_label_and_queries')
        for name in ('asset', 'terminal'):
            check_identity(case[name])
    return data['cases']


def bind_product(*, full=False):
    binding = load(PRODUCT_BINDING)
    require(Path(binding['install_root']) == PRODUCT and binding['preparation_git'] == PRODUCT_COMMIT
            and binding['source_sha256'] == SOURCE_SHA and binding['wheel_sha256'] == WHEEL_SHA,
            'fixed_ba79_install')
    paths = {row['path']: row['sha256'] for row in binding['source_manifest']}
    require(len(paths) == 143 and set(RUNTIME_FILES) <= paths.keys(), 'fixed_ba79_manifest')
    for relative in (paths if full else RUNTIME_FILES):
        resolved = (PRODUCT / relative).resolve(strict=True)
        require(resolved.is_relative_to(PRODUCT) and sha(resolved) == paths[relative],
                'installed_source_changed:' + relative)
    for directory in reversed((PRODUCT, Path(binding['dependency_root']).resolve(strict=True))):
        if str(directory) not in sys.path:
            sys.path.insert(0, str(directory))
    return binding


def make_request(case, deadline):
    return {
        'schema': 'human-eye-m4-live-bounds-business-v1', 'label': case['label'],
        'nonce': uuid4().hex, 'queries': case['queries'],
        'asset_sha256': case['asset']['sha256'], 'terminal_sha256': case['terminal']['sha256'],
        'deadline_ns': deadline, 'diagnostic_sha256': sha(HERE / 'diagnostic.py'),
        'product_commit': PRODUCT_COMMIT, 'registered_requests_sha256': sha(ROOT / 'REQUESTS.json'),
    }


def bind_request(request, case):
    required = {'schema', 'label', 'nonce', 'queries', 'asset_sha256', 'terminal_sha256',
                'deadline_ns', 'diagnostic_sha256', 'product_commit', 'registered_requests_sha256'}
    require(type(request) is dict and request.keys() == required, 'registered_request_shape')
    fresh = make_request(case, request['deadline_ns'])
    require(all(request[k] == fresh[k] for k in required - {'nonce'}), 'registered_request_changed')
    nonce = request['nonce']
    require(type(nonce) is str and len(nonce) == 32 and all(c in '0123456789abcdef' for c in nonce),
            'registered_nonce_shape')
    check(request['deadline_ns'])


def diagnostic_script(request):
    bind_product()
    from human_eye_plugin.blender_mcp_host import BlenderMCPHost

    source = (HERE / 'diagnostic.py').read_bytes()
    require(digest(source) == request['diagnostic_sha256'], 'diagnostic_source_unbound')
    connector = BlenderMCPHost(PRODUCT, timeout_s=30)
    binding = load(PRODUCT_BINDING)
    pins = {row['path']: row['sha256'] for row in binding['source_manifest']}
    require(connector._readonly_host_source_sha256 == pins['human_eye_plugin/blender_host.py']
            and connector._readonly_scene_residency_sha256 == pins['human_eye_plugin/scene_residency.py'],
            'actual_bootstrap_sources_unbound')
    wire_request = encoded(request).decode('ascii').strip()
    source_b64 = base64.b64encode(source).decode('ascii')
    lines = [
        'import base64 as _b64, hashlib as _hash, json as _json, os as _os',
        '_bound = _json.loads(' + repr(wire_request) + ')',
        'try:',
        *connector._resident_setup(),
        '    _source = _b64.b64decode(' + repr(source_b64) + ')',
        "    if _hash.sha256(_source).hexdigest() != _bound['diagnostic_sha256']:",
        "        raise ValueError('registered_diagnostic_sha256')",
        "    _verified_diagnostic = {'__name__': 'human_eye_live_bounds_registered'}",
        "    exec(compile(_source, '<registered-live-bounds-diagnostic>', 'exec'), _verified_diagnostic)",
        "    _packet = _verified_diagnostic['diagnose'](_host, _bound['queries'], _bound['deadline_ns'])",
        "    _reply = dict(status='complete', request=_bound, pid=_os.getpid(),",
        "                  readonly_host_sha256=_module._READONLY_LOADED_HOST_SHA256, packet=_packet)",
        'except Exception as _error:',
        "    _reply = dict(status='error', request=_bound, pid=_os.getpid(),",
        "                  error_type=type(_error).__name__, error=str(_error))",
        'print(' + repr(PREFIX) + " + _json.dumps(_reply, sort_keys=True, separators=(',', ':'), allow_nan=False))",
    ]
    script = '\n'.join(lines) + '\n'
    require(len(script.encode('utf8')) <= native.MAX_CODE, 'registered_script_not_in_native_budget')
    return script


def capture_script(plan, target):
    require(target.name in ('INITIAL_SOURCE.json', 'TERMINAL_SOURCE.json'),
            'closure_capture_output_target')
    invoke = '\ncapture_device(bpy, ' + repr(str(target)) + ', ' + repr(plan['asset']['sha256']) + ', terminal=True)\n'
    return CAPTURE.read_text(encoding='utf8') + invoke


def read_stdout(outer, prefix):
    response = outer['response']
    require(response.get('status') == 'success' and response.get('result', {}).get('executed') is True,
            'worker_rpc_rejected:' + str(response.get('error')))
    records = response['result']['result'].splitlines()
    require(len(records) == 1 and records[0].startswith(prefix), 'registered_worker_stdout')
    return json.loads(records[0].removeprefix(prefix))


def execute_diagnostic(session, slot, request, script):
    outer = session.run(script)
    save(slot / 'DIAGNOSTIC_CLIENT.json', outer)
    response = read_stdout(outer, PREFIX)
    require(response['request'] == request and response['pid'] == session.config['pid']
            and outer['original_deadline_ns'] == request['deadline_ns'], 'host_rpc_binding')
    require(response['status'] == 'complete', 'registered_host_error:' + str(response.get('error')))
    packet = response['packet']
    host_sha = sha(PRODUCT / 'human_eye_plugin/blender_host.py')
    require(response['readonly_host_sha256'] == host_sha and packet['status'] == 'complete',
            'installed_readonly_host_or_packet_status_changed')
    save(slot / 'DIAGNOSTIC.json', packet)
    receipt = {
        'schema': 'human-eye-m4-live-bounds-rpc-receipt-v1', 'request': request,
        'script_sha256': digest(script.encode('utf8')), 'elapsed_ns': outer['elapsed_ns'],
        'pid': response['pid'], 'readonly_host_sha256': host_sha,
        'raw_client': identity(slot / 'DIAGNOSTIC_CLIENT.json'),
        'diagnostic': identity(slot / 'DIAGNOSTIC.json'),
        'outer_original_deadline_ns': outer['original_deadline_ns'],
    }
    save(slot / 'DIAGNOSTIC_RECEIPT.json', receipt)


def independent_capture(session, slot, case, filename):
    output = slot / filename
    require(not output.exists(), 'independent_capture_would_overwrite_existing_record')
    outer = session.run(capture_script(case, output))
    save(slot / filename.replace('.json', '_CLIENT.json'), outer)
    receipt = read_stdout(outer, CAPTURE_PREFIX)
    require(receipt['pid'] == session.config['pid'] and receipt['sha256'] == sha(output)
            and receipt['bytes'] == output.stat().st_size, 'independent_capture_receipt_binding')
    return receipt


def worker_closed(slot, closed, request):
    worker = load(slot / 'native/WORKER_CLOSED.json')
    require(closed['pid'] == worker['pid'] and closed['error'] is None and closed['process_reaped']
            and closed['exit_code'] == 0 and closed['source_file_unchanged']
            and closed['protected_files_unchanged'] and not worker['poisoned']
            and worker['initial_geometry_fingerprint'] == worker['final_geometry_fingerprint']
            and closed['response'] == {'status': 'closed', 'pid': worker['pid'], 'deadline_ns': request['deadline_ns']}
            and worker['original_deadline_ns'] == request['deadline_ns']
            and worker['closed_ns'] <= request['deadline_ns'], 'worker_closure_contract')
    return worker


def closure_evidence(slot, closed, request, *, offline):
    worker = worker_closed(slot, closed, request)
    index = load(slot / 'native/WIRE/INDEX.json')
    require([row['sequence'] for row in index] == ([1, 2] if offline else [1, 2, 3, 4]),
            'actual_native_wire_call_order')
    diagnostic_seq = 1 if offline else 2
    wire_rows = []
    for row in index:
        sequence = row['sequence']
        path = slot / 'native/WIRE' / str(sequence).zfill(3)
        tx = path / 'REQUEST.bin'
        rx = path / 'RESPONSE.bin'
        require(row['response_sendall_completed'] and row['request_bytes'] == tx.stat().st_size
                and row['response_attempted_bytes'] == rx.stat().st_size
                and tx.stat().st_size + rx.stat().st_size == row['request_response_attempted_bytes'],
                'actual_tcp_wire_sizes_or_send')
        wire_rows.append({'sequence': sequence, 'request': identity(tx), 'response': identity(rx)})
        if sequence == diagnostic_seq:
            got = json.loads(tx.read_bytes())
            script = diagnostic_script(request)
            require(got == {'type': 'execute_code', 'params': {'code': script}}
                    and load(rx) == load(slot / 'DIAGNOSTIC_CLIENT.json')['response']
                    and digest(script.encode('utf8')) == load(slot / 'DIAGNOSTIC_RECEIPT.json')['script_sha256'],
                    'actual_diagnostic_tcp_outbound_or_inbound_binding')
        elif sequence == len(index):
            require(load(tx) == {'type': 'close'} and load(rx) == closed['response'], 'actual_close_wire_binding')
        else:
            filename = 'INITIAL_SOURCE.json' if sequence == 1 else 'TERMINAL_SOURCE.json'
            outer = load(slot / filename.replace('.json', '_CLIENT.json'))
            capture_request = {'type': 'execute_code', 'params': {
                'code': capture_script(inputs()[request['label']], slot / filename)}}
            require(load(tx) == capture_request and load(rx) == outer['response'],
                    'actual_independent_capture_wire_binding')
    audit = [json.loads(row) for row in (slot / 'native/WORKER_EVENTS.jsonl').read_bytes().splitlines()]
    diagnostic_events = [e for e in audit if e.get('sequence') == diagnostic_seq and e.get('status') == 'completed']
    require(len(diagnostic_events) == 1 and
            diagnostic_events[0]['script_sha256'] == load(slot / 'DIAGNOSTIC_RECEIPT.json')['script_sha256']
            and diagnostic_events[0]['render_events_before'] == diagnostic_events[0]['render_events_after'] == 0,
            'one_read_window_no_render_audit')
    return {'worker': worker, 'launcher': closed, 'wire': wire_rows, 'worker_events': audit}


def replay_worker(label, slot):
    require(slot == ROOT / 'preflight/replay' / label / 'slots' / label, 'name_registered_loopback_slot')
    case = inputs()[label]
    request = load(slot / 'BUSINESS_REQUEST.json')
    bind_request(request, case)
    script = diagnostic_script(request)
    archive = load(case['terminal']['path'])
    workspace = slot / 'native'
    receipt = workspace / 'REPLAY_READY.json'
    deadline = request['deadline_ns']
    with socket.socket() as server:
        server.bind(('127.0.0.1', 0))
        server.listen(1)
        save(receipt, {'host': '127.0.0.1', 'port': server.getsockname()[1], 'pid': os.getpid(),
                       'deadline_ns': deadline, 'original_terminal': case['terminal'],
                       'boundary': 'sealed arrays and synthesized RNA, no Blender started'}, replace=True)
        for sequence in (1, 2):
            check(deadline)
            server.settimeout(min(30, (deadline - perf_counter_ns()) / 1e9))
            connection, _ = server.accept()
            with meter.WireSocket(connection, sequence) as wire:
                started = perf_counter_ns()
                query = native._read_request(wire, deadline)
                if sequence == 1:
                    require(query == {'type': 'execute_code', 'params': {'code': script}},
                            'unregistered_loopback_script')
                    output = io.StringIO()
                    with contextlib.redirect_stdout(output):
                        exec(compile(script, '<registered-live-bounds-loopback>', 'exec'),
                             {'bpy': archive_as_bpy(archive)})
                    response = {'status': 'success', 'result': {'executed': True, 'result': output.getvalue()}}
                    event = {'sequence': sequence, 'status': 'completed',
                             'script_sha256': digest(script.encode('utf8')), 'started_ns': started,
                             'render_events_before': 0, 'render_events_after': 0}
                    native.append(workspace / 'WORKER_EVENTS.jsonl', event)
                else:
                    require(query == {'type': 'close'}, 'unregistered_loopback_close')
                    response = {'status': 'closed', 'pid': os.getpid(), 'deadline_ns': deadline}
                wire.sendall(encoded(response))
    meter.flush(workspace)
    fingerprint = sha(case['terminal']['path'])
    save(workspace / 'WORKER_CLOSED.json', {
        'pid': os.getpid(), 'closed_ns': perf_counter_ns(), 'poisoned': False,
        'original_deadline_ns': deadline, 'initial_geometry_fingerprint': fingerprint,
        'final_geometry_fingerprint': fingerprint, 'offline_fixture': True,
    })


def start_replay(label, slot, case, deadline):
    session = native.NativeSession()
    session.workspace = slot / 'native'
    session.workspace.mkdir(exist_ok=False)
    original = case['asset']['path']
    session.config = {'deadline_ns': deadline, 'asset': original, 'asset_copy': original,
                      'asset_sha256': case['asset']['sha256']}
    command = [str(PYTHON), '-IB', '-X', 'utf8', str(Path(__file__).resolve()), 'replay-worker', label]
    with (session.workspace / 'worker_stdout.txt').open('xb') as out, \
            (session.workspace / 'worker_stderr.txt').open('xb') as err:
        session.process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                           cwd=session.workspace, creationflags=subprocess.CREATE_NO_WINDOW)
    started = perf_counter_ns()
    path = session.workspace / 'REPLAY_READY.json'
    try:
        while not path.exists():
            require(session.process.poll() is None and perf_counter_ns() - started < 30 * 10**9,
                    'loopback_process_exited_or_timed_out')
            check(deadline)
            sleep(.01)
        handshake = load(path)
        require(handshake['pid'] == session.process.pid and handshake['deadline_ns'] == deadline
                and handshake['host'] == '127.0.0.1' and 1 <= handshake['port'] <= 65535
                and handshake['original_terminal'] == case['terminal'], 'loopback_real_owner_handshake')
        session.config.update({k: handshake[k] for k in ('pid', 'host', 'port')})
        return session
    except BaseException:
        session._kill()
        raise


class ReachedAppointment(RuntimeError):
    """Stop cold verification at the actual reservation boundary."""


class ReservationProbe:
    def __init__(self, budget):
        self.budget = budget

    def reserve(self, kind, label, phase):
        require((kind, phase) == ('Blender_start', 'formal') and label in LABELS,
                'cold_probe_wrong_reservation')
        snapshot = self.budget.snapshot()
        require(snapshot['counts']['Blender_start_attempts'] == 0
                and callable(self.budget.reserve), 'cold_budget_or_reservation_changed')
        raise ReachedAppointment(label)


def formal_budget(root=ROOT):
    module = import_file('live_bounds_budget', BUDGET)
    module.LIMITS = {'Blender_start_attempts': 2, 'all_rasters': 0, 'consumer_tasks': 0,
                     'tools_per_slot': 1, 'rasters_by_slot': dict.fromkeys(LABELS, 0)}
    return module.Budget(root / 'budget')


def start_live(label, slot, case, deadline, budget):
    require(sha(BLENDER) == BLENDER_SHA and slot.parent.name == 'slots' and slot.name == label,
            'real_owned_slot_inputs')
    reservation = budget.reserve('Blender_start', label, 'formal')
    try:
        session = native.NativeSession.start(
            blender=BLENDER, asset=Path(case['asset']['path']), workspace=slot / 'native',
            deadline_ns=deadline, condition='P', expected_asset_sha256=case['asset']['sha256'],
            max_calls=3,
        )
    except BaseException:
        spawn = slot / 'native/SPAWN.json'
        budget.settle_start(reservation, pid=load(spawn)['pid'] if spawn.exists() else None,
                            spawn_status='spawned' if spawn.exists() else 'no_spawn_receipt', outcome='failed')
        raise
    try:
        budget.settle_start(reservation, pid=session.process.pid, spawn_status='spawned', outcome='ready')
    except BaseException:
        session.close()
        raise
    return session


def frozen_targets():
    files = [Path(__file__), HERE / 'replay_rna.py', HERE / 'diagnostic.py', HERE / 'verify.py',
             HERE / 'controls.py', HERE / 'diagnostic_controls.py', HERE / 'prepare_inputs.py',
             HERE / 'seal.py', HERE / 'PLAN.md', ROOT / 'CONTROLS.json',
             ROOT / 'preflight/HOST_CONTROLS.json',
             VERIFY / 'm4_source_region_visual_scope_proof_001/proof.py',
             VERIFY / 'm4_source_region_visual_scope_proof_001/controls.py',
             ROOT / 'REQUESTS.json', ROOT / 'INPUT_CUSTODY.json', PRODUCT_BINDING, CAPTURE, BUDGET,
             NATIVE_ROOT / 'owned_native.py', NATIVE_ROOT / 'wire_meter.py', BLENDER, PYTHON]
    return [identity(path) for path in files]


def gate_record(path, value):
    if path.exists():
        require(load(path) == value, 'attempt_already_registered')
    else:
        save(path, value)


def verify_replay_result(label, path):
    result = load(path)
    require(result['offline'] and result['label'] == label and result['state'] == 'passed'
            and result['verified']['passed'] and not result['actual_blender_started'],
            'actual_valid_loopback_required:' + label)
    check_identity(result['publication'])
    publication = load(result['publication']['path'])
    request = load(Path(path).parent / 'BUSINESS_REQUEST.json')
    receipt = load(Path(path).parent / 'DIAGNOSTIC_RECEIPT.json')
    require(receipt['request'] == request and request['registered_requests_sha256'] == sha(ROOT / 'REQUESTS.json')
            and request['diagnostic_sha256'] == sha(HERE / 'diagnostic.py'),'stale_loopback_inputs')
    check_identity(receipt['diagnostic'])
    check_identity(receipt['raw_client'])
    check_identity(publication['request'])
    for pin in result['verified']['pins'].values():
        check_identity(pin)
    for row in publication['closure']['wire']:
        check_identity(row['request'])
        check_identity(row['response'])


def verify_frozen():
    freeze = load(ROOT / 'FREEZE.json')
    require(freeze['schema'] == 'human-eye-m4-live-bounds-freeze-v1' and
            freeze['files'] == frozen_targets(), 'frozen_runner_or_inputs_changed')
    for label, pin in zip(LABELS, freeze['replay'], strict=True):
        check_identity(pin)
        expected = ROOT / 'preflight/replay' / label / 'slots' / label / 'SLOT_RESULT.json'
        require(Path(pin['path']) == expected, 'unadmitted_valid_loopback')
        verify_replay_result(label, expected)
    return freeze


def run_slot(root, label, *, offline=False, cold=False):
    started = perf_counter_ns()
    deadline = started + SLOT_NS
    cases = inputs()
    case = cases[label]
    slot = root / 'slots' / label
    bind_product()
    request = make_request(case, deadline)
    bind_request(request, case)
    script = diagnostic_script(request)
    require(callable(native.NativeSession.start) and callable(native.NativeSession.close),
            'missing_real_owned_blender_entry')
    if cold:
        import verify
        verify_frozen()
        require(callable(verify.verify_slot), 'actual_cold_scorer_import')
        probe = ReservationProbe(formal_budget(ROOT / 'preflight/cold' / label))
        try:
            start_live(label, slot, case, deadline, probe)
        except ReachedAppointment as stop:
            require(str(stop) == label and not slot.exists(), 'cold_probe_started_or_wrong_label')
        else:
            raise ValueError('cold_probe_did_not_reach_real_launch')
        save(ROOT / 'preflight' / ('COLD_' + label + '.json'), {
            'schema': 'human-eye-m4-live-bounds-cold-preflight-v1', 'label': label,
            'reached': 'before Budget.reserve(Blender_start)', 'actual_blender_starts': 0,
            'registered_script_sha256': digest(script.encode('utf8')),
            'freeze': identity(ROOT / 'FREEZE.json'), 'request': request,
            'elapsed_ns': perf_counter_ns() - started, 'pid': os.getpid(),
        })
        return

    slot.mkdir(parents=True, exist_ok=False)
    save(slot / 'BUSINESS_REQUEST.json', request)
    session = None
    closed = None
    error = None
    captures = {}
    try:
        if offline:
            session = start_replay(label, slot, case, deadline)
        else:
            budget = formal_budget()
            session = start_live(label, slot, case, deadline, budget)
            captures['initial'] = independent_capture(session, slot, case, 'INITIAL_SOURCE.json')
            budget.admit_business(label, 'formal')
        execute_diagnostic(session, slot, request, script)
        if not offline:
            captures['terminal'] = independent_capture(session, slot, case, 'TERMINAL_SOURCE.json')
    except Exception as failure:
        error = {'type': type(failure).__name__, 'message': str(failure), 'traceback': traceback.format_exc()}
    finally:
        if session is not None:
            try:
                closed = session.close()
            except Exception as failure:
                if error is None:
                    error = {'type': type(failure).__name__, 'message': str(failure), 'traceback': traceback.format_exc()}

    closure = None
    safe_worker_closed = None
    if closed is not None:
        try:
            safe_worker_closed = worker_closed(slot, closed, request)
        except Exception:
            if error is None:
                error = {'type': 'ClosureError', 'message': 'worker_closure_contract',
                         'traceback': traceback.format_exc()}
    if error is None:
        try:
            closure = closure_evidence(slot, closed, request, offline=offline)
        except Exception as failure:
            error = {'type': type(failure).__name__, 'message': str(failure), 'traceback': traceback.format_exc()}
    receipt = {
        'schema': 'human-eye-m4-live-bounds-slot-publication-v1', 'label': label, 'offline': offline,
        'state': 'collected' if error is None else 'failed', 'error': error, 'captures': captures,
        'request': identity(slot / 'BUSINESS_REQUEST.json'), 'closure': closure,
        'launcher_close_receipt': closed, 'safe_worker_closed': safe_worker_closed,
        'started_ns': started, 'closed_ns': perf_counter_ns(), 'deadline_ns': deadline,
    }
    receipt['elapsed_ns'] = receipt['closed_ns'] - started
    save(slot / 'SLOT_PUBLICATION.json', receipt)

    verified = None
    if error is None:
        try:
            import verify
            verified = verify.verify_slot(slot, case, offline=offline)
            require(verified['passed'] is True, 'independent_scorer_did_not_pass')
            check(deadline)
        except Exception as failure:
            error = {'type': type(failure).__name__, 'message': str(failure), 'traceback': traceback.format_exc()}
    result = {'schema': 'human-eye-m4-live-bounds-slot-result-v1', 'label': label, 'offline': offline,
              'state': 'passed' if error is None else 'failed', 'error': error, 'verified': verified,
              'publication': identity(slot / 'SLOT_PUBLICATION.json'), 'started_ns': started,
              'closed_ns': perf_counter_ns(), 'deadline_ns': deadline, 'actual_blender_started': not offline
              and (slot / 'native/SPAWN.json').exists(), 'models': 0, 'rasters': 0}
    result['elapsed_ns'] = result['closed_ns'] - started
    save(slot / 'SLOT_RESULT.json', result)
    if error is not None:
        print(json.dumps(error, ensure_ascii=False))
        return False
    print(label + ' pass ' + str(slot))
    return True


def check_offline_controls():
    host_controls = load(ROOT / 'preflight/HOST_CONTROLS.json')
    require(host_controls['passed'] and host_controls['diagnostic_sha256'] == sha(HERE / 'diagnostic.py')
            and host_controls['installed_host_sha256'] == sha(PRODUCT / 'human_eye_plugin/blender_host.py')
            and host_controls['live_Blender'] == host_controls['models'] == 0, 'stale_host_controls')
    semantic_controls = load(ROOT / 'CONTROLS.json')
    require(semantic_controls['passed'] and semantic_controls['real_Blender'] == semantic_controls['models'] == 0,
            'missing_semantic_controls')
    for pin in semantic_controls['source_pins']:
        check_identity(pin)


def freeze():
    inputs()
    check_offline_controls()
    bind_product(full=True)
    pins = []
    for label in LABELS:
        result = ROOT / 'preflight/replay' / label / 'slots' / label / 'SLOT_RESULT.json'
        verify_replay_result(label, result)
        pins.append(identity(result))
    gate_record(ROOT / 'FREEZE.json', {'schema': 'human-eye-m4-live-bounds-freeze-v1',
                'files': frozen_targets(), 'replay': pins, 'formal_order': list(LABELS)})


def formal():
    verify_frozen()
    bind_product(full=True)
    for label in LABELS:
        cold = load(ROOT / 'preflight' / ('COLD_' + label + '.json'))
        require(cold['freeze'] == identity(ROOT / 'FREEZE.json') and cold['label'] == label
                and cold['actual_blender_starts'] == 0
                and cold['reached'] == 'before Budget.reserve(Blender_start)', 'cold_actual_entry_needed')
    save(ROOT / 'FORMAL_START.json', {'freeze': identity(ROOT / 'FREEZE.json'), 'order': list(LABELS),
                'pid': os.getpid(), 'started_ns': perf_counter_ns()})
    results = {}
    for label in LABELS:
        try:
            passed = run_slot(ROOT, label)
        except Exception:
            passed = False
            save(ROOT / (label + '_EARLY_FAILURE.json'), {'traceback': traceback.format_exc()})
        results[label] = 'passed' if passed else 'failed'
        if label == 'RAIL' and not passed:
            publication = ROOT / 'slots' / label / 'SLOT_PUBLICATION.json'
            if not publication.is_file() or load(publication)['safe_worker_closed'] is None:
                results['ASSEMBLY'] = 'unrun'
                break
    save(ROOT / 'FORMAL_END.json', {'results': results, 'closed_ns': perf_counter_ns(),
                'budget': formal_budget().snapshot()})
    return all(results.get(label) == 'passed' for label in LABELS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True)
    for name in ('replay', 'replay-worker', 'cold'):
        actions.add_parser(name).add_argument('label', choices=LABELS)
    for name in ('freeze', 'formal'):
        actions.add_parser(name)
    args = parser.parse_args()
    require_interpreter()
    if args.action == 'replay':
        return 0 if run_slot(ROOT / 'preflight/replay' / args.label, args.label, offline=True) else 1
    if args.action == 'replay-worker':
        replay_worker(args.label, ROOT / 'preflight/replay' / args.label / 'slots' / args.label)
    elif args.action == 'freeze':
        freeze()
    elif args.action == 'cold':
        run_slot(ROOT, args.label, cold=True)
    elif args.action == 'formal':
        return 0 if formal() else 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())





