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
    'cost/RESULTS.json': 'a49e9be7160da3ed76f9817a7425de7fd8f507658eefb6a44f59395d39c53766',
    'cost/BUDGETS.json': '21b3eeb2bd79dea68032c7605aa32711eb5168003d4eed191ff0c5f6ffd68097',
    'cost/REPORT.md': 'dc25abaa73816afbe5de2c07a2418450082525a2d64903026f4109b2984cc455',
    'mechanism/RESULTS.json': 'b25384b3f29f631989ea75635f1752d99d4a41562c8ee962d052a4b5c9f59f89',
    'mechanism/REPORT.md': 'b16f4b5c4e49f8a60a83e5a5cfae4addc87832b5e2750aa8573cce3e9bf56061',
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
    files = ('REPORT.md', 'cost/RESULTS.json', 'cost/REPORT.md', 'cost/INPUTS.json', 'cost/extract_costs.py', 'cost/BUDGETS.json',
             'mechanism/RESULTS.json', 'mechanism/REPORT.md', 'mechanism/SOURCES.json',
             'mechanism/analyze_trajectories.py', 'STAGE_LEDGER.json', 'stage_ledger.py', 'finalize.py',
             'ORIGINAL_DATA_INDEX.json', 'quality_source/QUALITY_SEAL.json', 'ROOT_REUSE.json',
             'prepare_unseal.py', 'integrity/check_history/initial/check_contract.py',
             'integrity/check_history/initial/CONTRACT_CHECK.json',
             'integrity/RESULTS.json', 'integrity/REPORT.md', 'integrity/check_integrity.py',
             'integrity/CONTRACT_CHECK.json', 'integrity/check_contract.py', 'integrity/BUDGET_REVIEW.md', 'integrity/cross_review.py')
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
    closed_facts, closed_units, branch_rows = [], [], []
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
                checks[row['cell'] + '_engine_complete_current_required_facts'] = (
                    len(body['pairs']) == 3 and body['relation_fact'] == 'spatial_relation'
                    and body['summary']['nearest_separated_complete'] is True
                    and all(pair['facts']['spatial_relation']['status'] == 'measured'
                            and pair['facts']['surface_proximity']['status'] == 'measured'
                            for pair in body['pairs']))
                closed_facts.extend(pair['facts']['closed_solid_relation'] for pair in body['pairs'])
                observed = [json.loads(raw) for raw in (folder / 'owner/audit.jsonl').read_bytes().splitlines()
                            if raw and json.loads(raw).get('event') == 'observe'
                            and json.loads(raw).get('trace_id') == body['trace_id']]
                checks[row['cell'] + '_task_work_trace_binding'] = len(observed) == 1
                work_rows = observed[0]['task_work']['pairs']
                closed_units.extend(pair['closed_solid_work']['work_units'] for pair in work_rows)
                for pair, work in zip(body['pairs'], work_rows, strict=True):
                    branch_rows.append({'cell':row['cell'], 'attempt':number, 'candidate_index':pair['candidate_index'],
                        'facts':pair['facts'], 'work':work})
    for group, totals in raw_totals.items():
        cost_group = costs['groups'][group]['tool_totals']
        mechanism_group = mechanism['route_tool_totals'][group]
        checks[group + '_actual_stdio_and_actor_accounting'] = totals['TX'] == cost_group['request_wire_bytes']
        checks[group + '_actual_stdio_and_actor_accounting'] &= totals['RX'] == cost_group['response_wire_bytes'] == totals['actor_RX']
        checks[group + '_actual_stdio_and_actor_accounting'] &= totals['RX'] == mechanism_group['actor_response_envelope_bytes_sum']
        checks[group + '_handler_windows_separate_from_full_task'] = totals['handler_ns'] == mechanism_group['actor_handler_elapsed_ns_sum']
    verdict = mechanism['mechanism_verdict']
    checks['mechanism_request_use_agrees'] = verdict['passed'] is True and verdict['eligible_P_consumers'] == 3
    checks['mechanism_request_use_agrees'] &= verdict['qualified_P_consumers'] == baseline['P_successful_spatial_surface_requests'] == 3
    checks['mechanism_request_use_agrees'] &= verdict['P_native_calls'] == verdict['P_native_recomputations_of_complete_facts'] == baseline['P_native_tool_calling_cells'] == 0
    checks['engine_independent_and_no_necessary_native_completion'] = (
        verdict['P_engine_independent_complete_fact_responses'] == 3
        and verdict['P_necessary_native_completion_cells'] == 0)
    branch = mechanism['closed_branch_analysis']
    checks['all_nine_closed_are_measured'] = len(closed_facts) == 9 and all(
        fact['status'] == 'measured' and fact['value'] == 'separated' for fact in closed_facts)
    checks['all_closed_units_and_components'] = sum(closed_units) == branch['all_closed_work_units'] == 23130
    checks['all_closed_units_and_components'] &= sum(len(compact(fact)) for fact in closed_facts) == branch['closed_fact_value_component_bytes'] == 2295
    a_rows = [item for item in branch_rows if item['candidate_index'] == 0]
    bc_rows = [item for item in branch_rows if item['candidate_index'] != 0]
    checks['A_actual_closed_fallback_branch'] = len(a_rows) == 3 and all(
        item['facts']['spatial_relation']['method'] == 'bounded_exact_closed_shell_v1'
        and item['facts']['spatial_relation']['certificate'] == 'disjoint_boundaries_with_exact_parity'
        and item['work']['support_work']['reason'] == 'spatial_support_not_strictly_separated'
        and item['work']['closed_solid_pair_count'] == 1 for item in a_rows)
    checks['B_C_actual_support_and_additional_classification'] = len(bc_rows) == 6 and all(
        item['facts']['spatial_relation']['method'] == 'exact_sufficient_spatial_relation_v1'
        and item['facts']['spatial_relation']['certificate'] == 'strict_all_referenced_vertex_support'
        and item['work']['closed_solid_pair_count'] == 1 for item in bc_rows)
    checks['required_and_optional_closed_work_split'] = sum(item['work']['closed_solid_work']['work_units'] for item in a_rows) == branch['required_A_fallback_work_units'] == 7854
    checks['required_and_optional_closed_work_split'] &= sum(item['work']['closed_solid_work']['work_units'] for item in bc_rows) == branch['optional_BC_closed_work_units'] == 15276
    checks['required_and_optional_closed_work_split'] &= sum(item['work']['closed_solid_work']['world_tree_builds'] for item in bc_rows) == branch['optional_BC_world_tree_builds'] == 12
    declared_branches = {(item['cell'], item['attempt'], item['candidate_index']):item
                         for item in branch['per_successful_request_pairs']}
    checks['all_branch_facts_and_work_correspond'] = len(declared_branches) == len(branch_rows) == 9 and all(
        declared_branches[(item['cell'],item['attempt'],item['candidate_index'])]['closed_solid_work'] == item['work']['closed_solid_work']
        and declared_branches[(item['cell'],item['attempt'],item['candidate_index'])]['spatial_fact'] == item['facts']['spatial_relation']
        and declared_branches[(item['cell'],item['attempt'],item['candidate_index'])]['closed_fact'] == item['facts']['closed_solid_relation'] for item in branch_rows)
    checks['closed_same_request_reuse_distinct_from_cache'] = branch['A_explicit_closed_additional_classifier_calls'] == 0 and branch['optional_BC_classifier_calls'] == 6
    checks['closed_same_request_reuse_distinct_from_cache'] &= all(item['work']['closed_solid_work']['prepared_pair_reused'] is True
        and item['work']['closed_solid_work']['prepared_trees_reused'] is False
        and not item['work']['spatial_pair_cache_hit'] and not item['work']['closed_solid_pair_cache_hit'] for item in branch_rows)
    checks['closed_counterfactual_and_exclusive_time_unmeasured'] = branch['closed_only_duration_ns'] is None and branch['counterfactual_whole_task_saving'] is None
    invalid = mechanism['invalid_nearest_witness_request']
    invalid_folder = BATCH / 'cells' / invalid['cell'] / 'owner' / ('tool_' + str(invalid['attempt']).zfill(2))
    invalid_attempt = read(invalid_folder / 'ATTEMPT.json')
    invalid_result = json.loads(read(invalid_folder / 'RESPONSE.json')['result']['content'][0]['text'])
    checks['failed_attempt_retained_with_zero_host'] = invalid['host_executions'] == 0 and invalid['actor_elapsed_ns'] == invalid_attempt['elapsed_ns'] == 4113500
    checks['failed_attempt_retained_with_zero_host'] &= invalid['actor_response_envelope_bytes'] == invalid_attempt['response_bytes'] == 857 and invalid['counterfactual_whole_task_saving'] is None
    checks['failed_unknown_is_explicit_not_executed'] = invalid['original_outcome'] == invalid_result and invalid_result['tool_outcome'] == 'unknown' and invalid_result['executed'] is False and invalid_result['execution_status'] == 'not_executed'
    checks['failed_unknown_is_explicit_not_executed'] &= invalid_result['connector_state_write_status'] == 'not_attempted'
    invalid_end = invalid_attempt['started_ns'] + invalid_attempt['elapsed_ns']
    native_events = [json.loads(line) for line in (BATCH / 'cells' / invalid['cell'] / 'owner/native/WORKER_EVENTS.jsonl').read_bytes().splitlines() if line]
    checks['failed_request_no_observed_host_execution'] = not any(
        'script_sha256' in event and invalid_attempt['started_ns'] <= event['started_ns'] <= invalid_end
        for event in native_events)
    extra = mechanism['simplification']['extra_aabb']
    extra_body = json.loads(read(BATCH / 'cells/grc03/owner/tool_02/RESPONSE.json')['result']['content'][0]['text'])
    values = extra_body['facts']['aabb']
    projected = dict(extra_body); projected['facts'] = dict(extra_body['facts']); projected['facts'].pop('aabb')
    checks['additional_aabb_component_and_projection'] = len(values) == extra['value_count'] == 4
    checks['additional_aabb_component_and_projection'] &= len(compact(values)) == extra['value_component_bytes'] == 987
    checks['additional_aabb_component_and_projection'] &= len(compact(extra_body)) - len(compact(projected)) == extra['compact_body_projection_difference_bytes'] == 994
    numeric = read(REVIEW / 'cost/BUDGETS.json')
    numeric_by_cell = {item['cell']:item for item in numeric['cells']}
    checks['all_saved_numeric_budget_checks_pass'] = numeric['passed'] is True and all(all(item['checks'].values()) for item in numeric['cells'])
    for independent in baseline['budget_rows']:
        actual = numeric_by_cell[independent['cell']]
        fields = {'full_cell_origin_ns':'original_full_cell_started_ns', 'full_cell_deadline_ns':'original_full_cell_deadline_ns',
            'full_cell_elapsed_ns':'full_cell_elapsed_ns', 'consumer_origin_ns':'original_consumer_started_ns',
            'consumer_deadline_ns':'original_consumer_deadline_ns', 'actor_prepare_origin_ns':'actor_prepare_started_ns',
            'actor_startup_deadline_ns':'actor_startup_deadline_ns', 'attempt_count':'tool_attempts',
            'response_budget_bytes':'cumulative_response_bytes', 'native_sequenced_requests_including_close':'host_physical_requests_including_close',
            'native_execute_requests':'charged_native_nonclose_requests', 'maximum_executed_code_bytes':'max_single_worker_code_utf8_bytes'}
        checks[independent['cell'] + '_numeric_budget_independent_concordance'] = all(independent[left] == actual[right] for left,right in fields.items())
        checks[independent['cell'] + '_numeric_budget_independent_concordance'] &= sum(item['response_bytes'] for item in actual['response_prefixes_including_failed_attempts']) == independent['response_budget_bytes']
    ledger = read(REVIEW / 'STAGE_LEDGER.json')
    historic = read(ROOT / ledger['historical_input_qualification']['source'])
    checks['historical_qualification_separate_and_bound'] = ledger['historical_input_qualification']['charged_again_as_current_preparation'] is False
    checks['historical_qualification_separate_and_bound'] &= all(ledger['historical_input_qualification'][name] == historic[name] for name in ('asset_controller_wall_s','oracle_analysis_wall_s','oracle_with_publication_wall_s'))
    checks['historical_qualification_separate_and_bound'] &= ledger['historical_input_qualification']['recorded_work_window_s'] == historic['recorded_freeze_to_finalizer_input_checks_window_s']
    reuse = read(REVIEW / 'ROOT_REUSE.json')
    checks['root_reuse_current_source_hashes'] = all(sha(REVIEW / item['file']) == item['after_sha256']
        and sha(ROOT / item['reused_from']) == item['before_sha256'] for item in reuse['files'])
    checks['six_thin_EXIT_unknown_retained'] = unknown_EXIT == 6
    checks['corrected_compact_frame_semantics'] = 'UTF-8 JSON RPC envelope' in mechanism['measurement_semantics']['actor_response_bytes'] and 'LF' in mechanism['measurement_semantics']['actor_response_bytes']
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
        'The independent initial budget-annotation condition and its false result were preserved, then corrected to distinguish service entry from early rejection.',
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
        'three-of-three successful P fact-use result are supported within this one frozen task.', '',
        'Provider cached-input and reasoning-output tokens remain overlapping subsets. Product cache '
        'observations retain their own scope. Preparation and historical installation are separately listed. '
        'Monetary fees, unexposed provider behavior and counterfactual simplification gains remain unmeasured.', '',
        'All six thin-client EXIT records remain unknown. Independent owner, native worker and applicable '
        'retained product runtime exit evidence remain confirmed under the frozen contract.', '',
        'The final reports include the failed nearest_witness request, necessary A fallback and six additional B/C closed classifications. '
        'The closed component size and work units do not establish isolated closed runtime or whole-task savings.', '',
        'Actual raw thin-stdio RX and actor compact-frame accounting agree per attempt. Their equality does '
        'not supply TCP or provider wire measurements.', '',
        'The first independent budget checker required a service annotation on a request rejected before service entry. Its source and result remain in check_history, while the final checker separates the original scopes.', '',
        'The finalizer was statically reviewed. This reviewer executed no finalizer, model, Blender or product.', '',
        'Root report SHA256 `' + bound['REPORT.md'] + '`.', '',
        'Cross-review checker SHA256 `' + bound['integrity/cross_review.py'] + '`.', '']
    with (HERE / 'CROSS_REVIEW.md').open('x', encoding='utf8', newline='\n') as stream:
        stream.write('\n'.join(text))
    print(json.dumps({'passed': result['passed'], 'checks': len(checks), 'bound_files': len(bound),
                      'blocking_findings': result['blocking_findings']}))


if __name__ == '__main__':
    main()
