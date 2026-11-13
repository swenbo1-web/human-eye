"""Run the frozen FIX1 C engineering episode once, with no model consumer."""

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


def backend_identity(status):
    return {key: status[key] for key in ('episode_id', 'owner_pid', 'native_pid', 'native_host',
            'native_port', 'native_workspace', 'product_launcher_pid', 'product_runtime_proof',
            'session_id', 'worker_deadline_ns')}


def business_request(group, turn):
    assert group == 'C'
    name = 'human_eye_scene_observe'
    args = {'session_id': 'continuity-fix1-engineering-C-001', 'include_image': False,
            'query': {'mode': 'surface_scan', 'threshold_m': .002}}
    return {'jsonrpc': '2.0', 'id': group + '-' + turn, 'method': 'tools/call',
            'params': {'name': name, 'arguments': args}}


def verify_business(row, folder, source, qualification):
    """Bind the actual runner response, capture and owner geometry in one path."""
    body = json.loads(row['response']['result']['content'][0]['text'])
    row['body'] = body
    audit = [json.loads(line) for line in (folder / 'owner/audit.jsonl').read_bytes().splitlines()]
    host = [json.loads(line) for line in (folder / 'owner/native/WORKER_EVENTS.jsonl').read_bytes().splitlines()]
    host = [item for item in host if row['started_ns'] <= item.get('started_ns', -1) <= row['ended_ns']]
    assert len(host) == 1, 'single_capture_before_source_binding'
    capture = qualification.read_capture(folder / 'owner/native', host[0])
    return qualification.verify_c_turn(body, audit, host, source, row['turn'], row['request'], capture=capture)


