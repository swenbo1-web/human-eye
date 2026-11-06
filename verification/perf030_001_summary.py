"""Summarize the sealed raw observations without selecting or rerunning arms."""
from collections import Counter, defaultdict
import hashlib
import json

import numpy as np

from verification.perf030_001_qualification import OUT
from verification.perf030_001_compare import changed_pair


def main():
    source = OUT / 'formal_raw.jsonl'
    rows = [json.loads(line) for line in source.read_text(encoding='utf8').splitlines()]
    assert len(rows) == 12 * 5 * 4 * 2 * 3 * 2
    inputs = json.loads((OUT / 'inputs.json').read_text(encoding='utf8'))['cases']
    independent_truth = {}
    for case in inputs:
        if case['group'] == 'reject':
            continue
        for mode in ('cold', 'pose_miss', 'geometry_miss', 'hot'):
            left, right = changed_pair(case, mode)
            if case['group'] in ('target', 'small', 'edge'):
                # The unchanged xy projections overlap. Parallel horizontal
                # supporting planes attain this exact represented z gap.
                expected = float(right.vertices[:, 2].min() - left.vertices[:, 2].max())
            else:
                # These variants modify z only and remain inside the ring's
                # vertical interval, preserving the analytic horizontal gap.
                assert left.vertices[:, 2].min() >= right.vertices[:, 2].min()
                assert left.vertices[:, 2].max() <= right.vertices[:, 2].max()
                expected = case['expected_clearance_m']
            independent_truth[(case['name'], mode)] = expected
    oracle_failures = []
    for row in rows:
        expected = independent_truth.get((row['case'], row['mode']))
        if expected is None:
            continue
        actual = (row['measurement']['signed_clearance_m'] if row['entry'] == 'measure_pair_geometry'
                  else row['facts']['surface_clearance']['value'])
        if actual is None or abs(actual - expected) > 1e-14:
            oracle_failures.append({'case': row['case'], 'mode': row['mode'], 'expected': expected, 'actual': actual})
    grouped = defaultdict(lambda: defaultdict(list))
    paired = defaultdict(dict)
    for row in rows:
        grouped[(row['case'], row['group'], row['mode'], row['entry'])][row['arm']].append(row)
        paired[(row['case'], row['mode'], row['entry'], row['block'], row['repeat'])][row['arm']] = row
    comparisons = []
    for (case, group, mode, entry), arms in grouped.items():
        baseline = np.array([row['ms'] for row in arms['baseline']])
        candidate = np.array([row['ms'] for row in arms['candidate']])
        old, new = float(np.median(baseline)), float(np.median(candidate))
        old_p95, new_p95 = float(np.percentile(baseline, 95)), float(np.percentile(candidate, 95))
        comparisons.append({'case': case, 'group': group, 'mode': mode, 'entry': entry,
            'baseline_median_ms': old, 'candidate_median_ms': new, 'improvement': 1 - new / old,
            'baseline_p95_ms': old_p95, 'candidate_p95_ms': new_p95,
            'p95_pass': new_p95 - old_p95 <= max(1, old_p95 * .05),
            'small_hot_median_pass': new - old <= max(.2, old * .02),
            'baseline_statuses': dict(Counter(row.get('status', str(row.get('measurement', {}).get('measurement_valid'))) for row in arms['baseline'])),
            'candidate_statuses': dict(Counter(row.get('status', str(row.get('measurement', {}).get('measurement_valid'))) for row in arms['candidate']))})
    gate = []
    paired_block_gate = []
    for entry in ('measure_pair_geometry', 'task_result'):
        for mode in ('cold', 'pose_miss', 'geometry_miss'):
            selected = [row for row in comparisons if row['entry'] == entry and row['mode'] == mode and row['group'] == 'target']
            improvements = [row['improvement'] for row in selected]
            wins = sum(value > 0 for value in improvements)
            median = float(np.median(improvements))
            gate.append({'entry': entry, 'mode': mode, 'median_case_improvement': median,
                         'benefiting_groups': wins, 'pass': median >= .20 and wins >= 4})
            block_values = []
            for row in selected:
                arms = grouped[(row['case'], row['group'], mode, entry)]
                for block in range(5):
                    old = np.median([item['ms'] for item in arms['baseline'] if item['block'] == block])
                    new = np.median([item['ms'] for item in arms['candidate'] if item['block'] == block])
                    block_values.append(float(1 - new / old))
            paired_block_gate.append({'entry': entry, 'mode': mode,
                'median_25_paired_block_improvement': float(np.median(block_values)),
                'pass_20_percent': float(np.median(block_values)) >= .20})
    mismatches = []
    max_clearance_difference = 0
    max_witness_difference = 0
    exact_matches = 0
    for key, arms in paired.items():
        a, b = arms['baseline'], arms['candidate']
        if key[2] == 'measure_pair_geometry':
            left, right = a.get('measurement'), b.get('measurement')
            if left == right:
                exact_matches += 1
            for field in ('measurement_valid', 'reason', 'is_penetrating', 'witness_scope', 'measurement_method'):
                if left.get(field) != right.get(field):
                    mismatches.append({'key': key, 'field': field})
            if left.get('signed_clearance_m') is not None and right.get('signed_clearance_m') is not None:
                delta = abs(left['signed_clearance_m'] - right['signed_clearance_m'])
                max_clearance_difference = max(max_clearance_difference, delta)
                if delta > 1e-14:
                    mismatches.append({'key': key, 'field': 'signed_clearance_m', 'delta': delta})
            if left.get('point_a_world') is not None and right.get('point_a_world') is not None:
                delta = float(np.max(np.abs(np.asarray([left['point_a_world'], left['point_b_world']]) -
                                               np.asarray([right['point_a_world'], right['point_b_world']]))))
                max_witness_difference = max(max_witness_difference, delta)
                if delta > 1e-13:
                    mismatches.append({'key': key, 'field': 'witness', 'delta': delta})
        else:
            if a.get('facts') == b.get('facts') and a.get('status') == b.get('status'):
                exact_matches += 1
            else:
                mismatches.append({'key': key, 'field': 'task_facts'})
            if a['diagnostics'] != b['diagnostics']:
                mismatches.append({'key': key, 'field': 'cache_diagnostics'})
    failures = [row for row in comparisons if not row['p95_pass']]
    median_failures = [row for row in comparisons if (row['group'] == 'small' or row['mode'] == 'hot') and not row['small_hot_median_pass']]
    summary = {'raw_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'raw_records': len(rows),
        'paired_records': len(paired), 'exact_payload_matches': exact_matches,
        'exceptions': [row for row in rows if 'exception' in row],
        'semantic_mismatches': mismatches, 'max_clearance_difference_m': max_clearance_difference,
        'max_witness_coordinate_difference_m': max_witness_difference,
        'target_gates': gate, 'p95_failures': failures, 'small_hot_median_failures': median_failures,
        'paired_block_target_gates': paired_block_gate,
        'independent_oracle_checks': sum(row['group'] != 'reject' for row in rows),
        'independent_oracle_failures': oracle_failures,
        'overall_performance_pass': all(row['pass'] for row in gate) and not failures and not median_failures,
        'comparisons': comparisons}
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf8')
    print(json.dumps({key: value for key, value in summary.items() if key != 'comparisons'}, indent=2))


if __name__ == '__main__':
    main()
