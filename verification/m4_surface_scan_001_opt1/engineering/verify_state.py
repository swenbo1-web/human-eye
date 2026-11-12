"""Verify all pair partitions and public witnesses against frozen independent truth."""
from __future__ import annotations

from collections import Counter
from fractions import Fraction
import hashlib
import json
import math

from common import ROOT, encoded, load_module


def object_ids(snapshot):
    # Public host ID encoding, independently reproduced. No geometry algorithm imported.
    return {'blender:' + hashlib.sha256(encoded(['', row['name']])).hexdigest(): row['name']
            for row in snapshot['objects']}


def point_on_surface(point, source, geometry):
    point = tuple(Fraction(value) for value in point)
    vertices = [tuple(Fraction(value) for value in vertex) for vertex in source['vertices_world']]
    tolerance = Fraction(1, 10**10)
    for indices in source['triangles']:
        triangle = [vertices[index] for index in indices]
        normal = geometry.cross(geometry.sub(triangle[1], triangle[0]),
                                geometry.sub(triangle[2], triangle[0]))
        normal_sq = geometry.dot(normal, normal)
        offset = geometry.dot(normal, geometry.sub(point, triangle[0]))
        if offset * offset > tolerance * tolerance * normal_sq:
            continue
        # Barycentric projection and its reconstruction must both stay within
        # the explicitly recorded 0.1 nanometre presentation tolerance.
        bary = geometry.barycentric(point, triangle)
        projected = geometry.blend(triangle, bary)
        if min(bary) >= 0 and geometry.squared(point, projected) <= tolerance * tolerance:
            return True
        # Rounded edge witnesses can fall infinitesimally outside a face.
        clipped = [max(Fraction(0), value) for value in bary]
        total = sum(clipped)
        if total and geometry.squared(point, geometry.blend(triangle, [v / total for v in clipped])) <= tolerance * tolerance:
            return True
    return False


def verify(result, diagnostics, truth, snapshot, expected_source):
    geometry = load_module('_scan_independent_geometry',
        ROOT / 'verification/m4_grooved_rail_transfer_001/oracle/exact_geometry.py')
    ids = object_ids(snapshot)
    sources = {row['name']: row for row in snapshot['objects']}
    expected = {tuple(sorted((row['object_a'], row['object_b']))): row for row in truth['pairs']}
    assert len(expected) == 276 and len(ids) == 24
    assert result['result_kind'] == 'surface_scan' and result['status'] == 'complete'
    assert result['threshold_m'] == .002 and result['unit'] == 'm'
    assert result['coordinate_frame'] == 'world' and result['execution_authority'] is False
    assert result['binding']['runtime_source_sha256'] == expected_source
    assert result['delivery']['complete'] and result['scope_issues'] == []
    assert result['unsupported_objects'] == [] and result['unresolved'] == []
    partition = diagnostics['dispositions']
    assert len(partition) == 276
    seen = set()
    counts = Counter()
    measured_names = set()
    distance_errors = []
    for row in partition:
        pair_ids = row['object_ids']
        assert pair_ids == sorted(pair_ids) and len(set(pair_ids)) == 2
        names = tuple(sorted(ids[oid] for oid in pair_ids))
        assert names not in seen and names in expected
        seen.add(names)
        target = expected[names]
        state = row['status']
        counts[state] += 1
        assert state in ('bound_excluded', 'measured_match', 'measured_nonmatch'), row
        assert (state == 'measured_match') == target['matches_threshold'], (names, state)
        exact_sq = target['exact_squared_distance_m2']
        exact_sq = Fraction(int(exact_sq['numerator']), int(exact_sq['denominator']))
        if state == 'bound_excluded':
            lower = row['lower_bound_m']
            assert lower > .002 and Fraction(lower)**2 <= exact_sq
        else:
            measured_names.add(names)
            actual = row['distance_m']
            target_distance = math.sqrt(float(exact_sq))
            assert math.isfinite(actual) and abs(actual - target_distance) <= 1e-10
            distance_errors.append(abs(actual - target_distance))
    assert seen == set(expected)
    public_pairs = set()
    for match in result['matches']:
        objects = match['objects']
        assert len(objects) == 2 and [row['id'] for row in objects] == sorted(row['id'] for row in objects)
        names = tuple(sorted(row['name'] for row in objects))
        assert names not in public_pairs and expected[names]['matches_threshold']
        public_pairs.add(names)
        for row in objects:
            assert ids[row['id']] == row['name']
        left, right = match['point_a_world'], match['point_b_world']
        assert match['witness_status'] == 'measured'
        value = expected[names]['exact_squared_distance_m2']
        minimum = math.sqrt(float(Fraction(int(value['numerator']), int(value['denominator']))))
        assert abs(match['distance_m'] - minimum) <= 1e-10
        assert point_on_surface(left, sources[objects[0]['name']], geometry)
        assert point_on_surface(right, sources[objects[1]['name']], geometry)
        assert abs(math.dist(left, right) - match['distance_m']) <= 1e-10
    assert public_pairs == {pair for pair, row in expected.items() if row['matches_threshold']}
    coverage = result['coverage']
    assert coverage['objects'] == 24 and coverage['total_pairs'] == 276
    assert coverage['catalog_scope_confirmed'] is True
    for state in ('bound_excluded', 'measured_match', 'measured_nonmatch', 'unknown', 'deferred'):
        assert coverage[state] == counts[state]
    assert result['delivery']['delivered_matches'] == result['delivery']['matches_total'] == len(public_pairs)
    if 'candidate_pairs' in diagnostics:
        assert diagnostics['candidate_pairs'] == truth['candidate_count']
        assert len(measured_names) == truth['candidate_count']
    return {'passed': True, 'all_pairs_verified': 276, 'partitions': dict(counts),
            'true_matches': len(public_pairs), 'FP': 0, 'FN': 0, 'duplicate_pairs': 0,
            'all_measured_distances_verified': len(distance_errors),
            'maximum_distance_error_m': max(distance_errors, default=0.),
            'public_surface_witnesses_verified': 2 * len(public_pairs),
            'witness_and_distance_tolerance_m': 1e-10,
            'threshold_predicate_source': 'independent exact binary64 threshold truth',
            'candidate_recall': 1., 'final_recall': 1.}
