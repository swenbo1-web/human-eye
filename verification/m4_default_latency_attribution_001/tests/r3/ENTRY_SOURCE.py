"""Four fixed OFF-business sessions with a sequence-bound QA profiler switch."""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import time
import traceback
import types


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
ACTOR = ROOT / 'verification/m1_task_entry_001_eval/actor.py'
CLIENT = ROOT / 'verification/m1_task_entry_001_eval/preflight_client.py'
CYCLE = 'M4-DEFAULT-LATENCY-ATTRIBUTION-001'
BLENDER = 'D:/Tools/blender5.2/blender.exe'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def save(path, value):
    with Path(path).open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def load(name, path):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(Path(path).read_bytes(), str(path), 'exec', dont_inherit=True), module.__dict__)
    return module


def events(path):
    return [json.loads(line) for line in path.read_bytes().splitlines() if line] if path.exists() else []


def verify_commit(commit, paths):
    began = time.perf_counter_ns()
    assert len(commit) == 40 and all(char in '0123456789abcdef' for char in commit)
    checked = {}
    for relative in paths:
        blob = subprocess.run(['git', '-C', str(ROOT), 'show', commit + ':' + relative],
                              check=True, capture_output=True, timeout=30).stdout
        assert blob == (ROOT / relative).read_bytes(), 'source_not_in_frozen_commit: ' + relative
        checked[relative] = sha(blob)
    return {'commit': commit, 'files_sha256': checked, 'elapsed_ns': time.perf_counter_ns() - began}


def reserve(session, folder):
    ledger = HERE / 'OWNED_STARTS.jsonl'
    previous = events(ledger)
    assert len(previous) < 4, 'four_start_limit_no_replacement'
    row = {'ordinal': len(previous) + 1, 'session': session['id'], 'version': session['version'],
           'folder': str(folder), 'reserved_ns': time.perf_counter_ns()}
    with ledger.open('a', encoding='utf8', newline='\n') as stream:
        stream.write(json.dumps(row, sort_keys=True) + '\n')
    return row


def check_profile(event, planned):
    state = event['qa_work']
    assert event['sequence'] == state['worker_sequence'] == planned['sequence']
    assert state['profile_enabled'] is planned['profile_enabled']
    assert state['previous_profile_enabled'] is planned['previous_profile_enabled']
    assert state['errors'] == [] and state['profile_initial_present'] is False
    assert state['profile_restored_to_initial'] is True and state['profile_after_restore_present'] is False
    enabled = planned['profile_enabled']
    assert state['profile_install_attempted'] is enabled and state['profile_installed'] is enabled
    assert state['profile_actual_enabled'] is enabled
    assert state['profile_restore_attempted'] is enabled and state['profile_restore_succeeded'] is enabled
    assert state['callback_counts_status'] == ('collected' if enabled else 'not_collected')
    for key in ('python_calls', 'C_calls', 'C_returns', 'C_exceptions'):
        assert type(state[key]) is dict if enabled else state[key] is None
    return state


