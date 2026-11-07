"""Eight fixed real-kernel/cache groups; independent rational distance oracles."""
import copy
from fractions import Fraction as F
import json
import math
import sys
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_plugin import surface_proximity as surface, task_query
from human_eye_plugin.live_service import RequestBudgetError
from human_eye_plugin.scene_cache import SpatialSceneCache
from verification.test_concave_geometry import entity
from verification.test_task_complete_001 import large_world_pair


EVIDENCE = {}
NOOP = lambda stage: None


def triangle(identity, points):
    return entity(identity, points, [[0, 1, 2]])


def corner_pair(x=1., y=0.):
    return (triangle('focal', [(0, 0, 0), (-1, 0, 0), (0, -1, 0)]),
            triangle('target', [(x, y, 0), (x+1, y, 0), (x, y+1, 0)]))


def key_square(result):
    n, d, e = result['_exact_distance_sq']
    return F(n, d) * F(2) ** e


def corner_box_oracle(left, right):
    # Represented XY corner against a convex polygon, with overlapping Z.
    corner = [F(float(v)) for v in np.max(right.vertices[:, :2], axis=0)]
    assert (np.min(left.vertices[:, :2], axis=0) > np.max(right.vertices[:, :2], axis=0)).all()
    assert max(min(left.vertices[:, 2]), min(right.vertices[:, 2])) <= min(max(left.vertices[:, 2]), max(right.vertices[:, 2]))
    polygon = [[F(float(v)) for v in row] for row in left.vertices[:4, :2]]
    squares = []
    for start, end in zip(polygon, polygon[1:] + polygon[:1]):
        edge = [b-a for a, b in zip(start, end)]
        offset = [p-a for p, a in zip(corner, start)]
        t = max(F(0), min(F(1), sum(a*b for a, b in zip(offset, edge)) / sum(v*v for v in edge)))
        squares.append(sum((p-t*v)**2 for p, v in zip(offset, edge)))
    return min(squares)


