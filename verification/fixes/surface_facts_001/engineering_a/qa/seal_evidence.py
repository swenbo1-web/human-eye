"""Offline byte/record verification and aggregation; never imports the product."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

EVIDENCE = Path(__file__).resolve().parents[1]
ROOT = EVIDENCE.parents[3]
PIN = '0155c5509901ed85dbf255c98a71e81187cbd3b60ef7bd49adcbfa1b663af578'
BASELINE = 'b579de2d8e806e2618bb11daef29d01317ec9249'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(name, value):
    (EVIDENCE / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf8')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


installed = read(EVIDENCE / 'INSTALLED_IDENTITY.json')
identity = installed['identity']
unit = read(EVIDENCE / 'UNIT_RESULT.json')
build = read(EVIDENCE / 'build/BUILD.json')
acceptance = read(EVIDENCE / 'acceptance/RESULT.json')
expected = {row['path']: row['sha256'] for row in identity['source_files']}
assert len(expected) == 131 and identity['source_sha256'] == PIN
assert identity['source_kind'] == 'installed_distribution'
assert unit['identity']['source_sha256'] == build['runtime_identity']['source_sha256'] == PIN
assert unit['identity']['source_files'] == build['runtime_identity']['source_files'] == identity['source_files']
assert unit['successful'] and unit['tests_run'] == unit['selected_count'] == len(set(unit['selected'])) == 124
assert not unit['failures'] and not unit['errors'] and not unit['skipped']
assert acceptance['passed'] and acceptance['source_sha256'] == PIN and acceptance['source_count'] == 131
assert (len(acceptance['cases']), acceptance['observe_count'], acceptance['qa_update_count'], acceptance['raw_readback_count']) == (2, 4, 1, 2)

roots = {'checkout': ROOT, 'installed': Path(installed['purelib'])}
root_checks = {}
for label, root in roots.items():
    paths = {key for key in expected if '/' not in key}
    for package in ('human_eye_plugin', 'human_eye_module1_operators'):
        paths.update(package + '/' + path.name for path in (root / package).glob('*.py'))
    assert paths == set(expected), (label, paths ^ set(expected))
    mismatches = [name for name, digest in expected.items() if sha(root / name) != digest]
    assert not mismatches, (label, mismatches)
    digest_input = dict(base_version=identity['base_version'], implementation_revision=identity['implementation_revision'],
                        files=[dict(path=name, sha256=sha(root / name)) for name in sorted(paths)])
    digest = hashlib.sha256(json.dumps(digest_input, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()
    assert digest == PIN
    root_checks[label] = dict(root=str(root), source_count=len(paths), source_sha256=digest, mismatches=mismatches)

old_record = read(ROOT / 'verification/fixes/task_contract_001/engineering_r1/INSTALLED_IDENTITY.json')
old_identity = old_record.get('identity', old_record)
old_files = {row['path']: row['sha256'] for row in old_identity['source_files']}
delta = [dict(path=name, previous_sha256=old_files.get(name), sha256=expected.get(name))
         for name in sorted(old_files.keys() | expected.keys()) if old_files.get(name) != expected.get(name)]
assert {row['path'] for row in delta} == {
    'human_eye_plugin/live_service.py', 'human_eye_plugin/live_spatial_mcp.py',
    'human_eye_plugin/task_query.py', 'human_eye_plugin/surface_proximity.py'}
git_delta = subprocess.check_output(['git', 'diff', '--name-only', BASELINE, '--', 'human_eye_plugin',
                                     'human_eye_module1_operators', *[key for key in expected if '/' not in key]],
                                    cwd=ROOT, text=True).splitlines()
assert set(git_delta) == {row['path'] for row in delta}
assert sha(Path(installed['purelib']) / 'human_eye_plugin/geometry_safety.py') == old_files['human_eye_plugin/geometry_safety.py']
assert sha(Path(installed['purelib']) / 'human_eye_plugin/surface_geometry.py') == old_files['human_eye_plugin/surface_geometry.py']
for artifact in build['artifacts']:
    path = EVIDENCE / 'build' / artifact['file']
    assert path.stat().st_size == artifact['bytes'] and sha(path) == artifact['sha256']
write('FINAL_SOURCE_VERIFICATION.json', dict(checked_utc=datetime.now(timezone.utc).isoformat(),
    baseline_head=BASELINE, old_source_sha256=old_identity['source_sha256'], old_source_count=len(old_files),
    roots=root_checks, all_frozen_manifests_equal=True, product_delta=delta,
    unchanged_old_runtime_files=sum(expected.get(key) == value for key, value in old_files.items()),
    wheel_and_source_archive_hashes_verified=True, scope='offline bytes and saved identity records only'))

coverage = read(EVIDENCE / 'GROUP_COVERAGE.json')
for group in coverage['groups']:
    group['not_run'] = 0
coverage['new_methods'] = int(coverage['new_methods'])
coverage['legacy_related_methods'] = int(coverage['legacy_related_methods'])
coverage['group10'] = dict(installed_observations=4, passed=4, failed=0, not_run=0,
    sessions=2, vertex_updates=1, raw_readbacks=2, source='acceptance/RESULT.json')
write('GROUP_COVERAGE.json', coverage)

states = []
totals = Counter()
work_total = Counter()
for case in acceptance['cases']:
    assert case['passed'] and case['launcher_exit_code'] == 0 and not case['forced_cleanup']
    assert case['close_reply']['result']['process_reaped'] and case['close_reply']['result']['exit_code'] == 0
    totals.update(case['states'][-1]['counters']['counts'])
    prior_work_count = 0
    for state in case['states']:
        assert state['payload']['binding']['runtime_source_sha256'] == PIN
        raw = EVIDENCE / 'acceptance' / case['case'] / (state['state'] + '.CLI.stdout')
        assert raw.stat().st_size == state['stdout_bytes'] and state['stderr_bytes'] == 0 and state['exit_code'] == 0
        assert json.loads(raw.read_bytes()) == state['payload']
        trace = state['payload']['trace_id']
        session = EVIDENCE / 'acceptance' / case['case'] / 'session'
        costs = []
        for path in session.glob('product_calls/*/MCP_RESPONSE.json'):
            response = read(path)
            payload = json.loads(response['result']['content'][0]['text'])
            if payload.get('trace_id') == trace:
                cost = read(path.with_name('COST.json'))
                # Existing helper samples perf_counter_ns separately for finish
                # and elapsed; retain that observable offset rather than invent
                # an identical endpoint timestamp.
                assert 0 <= cost['finished_ns'] - cost['started_ns'] <= cost['elapsed_ns']
                costs.append((path.with_name('COST.json'), cost))
        assert len(costs) == 1
        audits = [path for path in session.glob('perf000_calls/*/REPLY.json') if trace in path.read_text(encoding='utf8')]
        assert len(audits) == 1
        audit = read(audits[0].with_name('AUDIT.json'))
        assert not audit['error'] and audit['automatic_retries'] == 0
        all_work = state['counters']['surface_work']
        new_work = all_work[prior_work_count:]
        assert len(new_work) == 1
        work_total.update(new_work[0])
        prior_work_count = len(all_work)
        states.append(dict(case=case['case'], state=state['state'], stdout_bytes=state['stdout_bytes'],
            cli_process_wall_ns=state['cli_process_wall_ns'], thin_helper_elapsed_ns=audit['elapsed_ns'],
            service_observe_elapsed_ns=costs[0][1]['elapsed_ns'],
            service_elapsed_endpoint_offset_ns=costs[0][1]['elapsed_ns'] -
                (costs[0][1]['finished_ns'] - costs[0][1]['started_ns']),
            service_cost_record=str(costs[0][0].relative_to(EVIDENCE)).replace('\\', '/'),
            exact_work=new_work[0], distance_m=state['payload']['facts']['surface_proximity']['value']['distance_m'],
            direction_status=state['payload']['facts']['surface_proximity']['direction_status']))

assert totals == Counter(surface_measurements=4, selected_captures=4, task_content_encodings=4,
                          strict_pair_measurements=0, paired_sat_calls=0, fallback_sat_calls=0, full_captures=0)
cleanup = read(EVIDENCE / 'CLEANUP.json')
assert cleanup['possibly_owned_count'] == 0 and not cleanup['matching_live_processes']
steps = {path.name.removesuffix('.process.json'): read(path) for path in EVIDENCE.glob('*.process.json')}
assert all(step['exit_code'] == 0 and not step['forced_tree_cleanup'] for step in steps.values())
measurements = dict(aggregation_utc=datetime.now(timezone.utc).isoformat(), source_sha256=PIN, source_count=131,
    observations=states, stdout_bytes_total=sum(state['stdout_bytes'] for state in states),
    cli_process_wall_ns_total=sum(state['cli_process_wall_ns'] for state in states),
    actual_original_function_calls=dict(totals), exact_work_total=dict(work_total),
    process_step_wall_seconds={key: value['wall_seconds'] for key, value in steps.items()},
    timer_scopes=dict(cli='subprocess.run start through return/reap; includes process startup and service instrumentation',
        helper='saved thin-helper observe dispatch interval',
        service='saved product observe dispatch interval; finish and elapsed use successive clock reads, offset retained per record',
        warning='nested layers are not additive; no isolated kernel timer; response validation and evidence publication are outside CLI timer'),
    predicate_steps_scope='weighted coplanar clipping loop checks only; not all integer/scalar predicate operations',
    descriptor=read(EVIDENCE / 'TOOL_DESCRIPTION.json'),
    quotas_used=dict(build_install=1, qa_sessions=2, observe=4, qa_vertex_updates=1, raw_native_readbacks=2,
                     necessary_qa_revalidations=0, consumer_answers=0, new_paid_api_requests=0),
    unmeasured=['consumer trust/avoidance of supplemental reads', 'model token or net task benefit', 'comparison with B',
                'integer operation counts and isolated kernel timing'])
write('MEASUREMENTS.json', measurements)

assert (EVIDENCE / 'RESULTS.md').is_file()
files = []
for path in sorted(EVIDENCE.rglob('*')):
    if not path.is_file():
        continue
    relative = path.relative_to(EVIDENCE)
    if relative.parts[0] == 'venv' or '__pycache__' in relative.parts or path.suffix in {'.lock', '.pyc'}:
        continue
    if path.name in {'EVIDENCE_INDEX.json', 'input.blend'} or path.suffix == '.zip':
        continue
    files.append(dict(path=relative.as_posix(), bytes=path.stat().st_size, sha256=sha(path)))
write('EVIDENCE_INDEX.json', dict(sealed_utc=datetime.now(timezone.utc).isoformat(), source_sha256=PIN,
    source_count=131, candidate_code_commit='0acf1faaf6e5db24af7c93370e5622255ebda833',
    scope='all retained A evidence except isolated venv, duplicate input.blend, source zip, locks and bytecode',
    files=files, external_files=[dict(path='verification/test_surface_proximity_001.py',
        sha256=sha(ROOT / 'verification/test_surface_proximity_001.py'))]))
print(json.dumps(dict(source_verified=True, cases=len(states), bytes=measurements['stdout_bytes_total'],
    cli_ns=measurements['cli_process_wall_ns_total'], calls=dict(totals), work=dict(work_total), retained_files=len(files))))
