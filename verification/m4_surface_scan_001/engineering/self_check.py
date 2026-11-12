"""Independent verifier counterexamples, with zero product or Blender calls."""
from __future__ import annotations

import copy
import argparse
from fractions import Fraction
import json
import math
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HERE, QUAL, save
from verify_state import object_ids, verify


def number(value):
    return float(Fraction(int(value['numerator']), int(value['denominator'])))


def synthetic(truth, snapshot):
    ids = object_ids(snapshot)
    by_name = {name: oid for oid, name in ids.items()}
    result = {'result_kind': 'surface_scan', 'status': 'complete', 'threshold_m': .002,
        'unit': 'm', 'coordinate_frame': 'world', 'execution_authority': False,
        'binding': {'runtime_source_sha256': 'self-check'},
        'delivery': {'complete': True, 'delivered_matches': truth['match_count'],
                     'matches_total': truth['match_count']},
        'scope_issues': [], 'unsupported_objects': [], 'unresolved': [], 'matches': [],
        'coverage': {'objects': 24, 'total_pairs': 276, 'catalog_scope_confirmed': True, 'bound_excluded': 0,
                     'measured_match': truth['match_count'], 'measured_nonmatch': 276 - truth['match_count'],
                     'unknown': 0, 'deferred': 0}}
    diagnostics = {'dispositions': []}
    for row in truth['pairs']:
        names = (row['object_a'], row['object_b'])
        ordered = sorted(names, key=lambda name: by_name[name])
        distance = math.sqrt(number(row['exact_squared_distance_m2']))
        diagnostics['dispositions'].append({'object_ids': [by_name[name] for name in ordered],
            'lower_bound_m': 0., 'distance_m': distance,
            'status': 'measured_match' if row['matches_threshold'] else 'measured_nonmatch'})
        if row['matches_threshold']:
            points = dict(zip(names, (row['witness']['point_a'], row['witness']['point_b']), strict=True))
            result['matches'].append({'objects': [{'id': by_name[name], 'name': name} for name in ordered],
                'distance_m': distance, 'point_a_world': [number(v) for v in points[ordered[0]]],
                'point_b_world': [number(v) for v in points[ordered[1]]]})
    return result, diagnostics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=HERE / 'SELF_CHECK.json')
    args = parser.parse_args()
    assert args.output.resolve().is_relative_to(HERE)
    started = time.perf_counter_ns()
    records = []
    for state in ('BASE', 'EDIT'):
        truth = json.loads((QUAL / (state + '_TRUTH.json')).read_bytes())
        source = json.loads((QUAL / (state + '_SNAPSHOT.json')).read_bytes())
        result, diagnostics = synthetic(truth, source)
        verified = verify(result, diagnostics, truth, source, 'self-check')
        records.append({'state': state, 'kind': 'valid_independent_synthetic', 'passed': verified['passed']})
        changes = {
            'duplicate_partition': lambda r, d: d['dispositions'].append(copy.deepcopy(d['dispositions'][0])),
            'missing_partition': lambda r, d: d['dispositions'].pop(),
            'incorrect_predicate': lambda r, d: d['dispositions'][0].update(status='unknown'),
            'extra_public_match': lambda r, d: r['matches'].append(copy.deepcopy(r['matches'][0])),
            'false_distance': lambda r, d: d['dispositions'][0].update(distance_m=42.),
            'false_surface_witness': lambda r, d: r['matches'][0].update(point_a_world=[2., 2., 2.]),
        }
        for name, mutate in changes.items():
            changed, metrics = copy.deepcopy(result), copy.deepcopy(diagnostics)
            mutate(changed, metrics)
            rejected = False
            try:
                verify(changed, metrics, truth, source, 'self-check')
            except AssertionError:
                rejected = True
            assert rejected, name
            records.append({'state': state, 'kind': name, 'rejected': True})
    saved = {'passed': True, 'checks': records, 'product_calls': 0, 'Blender_starts': 0,
             'elapsed_ns': time.perf_counter_ns() - started}
    save(args.output, saved)
    print(json.dumps(saved))


if __name__ == '__main__':
    main()
