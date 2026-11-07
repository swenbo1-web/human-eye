"""B's exact AABB pruning: analytic answers and actual narrow-work counters.

No A/B benchmark or Blender session is run here. The unchanged A 41-method
module is selected separately by the root's single fixed targeted run.
"""
import json
import math
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_plugin import surface_proximity as surface
from human_eye_plugin.live_service import RequestBudgetError
from human_eye_plugin.scene_cache import SpatialSceneCache
from verification import test_surface_proximity_001 as original
from verification.test_concave_geometry import entity


def triangles(identity, rows):
    points = [point for triangle in rows for point in triangle]
    return entity(identity, points, [(3*i, 3*i+1, 3*i+2) for i in range(len(rows))])


def horizontal(z, shift_x=0):
    return [(shift_x, 0, z), (shift_x+1, 0, z), (shift_x, 1, z)]


def two_levels(first=1, second=2):
    return (triangles('a', [horizontal(0)]),
            triangles('b', [horizontal(first), horizontal(second)]))


class SurfaceAABBPruningTests(unittest.TestCase):
    def measure(self, left, right, checkpoint=None, diagnostics=None):
        return surface.measure_surface_proximity(left, right,
            checkpoint or (lambda stage: None), diagnostics=diagnostics)

    def assert_distance(self, result, expected):
        self.assertTrue(result['measurement_valid'], result)
        self.assertEqual(result['distance_m'], expected)
        self.assertEqual(result['witness_status'], 'measured')
        self.assertEqual(result['method'], 'exact_binary64_triangle_surface_features_v2')
        self.assertEqual(result['work']['intersection_tests'],
                         result['work']['triangle_pairs'] - result['work']['aabb_pruned_pairs'])

    def test_bound_strictly_above_best_skips_only_later_narrow_work(self):
        # Parallel z=0,1,2 planes give independent distances 1 and 2.
        result = self.measure(*two_levels())
        self.assert_distance(result, 1.)
        work = result['work']
        self.assertEqual(work['triangle_pairs'], 2)
        self.assertEqual(work['aabb_bound_tests'], 1)  # First pair has no best.
        self.assertEqual(work['aabb_pruned_pairs'], 1)
        self.assertEqual(work['intersection_tests'], 1)
        self.assertEqual((work['point_face_tests'], work['point_edge_tests'],
                          work['edge_edge_tests']), (6, 18, 9))

    def test_equal_bound_is_not_pruned_and_preserves_first_tied_witness(self):
        left = triangles('a', [horizontal(0)])
        right = triangles('b', [horizontal(1), horizontal(1, .25)])
        result = self.measure(left, right)
        self.assert_distance(result, 1.)
        self.assertEqual(result['work']['aabb_bound_tests'], 1)
        self.assertEqual(result['work']['aabb_pruned_pairs'], 0)
        self.assertEqual(result['work']['intersection_tests'], 2)
        # A's first vertex projects onto the first B triangle. Later features
        # have equal z-gap and must not replace this first attaining witness.
        self.assertEqual(result['point_a_world'], [0., 0., 0.])
        self.assertEqual(result['point_b_world'], [0., 0., 1.])

    def test_bound_below_best_keeps_a_later_smaller_distance(self):
        result = self.measure(*two_levels(2, 1))
        self.assert_distance(result, 1.)
        self.assertEqual(result['work']['triangle_pairs'], 2)
        self.assertEqual(result['work']['aabb_pruned_pairs'], 0)
        self.assertEqual(result['work']['intersection_tests'], 2)
        self.assertEqual(result['point_b_world'], [0., 0., 1.])

    def test_zero_bound_keeps_true_edge_through_face_intersection(self):
        left, crossing = original.edge_face_crossing_pair()
        distant = [tuple(float(value) + (2 if k == 2 else 0)
                         for k, value in enumerate(point)) for point in left.vertices]
        right = triangles('b', [distant, crossing.vertices.tolist()])
        result = self.measure(left, right)
        self.assert_distance(result, 0.)
        self.assertEqual(result['work']['triangle_pairs'], 2)
        self.assertEqual(result['work']['aabb_bound_tests'], 1)
        self.assertEqual(result['work']['aabb_pruned_pairs'], 0)
        self.assertEqual(result['work']['intersection_tests'], 2)
        self.assertEqual(result['point_a_world'], result['point_b_world'])
        self.assertEqual(result['direction_status'], 'not_applicable')

    def test_zero_bound_keeps_coplanar_overlap_and_disjoint_triangles(self):
        left = triangles('a', [horizontal(0)])
        cases = [
            ('area_overlap', [(0.25, .25, 0), (.75, .25, 0), (.25, .75, 0)], 0.),
            # A has x+y<=1; B has x+y>=1.5. The closest pair is
            # (.5,.5,0) and (.75,.75,0), giving exact squared distance 1/8.
            ('disjoint_overlapping_aabbs', [(.75, .75, 0), (1.75, .75, 0),
                                           (.75, 1.75, 0)], math.sqrt(1/8)),
        ]
        for label, row, expected in cases:
            with self.subTest(case=label):
                result = self.measure(left, triangles('b', [horizontal(2), row]))
                self.assert_distance(result, expected)
                self.assertEqual(result['work']['aabb_bound_tests'], 1)
                self.assertEqual(result['work']['aabb_pruned_pairs'], 0)
                self.assertEqual(result['work']['intersection_tests'], 2)
                if expected == 0:
                    self.assertEqual(result['point_a_world'], result['point_b_world'])
                    self.assertEqual(result['direction_status'], 'not_applicable')
                else:
                    self.assertEqual(result['point_a_world'], [.5, .5, 0.])
                    self.assertEqual(result['point_b_world'], [.75, .75, 0.])

    def test_far_degenerate_face_is_validated_before_any_pruning(self):
        left = triangles('a', [horizontal(0)])
        right = triangles('b', [horizontal(1), [(100, 100, 100), (101, 101, 101),
                                               (102, 102, 102)]])
        result = self.measure(left, right)
        self.assertFalse(result['measurement_valid'], result)
        self.assertEqual(result['reason'], 'surface_degenerate_triangle')
        self.assertEqual(result['work']['validated_faces'], 3)
        self.assertEqual(result['work']['triangle_pairs'], 0)
        self.assertEqual(result['work']['aabb_bound_tests'], 0)
        self.assertEqual(result['work']['aabb_pruned_pairs'], 0)

    def test_bounds_and_best_use_same_exact_integer_frame_units(self):
        for scale, shift in ((math.ldexp(1., -600), np.zeros(3)),
                             (math.ldexp(1., -20), np.full(3, 2.**30))):
            with self.subTest(scale=scale):
                left, right = two_levels()
                left = entity('a', left.vertices * scale + shift, left.faces)
                right = entity('b', right.vertices * scale + shift, right.faces)
                result = self.measure(left, right)
                self.assert_distance(result, scale)
                self.assertEqual(result['work']['aabb_pruned_pairs'], 1)
                self.assertEqual(result['work']['intersection_tests'], 1)
                self.assertEqual(result['direction_a_to_b'], [0., 0., 1.])

    def test_fractional_and_max_bit_bound_comparisons_do_not_expand_products(self):
        origin = ((0, 0), (0, 0), (0, 0))
        xy = ((1, 1), (1, 1), (0, 0))  # Integer L2=2.
        for numerator, denominator, expected in ((3, 2, True), (2, 1, False),
                                                  (5, 2, False)):
            with self.subTest(best=(numerator, denominator)):
                self.assertEqual(surface._aabb_exceeds_best(origin, xy,
                    (numerator, denominator, None)), expected)
        xyz = ((1, 1), (1, 1), (1, 1))  # L2=3, crossing floor(5/2).
        self.assertTrue(surface._aabb_exceeds_best(origin, xyz, (5, 2, None)))
        self.assertEqual(surface.MAX_BITS, 4096)
        self.assertEqual(surface._MAX_SCRATCH_BITS, 8193)
        maximum = (1 << surface.MAX_BITS) - 1
        # Both bounds and best operands fit 4096 bits. The separated-axis gap
        # has 4097 bits; its unnecessary square would exceed even scratch.
        negative = ((-maximum, -maximum), (0, 0), (0, 0))
        positive = ((maximum, maximum), (0, 0), (0, 0))
        self.assertTrue(surface._aabb_exceeds_best(negative, positive,
                                                  (maximum, maximum-1, None)))
        self.assertFalse(surface._aabb_exceeds_best(origin, origin,
                                                   (maximum, maximum-1, None)))

    def test_irrelevant_far_face_can_avoid_an_old_narrow_intermediate_refusal(self):
        # All captured values are real binary64 values. A's near pair attains
        # s exactly. The far pair's coordinate is 2098 bits in the common
        # integer frame; squaring its plane height would exceed retained bits.
        # B may safely avoid that irrelevant work; this is not a timing sample.
        smallest, far = math.ldexp(1., -1074), math.ldexp(1., 1023)
        yz = lambda x: [(x, 0, 0), (x, smallest, 0), (x, 0, smallest)]
        result = self.measure(triangles('a', [yz(0)]),
                              triangles('b', [yz(smallest), yz(far)]))
        self.assert_distance(result, smallest)
        self.assertEqual(result['work']['aabb_pruned_pairs'], 1)
        self.assertEqual(result['work']['intersection_tests'], 1)
        self.assertEqual(result['point_a_world'], [0., 0., 0.])
        self.assertEqual(result['point_b_world'], [smallest, 0., 0.])

    def test_checkpoint_exceptions_propagate_before_a_prunable_pair(self):
        for error in (RuntimeError('checkpoint cancellation signal'),
                      RequestBudgetError('expired', 'surface_proximity_pair')):
            diagnostics, seen = {}, []

            def checkpoint(stage):
                if stage == 'surface_proximity_pair':
                    seen.append(stage)
                    if len(seen) == 2:
                        raise error

            with self.subTest(error=type(error).__name__):
                with self.assertRaises(type(error)) as caught:
                    self.measure(*two_levels(), checkpoint=checkpoint, diagnostics=diagnostics)
                self.assertIs(caught.exception, error)
                self.assertEqual(len(seen), 2)
                self.assertEqual(diagnostics['triangle_pairs'], 1)
                self.assertEqual(diagnostics['aabb_pruned_pairs'], 0)