def run_episode(group, frozen, transport, attach, qualification, driver):
    assert group == 'C'
    folder = BATCH / 'episodes' / group
    folder.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter_ns()
    deadline = started + 590 * 10**9
    result = {'group': group, 'episode_id': 'continuity-fix1-engineering-C-001',
              'started_ns': started, 'deadline_ns': deadline, 'business': [], 'administrative': [],
              'errors': [], 'model_calls': 0, 'API_calls': 0, 'automatic_retries': 0,
              'usage': None, 'usage_scope': 'No model consumer; no usage event exists.',
              'stages_ns': {}, 'same_thread_model_continuity': 'not_measured'}
    process = None
    episode = result['episode_id']

    def admin(operation, **params):
        check_deadline(deadline)
        mark = time.perf_counter_ns()
        message = {'jsonrpc': '2.0', 'id': 'admin-' + str(len(result['administrative']) + 1),
                   'method': 'continuity/' + operation, 'params': {'episode_id': episode, **params}}
        row = {'request': message, 'started_ns': mark}
        result['administrative'].append(row)
        try:
            row['response'] = attach.attach(read(folder / 'ENDPOINT.json'), 'native', message)
            assert 'error' not in row['response'], row['response']
            return row['response']['result']
        finally:
            row['ended_ns'] = time.perf_counter_ns()
            save(folder / ('ADMIN_' + str(len(result['administrative'])).zfill(2) + '.json'), row)

    try:
        check_deadline(deadline)
        ready = read(BATCH / 'inputs/C_READY.json')
        config = {'group': 'P', 'external_group': group, 'task': 'T1',
                  'episode_id': episode, 'session_id': episode, 'output': str(folder / 'owner'), 'endpoint': str(folder / 'ENDPOINT.json'),
                  'asset': str(QUAL / 'assembly.blend'), 'asset_sha256': frozen['scene_sha256'],
                  'blender': 'D:/Tools/blender5.2/blender.exe', 'worker_deadline_ns': deadline,
                  'dependency_python': ready['dependency_python'],
                  'read_schemas': read(BATCH / 'inputs/C_PUBLIC_TOOLS.json'),
                  'entry': ready['entry'], 'install_root': ready['install_root'],
                  'source_sha256': ready['source_sha256']}
        save(folder / 'ACTOR_CONFIG.json', config)
        command = [ready['dependency_python'], '-I', '-B', '-X', 'utf8', str(BATCH / 'runtime/actor.py'), '--config', str(folder / 'ACTOR_CONFIG.json')]
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
        sources = {'BASE': read(folder / 'owner/INITIAL.json')}
        driver.snapshot_binding(sources['BASE'], read(QUAL / 'BASE_SNAPSHOT.json'))
        c_reports = []
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
            assert backend_identity(before) == backend_identity(initial)
            assert before['owner_close_called'] is False
            assert read(folder / 'ENDPOINT.json') == endpoint_before
            admin('begin_turn', turn_id=turn, deadline_ns=deadline)
            request = business_request(group, turn)
            row = {'turn': turn, 'state': 'EDIT' if turn == 'EDIT' else 'BASE', 'request': request,
                   'waiting_and_barrier_before_turn_ns': time.perf_counter_ns() - previous_end,
                   'status_before': before, 'started_ns': time.perf_counter_ns(), 'errors': []}
            result['business'].append(row)
            requests = [
                {'jsonrpc': '2.0', 'id': 'init-' + turn, 'method': 'initialize', 'params': {'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'continuity-engineering-stub', 'version': '001'}}},
                {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                {'jsonrpc': '2.0', 'id': 'list-' + turn, 'method': 'tools/list'}, request]
            try:
                thin = transport.thin_turn(python=ready['dependency_python'], endpoint=folder / 'ENDPOINT.json',
                                           folder=folder / turn, requests=requests, deadline_ns=deadline)
                row['thin'] = thin
                row['ended_ns'] = time.perf_counter_ns()
                assert thin['confirmed'], thin
                responses = thin['responses']
                answer = next(value for value in responses if value.get('id') == request['id'])
                assert not answer['result'].get('isError'), answer
                row['response'] = answer
                row['status_after'] = admin('end_turn', turn_id=turn)
                assert backend_identity(row['status_after']) == backend_identity(initial)
                assert row['status_after']['owner_close_called'] is False
                assert row['status_after']['business_attempts'] == len(result['business'])
                assert row['status_after']['completed_turns'][-1]['business_attempts'] == 1
                assert not (folder / 'owner/CLOSE.json').exists()
                assert process.poll() is None
                assert read(folder / 'ENDPOINT.json') == endpoint_before
                report = verify_business(row, folder, sources[row['state']], qualification)
                c_reports.append(report)
                row['verification'] = report
                check_deadline(deadline)
            except BaseException as error:
                row['ended_ns'] = time.perf_counter_ns()
                row['errors'].append({'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()})
                raise
            finally:
                save(folder / ('TURN_' + turn + '.json'), row)
                previous_end = time.perf_counter_ns()
        result['sequence_verification'] = qualification.verify_c_sequence(c_reports)
        result['final_status_before_finish'] = admin('status')
    except BaseException as error:
        result['errors'].append({'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()})
    finally:
        if process is not None:
            mark = time.perf_counter_ns()
            try:
                result['cleanup'] = driver.finish(folder, process)
                assert result['cleanup']['confirmed'], result['cleanup']
            except BaseException as error:
                result['errors'].append({'stage': 'owned_cleanup', 'message': repr(error), 'traceback': traceback.format_exc()})
            result['stages_ns']['cleanup'] = time.perf_counter_ns() - mark
        result['asset_unchanged'] = sha(QUAL / 'assembly.blend') == frozen['scene_sha256']
        result['execution_counts'] = {'planned': 3, 'attempted': len(result['business']),
                                      'completed': sum(not row['errors'] for row in result['business']),
                                      'failed': sum(bool(row['errors']) for row in result['business']),
                                      'not_run': 3 - len(result['business'])}
        result['passed_before_publication'] = not result['errors'] and result['asset_unchanged'] and len(result['business']) == 3
        save(folder / 'RESULTS.json', result)
        closed = time.perf_counter_ns()
        timing = {'started_ns': started, 'business_receipts_closed_ns': closed, 'full_episode_wall_ns': closed - started,
                  'original_deadline_ns': deadline, 'within_590s': closed < deadline,
                  'accepted_success': result['passed_before_publication'] and closed < deadline,
                  'scope': 'input checks, owned startup, three thin lifecycles, pose/QA, verification, cleanup and RESULTS write/close',
                  'durability': 'buffered write and close; fsync of this report unmeasured'}
        mark = time.perf_counter_ns()
        save(folder / 'FINAL_TIMING.json', timing)
        save(folder / 'TIMING_PUBLICATION.json', {'started_ns': mark, 'closed_ns': time.perf_counter_ns(), 'scope': 'FINAL_TIMING publication; this receipt write is separate'})
    return timing


def main():
    frozen = read(BATCH / 'PREPARATION.json')
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() != frozen['preparation_parent_commit'], 'preparation_must_be_committed_before_engineering'
    preparation_path = (BATCH / 'PREPARATION.json').relative_to(ROOT).as_posix()
    assert subprocess.check_output(['git', 'show', 'HEAD:' + preparation_path], cwd=ROOT) == (BATCH / 'PREPARATION.json').read_bytes()
    for record in frozen['files']:
        assert sha(BATCH / record['path']) == record['sha256'], record['path']
    for path, expected in frozen['external_sha256'].items():
        assert sha(Path(path)) == expected, path
    reservation = BATCH / 'ENGINEERING_STARTED.json'
    with reservation.open('x', encoding='utf8') as stream:
        json.dump({'started_ns': time.perf_counter_ns(), 'groups': ['C'], 'maximum_episodes': 1, 'model_calls': 0,
                   'preparation_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()}, stream)
    transport = load('_continuity_transport', BATCH / 'runtime/consumer_transport.py')
    attach = load('_continuity_attach', ROOT / 'verification/native_plugin_complex_003/reused/stdio_attach.py')
    qualification = load('_continuity_qualification', BATCH / 'qualification/verify_continuity.py')
    driver = load('_continuity_reused_driver', ROOT / 'verification/m4_surface_scan_compact_consumption_001/runtime/driver.py')
    results = []
    row = run_episode('C', frozen, transport, attach, qualification, driver)
    results.append({'group': 'C', **row})
    value = {'episodes': results, 'planned_episodes': 1, 'started_episodes': 1, 'N_episodes': 0,
             'model_calls': 0, 'API_calls': 0, 'passed': row['accepted_success']}
    save(BATCH / 'ENGINEERING_RESULT.json', value)
    print(json.dumps(value))
    return 0 if value['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
