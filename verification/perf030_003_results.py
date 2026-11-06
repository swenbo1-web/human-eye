"""Conservative, single-observation Stage A qualification without NumPy."""
from collections import defaultdict
import math


CASE_IDS = (0, 1, 2, 3, 4, 5, 6, 11)
STATES = ('cold_measure', 'primed_hot_measure', 'cold_task')
STAGES = ('token_cache', 'closure', 'topology_components',
          'numeric_certification', 'direction_index', 'other')


def _entry_checks(row, case):
    result = row['result']
    payload = result.get('payload') or {}
    issues = []
    if result.get('exception') or result.get('trace_exception'):
        issues.append('entry_or_trace_exception')
    if row['state'] == 'cold_task':
        fact = payload.get('facts', {}).get('surface_clearance', {})
        value = fact.get('value')
        valid = fact.get('status') == 'measured'
        diagnostics = result.get('diagnostics', {})
        if diagnostics.get('pair_cache_hit') is not False or diagnostics.get('exact_pair_count') != 1:
            issues.append('cold_task_cache_semantics')
        if case['group'] == 'reject' and (valid or fact.get('reason') != 'geometry_resource_limit'):
            issues.append('reject_control_changed')
    else:
        value = payload.get('signed_clearance_m')
        valid = payload.get('measurement_valid') is True
        if case['group'] == 'reject' and (valid or payload.get('reason') != 'geometry_resource_limit'):
            issues.append('reject_control_changed')
    if case['group'] != 'reject':
        expected = case['expected_clearance_m']
        if not valid or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value - expected) > 1e-14:
            issues.append('analytic_clearance_mismatch')
        if row['state'] == 'cold_task':
            relation = payload.get('facts', {}).get('solid_relation', {})
            if relation.get('status') != 'measured' or relation.get('value') != 'not_penetrating':
                issues.append('analytic_solid_relation_mismatch')
        elif payload.get('is_penetrating') is not False:
            issues.append('analytic_solid_relation_mismatch')
    costs = result.get('costs', {})
    expected_prime = int(row['state'] == 'primed_hot_measure')
    if costs.get('prime_calls') != expected_prime:
        issues.append('prime_count')
    if row['case_index'] not in CASE_IDS or row['state'] not in STATES:
        issues.append('unexpected_case_or_state')
    return issues


def _trace_checks(trace, row, case):
    issues = []
    calls = trace.get('calls', [])
    if trace.get('call_count') != len(calls):
        issues.append('trace_call_count')
    if sum(trace.get('stages_ns', {}).get(stage, 0) for stage in STAGES) != trace.get('function_total_ns'):
        issues.append('exclusive_stage_sum')
    for call in calls:
        if sum(call.get('stages_ns', {}).get(stage, 0) for stage in STAGES) != call.get('function_total_ns'):
            issues.append('call_exclusive_stage_sum')
        if any(value < 0 for value in call.get('stages_ns', {}).values()):
            issues.append('negative_stage_duration')
        if call.get('counts_incomplete'):
            issues.append('incomplete_counter_coverage')
        if call.get('cache') == 'miss' and call.get('counter_coverage', {}).get('topology') == 'complete':
            counts = call.get('counts', {})
            faces, edges = call['input_faces'], call['association_edges']
            expected_counts = {'np_roll_calls': faces, 'face_rows': faces,
                'directed_edge_keys': 3 * faces, 'edge_faces_setdefault': 3 * faces,
                'incident_appends': 3 * faces, 'oriented_get': 3 * faces, 'oriented_set': 3 * faces,
                'manifold_edge_visits': edges, 'union_edge_visits': edges,
                'find_calls_derived': 2 * edges + faces}
            if any(counts.get(name) != value for name, value in expected_counts.items()):
                issues.append('completed_topology_counter_mismatch')
    if case['group'] == 'reject':
        if calls:
            issues.append('budget_reject_touched_convex')
    elif row['state'] == 'primed_hot_measure':
        if not calls or any(call.get('cache') != 'hit' for call in calls):
            issues.append('primed_measure_support_cache_miss')
        if trace.get('stages_ns', {}).get('topology_components') != 0:
            issues.append('primed_measure_rebuilt_topology')
        if case['name'] == 'ring_probe' and not any(call.get('negative_cache_hit') for call in calls):
            issues.append('ring_negative_cache_hit_missing')
    elif case['group'] == 'target':
        if len(calls) != 2 or any(call.get('cache') != 'miss' for call in calls):
            issues.append('target_cold_support_call_or_cache_count')
        if any(call.get('counter_coverage', {}).get('topology') != 'complete' for call in calls):
            issues.append('target_cold_topology_not_complete')
    return issues


