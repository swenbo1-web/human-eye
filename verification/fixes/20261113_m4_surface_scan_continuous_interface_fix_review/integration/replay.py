"""Independent read-only record review; no CLI/backend/provider subprocesses."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BATCH = ROOT / 'verification/m4_surface_scan_continuous_interface_fix_001'
OUT = Path(__file__).resolve().parent
hashes = {}
checks = []

def raw(path):
    path = Path(path)
    data = path.read_bytes()
    hashes[str(path)] = hashlib.sha256(data).hexdigest()
    return data

def read(path):
    return json.loads(raw(path))

def check(name, condition, detail=None):
    checks.append({'name': name, 'passed': bool(condition), 'detail': detail})

def load(name, path):
    raw(path)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def normalized(path):
    return str(path).removeprefix('\\\\?\\').replace('\\', '/').lower()

ep = load('_independent_interface_episode', BATCH / 'runtime/episode.py')
tr = ep.transport
compat = tr.compatibility
stop = load('_independent_interface_stop', BATCH / 'review/stop_recommendation.py')
check('run_episode_actual_global_transport', ep.run_episode.__globals__['transport'] is tr)
check('consume_turn_actual_global_archive', tr.consume_turn.__globals__['archive_turn'] is tr.archive_turn)
check('consume_turn_is_old_function', normalized(tr.consume_turn.__code__.co_filename) == normalized(ROOT / 'verification/m4_surface_scan_continuity_001_fix1/runtime/consumer_transport.py'))
check('run_episode_is_old_function', normalized(ep.run_episode.__code__.co_filename) == normalized(ROOT / 'verification/m4_surface_scan_continuity_001_fix1/consumer/episode.py'))
check('wrapper_pack_not_exported', not hasattr(ep, 'pack'))
check('legacy_pack_available', callable(ep.legacy.pack.capture_cell))
old_driver_path = ROOT / 'verification/m4_surface_scan_continuous_consumption_001/runtime/driver.py'
old_driver = raw(old_driver_path).decode('utf8')
check('old_outer_archive_requires_missing_pack', 'sources = coordinator.pack.capture_cell(runtime, archive)' in old_driver)

cases = []
total = {'completed': 0, 'failed': 0, 'not_run': 0}
for cid in ('8a16aa', '977485', 'ea8590', '993efc'):
    home = BATCH / 'integration/offline/a04' / cid
    meta = read(home / 'CASE.json')
    result = read(home / 'episode/EPISODE_RESULT.json')
    envelope = read(home / 'episode/quality/public/EPISODE.json')
    closing = read(home / 'owner/CLOSE.json')
    controls = read(home / 'owner/CONTROL_EVENTS.json')
    finish = result['owner_finish']
    failure_case = cid == '993efc'
    expected_counts = {'completed': 1, 'failed': 1, 'not_run': 1} if failure_case else {'completed': 3, 'failed': 0, 'not_run': 0}
    check(cid + ':counts', result['counts'] == expected_counts == envelope['counts'])
    check(cid + ':finish_once', finish['confirmed'] is True and finish['finish_calls'] == 1 and closing == finish)
    check(cid + ':controls_preclose', all(e['finish_calls'] == 0 for e in controls))
    check(cid + ':registered_edit_count', finish['registered_edits'] == (0 if failure_case else 1))
    check(cid + ':qualified', result['qualified_execution'] is (not failure_case))
    check(cid + ':unscored_provider0', result['new_provider_calls'] == 0 and result['mode'] == 'local_synthetic_processes' and result['model_continuity_attestation'] == 'pending_actual_consumer')
    rows = []
    observed_uuid = None
    endpoint_sha = None
    marker = None
    for index, turn in enumerate(result['turns'], 1):
        label = turn['turn_label']
        folder = home / 'episode/turns' / label
        rec = read(folder / 'CONSUMER.json')
        timing = read(folder / 'FINAL_TIMING.json')
        fake = read(home / 'work' / ('FAKE_TURN_' + str(index) + '.json'))
        binding = read(folder / 'BUSINESS_SOURCE_BINDING.json')
        events = [json.loads(line)['event'] for line in raw(folder / 'events.jsonl').splitlines()]
        items = [event['item'] for event in events if event.get('type') == 'item.completed' and event.get('item', {}).get('type') == 'mcp_tool_call']
        check(cid + ':' + label + ':single_tool', len(items) == 1 == len(rec['tool_calls']))
        item = items[0]
        response_path = home / 'owner' / ('tool_' + str(index).zfill(2)) / 'RESPONSE.json'
        response = read(response_path)
        request = read(response_path.with_name('REQUEST.json'))
        attempt = read(response_path.with_name('ATTEMPT.json'))
        copied = folder / 'owner_turn' / ('tool_' + str(index).zfill(2)) / 'RESPONSE.json'
        check(cid + ':' + label + ':original_copy_bytes', raw(copied) == raw(response_path))
        check(cid + ':' + label + ':event_bound_to_consumer', item == rec['tool_calls'][0]['item'])
        check(cid + ':' + label + ':request_bound', request['params']['name'] == item['tool'] and compat.encoded(request['params']['arguments']) == compat.encoded(item['arguments']))
        exact = compat.encoded(response['result']) == compat.encoded(item['result'])
        converted = compat.successful_result_matches(response, item)
        error_turn = index == 2 and cid in ('ea8590', '993efc')
        check(cid + ':' + label + ':content_equal', response['result']['content'] == item['result']['content'])
        check(cid + ':' + label + ':compatibility_result', converted is (not error_turn))
        check(cid + ':' + label + ':old_exact_result', exact is (error_turn and cid == 'ea8590'))
        expected_failed = failure_case and index == 2
        check(cid + ':' + label + ':status', rec['status'] == ('failed' if expected_failed else 'completed') and rec['valid_completion'] is (not expected_failed))
        check(cid + ':' + label + ':error_facts_preserved', response['result']['isError'] is error_turn and item['status'] == ('failed' if error_turn else 'completed') and item['error'] is None and attempt['is_error'] is error_turn)
        check(cid + ':' + label + ':binding_status', bool(binding['binding_errors']) is expected_failed)
        check(cid + ':' + label + ':safe_close', rec['process_reaped'] and rec['readers_stopped'] and rec['bridge_cleanup']['confirmed'] is True and rec['safe_to_continue'] and rec['mutation_unknown'] is False)
        check(cid + ':' + label + ':final_preserved', bool(raw(folder / 'PUBLIC_FINAL.txt')) and rec['final'] is not None)
        check(cid + ':' + label + ':timing_status', timing['accepted_success'] is (not expected_failed))
        if observed_uuid is None:
            observed_uuid = fake['observed_thread']; endpoint_sha = fake['endpoint_sha256']; marker = fake['marker']
        check(cid + ':' + label + ':same_UUID', fake['observed_thread'] == observed_uuid == rec['thread_id'])
        check(cid + ':' + label + ':resume', fake['resumed'] is (index != 1) and fake['requested_thread'] == (None if index == 1 else observed_uuid) and rec['expected_thread_id'] == (None if index == 1 else observed_uuid))
        check(cid + ':' + label + ':same_context', fake['endpoint_sha256'] == endpoint_sha and fake['marker'] == marker and normalized(fake['cwd']) == normalized(home / 'work') and normalized(rec['shared_work']) == normalized(home / 'work'))
        check(cid + ':' + label + ':fake_receipt_and_reaped_launch', type(fake['actual_pid']) is int and fake['actual_pid'] > 0 and fake['thin_returncode'] == 0 and rec['process_cleanup']['pid'] == rec['consumer_pid'] and rec['process_cleanup']['parent_reaped'] and rec['process_cleanup']['parent_exit'] == 0)
        starts = list(folder.glob('attachments/bridge_*/STARTED.json'))
        exits = list(folder.glob('attachments/bridge_*/EXIT.json'))
        check(cid + ':' + label + ':one_thin', len(starts) == len(exits) == 1)
        start, exit_record = read(starts[0]), read(exits[0])
        check(cid + ':' + label + ':thin_closed_not_owner', start['pid'] == exit_record['pid'] and exit_record['normal_exit'] is True and exit_record['backend_close_requested'] is False)
        if error_turn:
            check(cid + ':' + label + ':error_not_success_stop', stop.shared_success_binding_fault('CLI_result_differs_from_owner', response, item) is False)
        rows.append({'turn': label, 'owner_isError': response['result']['isError'], 'CLI_tool_status': item['status'], 'old_exact': exact, 'new_success_compatibility': converted, 'binding_errors': binding['binding_errors'], 'consumer_status': rec['status'], 'final_preserved': rec['final'] is not None})
    check(cid + ':executed_slots', len(rows) == (2 if failure_case else 3))
    if failure_case:
        check(cid + ':notrun_no_EDIT_artifacts', not (home / 'episode/turns/EDIT').exists() and not (home / 'work/FAKE_TURN_3.json').exists())
    for k, v in result['counts'].items(): total[k] += v
    cases.append({'id': cid, 'test': meta['test'], 'counts': result['counts'], 'turns': rows, 'same_thread_uuid': observed_uuid, 'finish': finish})

history = []
for attempt in ('a01', 'a02', 'a03', 'a04'):
    home = BATCH / 'integration/offline' / attempt
    recs = list(home.glob('*/episode/turns/*/CONSUMER.json'))
    fakes = list(home.glob('*/work/FAKE_TURN_*.json'))
    starts = list(home.glob('*/episode/turns/*/attachments/bridge_*/STARTED.json'))
    exits = list(home.glob('*/episode/turns/*/attachments/bridge_*/EXIT.json'))
    result = read(home / 'RESULT.json')
    check(attempt + ':11process_pairs', len(recs) == len(fakes) == len(starts) == len(exits) == 11)
    check(attempt + ':CLI_receipts_and_reaped_launches', all(type(read(p)['actual_pid']) is int and read(p)['thin_returncode'] == 0 for p in fakes) and all(read(p)['process_reaped'] and read(p)['process_cleanup']['parent_exit'] == 0 for p in recs))
    thin_start_keys = {(read(p)['pid'], read(p)['instance_nonce']) for p in starts}
    thin_exit_keys = {(read(p)['pid'], read(p)['instance_nonce']) for p in exits}
    check(attempt + ':thin_pid_nonce_close', thin_start_keys == thin_exit_keys and len(thin_start_keys) == 11 and all(read(p)['normal_exit'] for p in exits))
    check(attempt + ':4_cases', result['tests'] == 4 and result['failures'] == result['errors'] == 0)
    history.append({'attempt': attempt, 'actual_fake_CLI': len(fakes), 'actual_thin': len(starts), 'closed_thin': len(exits), 'case_count': result['tests']})
check('a04_12slots', total == {'completed': 10, 'failed': 1, 'not_run': 1})
failure = read(BATCH / 'integration/offline/a03_ARCHIVE_FAILURE.json')
check('a03_publication_failure_preserved', failure['main_exit_code'] == 1 and failure['exception_type'] == 'FileNotFoundError')
for source in (BATCH / 'runtime/consumer_transport.py', BATCH / 'compatibility.py', Path(tr.consume_turn.__code__.co_filename), Path(ep.run_episode.__code__.co_filename)):
    raw(source)
result = {'delivery': 'b51dc02eb4f25966f983033b42dad3c9cfec9393', 'assertions': len(checks), 'passed': sum(c['passed'] for c in checks), 'failed': [c for c in checks if not c['passed']], 'a04_counts': total, 'cases': cases, 'history': history, 'new_calls': {'model': 0, 'Blender': 0, 'product': 0, 'fixture_processes': 0}, 'next_002_required_adapter': ['new episode and transport paths in the new frozen driver', 'reuse coordinator.legacy.pack for outer originals archive', 'wire success-only shared binding fault into existing stop_reasons after sole cleanup', 'offline outer run_one qualification covers postclose, archive and publish before the six formal episodes'], 'AL': {'parent': 'a22c631e rev1/write628; not borrowed', 'self_old_assignment': '83190789b8504a49bb04b5450cedf946; current=false; no AL writes'}, 'scope': 'Independent original-record read and imported pure compatibility/global linkage inspection. Historical fixture integration is not real model context or task quality.'}
(OUT / 'RESULTS.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
(OUT / 'CHECKS.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding='utf8')
(OUT / 'INPUT_SHA256.json').write_text(json.dumps(hashes, ensure_ascii=False, indent=2), encoding='utf8')
print(json.dumps({key: result[key] for key in ('assertions', 'passed', 'failed', 'a04_counts', 'history')}))
