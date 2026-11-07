"""One fixed ABBA BAAB installed comparison; no automatic retries or resampling."""
import argparse
import copy
import ctypes
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import statistics
import subprocess
import sys
import threading
import time

from verification import visual004_native as native
from verification.visual004_session import client, load_broker_ready

ORDER = ('A', 'B', 'B', 'A', 'B', 'A', 'A', 'B')
STATES = ('edge_crossing_cold', 'closed_separated_cold', 'closed_separated_hot')
ASSET_SHA = '4e62bdd23a4a3c27185be864ce25d7eab4a97e0eb723bc63bfa4c348e1d26a17'
TRUTH_SHA = '275f9e5ae73389fd8f5982596ef0d191ad70317d23d254c5e5d0e9f18a429a73'
A_PIN = '0155c5509901ed85dbf255c98a71e81187cbd3b60ef7bd49adcbfa1b663af578'
HELPERS = ('perf000_scene_tool', 'perf010_qualification', 'visual004_native',
           'visual004_session', 'visual004_product')
COUNTS = dict(surface_measurements=0, strict_pair_measurements=0, paired_sat_calls=0,
              fallback_sat_calls=0, selected_captures=0, full_captures=0, task_content_encodings=0)


def utc():
    return datetime.now(timezone.utc).isoformat()


def require(value, reason):
    if not value:
        raise ValueError(reason)


def purelib(executable):
    return executable.parent.parent / 'Lib/site-packages'


def fact_geometry(payload):
    fact = copy.deepcopy(payload['facts']['surface_proximity'])
    del fact['method']
    return fact


def observation_records(workspace, trace_id):
    costs = []
    for path in workspace.glob('product_calls/*/MCP_RESPONSE.json'):
        response = native.load(path)
        payload = json.loads(response['result']['content'][0]['text'])
        if payload.get('trace_id') == trace_id:
            costs.append((path.parent, native.load(path.with_name('COST.json'))))
    require(len(costs) == 1, 'Exactly one original product response and COST')
    helpers = [path for path in workspace.glob('perf000_calls/*/REPLY.json')
               if trace_id in path.read_text(encoding='utf8')]
    require(len(helpers) == 1, 'Exactly one thin helper reply')
    audit = native.load(helpers[0].with_name('AUDIT.json'))
    require(audit['automatic_retries'] == 0 and not audit['error'], 'No helper retry or error')
    events = [json.loads(line) for line in (workspace / 'product_audit.jsonl').read_text(encoding='utf8').splitlines()]
    observed = [row for row in events if row.get('event') == 'observe' and row.get('trace_id') == trace_id]
    require(len(observed) == 1, 'One actual observe audit')
    cost = costs[0][1]
    require(not cost['error'] and cost['source_asset_unchanged'], 'Service observe success and original asset unchanged')
    require(0 <= cost['finished_ns'] - cost['started_ns'] <= cost['elapsed_ns'], 'Successive service clock reads')
    return dict(service_cost=cost, helper_audit=audit, product_observe_audit=observed[0],
                product_call_folder=str(costs[0][0].relative_to(workspace)),
                helper_call_folder=str(helpers[0].parent.relative_to(workspace)))


