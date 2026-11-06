"""Standard-library statistics over the single frozen PERF-030-002 sequence."""
from collections import defaultdict
import math
import statistics


def _expected_clearance(case, mode):
    left, right = case['meshes']
    z_values = [point[2] for point in left['vertices']]
    magnitude = max(abs(value) for point in left['vertices'] for value in point)
    if mode == 'pose_miss':
        step = max(.000001, 2 * math.ulp(magnitude))
        z_values = [value + step for value in z_values]
    elif mode == 'geometry_miss':
        bottom = min(z_values)
        height = max(z_values) - bottom
        factor = 1 + max(.0001, 4 * math.ulp(magnitude) / height)
        z_values = [bottom + (value - bottom) * factor for value in z_values]
    reference_z = [point[2] for point in right['vertices']]
    if case['group'] in ('target', 'small', 'edge'):
        return min(reference_z) - max(z_values)
    if min(z_values) < min(reference_z) or max(z_values) > max(reference_z):
        raise ValueError('Ring oracle requires vertical overlap of the same fixed probe')
    return case['expected_clearance_m']


def _differences(left, right, path=''):
    if type(left) is not type(right):
        return [{'field': path, 'baseline': left, 'candidate': right}]
    if isinstance(left, dict):
        result = []
        for key in sorted(set(left) | set(right)):
            child = path + '.' + key if path else key
            if key not in left or key not in right:
                result.append({'field': child, 'baseline': left.get(key), 'candidate': right.get(key),
                               'missing_in': 'baseline' if key not in left else 'candidate'})
            else:
                result.extend(_differences(left[key], right[key], child))
        return result
    if isinstance(left, list):
        if len(left) != len(right):
            return [{'field': path, 'baseline': left, 'candidate': right}]
        result = []
        for index, (old, new) in enumerate(zip(left, right)):
            result.extend(_differences(old, new, path + '[' + str(index) + ']'))
        return result
    if left == right:
        return []
    return [{'field': path, 'baseline': left, 'candidate': right}]


def _supported(row):
    result = row['result']
    payload = result.get('payload') or {}
    if result.get('exception'):
        return False
    if row['entry'] == 'measure_pair_geometry':
        return payload.get('measurement_valid') is True
    return payload.get('facts', {}).get('surface_clearance', {}).get('status') == 'measured'


def _stats(rows):
    costs = [row['result'].get('costs', {}) for row in rows]
    values = [item['kernel_ns'] / 1e6 for item in costs if isinstance(item.get('kernel_ns'), (int, float))]
    valid = len(values) == 15 and all(value > 0 and math.isfinite(value) for value in values)
    valid = valid and all(_supported(row) for row in rows)
    if not values:
        return {'records': len(rows), 'timed_records': 0, 'valid_15': False}
    ordered = sorted(values)
    return {'records': len(rows), 'timed_records': len(values), 'valid_15': valid,
            'median_ms': statistics.median(values),
            'p95_ms': .7 * ordered[13] + .3 * ordered[14] if len(values) == 15 else None}