def business(row, peer, native, folder, template, expected_source, reference, generation, deadline):
    request = copy.deepcopy(template)
    request['id'] = row['label']
    save(folder / (row['label'] + '.REQUEST.json'), request)
    row['started_ns'] = time.perf_counter_ns()
    try:
        response = peer.call(request)
    finally:
        row['ended_ns'] = time.perf_counter_ns()
        row['entry_elapsed_ns'] = row['ended_ns'] - row['started_ns']
        if peer.records and peer.records[-1]['request_id'] == row['label']:
            row['stdio'] = copy.deepcopy(peer.records[-1])
    verify_began = time.perf_counter_ns()
    try:
        save(folder / (row['label'] + '.RESPONSE.json'), response)
        received = events(native.workspace / 'WORKER_EVENTS.jsonl')
        assert len(received) == row['sequence'], 'unexpected_or_missing_worker_RPC'
        event = received[-1]
        row['worker_received_RPC_count'] = 1
        row['worker_received_events'] = [event]
        assert row['started_ns'] <= event['started_ns'] <= row['ended_ns']
        assert event['status'] == 'completed' and event['terminal_geometry_and_file_checks_passed']
        qa = check_profile(event, row)
        assert response['result']['isError'] is False
        body = json.loads(response['result']['content'][0]['text'])
        row['body'] = body
        assert body['status'] == 'observed' and body['execution_authority'] is False and 'geometry' not in body
        assert body['context']['runtime_source_sha256'] == expected_source
        current = {key: value for key, value in body.items() if key != 'trace_id'}
        if reference is not None:
            assert current == reference, 'same_session_facts_or_source_changed'
        assert len(qa['after']['hosts']) == 1
        current_generation = qa['after']['hosts'][0]['generation']
        if generation is not None:
            assert current_generation == generation, 'capture_generation_changed'
        trace = None
        while trace is None:
            audit = events(folder / 'audit.jsonl')
            matched = [item['trace'] for item in audit if item.get('event') == 'request_trace'
                       and item['trace']['annotations'].get('mcp_request_id') == row['label']]
            assert len(matched) <= 1
            if matched:
                trace = matched[0]
                observed = [item['task_work'] for item in audit if item.get('event') == 'observe']
                assert len(observed) == row['sequence']
                row['task_work'] = observed[-1]
                row['request_trace'] = trace
                break
            if time.perf_counter_ns() >= min(deadline, row['started_ns'] + 30 * 10**9):
                raise TimeoutError('original_request_trace_validation_window')
            time.sleep(.001)
        row['successful_normalize_hash_spans'] = sum(span['name'] == 'scene.hash'
            and span['outcome'] == 'completed' for span in trace['spans'])
        cold = row['phase'] == 'cold'
        assert row['task_work']['result_cache_hit'] is (not cold)
        assert row['successful_normalize_hash_spans'] == (1 if cold else 0)
        for key in ('to_mesh', 'triangulations', 'world_transforms', 'resource_builds'):
            assert key in qa['host_residency_delta']
            assert qa['host_residency_delta'][key] == (4 if cold else 0)
        if not cold:
            assert all(row['task_work'][key] == 0 for key in
                       ('exact_pair_count', 'surface_pair_count', 'closed_solid_pair_count'))
        if row['profile_enabled']:
            assert qa['python_calls'].get('capture_task_scene', 0) == 1
        row['status'] = 'completed'
        return current, current_generation
    finally:
        row['verification_elapsed_ns'] = time.perf_counter_ns() - verify_began
        row['request_with_checks_ns'] = time.perf_counter_ns() - row['started_ns']


