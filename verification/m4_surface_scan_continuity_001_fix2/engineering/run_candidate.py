"""Collect one FIX2 C episode, close it once, then qualify frozen records."""

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import time
import traceback


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
FIX1 = ROOT / 'verification/m4_surface_scan_continuity_001_fix1'
QUAL = ROOT / 'verification/m4_surface_scan_001/qualification'
TURNS = ('BASE', 'REPEAT', 'EDIT')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(path):
    return json.loads(path.read_bytes())


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n', encoding='utf8', newline='\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_deadline(deadline):
    if time.perf_counter_ns() >= deadline:
        raise TimeoutError('original_episode_590s_deadline')


def error_record(error, stage):
    return {'stage': stage, 'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}


def backend_identity(status):
    return {key: status[key] for key in ('episode_id', 'owner_pid', 'native_pid', 'native_host',
            'native_port', 'native_workspace', 'product_launcher_pid', 'product_runtime_proof',
            'session_id', 'worker_deadline_ns')}


def business_request(group, turn):
    assert group == 'C'
    return {'jsonrpc': '2.0', 'id': group + '-' + turn, 'method': 'tools/call',
            'params': {'name': 'human_eye_scene_observe', 'arguments': {
                'session_id': 'continuity-fix2-engineering-C-001', 'include_image': False,
                'query': {'mode': 'surface_scan', 'threshold_m': .002}}}}


def validate_online_body(body):
    """Check explicit completion only; geometric qualification occurs after close."""
    assert type(body) is dict, 'online_observe_body_object'
    assert body.get('result_kind') == 'surface_scan' and body.get('status') == 'complete', 'online_observe_not_complete'
    coverage = body.get('coverage')
    assert type(coverage) is dict, 'online_coverage_object'
    assert all(type(coverage.get(key)) is int and coverage[key] == 0 for key in ('unknown', 'deferred')), 'online_coverage_unresolved'
    assert coverage.get('catalog_scope_confirmed') is True, 'online_catalog_scope_unconfirmed'
    assert all(body.get(key) == [] for key in ('scope_issues', 'unsupported_objects', 'unresolved')), 'online_scope_unresolved'
    delivery = body.get('delivery')
    assert type(delivery) is dict and delivery.get('complete') is True, 'online_delivery_incomplete'


def verify_business(row, folder, source, qualification):
    """Qualify one original business interval using the closed worker's WIRE."""
    body = json.loads(row['response']['result']['content'][0]['text'])
    audit = [json.loads(line) for line in (folder / 'owner/audit.jsonl').read_bytes().splitlines()]
    events = [json.loads(line) for line in (folder / 'owner/native/WORKER_EVENTS.jsonl').read_bytes().splitlines()]
    host = [item for item in events if type(item.get('started_ns')) is int
            and row['started_ns'] <= item['started_ns'] <= row['ended_ns']]
    for event in host:
        assert type(event.get('elapsed_ns')) is int and event['elapsed_ns'] > 0, 'host_event_positive_elapsed_required'
        assert event['started_ns'] + event['elapsed_ns'] <= row['ended_ns'], 'host_event_outside_original_business_window'
    assert len(host) == 1, 'single_capture_in_original_business_window'
    capture = qualification.read_capture(folder / 'owner/native', host[0])
    return qualification.verify_c_turn(body, audit, host, source, row['turn'], row['request'], capture=capture)


def verify_terminal_wire(folder):
    wire = folder / 'owner/native/WIRE'
    index = read(wire / 'INDEX.json')
    assert type(index) is list and bool(index), 'terminal_WIRE_index_required'
    assert [row['sequence'] for row in index] == list(range(1, len(index) + 1)), 'terminal_WIRE_sequence'
    last_request = last_response = None
    for row in index:
        sequence = row['sequence']
        assert type(sequence) is int and row['response_sendall_completed'] is True, 'terminal_WIRE_send_unconfirmed'
        request_raw = (wire / str(sequence).zfill(3) / 'REQUEST.bin').read_bytes()
        response_raw = (wire / str(sequence).zfill(3) / 'RESPONSE.bin').read_bytes()
        assert type(row['request_bytes']) is int and row['request_bytes'] == len(request_raw) > 0, 'terminal_WIRE_request_size'
        assert type(row['response_attempted_bytes']) is int and row['response_attempted_bytes'] == len(response_raw) > 0, 'terminal_WIRE_response_size'
        assert row['request_response_attempted_bytes'] == len(request_raw) + len(response_raw), 'terminal_WIRE_total_size'
        last_request, last_response = json.loads(request_raw), json.loads(response_raw)
    assert last_request.get('type') == 'close' and last_response.get('status') == 'closed', 'terminal_WIRE_close_frame'
    return {'passed': True, 'frames': len(index), 'complete_sendall': True, 'closed_frame_verified': True}


def qualify_after_finish(result, folder, sources, qualification, deadline):
    """Read terminal artifacts only after the sole finish has been confirmed."""
    result['qualification_started_ns'] = time.perf_counter_ns()
    try:
        check_deadline(deadline)
        assert result.get('cleanup', {}).get('confirmed') is True, 'qualification_requires_confirmed_finish'
        result['terminal_wire_verification'] = verify_terminal_wire(folder)
        check_deadline(deadline)
        reports = []
        for row in result['business']:
            if row['execution_state'] != 'succeeded':
                continue
            check_deadline(deadline)
            row['qualification_started_ns'] = time.perf_counter_ns()
            try:
                report = verify_business(row, folder, sources[row['state']], qualification)
                row['verification'] = report
                assert type(report) is dict and report.get('passed') is True, 'business_qualification_not_passed'
                check_deadline(deadline)
                row['qualification_state'] = 'passed'
                reports.append(report)
            except BaseException as error:
                row['qualification_state'] = 'failed'
                row['qualification_errors'].append(error_record(error, 'business_qualification'))
            finally:
                row['qualification_ended_ns'] = time.perf_counter_ns()
                save(folder / ('TURN_' + row['turn'] + '.json'), row)
        if len(reports) == 3 and all(row['qualification_state'] == 'passed' for row in result['business']):
            check_deadline(deadline)
            result['sequence_qualification_started_ns'] = time.perf_counter_ns()
            try:
                result['sequence_verification'] = qualification.verify_c_sequence(reports)
                assert result['sequence_verification'].get('passed') is True, 'sequence_qualification_not_passed'
                check_deadline(deadline)
                result['sequence_qualification_state'] = 'passed'
            except BaseException as error:
                result['sequence_qualification_state'] = 'failed'
                result['qualification_errors'].append(error_record(error, 'sequence_qualification'))
            finally:
                result['sequence_qualification_ended_ns'] = time.perf_counter_ns()
    except BaseException as error:
        result['qualification_errors'].append(error_record(error, 'postclose_qualification'))
    finally:
        result['qualification_ended_ns'] = time.perf_counter_ns()
        result['stages_ns']['qualification'] = result['qualification_ended_ns'] - result['qualification_started_ns']


def publish_result(result, folder, deadline):
    """Publish execution and qualification separately, retaining publication errors."""
    business = result['business']
    result['execution_counts'] = {
        'planned': 3, 'attempted': len(business),
        'successful_returns': sum(row['successful_return'] for row in business),
        'succeeded': sum(row['execution_state'] == 'succeeded' for row in business),
        'failed': sum(row['execution_state'] == 'failed' for row in business),
        'not_run': 3 - len(business),
    }
    result['qualification_counts'] = {
        'planned': 3,
        'passed': sum(row['qualification_state'] == 'passed' for row in business),
        'failed': sum(row['qualification_state'] == 'failed' for row in business),
        'unverified': 3 - sum(row['qualification_state'] in ('passed', 'failed') for row in business),
    }
    result['passed_before_publication'] = bool(not result['errors'] and not result['qualification_errors']
        and result['asset_unchanged'] and result.get('cleanup', {}).get('confirmed') is True
        and result['execution_counts']['succeeded'] == 3 and result['qualification_counts']['passed'] == 3
        and result['sequence_qualification_state'] == 'passed' and time.perf_counter_ns() < deadline)
    result['publication_errors'] = []
    try:
        save(folder / 'RESULTS.json', result)
    except BaseException as error:
        result['publication_errors'].append(error_record(error, 'RESULTS_publication'))
    closed = time.perf_counter_ns()
    timing = {'started_ns': result['started_ns'], 'business_receipts_closed_ns': closed,
              'full_episode_wall_ns': closed - result['started_ns'], 'original_deadline_ns': deadline,
              'within_590s': closed < deadline,
              'accepted_success': result['passed_before_publication'] and not result['publication_errors'] and closed < deadline,
              'publication_errors': result['publication_errors'],
              'scope': 'Input checks, startup, three thin lifecycles, pose/QA, sole finish, postclose qualification and RESULTS write/close',
              'durability': 'Buffered write and close; fsync of these reports unmeasured'}
    publication_started = time.perf_counter_ns()
    try:
        save(folder / 'FINAL_TIMING.json', timing)
    except BaseException as error:
        result['publication_errors'].append(error_record(error, 'FINAL_TIMING_publication'))
        timing['accepted_success'] = False
    publication_closed = time.perf_counter_ns()
    try:
        save(folder / 'TIMING_PUBLICATION.json', {'started_ns': publication_started, 'closed_ns': publication_closed,
             'scope': 'FINAL_TIMING publication; this receipt publication is separate'})
    except BaseException as error:
        result['publication_errors'].append(error_record(error, 'TIMING_PUBLICATION_receipt'))
        timing['accepted_success'] = False
    if result['publication_errors']:
        timing['accepted_success'] = False
        try:
            save(folder / 'FINAL_TIMING.json', timing)
        except BaseException as error:
            result['publication_errors'].append(error_record(error, 'failed_FINAL_TIMING_correction'))
        try:
            save(folder / 'PUBLICATION_ERROR.json', {'errors': result['publication_errors'], 'accepted_success': False,
                'execution_counts': result['execution_counts'], 'qualification_counts': result['qualification_counts']})
        except BaseException:
            pass
    return timing


def run_episode(group, frozen, transport, attach, qualification, driver):
    assert group == 'C'
    folder = BATCH / 'episodes' / group
    folder.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter_ns()
    deadline = started + 590 * 10**9
    result = {'group': group, 'episode_id': 'continuity-fix2-engineering-C-001',
              'started_ns': started, 'deadline_ns': deadline, 'business': [], 'administrative': [],
              'errors': [], 'qualification_errors': [], 'sequence_qualification_state': 'unverified',
              'model_calls': 0, 'API_calls': 0, 'automatic_retries': 0, 'usage': None,
              'usage_scope': 'No model consumer; no usage event exists.', 'stages_ns': {},
              'same_thread_model_continuity': 'not_measured'}
    process = None
    sources = {}
    episode = result['episode_id']

    def admin(operation, **params):
        check_deadline(deadline)
        row = {'request': {'jsonrpc': '2.0', 'id': 'admin-' + str(len(result['administrative']) + 1),
               'method': 'continuity/' + operation, 'params': {'episode_id': episode, **params}},
               'started_ns': time.perf_counter_ns()}
        result['administrative'].append(row)
        try:
            row['response'] = attach.attach(read(folder / 'ENDPOINT.json'), 'native', row['request'])
            assert 'error' not in row['response'], row['response']
            return row['response']['result']
        finally:
            row['ended_ns'] = time.perf_counter_ns()
            save(folder / ('ADMIN_' + str(len(result['administrative'])).zfill(2) + '.json'), row)

    try:
        check_deadline(deadline)
        ready = read(BATCH / 'inputs/C_READY.json')
        config = {'group': 'P', 'external_group': group, 'task': 'T1', 'episode_id': episode, 'session_id': episode,
                  'output': str(folder / 'owner'), 'endpoint': str(folder / 'ENDPOINT.json'),
                  'asset': str(QUAL / 'assembly.blend'), 'asset_sha256': frozen['scene_sha256'],
                  'blender': 'D:/Tools/blender5.2/blender.exe', 'worker_deadline_ns': deadline,
                  'dependency_python': ready['dependency_python'], 'read_schemas': read(BATCH / 'inputs/C_PUBLIC_TOOLS.json'),
                  'entry': ready['entry'], 'install_root': ready['install_root'], 'source_sha256': ready['source_sha256']}
        save(folder / 'ACTOR_CONFIG.json', config)
        command = [ready['dependency_python'], '-I', '-B', '-X', 'utf8', str(FIX1 / 'runtime/actor.py'), '--config', str(folder / 'ACTOR_CONFIG.json')]
        startup_deadline = min(deadline, time.perf_counter_ns() + 40 * 10**9)
        with (folder / 'actor_stdout.bin').open('wb') as stdout, (folder / 'actor_stderr.bin').open('wb') as stderr:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        save(folder / 'ACTOR_LAUNCH.json', {'pid': process.pid, 'argv': command, 'started_ns': started,
                                          'deadline_ns': deadline, 'startup_deadline_ns': startup_deadline})
        while not (folder / 'ENDPOINT.json').exists():
            assert process.poll() is None, 'actor_startup_failed'
            check_deadline(startup_deadline)
            time.sleep(.02)
        result['stages_ns']['startup'] = time.perf_counter_ns() - started
        endpoint_before = read(folder / 'ENDPOINT.json')
        initial = admin('status')
        result['initial_status'] = initial
        sources['BASE'] = read(folder / 'owner/INITIAL.json')
        driver.snapshot_binding(sources['BASE'], read(QUAL / 'BASE_SNAPSHOT.json'))
        previous_end = time.perf_counter_ns()
        for turn in TURNS:
            check_deadline(deadline)
            if turn == 'EDIT':
                mark = time.perf_counter_ns()
                result['registered_pose'] = admin('qa_advance')
                sources['EDIT'] = result['registered_pose']['snapshot']
                driver.snapshot_binding(sources['EDIT'], read(QUAL / 'EDIT_SNAPSHOT.json'))
                result['stages_ns']['registered_pose_and_readback'] = time.perf_counter_ns() - mark
            before = admin('status')
            assert backend_identity(before) == backend_identity(initial), 'backend_identity_changed'
            assert before['owner_close_called'] is False
            assert read(folder / 'ENDPOINT.json') == endpoint_before, 'endpoint_changed'
            admin('begin_turn', turn_id=turn, deadline_ns=deadline)
            request = business_request(group, turn)
            row = {'turn': turn, 'state': 'EDIT' if turn == 'EDIT' else 'BASE', 'request': request,
                   'waiting_and_barrier_before_turn_ns': time.perf_counter_ns() - previous_end,
                   'status_before': before, 'started_ns': time.perf_counter_ns(), 'ended_ns': None,
                   'errors': [], 'execution_state': 'attempted', 'successful_return': False,
                   'qualification_state': 'unverified', 'qualification_errors': []}
            result['business'].append(row)
            requests = [
                {'jsonrpc': '2.0', 'id': 'init-' + turn, 'method': 'initialize', 'params': {'protocolVersion': '2025-03-26',
                 'capabilities': {}, 'clientInfo': {'name': 'continuity-engineering-stub', 'version': '001'}}},
                {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                {'jsonrpc': '2.0', 'id': 'list-' + turn, 'method': 'tools/list'}, request]
            try:
                try:
                    row['thin'] = transport.thin_turn(python=ready['dependency_python'], endpoint=folder / 'ENDPOINT.json',
                        folder=folder / turn, requests=requests, deadline_ns=deadline)
                finally:
                    row['ended_ns'] = time.perf_counter_ns()
                thin = row['thin']
                answer = next(value for value in thin['responses'] if value.get('id') == request['id'])
                row['response'] = answer
                assert 'error' not in answer and type(answer.get('result')) is dict, 'online_RPC_error'
                assert not answer['result'].get('isError'), 'online_tool_error'
                row['body'] = json.loads(answer['result']['content'][0]['text'])
                validate_online_body(row['body'])
                row['successful_return'] = True
                assert thin['confirmed'], thin
                row['status_after'] = admin('end_turn', turn_id=turn)
                assert backend_identity(row['status_after']) == backend_identity(initial), 'backend_identity_changed'
                assert row['status_after']['owner_close_called'] is False
                assert row['status_after']['business_attempts'] == len(result['business'])
                assert row['status_after']['completed_turns'][-1]['business_attempts'] == 1
                assert not (folder / 'owner/CLOSE.json').exists(), 'owner_finished_during_collection'
                assert process.poll() is None, 'actor_stopped_during_collection'
                assert read(folder / 'ENDPOINT.json') == endpoint_before, 'endpoint_changed'
                check_deadline(deadline)
                row['execution_state'] = 'succeeded'
            except BaseException as error:
                row['execution_state'] = 'failed'
                row['errors'].append(error_record(error, 'collection'))
                raise
            finally:
                save(folder / ('TURN_' + turn + '.json'), row)
                previous_end = time.perf_counter_ns()
        result['final_status_before_finish'] = admin('status')
    except BaseException as error:
        result['errors'].append(error_record(error, 'collection'))
    finally:
        if process is not None:
            mark = time.perf_counter_ns()
            try:
                result['cleanup'] = driver.finish(folder, process)
                assert result['cleanup']['confirmed'], 'owner_finish_unconfirmed'
            except BaseException as error:
                result['errors'].append(error_record(error, 'owned_cleanup'))
            result['stages_ns']['cleanup'] = time.perf_counter_ns() - mark
        qualify_after_finish(result, folder, sources, qualification, deadline)
        try:
            result['asset_unchanged'] = sha(QUAL / 'assembly.blend') == frozen['scene_sha256']
        except BaseException as error:
            result['asset_unchanged'] = False
            result['errors'].append(error_record(error, 'asset_readback'))
        timing = publish_result(result, folder, deadline)
    return timing


def validate_preparation(frozen, require_committed=True):
    preparation = BATCH / 'PREPARATION.json'
    relative = preparation.relative_to(ROOT).as_posix()
    assert BATCH.name == 'm4_surface_scan_continuity_001_fix2', 'current_FIX2_batch_required'
    assert read(preparation) == frozen, 'current_preparation_bytes_required'
    for record in frozen['files']:
        path = BATCH / record['path']
        assert path.resolve().is_relative_to(BATCH.resolve()), 'preparation_path_outside_batch'
        assert sha(path) == record['sha256'], record['path']
    for path, expected in frozen['external_sha256'].items():
        assert sha(Path(path)) == expected, path
    if require_committed:
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        assert head != frozen['preparation_parent_commit'], 'preparation_must_be_committed_before_engineering'
        assert subprocess.check_output(['git', 'show', head + ':' + relative], cwd=ROOT) == preparation.read_bytes(), 'committed_current_preparation_required'
    return {'preparation_path': relative, 'file_count': len(frozen['files']),
            'external_count': len(frozen['external_sha256']), 'committed_verified': require_committed}


def main():
    frozen = read(BATCH / 'PREPARATION.json')
    validate_preparation(frozen)
    with (BATCH / 'ENGINEERING_STARTED.json').open('x', encoding='utf8') as stream:
        json.dump({'started_ns': time.perf_counter_ns(), 'groups': ['C'], 'maximum_episodes': 1, 'model_calls': 0,
                   'preparation_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()}, stream)
    transport = load('_fix2_fixed_transport', FIX1 / 'runtime/consumer_transport.py')
    attach = load('_fix2_fixed_attach', ROOT / 'verification/native_plugin_complex_003/reused/stdio_attach.py')
    qualification = load('_fix2_fixed_qualification', FIX1 / 'qualification/verify_continuity.py')
    driver = load('_fix2_fixed_driver', ROOT / 'verification/m4_surface_scan_compact_consumption_001/runtime/driver.py')
    timing = run_episode('C', frozen, transport, attach, qualification, driver)
    value = {'episodes': [{'group': 'C', **timing}], 'planned_episodes': 1, 'started_episodes': 1,
             'N_episodes': 0, 'model_calls': 0, 'API_calls': 0, 'passed': timing['accepted_success']}
    save(BATCH / 'ENGINEERING_RESULT.json', value)
    print(json.dumps(value))
    return 0 if value['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
