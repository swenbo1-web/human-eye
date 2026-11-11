"""Read-only independent re-derivation from saved original records; no product import."""
import ast
import collections
import copy
import difflib
import hashlib
import json
from pathlib import Path
import statistics
import subprocess

HERE = Path(__file__).resolve().parent
WT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BATCH = WT / 'verification/m4_default_latency_attribution_001'
HEAD = 'a1b402a434623c82ebcec2a48c7a09f0ca97d7df'
PINS = {}
FAILURES = []


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_bytes(path):
    path = Path(path)
    raw = path.read_bytes()
    key = str(path)
    digest = sha(raw)
    if key in PINS:
        assert PINS[key] == digest
    PINS[key] = digest
    return raw


def read(path):
    return json.loads(read_bytes(path))


def lines(path):
    return [json.loads(row) for row in read_bytes(path).splitlines() if row.strip()]


def need(value, description):
    if not value:
        FAILURES.append(description)


def git(*args):
    return subprocess.run(['git', '-C', str(WT), *args], check=True,
                          capture_output=True, timeout=30).stdout


def main():
    need(git('rev-parse', 'HEAD').decode().strip() == HEAD, 'fixed HEAD')
    status = git('status', '--porcelain', '--untracked-files=no')
    need(not status, 'tracked worktree clean')
    entry = read(BATCH / 'entry/run_01/RESULTS.json')
    schedule = read(BATCH / 'SCHEDULE.json')
    work = read(BATCH / 'WORK_ORDER.json')
    bindings = read(BATCH / 'preparation/INPUT_BINDINGS.json')
    counts = collections.Counter()
    summaries = []
    all_semantics = None
    needs_full_native_text_normalization = collections.Counter()
    need([c['id'] for c in entry['cases']] == ['01_B', '02_C', '03_C', '04_B'], 'fixed BCCB')
    for case in entry['cases']:
        folder = BATCH / 'entry/run_01' / case['id']
        worker = lines(folder / 'native/WORKER_EVENTS.jsonl')
        need(worker == case['all_worker_events'], case['id'] + ' original worker mirror')
        need([v.get('sequence') for v in worker] == list(range(1, 24)), case['id'] + ' 23 worker RPCs')
        need(case['recorded_image_construction_events'] == [], case['id'] + ' no image events list')
        previous = None
        for index, event in enumerate(worker):
            qa = event['qa_work']
            enabled = case['rows'][index]['profile_enabled'] if index < 22 else False
            need(qa['profile_enabled'] is enabled and qa['previous_profile_enabled'] is previous,
                 case['id'] + ' mode/previous ' + str(index + 1))
            previous = enabled
            need(qa['profile_initial_present'] is False and qa['profile_after_restore_present'] is False
                 and qa['profile_restored_to_initial'] is True and qa['errors'] == [],
                 case['id'] + ' profile reset ' + str(index + 1))
            need(all(qa[k] is enabled for k in ('profile_install_attempted', 'profile_installed',
                 'profile_actual_enabled', 'profile_restore_attempted', 'profile_restore_succeeded')),
                 case['id'] + ' profile state ' + str(index + 1))
            need(all(isinstance(qa[k], dict) if enabled else qa[k] is None
                     for k in ('python_calls', 'C_calls', 'C_returns', 'C_exceptions')),
                 case['id'] + ' count collection ' + str(index + 1))
            need(qa['callback_counts_status'] == ('collected' if enabled else 'not_collected'), 'count status')
            need(not event.get('changed_or_new_PNG_files') and event.get('event') not in
                 ('render_started', 'render_completed', 'render_cancelled') and
                 ('render_events_after' not in event or event['render_events_after'] == event['render_events_before']),
                 case['id'] + ' image/render observation')
            counts['RPC'] += 1
            counts['profile_initial_None'] += qa['profile_initial_present'] is False
            counts['profile_restored_None'] += qa['profile_restored_to_initial'] is True
            counts['ON_dict' if enabled else 'OFF_null'] += 1
        counts['close_status_unknown'] += worker[-1]['status'] == 'unknown'
        need(case['native_close']['response']['status'] == 'closed' and case['native_close']['error'] is None
             and case['native_close']['exit_code'] == 0 and case['worker_closed']['poisoned'] is False,
             case['id'] + ' independent terminal close evidence')

        raw_observes = [a for a in lines(folder / 'audit.jsonl') if a.get('event') == 'observe']
        need(len(raw_observes) == 22, case['id'] + ' raw observe count')
        core_reference = capture_reference = None
        session_timings = {True: [], False: []}
        pairs = {}
        for index, row in enumerate(case['rows']):
            event = worker[index]
            qa = event['qa_work']
            proto = folder / 'product' / f'{index + 5:03}'
            tx = read(proto / 'TX.bin')
            rx = read(proto / 'RX.bin')
            body = json.loads(rx['result']['content'][0]['text'])
            expected = copy.deepcopy(schedule['request_template'])
            expected['id'] = row['request_id']
            need(tx == expected, case['id'] + ' fixed business wire ' + row['label'])
            need(body == row['body'] and 'geometry' not in body and body['execution_authority'] is False,
                 case['id'] + ' raw result ' + row['label'])
            need(body['context']['runtime_source_sha256'] == work['versions'][case['version']]['source_sha256'],
                 case['id'] + ' runtime source')
            core = {k: v for k, v in body.items() if k != 'trace_id'}
            if core_reference is None:
                core_reference = core
            need(core == core_reference, case['id'] + ' same-session complete body ' + row['label'])
            semantics = {k: body[k] for k in ('sets', 'coverage', 'measurement_contracts')}
            semantics['pairs'] = [{'target_name': body['target']['name'], 'candidate_name': candidate['name'],
                **{k: candidate[k] for k in ('closed_solid_relation', 'surface_proximity', 'separation_gap')}}
                for candidate in body['candidates']]
            if all_semantics is None:
                all_semantics = semantics
            need(semantics == all_semantics, case['id'] + ' cross-session named facts ' + row['label'])

            call_dir = folder / 'native' / ('call_' + str(index + 1))
            logical = {}
            for name in ('SCRIPT.py', 'stdout.txt', 'stderr.txt'):
                raw = read_bytes(call_dir / name)
                logical[name] = raw.replace(b'\r\n', b'\n')
                need(logical[name].replace(b'\n', b'\r\n') == raw,
                     case['id'] + ' reversible Windows storage ' + row['label'] + name)
                needs_full_native_text_normalization[name] += raw != logical[name]
            need(sha(logical['SCRIPT.py']) == event['script_sha256'] and
                 len(logical['stdout.txt']) == event['stdout_bytes'] and
                 len(logical['stderr.txt']) == event['stderr_bytes'] and not logical['stderr.txt'],
                 case['id'] + ' logical metadata matches actual code/output ' + row['label'])
            marker = b'HUMAN_EYE_BLENDER_MCP:'
            need(logical['stdout.txt'].startswith(marker), 'native protocol marker')
            packet = json.loads(logical['stdout.txt'][len(marker):])['result']
            capture = packet['capture']
            if capture_reference is None:
                capture_reference = capture
            need(capture == capture_reference, case['id'] + ' full captured references same ' + row['label'])
            generation = {k: capture['capture_state'][k] for k in ('instance_id', 'epoch', 'revision')}
            need(len(qa['after']['hosts']) == 1 and generation == qa['after']['hosts'][0]['generation'],
                 case['id'] + ' raw capture generation -> residency ' + row['label'])
            named = [body['target'], *body['candidates']]
            need(capture['task_selection']['bindings'] == [{k: o[k] for k in ('object_id', 'name')} for o in named]
                 and capture['revision'] == body['context']['scene_revision']
                 and capture['host_identity'] == body['context']['host_identity'],
                 case['id'] + ' raw capture -> public binding ' + row['label'])
            cold = index == 0
            need(len(packet['resources']) == (4 if cold else 0), case['id'] + ' resource payload ' + row['label'])
            work_row = raw_observes[index]['task_work']
            need(work_row == row['task_work'], case['id'] + ' original task diagnostics ' + row['label'])
            counters = ('exact_pair_count', 'closed_solid_pair_count', 'surface_pair_count')
            if cold:
                need([work_row[k] for k in (*counters, 'pair_calls', 'rank_calls')] == [0, 3, 3, 3, 1]
                     and work_row['result_cache_hit'] is False, case['id'] + ' cold diagnostic contract')
            else:
                need(work_row == {**{k: 0 for k in counters}, 'result_cache_hit': True},
                     case['id'] + ' warm sparse emitted contract ' + row['label'])
                counts['warm_sparse_4_keys'] += 1
            need(row['successful_normalize_hash_spans'] == int(cold), 'normalization span count')
            need(all(qa['host_residency_delta'][k] == (4 if cold else 0)
                 for k in ('to_mesh', 'triangulations', 'world_transforms', 'resource_builds')),
                 case['id'] + ' host work ' + row['label'])
            counts['business'] += 1
            counts['same_session_whole_body_matches'] += core == core_reference
            counts['source_and_capture_binding_matches'] += 1
            if row['phase'] == 'warm':
                elapsed = row['ended_ns'] - row['started_ns']
                need(elapsed == row['entry_elapsed_ns'], 'outer recorded timing arithmetic')
                session_timings[row['profile_enabled']].append(elapsed)
                pairs.setdefault(row['pair_index'], {})[row['profile_enabled']] = elapsed
        need(len(pairs) == 10 and all(set(pair) == {True, False} for pair in pairs.values()), '10 warm pairs')
        summaries.append({'id': case['id'], 'ON_median_ns': statistics.median(session_timings[True]),
            'OFF_median_ns': statistics.median(session_timings[False]),
            'paired_ON_minus_OFF_median_ns': statistics.median(p[True] - p[False] for p in pairs.values())})
    need(counts['business'] == 88 and counts['RPC'] == counts['profile_initial_None'] ==
         counts['profile_restored_None'] == 92 and counts['warm_sparse_4_keys'] == 84,
         'finite denominator totals')

    # Independently verify the exact small analyzer transformation without executing it.
    frozen = read_bytes(BATCH / 'analysis/analyze_saved.py')
    derived = read_bytes(BATCH / 'analysis/analyze_saved_fields_02.py')
    need(sha(frozen) == 'ce877249d0cbb85ae3edfa4342af6672ebd25256f64fa9a84e747a6ae53c3dff', 'frozen analyzer retained')
    tree = ast.parse(derived)
    helper = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'warm_recorded_work_matches')
    need("'pair_calls'" not in ast.unparse(helper) and "'rank_calls'" not in ast.unparse(helper), 'narrow emitted counters only')
    recorded_diff = read_bytes(BATCH / 'analysis/field_fix_001/SOURCE.diff').decode()
    calculated_diff = ''.join(difflib.unified_diff(frozen.decode().splitlines(True), derived.decode().splitlines(True),
        fromfile='frozen_ce877249/analyze_saved.py', tofile='derived/analyze_saved_fields_02.py'))
    need(recorded_diff == calculated_diff, 'saved analyzer diff exact')
    contracts = read(BATCH / 'analysis/field_fix_001/SOURCE_CONTRACT.json')
    for version in ('B', 'C'):
        for filename, binding in contracts['versions'][version]['sources'].items():
            raw = read_bytes(binding['path'])
            need(sha(raw) == binding['source_sha256'], version + ' actual installed source contract ' + filename)
            tree = ast.parse(raw)
            method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                          and n.name == binding['method'])
            fragment = (ast.get_source_segment(raw.decode(), method) + '\n').encode()
            need(fragment == read_bytes(BATCH / 'analysis/field_fix_001' / binding['fragment_path']) and
                 sha(fragment) == binding['fragment_sha256'], version + ' exact code fragment ' + filename)
    old_error = read(BATCH / 'POST_RUN_REVIEW_01_ERROR.json')
    post = read(BATCH / 'POST_RUN_REVIEW.json')
    need(old_error['passed'] is False and len(old_error['failed_checks']) == 3 and
         "KeyError: 'pair_calls'" in old_error['execution_error'], 'first reviewer failures retained')
    need(sha(read_bytes(BATCH / 'POST_RUN_REVIEW_01_ERROR.json')) ==
         post['review_parser_corrections']['initial_review_sha256'], 'old failure digest retained')
    need("KeyError: 'pair_calls'" in read_bytes(BATCH / 'analysis/run_01/ANALYZER_EXCEPTION.txt').decode(),
         'first analyzer failure retained')
    read_bytes(BATCH / 'analysis/run_01/PARTIAL_CHECKS.json')
    old_review = read_bytes(BATCH / 'history/post_run_review_01/POST_RUN_REVIEW_EXECUTED.py')
    new_review = read_bytes(BATCH / 'POST_RUN_REVIEW_EXECUTED.py')
    review_diff = ''.join(difflib.unified_diff(old_review.decode().splitlines(True), new_review.decode().splitlines(True)))
    (HERE / 'POSTRUN_REVIEW.diff').write_text(review_diff, encoding='utf8', newline='\n')
    for rel in ('entry/qa_native.py', 'entry/qa_instrumentation.py', 'entry/run_entry.py'):
        raw = read_bytes(BATCH / rel)
        registered = str((BATCH / rel).relative_to(WT)).replace('\\', '/')
        need(sha(raw) == bindings['source_files_sha256'][registered], 'registered QA bytes ' + rel)
    for rel in ('REPORT.md', 'REVIEW.md', 'tests/r5/RESULTS.json', 'analysis/run_02/RESULTS.json'):
        read_bytes(BATCH / rel)
    need(git('rev-parse', 'HEAD').decode().strip() == HEAD and
         git('status', '--porcelain', '--untracked-files=no') == status, 'ending fixed source state')
    need(all(sha(Path(name).read_bytes()) == digest for name, digest in PINS.items()), 'all read inputs unchanged')
    result = {'passed': not FAILURES, 'failures': FAILURES, 'fixed_HEAD': HEAD, 'counts': counts,
              'timing_recomputed_from_saved_outer_intervals': summaries,
              'native_text_files_requiring_CRLF_to_LF_for_logical_metadata': needs_full_native_text_normalization,
              'first_reviewer_failures': old_error['failed_checks'],
              'cold_and_warm_diagnostics': {'cold': [0, 3, 3, 3, 1],
                  'warm': 'three emitted zero pair counters plus result_cache_hit=True; pair_calls/rank_calls absent'},
              'source_files_copied': 0, 'product_imports': 0, 'new_Blender_sessions': 0,
              'new_model_consumers': 0, 'new_performance_samples': 0,
              'claims': 'Saved-record integrity and fixed-source semantic audit, not independent live measurements or geometry truth.'}
    for filename, content in [('RESULTS.json', result), ('INPUT_PINS.json', PINS)]:
        with (HERE / filename).open('x', encoding='utf8', newline='\n') as stream:
            json.dump(content, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write('\n')
    print(json.dumps({'passed': not FAILURES, 'counts': counts, 'failures': FAILURES,
                      'timing_recomputed': summaries}, ensure_ascii=False))
    raise SystemExit(0 if not FAILURES else 1)


if __name__ == '__main__':
    main()