def run_session(args, sequence, version, checks):
    started_ns = time.perf_counter_ns()
    folder = args.output / ('%02d_%s' % (sequence, version))
    folder.mkdir(parents=True, exist_ok=False)
    workspace = folder / 'session'
    executable, pin = args.executables[version], args.pins[version]
    tool = purelib(executable) / 'verification/perf000_scene_tool.py'
    remaining = (args.cutoff - datetime.now(timezone.utc)).total_seconds()
    require(remaining > 30, 'New-session cutoff leaves insufficient cleanup time')
    lease = min(180.0, remaining - 10)
    command = [str(executable), '-I', '-B', str(args.service_entry), '--asset', str(args.asset),
        '--workspace', str(workspace), '--blender', str(args.blender), '--condition', 'P',
        '--pin', pin, '--source-count', str(args.source_count),
        '--expected-asset-sha256', ASSET_SHA, '--seconds', str(lease)]
    record = dict(sequence=sequence, version=version, started_utc=utc(), command=command,
        observes_started=0, raw_readbacks_started=0, states=[], forced_cleanup=[], passed=False)
    native.save(folder / 'START.json', record)
    marks = dict(start=started_ns)
    process = None
    handle = None
    timer = None

    def stop():
        event = dict(utc=utc())
        if process is not None and process.poll() is None:
            result = subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                capture_output=True, text=True, timeout=8, creationflags=subprocess.CREATE_NO_WINDOW)
            event['taskkill_exit'] = result.returncode
        if handle and checks.kernel.WaitForSingleObject(handle, 0) == 258:
            event['worker_terminate'] = bool(checks.kernel.TerminateProcess(handle, 124))
        record['forced_cleanup'].append(event)

    try:
        marks['launch'] = time.perf_counter_ns()
        with (folder / 'service.stdout.log').open('xb') as out, (folder / 'service.stderr.log').open('xb') as err:
            process = subprocess.Popen(command, stdout=out, stderr=err, stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW, cwd=str(folder))
        record['launcher_pid'] = process.pid
        timer = threading.Timer(lease, stop)
        timer.daemon = True
        timer.start()
        deadline = time.monotonic() + lease - 5
        while not (workspace / 'BROKER_READY.json').exists():
            require(process.poll() is None and time.monotonic() < deadline, 'Owned session startup failed')
            time.sleep(.02)
        ready = load_broker_ready(workspace)
        record['ready'] = ready
        handle = checks.kernel.OpenProcess(0x00100000 | 0x1000 | 1, False, ready['worker_pid'])
        require(handle, 'Cannot retain actual worker process handle')
        marks['ready'] = time.perf_counter_ns()
        record['raw_readbacks_started'] += 1
        raw = client(workspace, dict(request_id='comparison-qualification', operation='native_run',
                                    args=dict(code=checks.READBACK)))
        native.save(folder / 'RAW_READBACK_REPLY.json', raw)
        require(raw.get('ok') and raw.get('operation_succeeded'), 'Single qualification raw readback failed')
        current = json.loads(raw['result']['stdout'])
        require(current == native.load(args.author / 'BUILD_READBACK.json'), 'Original control geometry unchanged')
        truth = native.load(args.author / 'TRUTH.json')
        marks['qualified'] = time.perf_counter_ns()
        prior_counts = dict(COUNTS)
        prior_work_count = 0
        for index, state in enumerate(STATES):
            require(datetime.now(timezone.utc) < args.cutoff, 'New-query cutoff reached')
            expected = truth['states']['edge_crossing' if index == 0 else 'closed_separated']
            query = dict(mode='task', objects=[dict(name=name) for name in expected['objects']],
                         requested_facts=['surface_proximity'])
            cli = [str(executable), '-I', '-B', str(tool), 'observe', '--workspace', str(workspace),
                   '--query-literal', repr(query), '--detail', 'brief']
            record['observes_started'] += 1
            before = time.perf_counter_ns()
            response = subprocess.run(cli, capture_output=True, timeout=min(35, deadline - time.monotonic()))
            wall = time.perf_counter_ns() - before
            (folder / (state + '.CLI.stdout')).write_bytes(response.stdout)
            (folder / (state + '.CLI.stderr')).write_bytes(response.stderr)
            row = dict(state=state, command=cli, cli_process_wall_ns=wall, exit_code=response.returncode,
                       stdout_bytes=len(response.stdout), stderr_bytes=len(response.stderr))
            record['states'].append(row)
            require(response.returncode == 0 and not response.stderr, 'Actual observe transport failed')
            payload = json.loads(response.stdout.decode('utf8'))
            row['payload'] = payload
            require(payload['binding']['runtime_source_sha256'] == pin, 'Own installed runtime pin')
            require(payload['binding']['capture_scope'] == 'selected_objects'
                    and payload['binding']['selected_count'] == 2, 'One selected capture binding')
            require([obj['name'] for obj in payload['binding']['objects']] == expected['objects'], 'A-to-B bound objects')
            require(payload['facts']['surface_proximity']['method'] == args.methods[version], 'Declared own algorithm method')
            row['verified'] = checks.check_payload(payload, expected, current)
            counters = native.load(workspace / 'QA_COUNTS.json')
            row['counters'] = counters
            native.save(folder / (state + '.COUNTS.json'), counters)
            row['actual_call_delta'] = {name: counters['counts'][name] - prior_counts[name] for name in COUNTS}
            row['new_surface_work'] = counters['surface_work'][prior_work_count:]
            expected_delta = dict(COUNTS, selected_captures=1, task_content_encodings=1,
                                  surface_measurements=int(index < 2))
            require(row['actual_call_delta'] == expected_delta, 'Actual one capture/encoding and cold/hot surface calls')
            require(len(row['new_surface_work']) == int(index < 2), 'Only actual cache misses contribute new geometry work')
            prior_counts = dict(counters['counts'])
            prior_work_count = len(counters['surface_work'])
            row['original_records'] = observation_records(workspace, payload['trace_id'])
            task_work = row['original_records']['product_observe_audit']['task_work']
            require(task_work['surface_pair_cache_hit'] is (index == 2), 'Actual surface cache hit state')
            require(task_work['surface_pair_count'] == int(index < 2), 'Actual surface cache miss count')
            if index == 2:
                cold = record['states'][1]['payload']
                require(payload['facts'] == cold['facts'], 'Hot geometry and witness exactly match cold')
                for key in ('scene_revision', 'scene_fingerprint', 'objects'):
                    require(payload['binding'][key] == cold['binding'][key], 'Hot query current unchanged capture binding')
        expected_counts = dict(COUNTS, surface_measurements=2, selected_captures=3, task_content_encodings=3)
        require(record['states'][-1]['counters']['counts'] == expected_counts, 'Session actual final function counters')
        record['passed'] = True
    except BaseException as exc:
        record['error'] = dict(type=type(exc).__name__, message=str(exc))
    finally:
        marks['cleanup'] = time.perf_counter_ns()
        if process is not None and process.poll() is None:
            try:
                record['close_reply'] = client(workspace, dict(request_id='comparison-close', operation='close', args={}))
            except BaseException as exc:
                record['close_error'] = dict(type=type(exc).__name__, message=str(exc))
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                stop()
                process.wait(timeout=8)
        if timer is not None:
            timer.cancel()
            timer.join(timeout=9)
            record['watchdog_joined'] = not timer.is_alive()
        record['launcher_exit_code'] = None if process is None else process.poll()
        if handle:
            state = checks.kernel.WaitForSingleObject(handle, 0)
            if state == 258:
                stop()
                state = checks.kernel.WaitForSingleObject(handle, 5000)
            exit_code = ctypes.c_uint32()
            record['worker_exited'] = state == 0
            record['worker_exit_code'] = exit_code.value if checks.kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)) else None
            checks.kernel.CloseHandle(handle)
        marks['end'] = time.perf_counter_ns()
        record.update(ended_utc=utc(), startup_to_reap_ns=marks['end'] - started_ns)
        record['timing_phase_marks_ns'] = marks
        if all(key in marks for key in ('launch', 'ready', 'qualified')):
            record['nonoverlapping_phase_ns'] = dict(
                preparation=marks['launch'] - marks['start'],
                launch_asset_copy_startup_to_ready=marks['ready'] - marks['launch'],
                qualification_and_checks=marks['qualified'] - marks['ready'],
                queries_plus_validation_audit_publication=marks['cleanup'] - marks['qualified'],
                cleanup_reap=marks['end'] - marks['cleanup'])
            require(sum(record['nonoverlapping_phase_ns'].values()) == record['startup_to_reap_ns'], 'Exact nonoverlapping phase accounting')
        record['passed'] = bool(record['passed'] and not record['forced_cleanup'] and record.get('worker_exited')
            and record.get('watchdog_joined') and record['launcher_exit_code'] == record.get('worker_exit_code') == 0
            and record.get('close_reply', {}).get('result', {}).get('protected_files_unchanged') is True
            and record.get('close_reply', {}).get('result', {}).get('source_file_unchanged') is True)
        native.save(folder / 'RESULT.json', record)
    return record