class ExactRankTests(unittest.TestCase):
    def setUp(self):
        self.row = dict(kernel_calls=0, nearest_calls=0, frames=[], local_squares=[], results=[], oracles=[])
        EVIDENCE[self._testMethodName] = self.row
        kernel, nearest, frame = surface.measure_surface_proximity, surface._nearest, surface._integer_frame
        def measured(*args, **kwargs):
            self.row['kernel_calls'] += 1
            result = kernel(*args, **kwargs)
            self.row['results'].append(copy.deepcopy(result))
            return result
        def solved(*args, **kwargs):
            self.row['nearest_calls'] += 1
            value = nearest(*args, **kwargs)
            self.row['local_squares'].append([value[0], value[1]])
            return value
        def framed(*args, **kwargs):
            value = frame(*args, **kwargs)
            self.row['frames'].append(value[1])
            return value
        for owner, name, replacement in ((surface, 'measure_surface_proximity', measured),
                (task_query, 'measure_surface_proximity', measured),
                (surface, '_nearest', solved), (surface, '_integer_frame', framed)):
            manager = patch.object(owner, name, replacement)
            manager.start(); self.addCleanup(manager.stop)

    def measure(self, pair, oracle):
        before = self.row['nearest_calls']
        result = surface.measure_surface_proximity(*pair, NOOP, retain_exact_rank=True)
        self.assertTrue(result['measurement_valid'], result)
        self.assertEqual(self.row['nearest_calls'], before+1)
        self.assertEqual(key_square(result), oracle)
        self.row['oracles'].append(str(oracle))
        return result

    def rank(self, records):
        before = self.row['nearest_calls']
        result = surface._rank_surface_results(records, NOOP)
        self.assertEqual(self.row['nearest_calls'], before)
        self.row['rank'] = result
        return result

    def test_g01_equal_published_float_distinct_exact_distances(self):
        a = self.measure(corner_pair(), F(1))
        epsilon = 2.**-27
        b = self.measure(corner_pair(y=epsilon), F(1)+F(epsilon)**2)
        self.assertEqual(a['distance_m'], b['distance_m'])
        self.assertEqual(a['distance_m'], 1.)
        self.assertEqual(self.rank({'b': b, 'a': a})['ordered_object_id_groups'], [['a'], ['b']])

    def test_g02_world_factors_reverse_local_comparison(self):
        epsilon = 2.**-200
        a = self.measure(corner_pair(x=2., y=epsilon), F(4)+F(epsilon)**2)
        b = self.measure(corner_pair(x=3.), F(9))
        local_a, local_b = (F(*v) for v in self.row['local_squares'])
        self.assertGreater(local_a, local_b)
        self.assertNotEqual(*self.row['frames'])
        self.assertLess(key_square(a), key_square(b))
        self.assertEqual(self.rank({'b': b, 'a': a})['ordered_object_id_groups'], [['a'], ['b']])

    def test_g03_positive_exact_ties_stable_ids_different_factors(self):
        focal = triangle('focal', [(-2, -2, 4), (4, -2, -2), (-2, 4, -2)])
        a = self.measure((focal, triangle('a', [(0, 0, 1), (1, 0, 2), (0, 1, 2)])), F(1, 3))
        b = self.measure((focal, triangle('b', [(0, 0, 1), (.5, 0, 1.5), (0, .5, 1.5)])), F(1, 3))
        self.assertNotEqual(*self.row['frames'])
        result = self.rank({'z': b, 'a': a})
        self.assertEqual(result['ordered_object_id_groups'], [['a', 'z']])
        self.assertEqual(result['status'], 'ranked')

    def test_g04_exact_zero_ties(self):
        left, _ = corner_pair()
        a = self.measure((left, left), F(0))
        b = self.measure((left, triangle('other', [(0, 0, 0), (-.5, 0, 0), (0, -.5, 0)])), F(0))
        self.assertEqual(a['_exact_distance_sq'], [0, 1, 0])
        self.assertEqual(self.rank({'z': b, 'a': a})['ordered_object_id_groups'], [['a', 'z']])

    def test_g05_witness_failure_retains_valid_exact_distance(self):
        pair = large_world_pair()
        result = self.measure(pair, corner_box_oracle(*pair))
        self.assertEqual(result['witness_status'], 'unknown')
        self.assertTrue(result['witness_reason'])
        self.assertEqual(self.rank({'target': result})['status'], 'ranked')
        fact = task_query._surface_proximity_fact(result)
        self.assertEqual(fact['status'], 'unknown')
        self.assertEqual(fact['value']['distance_m'], result['distance_m'])

    def test_g06_unknown_candidate_and_original_reason_remain(self):
        pair = corner_pair()
        known = self.measure(pair, F(1))
        bad = triangle('bad', [(2, 0, 0), (3, 0, 0), (4, 0, 0)])
        unknown = surface.measure_surface_proximity(pair[0], bad, NOOP, retain_exact_rank=True)
        self.assertFalse(unknown['measurement_valid'])
        self.assertEqual(unknown['reason'], 'surface_degenerate_triangle')
        self.assertNotIn('_exact_distance_sq', unknown)
        result = self.rank({'known': known, 'unknown': unknown})
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['unresolved'], {'unknown': 'surface_degenerate_triangle'})
        self.assertEqual(result['scope'], 'provided_kernel_results_only')

    def test_g07_old_and_rank_cache_separation_hit_and_exact_byte_charge(self):
        left, right = corner_pair(y=2.**-27)
        cache = SpatialSceneCache()
        def obtain(retain):
            diagnostics = {}
            result = task_query._surface_pair_measurement(left, right, cache, NOOP,
                source='unit_fixture', diagnostics=diagnostics, retain_exact_rank=retain)
            self.row.setdefault('cache_calls', []).append(dict(retain=retain, diagnostics=diagnostics))
            return result
        old = obtain(False); old_hit = obtain(False)
        self.assertNotIn('_exact_distance_sq', old)
        self.assertEqual(old, old_hit)
        self.assertEqual(self.rank({'legacy': old})['status'], 'unknown')
        rank_result = obtain(True)
        expected_key = rank_result['_exact_distance_sq'].copy()
        self.assertEqual(key_square(rank_result), F(1)+F(2.**-27)**2)
        rank_result['_exact_distance_sq'][0] = 999
        hit = obtain(True)
        self.assertEqual(hit['_exact_distance_sq'], expected_key)
        self.assertEqual(self.rank({'new': hit})['status'], 'ranked')
        self.assertEqual([v['diagnostics']['surface_pair_cache_hit'] for v in self.row['cache_calls']], [False, True, False, True])
        self.assertEqual(self.row['nearest_calls'], 2)
        payloads = [entry[0] for entry in cache._measurements.values()]
        self.assertEqual(sum('_exact_distance_sq' in json.loads(p) for p in payloads), 1)
        charged = sum(sys.getsizeof(p)+sys.getsizeof(k)+256+64 for k, (p, _) in cache._measurements.items())
        self.assertEqual(cache.stats()['accounted_bytes'], charged)
        self.assertEqual(cache.stats()['accounted_bytes'], cache._slow_recount_bytes())
        self.row['cache_stats'] = cache.stats()
        self.row['serialized_payload_bytes'] = [len(p) for p in payloads]
        self.row['independent_charged_bytes'] = charged

    def test_g08_public_projection_and_comparison_deadline(self):
        a = self.measure(corner_pair(), F(1))
        b = self.measure(corner_pair(x=2.), F(4))
        fact = task_query._surface_proximity_fact(a)
        without = {k: v for k, v in a.items() if k != '_exact_distance_sq'}
        self.assertEqual(fact, task_query._surface_proximity_fact(without))
        self.assertNotIn('_exact_distance_sq', json.dumps(fact))
        error = RequestBudgetError('expired', 'surface_proximity_rank_compare')
        seen = []
        def checkpoint(stage):
            seen.append(stage)
            if stage == 'surface_proximity_rank_compare':
                raise error
        before = self.row['nearest_calls']
        with self.assertRaises(RequestBudgetError) as caught:
            surface._rank_surface_results({'b': b, 'a': a}, checkpoint)
        self.assertIs(caught.exception, error)
        self.assertEqual(self.row['nearest_calls'], before)
        self.row['deadline_stages'] = seen
        self.row['public_fact'] = fact