def run_case(session, ready, work, template, folder, peer_class, native_class, client):
    began = time.perf_counter_ns()
    folder.mkdir(parents=True, exist_ok=False)
    case = {'case': {'id': session['id'], 'version': session['version']},
            'id': session['id'], 'version': session['version'], 'rows': [], 'errors': [],
            'started_ns': began, 'timing_stages_ns': {}, 'product_close': None, 'native_close': None}
    stages = case['timing_stages_ns']
    native = peer = runtime_handle = None
    deadline = began + 570 * 10**9
    try:
        case['start_reservation'] = reserve(session, folder)
        stage = time.perf_counter_ns()
        modes = [row['profile_enabled'] for row in session['business']] + [False]
        native = native_class.start(blender=BLENDER, asset=ROOT / work['asset'], workspace=folder / 'native',
            deadline_ns=deadline, condition='P', expected_asset_sha256=work['asset_sha256'],
            max_calls=128, qa_profile_schedule=modes)
        stages['native_startup'] = time.perf_counter_ns() - stage
        config = {'schema_version': '1.0', 'enabled': True, 'observe_on_prompt': False,
                  'project_root': ready['install_root'], 'state_file': str(folder / 'state.json'),
                  'audit_file': str(folder / 'audit.jsonl'), 'request_budget_s': 30.,
                  'expected_identity': {'source_sha256': ready['source_sha256']},
                  'blender': {'host': native.host, 'port': native.port, 'timeout_s': 30.}}
        save(folder / 'product_config.json', config)
        stage = time.perf_counter_ns()
        peer = peer_class(dict(ready, group='S', product_config=folder / 'product_config.json'), folder / 'product')
        stages['product_startup'] = time.perf_counter_ns() - stage
        stage = time.perf_counter_ns()
        initialized = peer.call({'jsonrpc': '2.0', 'id': 'init', 'method': 'initialize', 'params': {
            'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'default-latency-QA', 'version': '001'}}})
        identity = initialized['result']['_meta']['human_eye']
        assert identity['source_sha256'] == ready['source_sha256'] and identity['source_kind'] == 'installed_distribution'
        assert identity['distribution_version'] == ready['version']
        save(folder / 'ACTUAL_INITIALIZE.json', initialized)
        peer.call({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        listing = peer.call({'jsonrpc': '2.0', 'id': 'list', 'method': 'tools/list'})
        save(folder / 'ACTUAL_TOOLS.json', listing)
        assert {tool['name'] for tool in listing['result']['tools']} == {'human_eye_spatial_relations', 'human_eye_surface_nearest'}
        assert peer.call({'jsonrpc': '2.0', 'id': 'ping', 'method': 'ping'})['result'] == {}
        assert len(peer.records) == 4 and events(native.workspace / 'WORKER_EVENTS.jsonl') == []
        stages['metadata'] = time.perf_counter_ns() - stage
        stage = time.perf_counter_ns()
        startup_pids = {item['trace']['pid'] for item in events(folder / 'audit.jsonl')
                        if item.get('event') == 'request_trace'}
        assert len(startup_pids) == 1
        proof, runtime_handle = client._windows_runtime_proof(peer.process, startup_pids.pop(), deadline)
        save(folder / 'PRODUCT_RUNTIME_PROOF.json', proof)
        assert proof['confirmed'] is True
        stages['product_PID_proof'] = time.perf_counter_ns() - stage
        reference = generation = None
        stage = time.perf_counter_ns()
        for planned in session['business']:
            row = dict(planned, label=planned['request_id'], status='attempted')
            case['rows'].append(row)
            reference, generation = business(row, peer, native, folder, template,
                                             ready['source_sha256'], reference, generation, deadline)
        stages['business_loop'] = time.perf_counter_ns() - stage
    except BaseException as exc:
        case['errors'].append({'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()})
    finally:
        stage = time.perf_counter_ns()
        if peer is not None:
            try:
                case['product_close'] = peer.close()
            except BaseException as exc:
                case['errors'].append({'stage': 'product_close', 'error': repr(exc)})
        stages['product_close'] = time.perf_counter_ns() - stage
        stage = time.perf_counter_ns()
        try:
            case['product_runtime_exit'] = client._runtime_exit(runtime_handle)
            if runtime_handle is not None:
                actual_exit = case['product_runtime_exit']
                if (actual_exit['confirmed'] is not True or actual_exit['exited'] is not True
                        or actual_exit['exit_code'] != 0 or actual_exit['handle_closed'] is not True):
                    case['errors'].append({'stage': 'actual_product_exit', 'error': 'unconfirmed_or_nonzero_or_handle_cleanup_failed'})
        except BaseException as exc:
            case['product_runtime_exit'] = {'confirmed': False, 'error': repr(exc)}
            case['errors'].append({'stage': 'actual_product_exit', 'error': repr(exc)})
        stages['runtime_exit_proof'] = time.perf_counter_ns() - stage
        stage = time.perf_counter_ns()
        if native is not None:
            try:
                case['native_close'] = native.close()
                closed = native.status()['closed']
                case['worker_closed'] = closed
                assert closed and not closed['poisoned']
                assert closed['pid'] == native.ready['pid'] == native.process.pid
                assert closed['final_geometry_fingerprint'] == closed['initial_geometry_fingerprint']
                assert case['native_close']['response']['status'] == 'closed' and case['native_close']['error'] is None
                assert case['native_close']['exit_code'] == 0 and case['native_close']['process_reaped']
                assert case['native_close']['source_file_unchanged'] and case['native_close']['protected_files_unchanged']
                received = events(native.workspace / 'WORKER_EVENTS.jsonl')
                case['all_worker_events'] = received
                assert len(received) == 23
                check_profile(received[-1], session['close'])
            except BaseException as exc:
                case['errors'].append({'stage': 'native_close_or_sequence', 'error': repr(exc)})
            try:
                case['all_worker_events'] = events(native.workspace / 'WORKER_EVENTS.jsonl')
            except BaseException as exc:
                case['errors'].append({'stage': 'worker_record_read', 'error': repr(exc)})
        stages['native_close'] = time.perf_counter_ns() - stage
        stages['verification'] = sum(row.get('verification_elapsed_ns', 0) for row in case['rows'])
        case['ended_ns'] = time.perf_counter_ns()
        case['session_wall_ns'] = case['ended_ns'] - began
        case['within_570s'] = case['session_wall_ns'] < 570 * 10**9
        case['passed'] = bool(not case['errors'] and case['within_570s'] and len(case['rows']) == 22
                              and all(row['status'] == 'completed' for row in case['rows'])
                              and case['product_close'] and case['product_close']['confirmed']
                              and case['product_runtime_exit']['confirmed'] is True and case['native_close'])
        save(folder / 'RESULTS.json', case)
    return case


def main():
    began = time.perf_counter_ns()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--frozen-commit', required=True)
    args = parser.parse_args()
    assert Path(args.output).name == args.output and args.output not in ('.', '..')
    bindings = read(BATCH / 'preparation/INPUT_BINDINGS.json')
    frozen = verify_commit(args.frozen_commit, bindings['critical_git_paths'])
    for name, digest in bindings['source_files_sha256'].items():
        assert sha((ROOT / name).read_bytes()) == digest
    work = read(BATCH / 'WORK_ORDER.json')
    schedule = read(BATCH / 'SCHEDULE.json')
    verifier = load('_attribution_read_only_inputs', BATCH / 'preparation/verify_inputs.py')
    verified = verifier.verify()
    output = HERE / args.output
    output.mkdir(exist_ok=False)
    save(output / 'VALIDATED_INPUTS.json', verified)
    save(output / 'FROZEN_COMMIT.json', frozen)
    actor = load('_attribution_original_peer', ACTOR)
    helper = load('_attribution_owned_native', HERE / 'qa_native.py')
    client = load('_attribution_runtime_proof', CLIENT)
    cases = []
    stop = None
    for session in schedule['sessions']:
        case = run_case(session, verified['versions'][session['version']], work,
                        schedule['request_template'], output / session['id'], actor.Peer, helper.NativeSession, client)
        cases.append(case)
        save(output / ('RESULTS_AFTER_' + str(len(cases)) + '.json'), {'cases': cases})
        if not case['passed']:
            stop = 'fixed_matrix_stopped_after_failed_session; no replacement'
            break
    source_checks = {name: sha((ROOT / name).read_bytes()) == digest
                     for name, digest in bindings['source_files_sha256'].items()}
    installed_checks = {name: sha(Path(name).read_bytes()) == digest
                        for name, digest in verified['checked_files_sha256'].items()}
    ended = time.perf_counter_ns()
    passed = len(cases) == 4 and all(case['passed'] for case in cases) and all(source_checks.values()) and all(installed_checks.values())
    save(output / 'RESULTS.json', {'cycle_id': CYCLE, 'cases': cases, 'passed': passed, 'stop': stop,
        'planned_sessions': 4, 'started_sessions': len(cases), 'not_run_sessions': schedule['sessions'][len(cases):],
        'source_checks': source_checks, 'installed_checks': installed_checks,
        'batch_started_ns': began, 'batch_ended_ns': ended, 'batch_wall_ns': ended - began,
        'preparation_verification_elapsed_ns': verified['verification_elapsed_ns'],
        'frozen_commit_verification_ns': frozen['elapsed_ns'],
        'batch_timing_scope': 'main entry through final source checks; includes setup, per-call validation and cleanup, excludes final result publication and interpreter import',
        'model_consumers': 0, 'images': 0, 'new_installations': 0})
    print(json.dumps({'passed': passed, 'started_sessions': len(cases), 'output': str(output)}))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