def analyze(results):
    require(len(results) == 8 and all(row['passed'] for row in results), 'All eight owned sessions passed')
    normalized = {}
    for index, state in enumerate(STATES):
        reference = fact_geometry(results[0]['states'][index]['payload'])
        require(all(fact_geometry(result['states'][index]['payload']) == reference for result in results),
                'All A/B numeric, topology and original witnesses exactly equal apart from method')
        normalized[state] = reference
    metrics = {}
    for index, state in enumerate(STATES):
        versions = {}
        for version in ('A', 'B'):
            rows = [result['states'][index] for result in results if result['version'] == version]
            samples = [row['cli_process_wall_ns'] for row in rows]
            service_samples = [row['original_records']['service_cost']['elapsed_ns'] for row in rows]
            helper_samples = [row['original_records']['helper_audit']['elapsed_ns'] for row in rows]
            versions[version] = dict(cli_wall_ns_samples=samples, median_ns=statistics.median(samples),
                range_ns=[min(samples), max(samples)], stdout_bytes_samples=[row['stdout_bytes'] for row in rows],
                service_elapsed_ns_samples=service_samples, service_median_ns=statistics.median(service_samples),
                service_range_ns=[min(service_samples), max(service_samples)],
                helper_elapsed_ns_samples=helper_samples, helper_median_ns=statistics.median(helper_samples),
                helper_range_ns=[min(helper_samples), max(helper_samples)],
                actual_call_deltas=[row['actual_call_delta'] for row in rows],
                new_surface_work=[row['new_surface_work'] for row in rows])
        pair_improvements = []
        for pair in range(4):
            members = results[2 * pair:2 * pair + 2]
            own = {result['version']: result['states'][index]['cli_process_wall_ns'] for result in members}
            pair_improvements.append(own['A'] - own['B'])
        median_a, median_b = versions['A']['median_ns'], versions['B']['median_ns']
        allowance = max(5_000_000, median_a * .05)
        metrics[state] = dict(versions=versions, paired_improvement_ns=pair_improvements,
            pairs_improved=sum(value > 0 for value in pair_improvements), median_improvement_ns=median_a - median_b,
            threshold_or_regression_allowance_ns=allowance)
    closed = metrics['closed_separated_cold']
    cold_work = {version: [row['states'][1]['new_surface_work'][0] for row in results if row['version'] == version]
                 for version in ('A', 'B')}
    for version in ('A', 'B'):
        require(all(row == cold_work[version][0] for row in cold_work[version]), 'Identical exact work in each version repeated cold state')
    wa, wb = cold_work['A'][0], cold_work['B'][0]
    require(wa['triangle_pairs'] == wb['triangle_pairs'] == 144, 'Visited triangle-pair meaning retained')
    reductions = {key: 1 - wb[key] / wa[key] for key in
                  ('intersection_tests', 'point_face_tests', 'point_edge_tests', 'edge_edge_tests')}
    algorithm = all(value >= .25 for value in reductions.values())
    zero_work = [row['states'][0]['new_surface_work'][0] for row in results]
    algorithm = algorithm and all(row['intersection_tests'] == 1
        and row['point_face_tests'] == row['point_edge_tests'] == row['edge_edge_tests'] == 0 for row in zero_work)
    algorithm = algorithm and all(not row['states'][2]['new_surface_work'] for row in results)
    complete_query = (closed['median_improvement_ns'] >= closed['threshold_or_regression_allowance_ns']
        and closed['pairs_improved'] >= 3
        and all(metrics[state]['median_improvement_ns'] >= -metrics[state]['threshold_or_regression_allowance_ns']
                for state in ('edge_crossing_cold', 'closed_separated_hot')))
    return dict(quality_gate=True, algorithm_gate=algorithm, closed_narrow_phase_reduction=reductions,
        complete_query_gate=complete_query, recommend='B_for_independent_final_review' if algorithm and complete_query else 'retain_A_close_route',
        metrics=metrics, geometry_equal_except_declared_method=True,
        fixed_pair_session_numbers=[dict(A=1, B=2), dict(A=4, B=3), dict(A=6, B=5), dict(A=7, B=8)],
        scope='four fixed samples per version/category; nested timers are not additive; no p95/model benefit claim')


