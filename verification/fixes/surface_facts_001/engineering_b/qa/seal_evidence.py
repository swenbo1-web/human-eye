"""Offline B byte/record sealing. No product imports, queries or gate changes."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import traceback
import zipfile

EVIDENCE = Path(__file__).resolve().parents[1]
ROOT = EVIDENCE.parents[3]
A_ROOT = EVIDENCE.parent / 'engineering_a'
A_PIN = '0155c5509901ed85dbf255c98a71e81187cbd3b60ef7bd49adcbfa1b663af578'
A_INDEX_SHA = 'bc911082594d6a55541223599541a6cd8a25e4209859f3003c9564b90a652a7c'
BASELINE = 'e053683ddc785d8b07366cfa8be68b9a03ac15c0'
ORDER = ['A', 'B', 'B', 'A', 'B', 'A', 'A', 'B']
STATES = ['edge_crossing_cold', 'closed_separated_cold', 'closed_separated_hot']
RUNTIME_DELTA = {'human_eye_plugin/surface_proximity.py', 'human_eye_plugin/task_query.py'}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(name, value):
    (EVIDENCE / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf8')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def manifest(identity):
    rows = identity['source_files']
    result = {row['path']: row['sha256'] for row in rows}
    assert len(rows) == len(result) == 131, '131 distinct runtime files'
    return result


def source_digest(identity, actual):
    value = dict(base_version=identity['base_version'], implementation_revision=identity['implementation_revision'],
                 files=[dict(path=name, sha256=digest) for name, digest in sorted(actual.items())])
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


def verify_disk(label, root, identity):
    expected = manifest(identity)
    names = {name for name in expected if '/' not in name}
    for package in ('human_eye_plugin', 'human_eye_module1_operators'):
        names.update(package + '/' + path.name for path in (root / package).glob('*.py'))
    assert names == set(expected), (label, 'runtime enumeration changed', names ^ set(expected))
    actual = {name: sha(root / name) for name in sorted(names)}
    assert actual == expected, (label, 'runtime bytes differ')
    digest = source_digest(identity, actual)
    assert digest == identity['source_sha256'], (label, 'runtime digest differs')
    return dict(root=str(root), source_count=len(actual), source_sha256=digest, mismatches=[])


def main():
    installed = read(EVIDENCE / 'INSTALLED_IDENTITY.json')
    identity = installed['identity']
    pin = identity['source_sha256']
    assert pin != A_PIN and identity['source_kind'] == 'installed_distribution'
    b_manifest = manifest(identity)
    initial_unit = read(EVIDENCE / 'UNIT_RESULT.json')
    recovery_unit = read(EVIDENCE / 'UNIT_RECOVERY.json')
    unit = read(EVIDENCE / 'UNIT_ACCEPTANCE.json')
    freeze = read(EVIDENCE / 'FREEZE.json')
    build = read(EVIDENCE / 'build/BUILD.json')
    comparison = read(EVIDENCE / 'comparison/RESULT.json')
    analysis = read(EVIDENCE / 'comparison/ANALYSIS.json')
    protocol = read(EVIDENCE / 'comparison/PROTOCOL.json')
    registration = read(EVIDENCE / 'PREREGISTRATION.json')
    assert comparison['analysis'] == analysis, 'Saved analysis preserved without recalculating gates'
    assert unit['identity']['source_sha256'] == build['runtime_identity']['source_sha256'] == pin
    assert unit['identity']['source_files'] == build['runtime_identity']['source_files'] == identity['source_files']
    assert freeze['source_sha256'] == initial_unit['identity']['source_sha256'] == recovery_unit['identity']['source_sha256'] == pin
    assert freeze['source_files'] == identity['source_files']
    assert unit['tests_run'] == unit['selected_count'] == unit['unique_methods'] == len(set(unit['selected'])) == 52
    assert initial_unit['selected'] == unit['selected'] and initial_unit['tests_run'] == 52
    assert not initial_unit['failures'] and not initial_unit['skipped'] and len(initial_unit['errors']) == 1
    assert not initial_unit['successful']
    assert recovery_unit['selected'] == [initial_unit['errors'][0][0]] and recovery_unit['tests_run'] == 1
    assert recovery_unit['successful'] and not recovery_unit['failures'] and not recovery_unit['errors'] and not recovery_unit['skipped']
    assert recovery_unit['source_drift']['compatible'] and initial_unit['source_drift']['compatible']
    assert unit['method_executions_including_recovery'] == initial_unit['tests_run'] + recovery_unit['tests_run'] == 53
    assert unit['successful'] and unit['remaining_failures'] == unit['remaining_qa_recovery_allowance'] == 0
    assert unit['initial_passed'] == 51 and unit['initial_errors'] == unit['recovered_methods'] == 1
    before_test = EVIDENCE / 'qa/test_surface_proximity_pruning_001.before_recovery.txt'
    after_test = ROOT / 'verification/test_surface_proximity_pruning_001.py'
    assert sha(before_test) == freeze['tests']['test_surface_proximity_pruning_001.py'] == recovery_unit['before_test_sha256']
    assert sha(after_test) == recovery_unit['after_test_sha256']
    assert after_test.read_bytes() == before_test.read_bytes().replace(
        b"RequestBudgetError('request_deadline_exceeded')", b"RequestBudgetError('expired', 'surface_proximity_pair')")
    before_runner = EVIDENCE / 'qa/surface_comparison.before_recovery.txt'
    after_runner = EVIDENCE / 'qa/surface_comparison.py'
    assert sha(before_runner) == freeze['fixed_inputs']['qa/surface_comparison.py']
    before_runner_bytes, after_runner_bytes = before_runner.read_bytes(), after_runner.read_bytes()
    def split_preflight(blob):
        start = blob.index(b'    unit_path = args.root / ')
        end = blob.index(b'    registration_path = args.root / ')
        return blob[:start], blob[start:end], blob[end:]
    before_regions, after_regions = split_preflight(before_runner_bytes), split_preflight(after_runner_bytes)
    assert before_regions[0] == after_regions[0] and before_regions[2] == after_regions[2], 'Runner changes limited to unit preflight'
    runner_diff = read(EVIDENCE / 'qa/RUNNER_RECOVERY_DIFF.json')
    assert runner_diff['before_sha256'] == sha(before_runner) and runner_diff['after_sha256'] == sha(after_runner)
    assert runner_diff['old_block'].encode('utf8') == before_regions[1]
    assert runner_diff['new_block'].encode('utf8') == after_regions[1]
    frozen_inputs = []
    for name, before_sha in freeze['fixed_inputs'].items():
        after_sha = sha(EVIDENCE / name)
        changed = before_sha != after_sha
        assert not changed or name == 'qa/surface_comparison.py', ('Unexpected frozen input change', name)
        frozen_inputs.append(dict(path=name, frozen_sha256=before_sha, final_sha256=after_sha, changed=changed,
            change_reason='necessary preflight recovery to read UNIT_ACCEPTANCE plus preserved initial/recovery results' if changed else None))
    recovery_record = dict(allowance_used=1, allowance_remaining=0, unique_methods=52, method_executions=53,
        initial_passed=51, initial_errors=initial_unit['errors'], initial_failures=initial_unit['failures'],
        recovery_passed=1, recovered_method=recovery_unit['selected'][0], final_accepted_methods=52,
        product_source_unchanged=True, fixture_change_exactly_verified=True,
        runner_change_limited_to_unit_preflight_verified=True, frozen_inputs=frozen_inputs)
    assert protocol['pins'] == comparison['pins'] == {'A': A_PIN, 'B': pin}
    assert protocol['order'] == registration['order'] == comparison['fixed_order'] == ORDER
    assert protocol['states'] == registration['categories'] == STATES
    assert protocol['root_preregistration_sha256'] == sha(EVIDENCE / 'PREREGISTRATION.json')
    assert protocol['targeted_suite']['record_sha256'] == sha(EVIDENCE / 'UNIT_ACCEPTANCE.json')

    roots = {
        'B_checkout': verify_disk('B_checkout', ROOT, identity),
        'B_installed': verify_disk('B_installed', Path(installed['purelib']), identity),
    }
    a_installed = read(A_ROOT / 'INSTALLED_IDENTITY.json')
    a_identity = a_installed['identity']
    assert a_identity['source_sha256'] == A_PIN
    a_manifest = manifest(a_identity)
    roots['A_installed_preserved'] = verify_disk('A_installed', Path(a_installed['purelib']), a_identity)
    delta = [dict(path=name, previous_sha256=a_manifest.get(name), sha256=b_manifest.get(name))
             for name in sorted(a_manifest.keys() | b_manifest.keys()) if a_manifest.get(name) != b_manifest.get(name)]
    assert {row['path'] for row in delta} == RUNTIME_DELTA
    assert sum(b_manifest.get(name) == digest for name, digest in a_manifest.items()) == 129
    git_delta = subprocess.check_output(['git', 'diff', '--name-only', BASELINE, '--',
        'human_eye_plugin', 'human_eye_module1_operators', *[name for name in b_manifest if '/' not in name]],
        cwd=ROOT, text=True).splitlines()
    assert set(git_delta) == RUNTIME_DELTA
    a_index_path = A_ROOT / 'EVIDENCE_INDEX.json'
    assert sha(a_index_path) == A_INDEX_SHA, 'A index original bytes'
    a_index = read(a_index_path)
    assert len(a_index['files']) == 183
    for row in a_index['files']:
        path = A_ROOT / row['path']
        assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256'], ('A evidence changed', row['path'])
    for row in a_index.get('external_files', []):
        assert sha(ROOT / row['path']) == row['sha256'], ('A external evidence changed', row['path'])
    wheel_records = []
    for artifact in build['artifacts']:
        path = EVIDENCE / 'build' / artifact['file']
        assert path.stat().st_size == artifact['bytes'] and sha(path) == artifact['sha256']
        if path.suffix == '.whl':
            with zipfile.ZipFile(path) as wheel:
                names = {name for name in wheel.namelist() if name in b_manifest}
                for package in ('human_eye_plugin', 'human_eye_module1_operators'):
                    names.update(name for name in wheel.namelist() if name.startswith(package + '/')
                                 and name.count('/') == 1 and name.endswith('.py'))
                assert names == set(b_manifest)
                actual = {name: hashlib.sha256(wheel.read(name)).hexdigest() for name in sorted(names)}
                assert actual == b_manifest and source_digest(identity, actual) == pin
            wheel_records.append(dict(file=artifact['file'], source_count=131, source_sha256=pin,
                                      bytes=artifact['bytes'], sha256=artifact['sha256']))
    assert len(wheel_records) == 1
    source_result = dict(checked_utc=datetime.now(timezone.utc).isoformat(), baseline_head=BASELINE,
        roots=roots, wheel=wheel_records, all_B_frozen_manifests_equal=True, product_delta=delta,
        unchanged_A_runtime_files=129, A_evidence_files_unchanged=183, A_evidence_index_sha256=A_INDEX_SHA,
        distribution_version=build['distribution_version'], source_count=131, source_sha256=pin,
        necessary_QA_recovery=recovery_record,
        scope='offline current byte hashes and frozen records; no product import or additional execution')
    write('FINAL_SOURCE_VERIFICATION.json', source_result)
    write('SOURCE_DELTA.json', delta)

    assert comparison['source_count'] == 131
    sessions = comparison['sessions']
    assert [row['version'] for row in sessions] == ORDER[:len(sessions)]
    assert len(sessions) <= 8 and comparison['observe_count'] <= 24 and comparison['raw_readback_count'] <= 8
    assert comparison['qa_update_count'] == comparison['consumer_answers'] == comparison['paid_api_requests'] == 0
    assert comparison['observe_count'] == sum(row['observes_started'] for row in sessions)
    assert comparison['raw_readback_count'] == sum(row['raw_readbacks_started'] for row in sessions)
    calls = {'A': Counter(), 'B': Counter()}
    work = {'A': Counter(), 'B': Counter()}
    observations = []
    session_rows = []
    verified_payloads = 0
    for session in sessions:
        version = session['version']
        command = session['command']
        workspace = Path(command[command.index('--workspace') + 1])
        assert workspace.is_relative_to(EVIDENCE / 'comparison')
        folder = workspace.parent
        assert read(folder / 'RESULT.json') == session
        assert len(session['states']) <= 3 and [row['state'] for row in session['states']] == STATES[:len(session['states'])]
        prior_counts = Counter()
        prior_work_count = 0
        for index, state in enumerate(session['states']):
            row = dict(sequence=session['sequence'], version=version, state=state['state'],
                exit_code=state['exit_code'], stdout_bytes=state['stdout_bytes'], stderr_bytes=state['stderr_bytes'],
                cli_process_wall_ns=state['cli_process_wall_ns'])
            raw = folder / (state['state'] + '.CLI.stdout')
            err = folder / (state['state'] + '.CLI.stderr')
            assert raw.stat().st_size == state['stdout_bytes'] and err.stat().st_size == state['stderr_bytes']
            if 'payload' not in state:
                row['not_verified_reason'] = 'transport or payload failure; original stdout/stderr retained'
                observations.append(row)
                continue
            payload = state['payload']
            assert json.loads(raw.read_bytes()) == payload
            assert payload['binding']['runtime_source_sha256'] == comparison['pins'][version]
            row.update(source_sha256=payload['binding']['runtime_source_sha256'],
                       method=payload['facts']['surface_proximity']['method'],
                       scene_revision=payload['binding']['scene_revision'],
                       scene_fingerprint=payload['binding']['scene_fingerprint'])
            if 'counters' not in state or 'original_records' not in state:
                row['not_verified_reason'] = 'response validation failed before full counter/audit collection'
                observations.append(row)
                continue
            counters = read(folder / (state['state'] + '.COUNTS.json'))
            assert counters == state['counters']
            actual_delta = {key: value - prior_counts[key] for key, value in counters['counts'].items()}
            new_work = counters['surface_work'][prior_work_count:]
            assert actual_delta == state['actual_call_delta'] and new_work == state['new_surface_work']
            calls[version].update(actual_delta)
            for item in new_work:
                work[version].update(item)
            prior_counts = Counter(counters['counts'])
            prior_work_count = len(counters['surface_work'])
            originals = state['original_records']
            product_folder = workspace / originals['product_call_folder']
            helper_folder = workspace / originals['helper_call_folder']
            cost = read(product_folder / 'COST.json')
            audit = read(helper_folder / 'AUDIT.json')
            assert cost == originals['service_cost'] and audit == originals['helper_audit']
            response = read(product_folder / 'MCP_RESPONSE.json')
            assert json.loads(response['result']['content'][0]['text']) == payload
            assert payload['trace_id'] in (helper_folder / 'REPLY.json').read_text(encoding='utf8')
            events = [json.loads(line) for line in (workspace / 'product_audit.jsonl').read_text(encoding='utf8').splitlines()]
            observed = [event for event in events if event.get('event') == 'observe' and event.get('trace_id') == payload['trace_id']]
            assert len(observed) == 1 and observed[0] == originals['product_observe_audit']
            assert 0 <= cost['finished_ns'] - cost['started_ns'] <= cost['elapsed_ns']
            assert 0 <= audit['finished_ns'] - audit['started_ns'] <= audit['elapsed_ns']
            row.update(actual_call_delta=actual_delta, new_surface_work=new_work,
                service_observe_elapsed_ns=cost['elapsed_ns'], thin_helper_elapsed_ns=audit['elapsed_ns'],
                service_elapsed_endpoint_offset_ns=cost['elapsed_ns'] - (cost['finished_ns'] - cost['started_ns']),
                helper_elapsed_endpoint_offset_ns=audit['elapsed_ns'] - (audit['finished_ns'] - audit['started_ns']),
                task_work=observed[0]['task_work'], complete_geometry_verified=bool(state.get('verified', {}).get('complete')))
            if state.get('verified', {}).get('complete'):
                verified_payloads += 1
            if session['passed']:
                assert not cost['error'] and not audit['error'] and audit['automatic_retries'] == 0
                assert actual_delta['selected_captures'] == actual_delta['task_content_encodings'] == 1
                assert actual_delta['surface_measurements'] == len(new_work) == int(index < 2)
                assert observed[0]['task_work']['surface_pair_cache_hit'] is (index == 2)
                assert observed[0]['task_work']['surface_pair_count'] == int(index < 2)
            observations.append(row)
        phases = session.get('nonoverlapping_phase_ns')
        if phases is not None:
            assert sum(phases.values()) == session['startup_to_reap_ns']
        session_rows.append(dict(sequence=session['sequence'], version=version, passed=session['passed'],
            started_utc=session['started_utc'], ended_utc=session['ended_utc'],
            startup_to_reap_ns=session['startup_to_reap_ns'], nonoverlapping_phase_ns=phases,
            launcher_exit_code=session['launcher_exit_code'], worker_exit_code=session.get('worker_exit_code'),
            forced_cleanup=session['forced_cleanup'], error=session.get('error')))
    assert sum(row['startup_to_reap_ns'] for row in sessions) == comparison['session_startup_to_reap_ns_total']
    assert (comparison['session_startup_to_reap_ns_total'] + comparison['preparation_and_final_analysis_outside_sessions_ns']
            == comparison['batch_wall_ns'])
    if comparison['passed']:
        assert len(sessions) == 8 and len(observations) == verified_payloads == comparison['observe_count'] == 24
        assert all(row['passed'] for row in sessions) and analysis['quality_gate']
        assert unit['successful'] and unit['remaining_failures'] == 0
        for version in ('A', 'B'):
            assert calls[version] == Counter(surface_measurements=8, selected_captures=12, task_content_encodings=12,
                strict_pair_measurements=0, paired_sat_calls=0, fallback_sat_calls=0, full_captures=0)
            for state in STATES:
                rows = [row for row in observations if row['version'] == version and row['state'] == state]
                metric = analysis['metrics'][state]['versions'][version]
                assert metric['cli_wall_ns_samples'] == [row['cli_process_wall_ns'] for row in rows]
                assert metric['service_elapsed_ns_samples'] == [row['service_observe_elapsed_ns'] for row in rows]
                assert metric['helper_elapsed_ns_samples'] == [row['thin_helper_elapsed_ns'] for row in rows]
    cleanup = read(EVIDENCE / 'CLEANUP.json')
    assert cleanup['possibly_owned_count'] == 0 and not cleanup['matching_live_processes']
    steps = {path.name.removesuffix('.process.json'): read(path) for path in EVIDENCE.glob('*.process.json')}
    measurement = dict(aggregation_utc=datetime.now(timezone.utc).isoformat(), source_sha256=pin, source_count=131,
        raw_quality_passed=comparison['passed'], fixed_analysis_record='comparison/ANALYSIS.json',
        fixed_analysis_sha256=sha(EVIDENCE / 'comparison/ANALYSIS.json'), analysis_preserved=analysis,
        observations=observations, actual_original_function_calls_by_version={key: dict(value) for key, value in calls.items()},
        exact_new_work_by_version={key: dict(value) for key, value in work.items()},
        exact_work_scope='only newly invoked original surface kernel work; hot historical work not recounted; absent A AABB keys remain absent',
        stdout_bytes_total=sum(row['stdout_bytes'] for row in observations),
        cli_process_wall_ns_total=sum(row['cli_process_wall_ns'] for row in observations),
        by_version={version: dict(stdout_bytes=sum(row['stdout_bytes'] for row in observations if row['version'] == version),
            cli_process_wall_ns=sum(row['cli_process_wall_ns'] for row in observations if row['version'] == version)) for version in ('A', 'B')},
        batch_wall_ns=comparison['batch_wall_ns'], sessions=session_rows,
        session_startup_to_reap_ns_total=comparison['session_startup_to_reap_ns_total'],
        preparation_and_final_analysis_outside_sessions_ns=comparison['preparation_and_final_analysis_outside_sessions_ns'],
        process_steps={key: dict(wall_seconds=value['wall_seconds'], exit_code=value['exit_code'],
            forced_tree_cleanup=value['forced_tree_cleanup'], started_utc=value['started_utc'], ended_utc=value['ended_utc'])
            for key, value in steps.items()},
        selected_unit_methods=unit['selected_count'], unit_methods_run=unit['tests_run'],
        method_executions_including_recovery=unit['method_executions_including_recovery'],
        initial_unit_failures=initial_unit['failures'], initial_unit_errors=initial_unit['errors'], initial_unit_skipped=initial_unit['skipped'],
        necessary_QA_recovery=recovery_record,
        denominators=dict(planned_sessions=8, sessions_started=len(sessions),
            sessions_passed=sum(bool(row['passed']) for row in sessions), sessions_not_started=8 - len(sessions),
            planned_observe=24, observes_started=comparison['observe_count'], verified_payloads=verified_payloads,
            observes_not_started=24 - comparison['observe_count']),
        quotas_used=dict(build_install=1, qa_sessions=len(sessions), observe=comparison['observe_count'],
            qualification_raw_reads=comparison['raw_readback_count'], qa_vertex_updates=0, necessary_QA_recoveries=1,
            remaining_QA_recovery_allowance=0, consumer_answers=0, paid_api_requests=0),
        timer_scopes=dict(batch='includes preflight, sessions and final analysis before summary publication; outer process wall separately retained',
            session='nonoverlapping preparation/startup including asset copy/qualification/queries with validation and audit/cleanup partition startup-to-reap',
            cli='subprocess.run start through return/reap, including process startup and service instrumentation',
            nested='helper and service elapsed fields are nested inside CLI; successive finish/elapsed clock offsets retained; do not add layers'),
        predicate_steps_scope='weighted coplanar clipping loop checks only, not all integer/scalar operations',
        unmeasured=['model consumer behavior or net benefit', 'p95 or population-level timing inference',
                    'uninstrumented performance', 'live MCP in-flight cancellation'])
    write('MEASUREMENTS.json', measurement)
    assert (EVIDENCE / 'RESULTS.md').is_file(), 'Root final report must exist before index sealing'
    files = []
    for path in sorted(EVIDENCE.rglob('*')):
        if not path.is_file():
            continue
        relative = path.relative_to(EVIDENCE)
        if relative.parts[0] == 'venv' or '__pycache__' in relative.parts or path.suffix in {'.lock', '.pyc', '.pyo'}:
            continue
        if path.name in {'EVIDENCE_INDEX.json', 'input.blend'} or path.suffix == '.zip':
            continue
        files.append(dict(path=relative.as_posix(), bytes=path.stat().st_size, sha256=sha(path)))
    external = sorted(RUNTIME_DELTA | {'verification/test_surface_proximity_001.py',
                                       'verification/test_surface_proximity_pruning_001.py'})
    write('EVIDENCE_INDEX.json', dict(sealed_utc=datetime.now(timezone.utc).isoformat(), source_sha256=pin,
        source_count=131, baseline_A_head=BASELINE,
        scope='all retained B evidence, including failures, except isolated venv, duplicate input.blend, source zip, locks, bytecode and self',
        files=files, external_files=[dict(path=name, sha256=sha(ROOT / name)) for name in external]))
    print(json.dumps(dict(source_verified=True, A_evidence_unchanged=183, observed=comparison['observe_count'],
        verified=verified_payloads, bytes=measurement['stdout_bytes_total'], cli_ns=measurement['cli_process_wall_ns_total'],
        recommendation=analysis['recommend'], retained_files=len(files))))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Keep every real seal failure; a later metadata correction cannot erase it.
        number = 1
        while (EVIDENCE / ('SEAL_FAILURE_%03d.json' % number)).exists():
            number += 1
        write('SEAL_FAILURE_%03d.json' % number, dict(utc=datetime.now(timezone.utc).isoformat(),
            error_type=type(exc).__name__, message=str(exc), traceback=traceback.format_exc(),
            scope='offline sealing failure; no product/QA invocation'))
        traceback.print_exc()
        sys.exit(1)
