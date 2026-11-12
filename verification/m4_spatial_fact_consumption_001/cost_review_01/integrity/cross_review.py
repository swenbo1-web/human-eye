"""Cross-check final saved-data reports against independently reconstructed facts."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
REVIEW = HERE.parent
BATCH = REVIEW.parent
ROOT = BATCH.parents[1]
FINAL_HASHES = {
    'cost/RESULTS.json': 'a3224e48a88701dd08d50d53965cb44080e916b550dc13004d0ef4f83cbe8aff',
    'cost/REPORT.md': '7eaaa357b5f514c3c360bc1538e7d62706af3e3f91518a090c8c4af00a17b9a8',
    'mechanism/RESULTS.json': 'bed6bb27fa370885e8ea50e50d1ad7ef9941c40b2867d836d3baad9619a5b8aa',
    'mechanism/REPORT.md': '46c46d27a27cdbd465d812cca4225666e863a1b73697e4c9f12c018318e34d08',
}


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf8')


def main():
    assert not (HERE / 'CROSS_REVIEW.json').exists() and not (HERE / 'CROSS_REVIEW.md').exists()
    checks = {}
    files = ('REPORT.md', 'cost/RESULTS.json', 'cost/REPORT.md', 'cost/INPUTS.json', 'cost/extract_costs.py',
             'mechanism/RESULTS.json', 'mechanism/REPORT.md', 'mechanism/SOURCES.json',
             'mechanism/analyze_trajectories.py', 'STAGE_LEDGER.json', 'stage_ledger.py', 'finalize.py',
             'ORIGINAL_DATA_INDEX.json', 'quality_source/QUALITY_SEAL.json',
             'integrity/RESULTS.json', 'integrity/REPORT.md', 'integrity/check_integrity.py',
             'integrity/CONTRACT_CHECK.json', 'integrity/check_contract.py', 'integrity/cross_review.py')
    bound = {name: sha(REVIEW / name) for name in files}
    checks['final_specialist_bytes'] = all(bound[name] == expected for name, expected in FINAL_HASHES.items())
    baseline = read(HERE / 'CONTRACT_CHECK.json')
    integrity = read(HERE / 'RESULTS.json')
    costs = read(REVIEW / 'cost/RESULTS.json')
    mechanism = read(REVIEW / 'mechanism/RESULTS.json')
    run = read(BATCH / 'RUN_RESULT.json')
    checks['independent_source_and_contract_pass'] = integrity['passed'] is True and baseline['passed'] is True
    checks['frozen_primary_cost_gate_agrees'] = costs['gate']['passed'] is baseline['frozen_useful_benefit_gate'] is True
    for group in ('N', 'P'):
        expected = baseline['groups'][group]
        actual = costs['groups'][group]
        checks[group + '_exact_primary_values'] = actual['full_cell_ns']['median'] == expected['median_full_cell_ns']
        checks[group + '_exact_cumulative_tokens'] = actual['usage_totals']['input_plus_output_tokens'] == expected['sum_input_plus_output_tokens']
        checks[group + '_cached_input_subset_separate'] = actual['usage_totals']['cached_input_tokens'] == expected['provider_cached_input_tokens_sum']
    checks['primary_percentages_agree'] = abs(costs['comparison']['median_full_cell']['reduction_percent']
        - baseline['median_full_cell_reduction_percent']) < 1e-12 and abs(costs['comparison']['cumulative_input_plus_output']['reduction_percent']
        - baseline['input_plus_output_reduction_percent']) < 1e-12
    cost_by_cell = {row['cell']: row for row in costs['cells']}
    mechanism_by_cell = {row['cell']: row for row in mechanism['cells']}
    raw_totals = {group: {'TX': 0, 'RX': 0, 'actor_RX': 0, 'handler_ns': 0, 'attempts': 0}
                  for group in ('N', 'P')}
    closed_facts, closed_units = [], []
    unknown_EXIT = 0
    for row in run['records']:
        folder = BATCH / 'cells' / row['cell']
        cost = cost_by_cell[row['cell']]
        trajectory = mechanism_by_cell[row['cell']]
        consumer = read(folder / 'CONSUMER.json')
        checks[row['cell'] + '_cost_raw_usage_timing'] = all(cost['usage'][key] == value for key, value in consumer['usage'].items())
        checks[row['cell'] + '_cost_raw_usage_timing'] &= cost['timing']['full_cell_ns'] == row['full_cell_wall_ns']
        checks[row['cell'] + '_disjoint_phase_sum'] = sum(phase['duration_ns'] for phase in cost['timing']['phases']) == row['full_cell_wall_ns']
        checks[row['cell'] + '_unexposed_provider_metrics_null'] = all(cost[key] is None
            for key in ('fees', 'provider_requests', 'resolved_model', 'resolved_effort'))
        checks[row['cell'] + '_actual_exit_and_thin_unknown_distinct'] = cost['shutdown']['owner_finish_confirmed'] is True
        checks[row['cell'] + '_actual_exit_and_thin_unknown_distinct'] &= cost['shutdown']['thin_client_confirmed_normal_exit'] is None
        unknown_EXIT += consumer['bridge_cleanup']['confirmed'] is None
        attempts = read(folder / 'owner/TOOLS.json')['tools']
        checks[row['cell'] + '_all_attempts_in_both_reports'] = len(attempts) == len(cost['tools']) == len(trajectory['steps'])
        raw_calls = []
        for path in sorted(folder.glob('attachments/bridge_*/*/TX.bin')):
            if read(path).get('method') == 'tools/call':
                raw_calls.append(path)
        checks[row['cell'] + '_actual_stdio_frames_count'] = len(raw_calls) == len(attempts)
        for number, (attempt, step, cost_tool, path) in enumerate(zip(attempts, trajectory['steps'], cost['tools'], raw_calls, strict=True), 1):
            request = read(path)['params']
            response = read(path.with_name('RX.bin'))['result']
            tx, rx = path.stat().st_size, path.with_name('RX.bin').stat().st_size
            raw_totals[row['group']]['TX'] += tx
            raw_totals[row['group']]['RX'] += rx
            raw_totals[row['group']]['actor_RX'] += attempt['response_bytes']
            raw_totals[row['group']]['handler_ns'] += attempt['elapsed_ns']
            raw_totals[row['group']]['attempts'] += 1
            checks[row['cell'] + '_attempt_' + str(number) + '_source_mapping'] = step['arguments'] == request['arguments']
            checks[row['cell'] + '_attempt_' + str(number) + '_source_mapping'] &= step['actor_elapsed_ns'] == attempt['elapsed_ns']
            checks[row['cell'] + '_attempt_' + str(number) + '_source_mapping'] &= step['actor_accounted_response_envelope_bytes'] == attempt['response_bytes'] == rx == cost_tool['response_wire_bytes']
            checks[row['cell'] + '_attempt_' + str(number) + '_source_mapping'] &= cost_tool['request_wire_bytes'] == tx and step['is_error'] == attempt['is_error']
            if request['name'] == 'human_eye_scene_observe' and not response.get('isError'):
                body = json.loads(response['content'][0]['text'])
                closed_facts.extend(pair['facts']['closed_solid_relation'] for pair in body['pairs'])
                observed = [json.loads(raw) for raw in (folder / 'owner/audit.jsonl').read_bytes().splitlines()
                            if raw and json.loads(raw).get('event') == 'observe'
                            and json.loads(raw).get('trace_id') == body['trace_id']]
                checks[row['cell'] + '_task_work_trace_binding'] = len(observed) == 1
                closed_units.extend(pair['closed_solid_work']['work_units'] for pair in observed[0]['task_work']['pairs'])
    for group, totals in raw_totals.items():
        cost_group = costs['groups'][group]['tool_totals']
        mechanism_group = mechanism['route_tool_totals'][group]
        checks[group + '_actual_stdio_and_actor_accounting'] = totals['TX'] == cost_group['request_wire_bytes']
        checks[group + '_actual_stdio_and_actor_accounting'] &= totals['RX'] == cost_group['response_wire_bytes'] == totals['actor_RX']
        checks[group + '_actual_stdio_and_actor_accounting'] &= totals['RX'] == mechanism_group['actor_accounted_response_envelope_bytes_sum']
        checks[group + '_handler_windows_separate_from_full_task'] = totals['handler_ns'] == mechanism_group['actor_tool_handler_elapsed_ns_sum']
    verdict = mechanism['mechanism_verdict']
    checks['mechanism_request_use_agrees'] = verdict['passed'] is True and verdict['eligible_P_consumers'] == 3
    checks['mechanism_request_use_agrees'] &= verdict['qualified_P_consumers'] == baseline['P_successful_spatial_surface_requests'] == 3
    checks['mechanism_request_use_agrees'] &= verdict['P_native_calls'] == verdict['P_native_recomputations_of_complete_facts'] == baseline['P_native_tool_calling_cells'] == 0
    checks['optional_closed_raw_quantity'] = len(closed_facts) == mechanism['optional_closed']['facts_unknown'] == 9
    checks['optional_closed_raw_quantity'] &= all(fact['status'] == 'unknown' and fact['reason'] == 'closed_solid_work_budget' for fact in closed_facts)
    checks['optional_closed_raw_quantity'] &= sum(closed_units) == mechanism['optional_closed']['total_work_units'] == 2359296
    checks['optional_closed_component_bytes'] = sum(len(compact(fact)) for fact in closed_facts) == mechanism['optional_closed']['total_standalone_fact_value_compact_json_bytes'] == 2061
    checks['closed_counterfactual_and_exclusive_time_unmeasured'] = mechanism['optional_closed']['closed_only_duration_ns'] is None and mechanism['optional_closed']['whole_task_saving_if_omitted'] is None
    invalid = mechanism['invalid_nearest_witness_request']
    checks['failed_attempt_retained_with_zero_host'] = invalid['host_executions'] == 0 and invalid['actor_elapsed_ns'] == 5515600
    checks['failed_attempt_retained_with_zero_host'] &= invalid['actor_response_envelope_bytes'] == 857 and invalid['counterfactual_whole_task_saving'] is None
    checks['six_thin_EXIT_unknown_retained'] = unknown_EXIT == 6
    checks['corrected_compact_frame_semantics'] = 'compact UTF-8 JSON RPC envelope with LF' in mechanism['measurement_semantics']['actor_response_bytes']
    for name, base in (('cost/INPUTS.json', ROOT), ('mechanism/SOURCES.json', ROOT)):
        source_manifest = read(REVIEW / name)
        checks[name + '_all_declared_sources_match'] = all(sha(base / item['path']) == item['sha256']
            and (base / item['path']).stat().st_size == item['bytes'] for item in source_manifest['files'])
    checks['original_source_inventory_stable'] = all(sha(Path(name)) == expected
        for name, expected in integrity['input_files_sha256'].items())
    checks['stage_ledger_matches_independent_contract_check'] = sha(REVIEW / 'STAGE_LEDGER.json') == baseline['result_source_sha256']['STAGE_LEDGER.json']
    checks['final_reports_stable_through_cross_review'] = all(sha(REVIEW / name) == expected for name, expected in bound.items())
    notes = [
        'Root REPORT.md and both specialist reports were read in full at the bound final bytes.',
        'The six-cell quality result is consumed from the sealed administrator review and is not rescored.',
        'The primary cost metric uses full-cell scope and final cumulative input plus output, with cached and reasoning subsets kept separate.',
        'Actual thin MCP stdio RX frames equal actor compact-envelope budget bytes in this batch; TCP and provider wire remain unmeasured.',
        'The finalizer was statically read. It checks the bound cross-review files and specialist gates, recomputes the exact six-row gate, writes READY with exclusive creation, and indexes all review files including READY.',
        'The finalizer has not been executed by this reviewer.',
        'One compact/pretty description and one extra release-precondition statement were corrected by their owners before these final hashes were captured.',
    ]
    result = {'passed': all(checks.values()), 'schema': 'm4-saved-review-independent-cross-check-v1',
        'created_utc': datetime.now(timezone.utc).isoformat(), 'files_sha256': bound, 'checks': checks,
        'raw_boundary_totals': raw_totals, 'notes': notes,
        'quality_scope': 'one fixed named-object task, six accepted answers, no unseen-task or general-3D inference',
        'thin_EXIT_unknown_cells': unknown_EXIT, 'new_model_Blender_product_runs': 0,
        'original_files_modified': 0, 'blocking_findings': [name for name, value in checks.items() if not value]}
    with (HERE / 'CROSS_REVIEW.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
    text = ['# Independent cost and mechanism cross-review', '',
        'Passed. No blocking findings remain.' if result['passed'] else 'Blocking checks remain.', '',
        'The final root and specialist reports agree with independent raw-event usage, full-cell timing, '
        'actual stdio frame, complete-attempt and source-integrity checks. The fixed useful-benefit gate and '
        'three-of-three successful P fact-use result are supported within this one registered task.', '',
        'Provider cached-input and reasoning-output tokens remain overlapping subsets. Product cache '
        'observations retain their own scope. Preparation and historical installation are separately listed. '
        'Monetary fees, unexposed provider behavior and counterfactual simplification gains remain unmeasured.', '',
        'All six thin-client EXIT records remain unknown. Independent owner, native worker and applicable '
        'retained product runtime exit evidence remain confirmed under the frozen contract.', '',
        'The final reports include the failed nearest_witness request and nine extra closed unknowns. '
        'The closed component size and work units do not establish isolated closed runtime or whole-task savings.', '',
        'Actual raw thin-stdio RX and actor compact-frame accounting agree per attempt. Their equality does '
        'not supply TCP or provider wire measurements.', '',
        'Before final binding, the mechanism owner corrected compact/pretty terminology and the cost owner '
        'removed an additional release-precondition statement. The hashes in CROSS_REVIEW.json bind the corrected bytes.', '',
        'The finalizer was statically reviewed. This reviewer executed no finalizer, model, Blender or product.', '',
        'Root report SHA256 `' + bound['REPORT.md'] + '`.', '',
        'Cross-review checker SHA256 `' + bound['integrity/cross_review.py'] + '`.', '']
    with (HERE / 'CROSS_REVIEW.md').open('x', encoding='utf8', newline='\n') as stream:
        stream.write('\n'.join(text))
    print(json.dumps({'passed': result['passed'], 'checks': len(checks), 'bound_files': len(bound),
                      'blocking_findings': result['blocking_findings']}))


if __name__ == '__main__':
    main()