def summarize(rows, inputs):
    pairs = defaultdict(dict)
    issues, costs = [], defaultdict(int)
    for index, row in enumerate(rows):
        key = (row['case_index'], row['state'])
        variant = 'diagnostic' if row['diagnostic'] else 'normal'
        if variant in pairs[key]:
            issues.append({'row': index, 'issue': 'duplicate_entry'})
        pairs[key][variant] = row
        case = inputs['cases'][row['case_index']]
        for issue in _entry_checks(row, case):
            issues.append({'row': index, 'case': case['name'], 'state': row['state'], 'issue': issue})
        for name, value in row['result'].get('costs', {}).items():
            if isinstance(value, int):
                costs[name] += value
    expected_order = [(case, state, diagnostic) for case in CASE_IDS for state in STATES for diagnostic in (False, True)]
    actual_order = [(row['case_index'], row['state'], row['diagnostic']) for row in rows]
    order_prefix_matches = actual_order == expected_order[:len(rows)]
    if not order_prefix_matches:
        issues.append({'issue': 'frozen_entry_order_mismatch'})
    comparisons = []
    for (case_index, state), variants in sorted(pairs.items()):
        if set(variants) != {'normal', 'diagnostic'}:
            issues.append({'case_index': case_index, 'state': state, 'issue': 'missing_pair'})
            continue
        normal, diagnostic = variants['normal']['result'], variants['diagnostic']['result']
        case = inputs['cases'][case_index]
        equal = all(normal.get(field) == diagnostic.get(field) for field in
                    ('payload', 'diagnostics', 'prime_payload', 'support_before', 'support_results', 'input_metadata'))
        if not equal:
            issues.append({'case': case['name'], 'state': state, 'issue': 'normal_diagnostic_response_or_support_difference'})
        proof = diagnostic.get('diagnostic_proof', {})
        proof_valid = (proof.get('strip_ast_equal') is True
                       and proof.get('original_function_ast_sha256') == proof.get('stripped_function_ast_sha256')
                       and proof.get('gate_credit_scope') == 'topology_components_only'
                       and proof.get('direction_mixed_numerical_selection') is True)
        if not proof_valid:
            issues.append({'case': case['name'], 'state': state, 'issue': 'diagnostic_ast_or_credit_proof'})
        trace = diagnostic.get('trace') or {}
        trace_issues = _trace_checks(trace, variants['diagnostic'], case)
        for issue in trace_issues:
            issues.append({'case': case['name'], 'state': state, 'issue': issue})
        old_costs, new_costs = normal.get('costs', {}), diagnostic.get('costs', {})
        n, d = old_costs.get('kernel_ns', 0), new_costs.get('kernel_ns', 0)
        denominator = max(n, d)
        stages = trace.get('stages_ns', {})
        topology = stages.get('topology_components', 0)
        direction = stages.get('direction_index', 0)
        bookkeeping = trace.get('instrumentation', {}).get('measured_bookkeeping_windows_ns', 0)
        preparation = new_costs.get('instrumentation_prepare_ns', 0) + new_costs.get('trace_publish_prepare_ns', 0)
        observed_instrumentation = bookkeeping + preparation
        discrepancy = abs(d - n)
        credit = max(0, topology - observed_instrumentation - discrepancy)
        credit_ratio = credit / denominator if denominator > 0 else 0
        observer_delta_ratio = discrepancy / denominator if denominator > 0 else 1
        observer_window_ratio = observed_instrumentation / denominator if denominator > 0 else 1
        trusted = denominator > 0 and observer_delta_ratio <= .10 and observer_window_ratio <= .10
        eligible = equal and proof_valid and not trace_issues and trusted and credit_ratio >= .30
        comparisons.append({'case_index': case_index, 'case': case['name'], 'group': case['group'], 'state': state,
            'complete_response_and_support_equal': equal, 'trace_issues': trace_issues,
            'normal_kernel_ns': n, 'diagnostic_kernel_ns': d,
            'normal_process_ns': old_costs.get('process_ns'), 'diagnostic_process_ns': new_costs.get('process_ns'),
            'diagnostic_stages_ns': stages, 'diagnostic_call_count': trace.get('call_count'),
            'operation_counts': trace.get('counts'), 'instrumentation': trace.get('instrumentation'),
            'observed_instrumentation_plus_preparation_ns': observed_instrumentation,
            'absolute_kernel_discrepancy_ns': discrepancy,
            'observer_delta_ratio': observer_delta_ratio, 'observer_window_ratio': observer_window_ratio,
            'observer_screen_pass': trusted,
            'topology_zero_cost_ideal_ratio': topology / denominator if denominator > 0 else None,
            'optimistic_topology_plus_direction_zero_cost_ratio': (topology + direction) / denominator if denominator > 0 else None,
            'topology_screening_credit_ns': credit, 'topology_screening_credit_ratio': credit_ratio,
            'cold_entry_30_percent_screen_pass': eligible if state in ('cold_measure', 'cold_task') else None,
            'screen_scope': 'empirical conservative screen, not a statistical lower confidence bound'})
    target_cases = []
    for case_index in range(5):
        selected = [row for row in comparisons if row['case_index'] == case_index and row['state'] in ('cold_measure', 'cold_task')]
        passed = len(selected) == 2 and all(row['cold_entry_30_percent_screen_pass'] for row in selected)
        target_cases.append({'case_index': case_index, 'case': inputs['cases'][case_index]['name'],
                             'both_cold_entries_pass': passed})
    complete = len(rows) == 48 and len(pairs) == 24 and order_prefix_matches
    prime_count_pass = costs.get('prime_calls') == 16
    qualifying = sum(row['both_cold_entries_pass'] for row in target_cases)
    supported = complete and prime_count_pass and not issues and qualifying >= 4
    return {'phase': 'A', 'records': len(rows), 'expected_records': 48, 'paired_entries': len(pairs),
            'complete': complete, 'prime_calls': costs.get('prime_calls', 0), 'expected_prime_calls': 16,
            'prime_count_pass': prime_count_pass, 'issues': issues, 'cost_totals': dict(costs),
            'target_case_screens': target_cases, 'qualifying_target_cases': qualifying,
            'qualification_supported': supported,
            'decision': 'eligible_for_one_topology_candidate' if supported else 'attribution_only_no_candidate_authorized_by_this_screen',
            'credit_scope': 'topology_components_only; mixed direction cost is optimistic upper display only',
            'observability': 'partial recorder windows and normal/diagnostic discrepancy are reported, never RTT-corrected',
            'unmeasured': ['total_causal_observer_tax', 'statistical_noise_bound', 'p95', 'candidate_speedup'],
            'comparisons': comparisons}