def summarize(rows, inputs):
    cases = inputs['cases']
    grouped = defaultdict(lambda: defaultdict(list))
    paired = defaultdict(dict)
    identities = defaultdict(lambda: defaultdict(set))
    oracle_failures, cache_failures, input_failures, reject_failures = [], [], [], []
    costs = defaultdict(int)
    exceptions = []
    for row in rows:
        case_index, mode, entry = row['case_index'], row['mode'], row['entry']
        result = row['result']
        if result.get('exception'):
            exceptions.append({'case_index': case_index, 'mode': mode, 'entry': entry,
                               'arm': row['arm'], 'exception': result['exception']})
        case = cases[case_index]
        grouped[(case_index, mode, entry)][row['arm']].append(row)
        paired[(case_index, mode, entry, row['block'], row['repeat'])][row['arm']] = row
        modified = result.get('modified_input', {})
        identities[(case_index, mode)][row['arm']].add(modified.get('sha256'))
        if mode in ('pose_miss', 'geometry_miss') and modified.get('vertices_changed') is not True:
            input_failures.append({'case': case['name'], 'mode': mode, 'arm': row['arm'], 'issue': 'no_real_vertex_change'})
        for key, value in result.get('costs', {}).items():
            if isinstance(value, int):
                costs[key] += value
        if case['group'] == 'reject':
            payload = result.get('payload') or {}
            if entry == 'measure_pair_geometry':
                rejected = payload.get('measurement_valid') is False and payload.get('reason') == 'geometry_resource_limit'
            else:
                rejected = all(fact.get('status') == 'unknown' and fact.get('reason') == 'geometry_resource_limit'
                               for fact in payload.get('facts', {}).values()) and bool(payload.get('facts'))
                diagnostics = result.get('diagnostics', {})
                rejected = rejected and diagnostics.get('pair_cache_hit') is False and diagnostics.get('exact_pair_count') == 1
            if not rejected:
                reject_failures.append({'case': case['name'], 'mode': mode, 'entry': entry, 'arm': row['arm']})
            continue
        payload = result.get('payload') or {}
        expected = _expected_clearance(case, mode)
        if entry == 'measure_pair_geometry':
            actual = payload.get('signed_clearance_m')
            valid = payload.get('measurement_valid') is True
        else:
            fact = payload.get('facts', {}).get('surface_clearance', {})
            actual = fact.get('value')
            valid = fact.get('status') == 'measured'
            diagnostics = result.get('diagnostics', {})
            hit = mode == 'hot'
            if diagnostics.get('pair_cache_hit') is not hit or diagnostics.get('exact_pair_count') != (0 if hit else 1):
                cache_failures.append({'case': case['name'], 'mode': mode, 'arm': row['arm'], 'diagnostics': diagnostics})
        if not valid or not isinstance(actual, (int, float)) or not math.isfinite(actual) or abs(actual - expected) > 1e-14:
            oracle_failures.append({'case': case['name'], 'mode': mode, 'entry': entry, 'arm': row['arm'],
                                    'expected': expected, 'actual': actual, 'exception': result.get('exception')})
    for key, arms in identities.items():
        digests = set().union(*arms.values())
        if set(arms) != {'baseline', 'candidate'} or len(digests) != 1 or None in digests:
            input_failures.append({'case': cases[key[0]]['name'], 'mode': key[1],
                                   'digests': {arm: sorted(str(value) for value in values) for arm, values in arms.items()}})
    comparisons = []
    for (case_index, mode, entry), arms in sorted(grouped.items()):
        old, new = _stats(arms.get('baseline', [])), _stats(arms.get('candidate', []))
        valid = old.get('valid_15') and new.get('valid_15')
        blocks = []
        for block in range(5):
            samples = {}
            for name in ('baseline', 'candidate'):
                selected = [item for item in arms.get(name, []) if item['block'] == block]
                if len(selected) == 3 and all(_supported(item) and 'kernel_ns' in item['result'].get('costs', {}) for item in selected):
                    samples[name] = statistics.median(item['result']['costs']['kernel_ns'] for item in selected)
            improvement = None
            if len(samples) == 2 and samples['baseline'] > 0:
                improvement = 1 - samples['candidate'] / samples['baseline']
            blocks.append({'block': block, 'improvement': improvement})
        improvement = 1 - new['median_ms'] / old['median_ms'] if valid else None
        comparisons.append({'case_index': case_index, 'case': cases[case_index]['name'], 'group': cases[case_index]['group'],
            'mode': mode, 'entry': entry, 'baseline': old, 'candidate': new, 'improvement': improvement,
            'block_improvements': blocks, 'benefiting_blocks': sum(item['improvement'] is not None and item['improvement'] > 0 for item in blocks),
            'median_nonregression_pass': bool(valid and new['median_ms'] - old['median_ms'] <= max(.2, old['median_ms'] * .02)),
            'p95_nonregression_pass': bool(valid and new['p95_ms'] - old['p95_ms'] <= max(1., old['p95_ms'] * .05))})
    targets = []
    for mode in ('cold', 'pose_miss', 'geometry_miss'):
        for entry in ('measure_pair_geometry', 'task_result'):
            selected = [item for item in comparisons if item['group'] == 'target' and item['mode'] == mode and item['entry'] == entry]
            values = [item['improvement'] for item in selected if item['improvement'] is not None]
            median = statistics.median(values) if len(values) == 5 else None
            wins = sum(value > 0 for value in values)
            targets.append({'mode': mode, 'entry': entry, 'valid_cases': len(values), 'benefiting_cases': wins,
                            'median_case_improvement': median, 'module_20_percent_pass': median is not None and median >= .20 and wins >= 4})
    payload_differences, unexplained_differences = [], []
    exact_pairs, missing_pairs = 0, []
    for key, arms in paired.items():
        if set(arms) != {'baseline', 'candidate'}:
            missing_pairs.append(list(key))
            continue
        old, new = arms['baseline']['result'], arms['candidate']['result']
        differences = _differences(old.get('payload'), new.get('payload'))
        diagnostics = _differences(old.get('diagnostics'), new.get('diagnostics'), 'diagnostics')
        if not differences and not diagnostics:
            exact_pairs += 1
        else:
            payload_differences.append({'key': list(key), 'fields': differences + diagnostics})
            for difference in differences + diagnostics:
                old_value, new_value = difference.get('baseline'), difference.get('candidate')
                tolerance = 1e-13 if any(token in difference['field'] for token in ('point_a_world', 'point_b_world', 'nearest_witness.value.a', 'nearest_witness.value.b')) else 1e-14
                numerical = (type(old_value) is float and type(new_value) is float
                             and math.isfinite(old_value) and math.isfinite(new_value)
                             and abs(old_value - new_value) <= tolerance)
                if not numerical:
                    unexplained_differences.append({'key': list(key), **difference})
    complete = len(rows) == 2880 and len(paired) == 1440 and not missing_pairs
    effective = [item for item in comparisons if item['group'] != 'reject']
    nonregression = complete and len(effective) == 11 * 4 * 2 and all(
        item['median_nonregression_pass'] and item['p95_nonregression_pass'] for item in effective)
    return {'records': len(rows), 'expected_records': 2880, 'complete': complete, 'paired_records': len(paired),
            'exact_full_payload_and_diagnostics_pairs': exact_pairs, 'missing_pairs': missing_pairs,
            'full_response_differences': payload_differences, 'unexplained_response_differences': unexplained_differences,
            'oracle_checks': sum(cases[row['case_index']]['group'] != 'reject' for row in rows),
            'oracle_failures': oracle_failures, 'reject_control_failures': reject_failures,
            'input_failures': input_failures, 'cache_failures': cache_failures, 'worker_cost_totals': dict(costs),
            'expected_prime_calls': 2160, 'prime_count_pass': costs.get('prime_calls') == 2160,
            'sample_exceptions': exceptions,
            'effective_nonregression_pass': bool(nonregression), 'target_gates': targets,
            'formal_correctness_pass': complete and costs.get('prime_calls') == 2160 and not (
                oracle_failures or cache_failures or input_failures or reject_failures or unexplained_differences or exceptions),
            'module_20_percent_pass': complete and all(item['module_20_percent_pass'] for item in targets),
            'comparisons': comparisons, 'allocation_calls': 'not_measured', 'rss': 'not_measured'}