class SurfaceAABBCacheTests(unittest.TestCase):
    setUp = original.SurfaceProximityTaskTests.setUp
    set_pair = original.SurfaceProximityTaskTests.set_pair
    observe = original.SurfaceProximityTaskTests.observe

    def work(self):
        events = [json.loads(line) for line in self.service.audit_path.read_text('utf8').splitlines()]
        return [event['task_work'] for event in events if event['event'] == 'observe'][-1]

    def test_algorithm_version_is_distinct_with_fresh_binding_and_zero_hot_work(self):
        left, right = two_levels()
        self.set_pair(left, right)
        original_pair = SpatialSceneCache.pair_measurement
        versions = []

        def recorded(cache, focal, reference, compute, *, parameters=None, algorithm_version):
            versions.append(algorithm_version)
            if len(versions) == 1:
                # Seed a deliberately recognizable result under A's key with
                # identical ordered meshes and parameters. B must not use it.
                original_pair(cache, focal, reference,
                    lambda: dict(measurement_valid=True, distance_m=999.),
                    parameters=parameters, algorithm_version='task-surface-proximity-exact-v1')
            return original_pair(cache, focal, reference, compute,
                parameters=parameters, algorithm_version=algorithm_version)

        with patch.object(SpatialSceneCache, 'pair_measurement', autospec=True,
                          side_effect=recorded):
            cold = self.observe()
            cold_work = self.work()
            hot = self.observe()
            hot_work = self.work()
            self.host.scene['revision'] = 'r2'
            revised = self.observe()
            revised_work = self.work()
            changed = entity('a', left.vertices + [0, 0, -1], left.faces)
            self.set_pair(changed, right, 'r3')
            updated = self.observe()
            updated_work = self.work()
        self.assertEqual(versions, ['task-surface-proximity-exact-aabb-v2'] * 4)
        for result, distance in ((cold, 1.), (hot, 1.), (revised, 1.), (updated, 2.)):
            fact = result['facts']['surface_proximity']
            self.assertEqual(result['status'], 'observed')
            self.assertEqual(fact['status'], 'measured')
            self.assertEqual(fact['value']['distance_m'], distance)
            self.assertEqual(fact['method'], 'exact_binary64_triangle_surface_features_v2')
        self.assertEqual(cold['facts'], hot['facts'])
        self.assertEqual(hot['facts'], revised['facts'])
        self.assertEqual(revised['binding']['scene_revision'], 'r2')
        self.assertNotEqual(cold['binding']['scene_fingerprint'], revised['binding']['scene_fingerprint'])
        self.assertNotEqual(revised['binding']['scene_fingerprint'], updated['binding']['scene_fingerprint'])
        self.assertEqual(cold_work['surface_pair_count'], 1)
        self.assertEqual(cold_work['surface_work']['aabb_pruned_pairs'], 1)
        for work in (hot_work, revised_work):
            self.assertEqual(work['surface_pair_count'], 0)
            self.assertTrue(work['surface_pair_cache_hit'])
            self.assertEqual(work['surface_work'], {})
        self.assertEqual(updated_work['surface_pair_count'], 1)
        self.assertFalse(updated_work['surface_pair_cache_hit'])


if __name__ == '__main__':
    unittest.main()
