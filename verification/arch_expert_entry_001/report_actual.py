"""Offline, stdlib-only summary of already completed ARCH-EXPERT-ENTRY-001 QA.

Never imports the product or starts Blender/RPC. Existing raw evidence is read
only; this writes ACTUAL_COSTS.json and ACTUAL_QA_REPORT.md beside the runs.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


COMMIT = 'c5116e30024ed12825aea6119c0f5172e6b9b46d'
SOURCE = '239cc00a3cf09e9c18874cf0071e811e3244695c93590f806048fab97129b3b9'
ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def lines(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf8').splitlines() if line]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def wire(path):
    return [(json.loads(line), len(line)) for line in Path(path).read_bytes().splitlines(keepends=True) if line.strip()]


def product_event(row):
    return next((event for event in row['blender_events'] if event['event'] == 'expert'), None)


def total_bytes(records):
    total = Counter()
    for row in records:
        total['stdio_tx'] += row['stdio_tx_bytes']
        total['stdio_rx'] += row['stdio_rx_bytes']
        for name, size in row['metric']['transport_bytes'].items():
            total['host_tx' if name.endswith('tx.bin') else 'host_rx'] += size
    return dict(total)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, default=HERE/'actual_run_02')
    args = parser.parse_args()
    run = args.run.resolve()
    result = read(run/'RESULTS.json')
    before, after = read(run/'identity_before.json'), read(run/'identity_after.json')
    assert result['passed'] and result['product_commit'] == COMMIT
    assert before == after and result['source_sha256'] == SOURCE
    assert len(before['source_files']) == result['source_members'] == 136
    payload = {key: before[key] for key in ('base_version', 'implementation_revision')}
    payload['files'] = before['source_files']
    canonical = hashlib.sha256(json.dumps(payload, ensure_ascii=True, sort_keys=True,
                                         separators=(',', ':')).encode('utf8')).hexdigest()
    assert canonical == SOURCE
    for source in before['source_files']:
        assert digest(ROOT/source['path']) == source['sha256'], source['path']
    for name in ('qa_fixture.py', 'observe_blender.py', 'instrumented_stdio.py', 'run_actual.py'):
        assert (HERE/name).read_bytes() == (run/(name+'.txt')).read_bytes(), name

    records = result['records']
    assert result['record_count'] == len(records) == 25
    expert = [row for row in records if row['tool'] == 'human_eye_arm_twist_observe']
    ordinary = [row for row in records if row['tool'] == 'human_eye_scene_observe']
    success = [row for row in expert if row['label'] != 'out_of_domain']
    domain_errors = [row for row in expert if row['label'] == 'out_of_domain']
    assert (len(expert), len(success), len(domain_errors), len(ordinary)) == (16, 14, 2, 9)
    assert all(row['result']['status'] == 'estimated' for row in success)
    assert all(row['ledger_before_sha256'] == row['ledger_after_sha256'] for row in records)
    assert all(not count for row in records for name, count in row['metric']['calls'].items()
               if name.endswith(('._locked', '._runtime', '._save', ':_atomic_write')))

    modes = []
    costs = []
    control_costs = []
    selected_work = Counter()
    direct_error = 0.0
    for mode, count in (('owned', 10), ('shared', 10), ('owned_task', 5)):
        folder = run/mode
        subset = [row for row in records if row['mode'] == mode]
        assert len(subset) == count
        tx, rx = dict((item['id'], (item, size)) for item, size in wire(folder/'stdio_tx.bin')), dict(
            (item['id'], (item, size)) for item, size in wire(folder/'stdio_rx.bin'))
        metrics = {row['request_id']: row for row in lines(folder/'metrics.jsonl') if row['event'] == 'tool'}
        attempts = {row['request_id']: row for row in lines(folder/'tool_attempts.jsonl')}
        assert len(metrics) == len(attempts) == count
        for row in subset:
            request_id = row['request_id']
            request, tx_size = tx[request_id]
            response, rx_size = rx[request_id]
            assert request['method'] == 'tools/call'
            assert request['params'] == dict(name=row['tool'], arguments=row['arguments'])
            assert (tx_size, rx_size) == (row['stdio_tx_bytes'], row['stdio_rx_bytes'])
            assert metrics[request_id] == row['metric']
            assert attempts[request_id]['response'] == response
            assert json.loads(next(item['text'] for item in response['result']['content']
                                   if item['type'] == 'text')) == row['result']
            assert bool(response['result'].get('isError')) == (row['label'] == 'out_of_domain')
            event = product_event(row)
            cost = dict(mode=mode, label=row['label'], request_id=request_id,
                        full_tool_rtt_ms=row['full_tool_rtt_ms'],
                        dispatch_content_ms=row['metric']['dispatch_content_ms'],
                        stdio_tx_bytes=tx_size, stdio_rx_bytes=rx_size,
                        host_transport_bytes=row['metric']['transport_bytes'])
            if event:
                calls = event['calls']
                assert calls['arm_twist_source.py:BoundArmPatch.analyze'] == 1
                assert calls['arm_twist_source.py:BoundArmPatch.capture'] == 1
                cost.update(product_method_ms=event['product_method_ms'], oracle_ms=event.get('oracle_ms'),
                            source_work=event['work_delta'], calls=calls,
                            prepared_before=event['prepared_before'], prepared_after=event['prepared_after'])
                if row['label'] == 'out_of_domain':
                    assert event['error'] and not event.get('oracle_file')
                    assert event['work_delta'].get('captures', 0) == 0
                else:
                    selected_work.update(event['work_delta'])
                    assert event['work_delta']['captures'] == 1
                    assert calls['arm_twist_expert.py:PreparedArmPatch.analyze'] == 1
                    assert calls['arm_twist_expert.py:ArmTwistExpert.predict_prepared'] == 1
                    oracle = read(Path(event['oracle_file']))
                    assert oracle['expert_module'].startswith('_human_eye_')
                    actual, expected = row['result'], oracle['report']
                    for key in ('schema', 'status', 'assessment', 'model_id', 'scope', 'reason'):
                        assert actual[key] == expected[key]
                    assert len(actual['regions']) == len(expected['regions']) == 25
                    for left, right in zip(actual['regions'], expected['regions']):
                        for key in ('section_index', 'vertex_ids', 'flagged'):
                            assert left[key] == right[key]
                        error = abs(left['predicted_severity']-right['predicted_severity'])
                        direct_error = max(direct_error, error)
                        assert error <= 1e-9
                    assert row['direct_model_max_abs_error'] == 0.0
                    if row['label'] in ('repeat', 'pose', 'recovered'):
                        assert event['prepared_before'] == event['prepared_after']
                        assert event['work_delta'].get('preparations', 0) == 0
                    if row['label'] == 'repeat':
                        assert event['work_delta'].get('static_reads', 0) == 0
                    if row['label'] in ('pose', 'recovered'):
                        assert event['work_delta']['static_reads'] == 1
                    if row['label'] in ('first', 'static', 'load_lifecycle'):
                        assert event['work_delta']['preparations'] == 1
            costs.append(cost)
        all_metrics = lines(folder/'metrics.jsonl')
        exit_event = next(row for row in reversed(all_metrics) if row['event'] == 'exit')
        for name, size in exit_event['transport_bytes'].items():
            assert (folder/name).stat().st_size == size
        assert read(folder/'exit.json')['returncode'] == 0
        assert digest(run/(mode+'_setup')/'fixture.blend') == result['fixture_sha256']
        if mode != 'shared':
            launch = next(row for row in all_metrics if row['event'] == 'default_worker_launch')
            assert launch['expression_unchanged'] and not launch['worker_path_override']
            native_controls = {row['id']: row for row in lines(folder/'blender_events.jsonl')
                               if row['event'] == 'control'}
            for item in all_metrics:
                if item['event'] != 'control':
                    continue
                request_id = item['id']
                control_costs.append(dict(mode=mode, request_id=request_id, params=item['params'],
                    control_capabilities_ms=item['duration_ms'],
                    native_control_ms=native_controls[request_id]['duration_ms'],
                    stdio_tx_bytes=tx[request_id][1], stdio_rx_bytes=rx[request_id][1],
                    scope='QA control plus existing capabilities RPC; excluded from tool cost. Times are nested, not additive. Host bytes are retained in whole-session raw wire but not isolated per control.'))
        modes.append(dict(mode=mode, tool_count=count, tool_bytes=total_bytes(subset),
                          whole_stdio_bytes={name: (folder/name).stat().st_size
                                             for name in ('stdio_tx.bin', 'stdio_rx.bin')},
                          whole_host_bytes=exit_event['transport_bytes'],
                          stdio_control_requests=sum(item['method'] == 'qa/control' for item, _ in tx.values()),
                          stdio_returncode=0))
    for item in lines(run/'controls.jsonl'):
        tx_bytes, rx_bytes = bytes.fromhex(item['tx_hex']), bytes.fromhex(item['rx_hex'])
        assert json.loads(tx_bytes) == dict(type='test_control', params=item['params'])
        assert 'control' in json.loads(rx_bytes)
        control_costs.append(dict(mode='shared', params=item['params'],
            external_control_rtt_ms=item['duration_ms'], socket_tx_bytes=len(tx_bytes),
            socket_rx_bytes=len(rx_bytes), scope='Private fixture-control socket outside production host wire and tool metrics.'))
    assert Counter(item['mode'] for item in control_costs) == dict(owned=10, shared=10, owned_task=5)
    for row in result['lazy_import_checks']:
        assert row['before'] == row['after'] == []
    spec = result['fixture_spec']
    assert spec['selection_bytes'] == len(json.dumps(spec['selection'], ensure_ascii=False,
                                                    separators=(',', ':')).encode('utf8')) == 19374
    assert len(spec['selection']['vertex_indices']) == spec['selected_vertices'] == 1602
    assert min(spec['selection']['vertex_indices']) == 20000
    assert max(spec['selection']['vertex_indices']) == 24803
    assert digest(run/'original_fixture.blend') == result['fixture_sha256']

    m5 = read(run/'m5_same_source'/'RESULTS.json')
    assert m5 == result['m5_same_source'] and m5['passed'] and m5['source_sha256'] == SOURCE
    m5_cases = []
    for row, steps in zip(m5['cases'], (0, 1, 4)):
        assert row['passed'] and row['setter_count'] == row['receipt']['engine_confirmed_steps'] == steps
        assert row['worker_closed'] and row['worker_returncode'] == 0
        assert row['native_check']['other_objects_unchanged'] == 3
        assert row['native_check']['error_m'] < 1e-7
        assert row['fixture_sha256_before'] == row['fixture_sha256_after']
        post = row['post_loop_delta']
        assert post['passed'] and post['host_requests'] == 3
        assert post['ledger_before_sha256'] == post['ledger_after_sha256']
        m5_cases.append({key: row[key] for key in ('label', 'worker_pid', 'loop_ms', 'lifecycle_ms',
            'loop_host_requests', 'loop_host_commands', 'loop_worker_calls', 'loop_resident_work', 'calls',
            'setter_count', 'save_events', 'worker_returncode', 'worker_closed', 'native_check',
            'loop_transport_bytes', 'whole_host_transport_bytes', 'post_loop_delta')})

    failed = run.parent/'actual_run_01'
    old = read(failed/'RESULTS.json')
    old_tx = [item for item, _ in wire(failed/'owned'/'stdio_tx.bin') if item['method'] == 'tools/call']
    old_rx = dict((item['id'], item) for item, _ in wire(failed/'owned'/'stdio_rx.bin'))
    assert not old['passed'] and len(old['records']) == 1 and len(old_tx) == 2
    assert all(item['params']['name'] == 'human_eye_scene_observe' for item in old_tx)
    old_error = old_rx[old_tx[-1]['id']]['result']
    assert old_error['isError']
    assert 'acquisition_static_triangle_source_required' in old_error['content'][0]['text']
    assert read(failed/'owned'/'exit.json')['returncode'] == 0
    cleanup = read(HERE/'PROCESS_CLEANUP.json')
    assert cleanup['task_workers_absent']
    summary = dict(passed=True, offline_only=True, product_commit=COMMIT, source_sha256=SOURCE,
                   source_members=136, source_unchanged=True, accepted_run=run.name,
                   tool_outcomes=dict(total=25, estimated_expert=14, expected_source_domain_errors=2, ordinary=9),
                   prior_actual_attempt=dict(run=failed.name, tools_attempted=2, tools_passed=1,
                       fixture_domain_failures=1, expert_calls=0, setters=0, owned_stdio_returncode=0),
                   fixture={key: value for key, value in spec.items() if key not in ('selection', 'pose_matrices', 'fixture')},
                   fixture_sha256=result['fixture_sha256'], direct_max_abs_error=direct_error,
                   selected_work_totals=dict(selected_work), modes=modes, costs=costs,
                   qa_control_costs=control_costs,
                   lazy_import_checks=result['lazy_import_checks'], processes=result['processes'],
                   direct_model_invocations=len(success), model_api_calls=0, user_assets=0,
                   source_capture_entries=len(expert), successful_capture_work=len(success),
                   m5_cases=m5_cases, runner_sequence_ms=result['runner_sequence_ms'],
                   m5_runner_sequence_ms=m5['runner_sequence_ms'], cleanup=cleanup,
                   limitations=[
                       'Estimated reports are dynamically covered; unknown normal semantics were statically reviewed and are not dynamically covered in this batch.',
                       'The actual compact selection is 19,374 B; legal >64 KiB input is CPU coverage only.',
                       'Whole tool RTT includes observer and the separate direct native/same-model oracle.',
                       'product_method_ms includes profiling overhead; no subtraction or performance guarantee.',
                       'Selected source-work rows do not measure all native reads: accepted native topology builds whole BMesh.',
                       'Ordinary lazy checks use a legal static scene; nearest armature support is not claimed.',
                       'Private QA controls/capabilities and M5 post-loop reads are reported outside expert tool cost.',
                       'M5 method entries, resident counters and actual native translation setters are separate measures.',
                       'Shared socket fixture is controlled terminate/wait returncode 1, not a clean exit 0.'])
    (HERE/'ACTUAL_COSTS.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', encoding='utf8')

    report = [
        '# ARCH-EXPERT-ENTRY-001 actual QA', '',
        f'Fixed product `{COMMIT}`; 136-source SHA256 `{SOURCE}`. Runtime identity and all 136 source file bytes match before/after and at offline audit. No product change was needed.', '',
        '`actual_run_02` passed all 25 expected tool outcomes: 14 real estimated expert reports, two expected unsupported-source errors, and nine ordinary reads. The 14 reports match independent native-RNA packets evaluated by the same already-loaded expert/model: 25 section scores/flags/native IDs each, maximum absolute severity difference 0.0. This is a same-model source/integration oracle, not an independent validation of model accuracy.', '',
        f"The isolated synthetic fixture has {spec['total_vertices']:,} mesh vertices and {spec['total_triangles']:,} triangles. Its explicit patch selects {spec['selected_vertices']:,} sparse native IDs 20000..24803 and {spec['selected_triangles']:,} triangles; compact selection JSON is {spec['selection_bytes']:,} bytes. The original and all three run fixture copies have SHA256 `{result['fixture_sha256']}` after execution. The saved synthetic dataset and original model were reused; no training or external model API calls occurred.", '',
        'Owned/shared exercise first, repeat, pose, static edit, DQ unsupported error, recovery, and file-load lifecycle; owned_task exercises first/repeat. Every successful analyze enters capture exactly once. Repeat reads current rows with no static read/preparation. Pose and recovery each perform one static read while reusing the prepared object and doing zero preparation. First/static/load each prepare once. Each DQ error enters capture once but increments successful `work.captures` by zero, and has no direct oracle. Across 16 expert calls there are 16 capture entries, 14 successful captures, 11 static reads and seven preparations.', '',
        'Ordinary task/nearest reads are performed after unlinking arm mesh/rig from the scene, retaining the same objects in bpy.data; the original objects are relinked for expert queries. All three Blender workers report no NumPy/expert/weights modules before or after those initial ordinary reads. This proves lazy loading in a legal static scene and does not extend nearest support to armature scenes. All 25 read tools leave the opaque action-ledger bytes unchanged and have zero `_locked`, `_runtime`, `_save`, and `_atomic_write` entries.', '',
        'Tool costs below are individual observed milliseconds, including instrumentation. Full tool RTT spans stdin write to complete stdout line and includes the separate direct oracle. Product method time stops before that oracle; oracle time is its independent native extraction, same-model analysis and artifact write. Inclusive nested profile times must not be summed. Private QA control/capabilities requests are outside these tool costs. Whole-session raw byte totals, including initialization/control/shutdown, are in ACTUAL_COSTS.json.', '',
        '| Mode | Call | Full RTT ms | Product method ms | Direct oracle ms | Stdio TX/RX B | Host TX/RX B |',
        '|---|---|---:|---:|---:|---:|---:|']
    for row in costs:
        host = row['host_transport_bytes']
        tx = sum(size for name, size in host.items() if name.endswith('tx.bin'))
        rx = sum(size for name, size in host.items() if name.endswith('rx.bin'))
        method = f"{row['product_method_ms']:.4f}" if 'product_method_ms' in row else '—'
        oracle = f"{row['oracle_ms']:.4f}" if row.get('oracle_ms') is not None else '—'
        report.append(f"| {row['mode']} | {row['label']} | {row['full_tool_rtt_ms']:.4f} | {method} | {oracle} | {row['stdio_tx_bytes']}/{row['stdio_rx_bytes']} | {tx}/{rx} |")
    report += ['',
        'QA controls are separate: owned has 10 control+capabilities requests, shared has 10 private socket controls, and owned_task has five control+capabilities requests. ACTUAL_COSTS.json retains their individual times and raw stdio/socket byte sizes. Owned control host bytes remain in whole-session wire and are not individually isolated; native control times are nested within control+capabilities timing and must not be added. Default owned worker expressions were checked unchanged.', '',
        'Source-work counters count selected rows returned/read by the adapter; they do not establish O(selected) native work. The accepted `_native_topology` path builds the whole native BMesh on static reads. Actual RNA bytes/copies and nonresident geometry internals are not exhaustively instrumented. This batch is correctness evidence with observed cost, not a topology performance matrix or performance guarantee.', '',
        'Same-source M5 reuses the existing independent rigid fixtures/runner, in separate processes. The 0/1/4 cases all complete and agree with direct native horizontal-face gaps; the other three objects stay unchanged. Each case then passes separate task/nearest/task reads with unchanged ledger, outside scheduler-loop timing/counters/bytes.', '',
        '| M5 case | Confirmed steps / actual setters | Scheduler ms | Lifecycle ms | Host requests | Worker `_capture` entries | Host evidence/full captures | Saves | Loop TX/RX B | Native gap error m |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for row in m5_cases:
        report.append(f"| {row['label']} | {row['setter_count']}/{row['setter_count']} | {row['loop_ms']:.4f} | {row['lifecycle_ms']:.4f} | {row['loop_host_requests']} | {row['loop_worker_calls']['_capture']} | {row['loop_host_commands']['capture_evidence']}/{row['loop_host_commands']['capture']} | {row['save_events']} | {row['loop_transport_bytes']['owned_tx.bin']}/{row['loop_transport_bytes']['owned_rx.bin']} | {row['native_check']['error_m']:.10g} |")
    report += ['',
        'M5 resident work records four to_mesh, four triangulations and four resource builds per case. Method capture entries above include wrappers/nested status work; they are not setter counts. Actual native `_assign_translation` is absent/one/four in zero/one/multi. Scheduler-loop scope ends at end_motion_goal. M5 reports no external model calls or user assets. The complete QA runner sequence was 19,534.3209 ms, including fixture creation/startup/control/oracle/M5; its M5 subrunner sequence was 5,660.1245 ms.', '',
        '`actual_run_01` is preserved in full: two ordinary tools attempted, task passed, nearest returned the existing conservative static-source-domain error while the armature was still in-scene. Zero expert calls and setters occurred. Only the verification fixture was corrected by scene unlink/relink; nearest/product semantics and the fixed source did not change. Run01 retains its executing harness source snapshots and failure traceback. Across both expert-entry attempts there were 27 tool attempts: 26 expected outcomes and this one fixture-domain failure; M5 is reported separately.', '',
        'Process records: run01 owned worker 7872, stdio exit0; run02 owned 37792 and owned_task 36444, stdio exit0; shared fixture 25376, its stdio server exit0 followed by explicit controlled terminate/wait return1. M5 workers 24328/35148/16248 each closed with exit0. The fixture creator returned0 and was synchronously waited; its PID was not recorded. PROCESS_CLEANUP.json records the final read-only process query: no task Blender/python command line remains. PID37792 has since been reused by unrelated Windows VSSVC.exe; it is not the completed Blender worker and was not touched.', '',
        'Actual unknown expert-report behavior is not covered by this estimated fixture. Actual selection exceeds16KiB but not64KiB; larger legal input is CPU covered. Unknown normal semantics were statically reviewed, not dynamically covered in this batch. No actual run or product import was performed by this offline reporter.', '',
        'Raw evidence: actual_run_02/RESULTS.json, each mode’s stdio/host binary captures, metrics.jsonl, Blender events, full native oracle packets/reports, controls, command files, source identities and fixture copies. ACTUAL_COSTS.json provides per-call costs, work/method counts, whole-session byte totals, M5 data and cleanup. Prior failed attempt is actual_run_01/.', '']
    (HERE/'ACTUAL_QA_REPORT.md').write_text('\n'.join(report), encoding='utf8')
    print(json.dumps(dict(passed=True, offline_only=True, expected_tool_outcomes=25,
                         source_files_checked=136, report='ACTUAL_QA_REPORT.md', summary='ACTUAL_COSTS.json')))


if __name__ == '__main__':
    main()