def main():
    batch_started_ns = time.perf_counter_ns()
    batch_started_utc = utc()
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--a-python', required=True, type=Path)
    parser.add_argument('--b-python', required=True, type=Path)
    parser.add_argument('--a-pin', required=True)
    parser.add_argument('--b-pin', required=True)
    parser.add_argument('--source-count', required=True, type=int)
    parser.add_argument('--b-method', required=True)
    parser.add_argument('--service-entry', required=True, type=Path)
    parser.add_argument('--cutoff-utc', required=True)
    parser.add_argument('--blender', type=Path, default=Path('D:/Tools/blender5.2/blender.exe'))
    args = parser.parse_args()
    args.root = args.root.resolve()
    args.output = args.output.resolve()
    args.service_entry = args.service_entry.resolve()
    args.cutoff = datetime.fromisoformat(args.cutoff_utc.replace('Z', '+00:00'))
    require(args.cutoff.tzinfo is not None, 'Explicit UTC/offset cutoff')
    args.executables = dict(A=args.a_python.resolve(), B=args.b_python.resolve())
    args.pins = dict(A=args.a_pin, B=args.b_pin)
    require(args.a_pin == A_PIN, 'Accepted A baseline source pin')
    args.methods = dict(A='exact_binary64_triangle_surface_features_v1', B=args.b_method)
    unit_path = args.root / 'UNIT_ACCEPTANCE.json'
    unit = native.load(unit_path)
    require(unit['successful'] and unit['tests_run'] == unit['selected_count'] == len(set(unit['selected']))
            and unit['unique_methods'] == 52 and unit['method_executions_including_recovery'] == 53
            and unit['remaining_failures'] == 0, 'Fixed targeted quality gate passed after one fixture recovery')
    recovery = native.load(args.root / 'UNIT_RECOVERY.json')
    require(unit['identity']['source_sha256'] == args.b_pin and recovery['source_drift']['compatible']
            and recovery['identity']['source_sha256'] == args.b_pin,
            'Targeted quality gate matches frozen B source')
    unit_summary = dict(selected=unit['selected_count'], passed=unit['tests_run'], remaining_failed=0,
                        initial_passed=51, initial_errors=1, recovered_methods=1, total_method_executions=53,
                        source_sha256=args.b_pin, record_sha256=native.sha(unit_path))
    registration_path = args.root / 'PREREGISTRATION.json'
    registration = native.load(registration_path)
    require(registration['order'] == list(ORDER) and registration['categories'] == list(STATES)
            and registration['paired_session_indices'] == [[1, 2], [4, 3], [6, 5], [7, 8]]
            and registration['samples_per_version_per_category'] == 4
            and registration['algorithm']['closed_cold_actual_narrow_pair_reduction_min'] == .25,
            'Root preregistration agrees with fixed comparison')
    a_root = args.root.parent / 'engineering_a'
    args.author = a_root / 'author/control'
    args.asset = args.author / 'scene.blend'
    require(native.sha(args.asset) == ASSET_SHA and native.sha(args.author / 'TRUTH.json') == TRUTH_SHA,
            'Fixed original A control asset and truth bytes')
    require(args.source_count == 131, 'Truthful fixed source count')
    helper_hashes = {}
    for name in HELPERS:
        hashes = {version: native.sha(purelib(executable) / 'verification' / (name + '.py'))
                  for version, executable in args.executables.items()}
        require(hashes['A'] == hashes['B'], 'Both installs use identical helper: ' + name)
        helper_hashes[name] = hashes
    require(native.sha(args.service_entry) == native.sha(a_root / 'qa/instrumented_service.py'),
            'Both versions use original A counting adapter bytes')
    checks_path = a_root / 'qa/surface_acceptance.py'
    spec = importlib.util.spec_from_file_location('surface_a_acceptance_checks', checks_path)
    checks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checks)
    args.output.mkdir(parents=True, exist_ok=False)
    protocol = dict(registered_utc=utc(), order=list(ORDER), states=list(STATES), sessions=8,
        observations=24, raw_qualification_reads_max=8, vertex_updates=0, automatic_retries=0,
        fixed_asset_sha256=ASSET_SHA, fixed_truth_sha256=TRUTH_SHA, source_count=131, pins=args.pins,
        methods=args.methods, helper_sha256=helper_hashes, counting_adapter_sha256=native.sha(args.service_entry),
        targeted_suite=unit_summary, root_preregistration_sha256=native.sha(registration_path),
        original_a_acceptance_checks_sha256=native.sha(checks_path), new_query_cutoff_utc=args.cutoff.isoformat(),
        gates=dict(quality='all targeted and real returns correct; same geometry/topology/witness; own source/binding',
            algorithm='closed cold actual intersection and feature work >=25% reduction; edge/hot no extra solve',
            closed_cli='median reduction >=max(5ms,5% of A median) AND >=3/4 paired improvements',
            edge_and_hot_cli='each median regression <=max(5ms,5% of A median)'),
        accounting='session phase intervals partition full startup-to-reap; CLI includes process startup and instrumentation; service/helper nested, not additive')
    native.save(args.output / 'PROTOCOL.json', protocol)
    results = []
    analysis = dict(quality_gate=False, recommend='incomplete_or_quality_failure')
    for sequence, version in enumerate(ORDER, 1):
        result = run_session(args, sequence, version, checks)
        results.append(result)
        if not result['passed']:
            break
    if len(results) == 8 and all(row['passed'] for row in results):
        try:
            analysis = analyze(results)
        except BaseException as exc:
            analysis['error'] = dict(type=type(exc).__name__, message=str(exc))
    batch_finished_ns = time.perf_counter_ns()
    analysis['targeted_suite'] = unit_summary
    summary = dict(started_utc=batch_started_utc, ended_utc=utc(),
        batch_wall_ns=batch_finished_ns - batch_started_ns,
        session_startup_to_reap_ns_total=sum(row['startup_to_reap_ns'] for row in results),
        preparation_and_final_analysis_outside_sessions_ns=batch_finished_ns - batch_started_ns -
            sum(row['startup_to_reap_ns'] for row in results),
        passed=len(results) == 8 and all(row['passed'] for row in results) and analysis['quality_gate'],
        source_count=131, pins=args.pins, fixed_order=list(ORDER),
        observe_count=sum(row['observes_started'] for row in results),
        raw_readback_count=sum(row['raw_readbacks_started'] for row in results),
        qa_update_count=0, consumer_answers=0, paid_api_requests=0, sessions=results, analysis=analysis)
    native.save(args.output / 'RESULT.json', summary)
    native.save(args.output / 'ANALYSIS.json', analysis)
    print(json.dumps(dict(passed=summary['passed'], observe_count=summary['observe_count'],
        raw_readback_count=summary['raw_readback_count'], recommendation=analysis['recommend'],
        gates={name: analysis.get(name) for name in ('quality_gate', 'algorithm_gate', 'complete_query_gate')},
        errors=[row.get('error') for row in results] + [analysis.get('error')])))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
