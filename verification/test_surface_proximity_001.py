"""Independent surface-proximity answers, grouped by the A acceptance plan.

Groups 01..09 are offline. Group 10 is the root-owned installed Blender QA.
Expected distances use parallel/axis support bounds and explicit attaining
points, or the retained Decimal corner-to-segment oracle on represented input.
"""
import json
import math
from fractions import Fraction
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_plugin import geometry_safety as geometry
from human_eye_plugin import live_spatial_mcp as mcp
from human_eye_plugin import surface_proximity as surface
from human_eye_plugin.live_service import LiveSpatialService, RequestBudgetError
from verification import test_task_complete_001 as previous
from verification.perf030_002_cases import triangle_truth
from verification.test_concave_geometry import box, entity
from verification.test_selected_task_query import SelectedHost


LEGACY_FACTS = ['surface_clearance', 'solid_relation', 'nearest_witness', 'pair_relation']


def triangle(identity, vertices):
    return entity(identity, vertices, [[0, 1, 2]])


def translated(mesh, vector, identity):
    return entity(identity, mesh.vertices + np.asarray(vector), mesh.faces)


def open_slanted_pair():
    u = np.array([1., -1., 0.]) / 8
    v = np.array([1., 1., -2.]) / 16
    vertices = np.array([-u - v, u - v, u + v, -u + v])
    faces = [[0, 1, 2], [0, 2, 3]]
    return (entity('a', vertices, faces),
            entity('b', vertices + np.array([1., 1., 1.]) / 64, faces))


def edge_face_crossing_pair():
    return (triangle('a', [(-2, -2, 0), (2, -2, 0), (0, 2, 0)]),
            triangle('b', [(0, 0, -1), (0, 0, 1), (0, 1, 1)]))


def parallel_triangles(gap=1.0):
    a = triangle('a', [(0, 0, 0), (1, 0, 0), (0, 1, 0)])
    return a, translated(a, (0, 0, gap), 'b')


class SurfaceProximityMathTests(unittest.TestCase):
    def measure(self, left, right, checkpoint=None):
        return surface.measure_surface_proximity(left, right, checkpoint or (lambda stage: None))

    def assert_original_witness(self, result, left, right, expected):
        self.assertTrue(result['measurement_valid'], result)
        self.assertGreaterEqual(result['distance_m'], 0)
        self.assertAlmostEqual(result['distance_m'], expected, delta=1e-14)
        self.assertEqual(result['witness_status'], 'measured')
        a, b = result['point_a_world'], result['point_b_world']
        self.assertEqual(len(a), 3)
        self.assertEqual(len(b), 3)
        self.assertTrue(all(math.isfinite(value) for p in (a, b) for value in p))
        self.assertAlmostEqual(math.dist(a, b), expected, delta=1e-9)
        bound = Fraction.from_float(1e-9) ** 2
        for point, mesh in ((a, left), (b, right)):
            distance_sq = min(triangle_truth(point, mesh.vertices[face])['distance_sq']
                              for face in mesh.faces)
            self.assertLessEqual(distance_sq, bound)
        return a, b

    def assert_zero(self, left, right):
        result = self.measure(left, right)
        a, b = self.assert_original_witness(result, left, right, 0.)
        self.assertEqual(result['distance_m'], 0)
        self.assertEqual(a, b)
        self.assertIsNone(result['direction_a_to_b'])
        self.assertEqual(result['direction_status'], 'not_applicable')
        return result

    def test_g01_open_slanted_surfaces_have_independent_metric_and_topology(self):
        left, right = open_slanted_pair()
        result = self.measure(left, right)
        self.assert_original_witness(result, left, right, math.sqrt(3) / 64)
        np.testing.assert_allclose(result['direction_a_to_b'],
                                   np.ones(3) / math.sqrt(3), rtol=0, atol=1e-14)
        self.assertEqual(result['direction_status'], 'measured')
        self.assertEqual(result['topology'], [
            {'boundary_edge_count': 4, 'nonmanifold_edge_count': 0},
            {'boundary_edge_count': 4, 'nonmanifold_edge_count': 0},
        ])

    def test_g02_edge_through_face_is_true_zero_in_both_orders(self):
        left, right = edge_face_crossing_pair()
        self.assert_zero(left, right)
        self.assert_zero(right, left)

    def test_g03_coplanar_separated_triangles_have_positive_gap(self):
        left, _ = parallel_triangles()
        right = translated(left, (2, 0, 0), 'b')
        result = self.measure(left, right)
        self.assert_original_witness(result, left, right, 1.)
        np.testing.assert_array_equal(result['direction_a_to_b'], [1, 0, 0])

    def test_g03_coplanar_point_contact_is_complete_zero(self):
        left, _ = parallel_triangles()
        self.assert_zero(left, translated(left, (1, 0, 0), 'b'))

    def test_g03_coplanar_shared_edge_is_complete_zero(self):
        left, _ = parallel_triangles()
        right = triangle('b', [(0, 0, 0), (1, 0, 0), (0, -1, 0)])
        self.assert_zero(left, right)

    def test_g03_coplanar_area_overlap_is_complete_zero(self):
        left, _ = parallel_triangles()
        self.assert_zero(left, translated(left, (.25, .25, 0), 'b'))

    def test_g04_minimum_at_face_interior(self):
        left = triangle('a', [(-2, -2, 0), (2, -2, 0), (0, 2, 0)])
        right = triangle('b', [(0, 0, 1), (.25, 0, 2), (0, .25, 2)])
        result = self.measure(left, right)
        a, b = self.assert_original_witness(result, left, right, 1.)
        np.testing.assert_allclose(a, [0, 0, 0], rtol=0, atol=1e-14)
        np.testing.assert_allclose(b, [0, 0, 1], rtol=0, atol=1e-14)

    def test_g04_minimum_at_edge_interior(self):
        left = triangle('a', [(0, 0, 0), (2, 0, 0), (0, -2, 0)])
        right = triangle('b', [(1, 1, 0), (1, 2, 1), (1.5, 2, 1)])
        result = self.measure(left, right)
        a, b = self.assert_original_witness(result, left, right, 1.)
        np.testing.assert_allclose(a, [1, 0, 0], rtol=0, atol=1e-14)
        np.testing.assert_allclose(b, [1, 1, 0], rtol=0, atol=1e-14)

    def test_g04_minimum_between_two_edge_interiors(self):
        left = triangle('a', [(0, -1, 0), (0, 1, 0), (-1, 0, 0)])
        right = triangle('b', [(1, 0, -1), (1, 0, 1), (2, 1, 0)])
        result = self.measure(left, right)
        a, b = self.assert_original_witness(result, left, right, 1.)
        np.testing.assert_allclose(a, [0, 0, 0], rtol=0, atol=1e-14)
        np.testing.assert_allclose(b, [1, 0, 0], rtol=0, atol=1e-14)

    def test_g04_minimum_at_endpoints(self):
        left = triangle('a', [(0, 0, 0), (-1, 0, 0), (0, -1, 0)])
        right = triangle('b', [(1, 1, 0), (2, 1, 0), (1, 2, 0)])
        result = self.measure(left, right)
        a, b = self.assert_original_witness(result, left, right, math.sqrt(2))
        np.testing.assert_array_equal(a, [0, 0, 0])
        np.testing.assert_array_equal(b, [1, 1, 0])

    def test_g04_exact_non_axis_frame_and_swapped_direction(self):
        left, right = parallel_triangles()
        # This integer matrix is five times an orthogonal rotation.
        transform = np.array([[3, 0, 4], [0, 5, 0], [-4, 0, 3.]])
        left = entity('a', left.vertices @ transform.T, left.faces)
        right = entity('b', right.vertices @ transform.T, right.faces)
        for a, b, direction in ((left, right, [.8, 0, .6]),
                                (right, left, [-.8, 0, -.6])):
            with self.subTest(focal=a.object_id):
                result = self.measure(a, b)
                self.assert_original_witness(result, a, b, 5.)
                np.testing.assert_allclose(result['direction_a_to_b'], direction,
                                           rtol=0, atol=1e-14)

    def test_g05_separated_closed_boxes_have_surface_gap(self):
        left = box((0, 0, 0), (1, 1, 1), 'a')
        right = box((2, 0, 0), (1, 1, 1), 'b')
        result = self.measure(left, right)
        self.assert_original_witness(result, left, right, 1.)
        self.assertEqual([row['boundary_edge_count'] for row in result['topology']], [0, 0])

    def test_g05_crossing_closed_boxes_have_surface_zero(self):
        left = box((0, 0, 0), (2, 2, 2), 'a')
        right = box((1, 0, 0), (2, 2, 2), 'b')
        self.assert_zero(left, right)

    def test_g05_strict_containment_has_positive_surface_distance(self):
        inner = box((0, 0, 0), (1, 1, 1), 'a')
        outer = box((0, 0, 0), (4, 4, 4), 'b')
        result = self.measure(inner, outer)
        self.assert_original_witness(result, inner, outer, 1.5)
        self.assertNotIn('is_penetrating', result)

    def test_g06_small_positive_gap_is_never_tolerance_contact(self):
        left, right = parallel_triangles(2.0 ** -40)
        result = self.measure(left, right)
        self.assert_original_witness(result, left, right, 2.0 ** -40)
        self.assertEqual(result['distance_m'], 2.0 ** -40)
        self.assertGreater(result['distance_m'], 0)

    def test_g06_representable_distance_survives_squared_float_underflow(self):
        gap = 2.0 ** -600
        left, right = parallel_triangles(gap)
        result = self.measure(left, right)
        self.assertTrue(result['measurement_valid'], result)
        self.assertEqual(result['distance_m'], gap)
        self.assertGreater(result['distance_m'], 0)
        np.testing.assert_array_equal(result['direction_a_to_b'], [0, 0, 1])

    def test_g06_micro_edge_crossing_remains_zero(self):
        epsilon = 2.0 ** -40
        left = triangle('a', [(-2, -2, 0), (2, -2, 0), (0, 2, 0)])
        right = triangle('b', [(0, 0, -epsilon), (0, 0, epsilon), (0, 1, epsilon)])
        self.assert_zero(left, right)

    def test_g06_slender_and_nearly_parallel_triangles_keep_positive_minimum(self):
        width, gap, slope = 2.0 ** -40, 2.0 ** -42, 2.0 ** -30
        left = triangle('a', [(0, 0, 0), (1, 0, 0), (0, width, 0)])
        right = triangle('b', [(0, 0, gap), (1, 0, gap + slope), (0, width, gap)])
        result = self.measure(left, right)
        self.assert_original_witness(result, left, right, gap)
        self.assertEqual(result['distance_m'], gap)

    def test_g07_large_exact_translation_preserves_represented_gap(self):
        left, right = parallel_triangles()
        vector = np.array([2.0 ** 40, -(2.0 ** 40), 2.0 ** 40])
        left = translated(left, vector, 'a')
        right = translated(right, vector, 'b')
        result = self.measure(left, right)
        self.assert_original_witness(result, left, right, 1.)

    def test_g07_world_publication_failure_retains_independent_distance(self):
        left, right = previous.large_world_pair()
        expected = previous.independent_corner_gap(left, right)
        result = self.measure(left, right)
        self.assertTrue(result['measurement_valid'], result)
        self.assertAlmostEqual(result['distance_m'], expected, delta=1e-14)
        self.assertEqual(result['witness_status'], 'unknown')
        self.assertTrue(result.get('witness_reason'))
        self.assertIsNone(result.get('point_a_world'))
        self.assertIsNone(result.get('point_b_world'))

    def test_g07_bit_budget_refuses_large_exact_intermediates(self):
        high = 2.0 ** 1023
        left = triangle('a', [(-high, -high, 0), (high, -high, 0), (0, high, 0)])
        right = triangle('b', [(-high, -high, high), (high, -high, high), (0, high, high)])
        result = self.measure(left, right)
        self.assertFalse(result['measurement_valid'], result)
        self.assertIn('bit', result['reason'])

    def test_g07_float_distance_range_failure_is_explicit(self):
        high = 2.0 ** 1023
        left = triangle('a', [(-high, 0, 0), (-high, 1, 0), (-high, 0, 1)])
        right = triangle('b', [(high, 0, 0), (high, 1, 0), (high, 0, 1)])
        result = self.measure(left, right)
        self.assertFalse(result['measurement_valid'], result)
        self.assertRegex(result['reason'], 'range|numeric|overflow|finite|represent')

    def test_g07_subnormal_rounding_respects_both_sides_of_the_halfway_boundary(self):
        smallest = math.ldexp(1.0, -1074)
        high = 1 << 300
        scaled_high = math.ldexp(smallest, 300)
        right = triangle('b', [(smallest, scaled_high, scaled_high),
                               (2 * smallest, scaled_high, scaled_high),
                               (smallest, scaled_high, 2 * scaled_high)])
        for sign in (1, -1):
            # B's closest edge has signed plane numerator s*H. Its projection
            # falls inside A. Comparing exact squares to (s/2)^2 cancels s^2.
            coefficient = 2 * high - sign
            denominator = coefficient ** 2 + 1
            self.assertEqual(4 * high * high > denominator, sign == 1)
            self.assertLess(high * high, denominator)
            self.assertGreaterEqual(2 * coefficient - high + sign, high)
            # The first B vertex's foot has A barycentric coordinates
            # lambda=(D-H*C)/D and mu=1/4, both strictly inside the face.
            barycentric_numerator = denominator - high * coefficient
            self.assertGreater(barycentric_numerator, 0)
            self.assertLess(4 * barycentric_numerator, 3 * denominator)
            self.assertEqual((high - sign) * denominator + high,
                             coefficient * barycentric_numerator)
            left = triangle('a', [(0, sign * smallest, 0),
                                   (0, sign * smallest, 4 * scaled_high),
                                   (smallest, 2 * scaled_high, 0)])
            with self.subTest(side='above_halfway' if sign == 1 else 'below_halfway'):
                result = self.measure(left, right)
                if sign == 1:
                    self.assertTrue(result['measurement_valid'], result)
                    self.assertEqual(result['distance_m'], smallest)
                else:
                    self.assertFalse(result['measurement_valid'], result)
                    self.assertIsNone(result['distance_m'])
                    self.assertIn('below_float_resolution', result['reason'])

    def test_g07_pre_capture_rounding_loss_is_not_reconstructed(self):
        base = 2.0 ** 60
        left = triangle('a', [(base, base, base), (base + 1, base, base),
                              (base, base + 1, base)])
        right = translated(left, (0, 0, 256), 'b')
        result = self.measure(left, right)
        self.assertFalse(result['measurement_valid'], result)
        self.assertIn('degenerate', result['reason'])

    def test_g08_degenerate_late_face_is_checked_before_zero_early_exit(self):
        left, right = edge_face_crossing_pair()
        left = entity('a', np.vstack([left.vertices, [[4, 4, 4], [5, 5, 5], [6, 6, 6]]]),
                      [[0, 1, 2], [3, 4, 5]])
        result = self.measure(left, right)
        self.assertFalse(result['measurement_valid'], result)
        self.assertIn('degenerate', result['reason'])

    def test_g08_nonmanifold_edge_counts_do_not_block_surface_metric(self):
        left = entity('a', [(0, 0, 0), (1, 0, 0), (0, 1, 0),
                            (0, 0, 1), (0, -1, 0)],
                      [[0, 1, 2], [0, 3, 1], [0, 1, 4]])
        right = triangle('b', [(0, 0, 3), (1, 0, 3), (0, 1, 3)])
        result = self.measure(left, right)
        self.assert_original_witness(result, left, right, 2.)
        self.assertEqual(result['topology'][0],
                         {'boundary_edge_count': 6, 'nonmanifold_edge_count': 1})

    def test_g08_duplicate_faces_count_incidence_without_solid_certification(self):
        left, right = parallel_triangles()
        for count, expected_nonmanifold in ((2, 0), (3, 3)):
            with self.subTest(copies=count):
                duplicated = entity('a', left.vertices, [[0, 1, 2]] * count)
                result = self.measure(duplicated, right)
                self.assert_original_witness(result, duplicated, right, 1.)
                self.assertEqual(result['topology'][0],
                    {'boundary_edge_count': 0, 'nonmanifold_edge_count': expected_nonmanifold})
                self.assertNotIn('is_closed', result)
                self.assertNotIn('solid_relation', result)

    def test_g08_face_order_and_winding_preserve_surface_values(self):
        left, right = open_slanted_pair()
        reversed_left = entity('a', left.vertices, left.faces[::-1, ::-1])
        reversed_right = entity('b', right.vertices, right.faces[::-1, ::-1])
        result = self.measure(reversed_left, reversed_right)
        self.assert_original_witness(result, reversed_left, reversed_right, math.sqrt(3) / 64)
        np.testing.assert_allclose(result['direction_a_to_b'],
                                   np.ones(3) / math.sqrt(3), rtol=0, atol=1e-14)

    def test_g08_unreferenced_points_cannot_reduce_triangle_surface_distance(self):
        left, right = parallel_triangles()
        left = entity('a', np.vstack([left.vertices, [[0, 0, 1]]]), left.faces)
        right = entity('b', np.vstack([right.vertices, [[0, 0, 0]]]), right.faces)
        result = self.measure(left, right)
        self.assert_original_witness(result, left, right, 1.)

    def test_g08_bad_face_indices_remain_unknown(self):
        vertices = np.array([(0, 0, 0), (1, 0, 0), (0, 1, 0)], dtype=float)
        _, right = parallel_triangles()
        for bad in (-1, 3):
            with self.subTest(index=bad):
                malformed = SimpleNamespace(vertices=vertices, faces=np.array([[0, 1, bad]]))
                result = self.measure(malformed, right)
                self.assertFalse(result['measurement_valid'], result)
                self.assertTrue(result['reason'])

    def test_g09_face_and_pair_budgets_precede_face_expansion(self):
        class CountOnlyFaces:
            def __init__(self, count):
                self.count = count

            def __len__(self):
                return self.count

            def __iter__(self):
                raise AssertionError('Over-budget faces expanded')

            def __getitem__(self, key):
                raise AssertionError('Over-budget faces indexed')

        vertices = np.array([(0, 0, 0), (1, 0, 0), (0, 1, 0)], dtype=float)
        for counts in ((4096, 1), (129, 128)):
            with self.subTest(counts=counts):
                left = SimpleNamespace(vertices=vertices, faces=CountOnlyFaces(counts[0]))
                right = SimpleNamespace(vertices=vertices, faces=CountOnlyFaces(counts[1]))
                result = self.measure(left, right)
                self.assertFalse(result['measurement_valid'], result)
                self.assertRegex(result['reason'], 'budget|limit')

    def test_g09_cancel_and_deadline_propagate_from_exact_pair_work(self):
        left, right = open_slanted_pair()
        for error in (RuntimeError('surface cancelled'), TimeoutError('surface deadline'),
                      RequestBudgetError('expired', 'surface_exact_loop')):
            seen = []

            def checkpoint(stage):
                if stage in ('surface_proximity_pair', 'surface_proximity_point_face_tests',
                             'surface_proximity_point_edge_tests', 'surface_proximity_edge_edge_tests'):
                    seen.append(stage)
                    if len(seen) == 2:
                        raise error

            with self.subTest(error=type(error).__name__):
                with self.assertRaises(type(error)):
                    self.measure(left, right, checkpoint)
                self.assertGreaterEqual(len(seen), 2)


class SurfaceProximityTaskTests(unittest.TestCase):
    setUp = previous.CurrentTaskEvidenceTests.setUp
    set_pair = previous.CurrentTaskEvidenceTests.set_pair

    def observe(self, facts=('surface_proximity',)):
        return self.service.observe('surface-proximity', include_image=False, query={
            'mode': 'task', 'objects': [{'id': 'a'}, {'id': 'b'}],
            'requested_facts': list(facts)})

    def assert_surface_fact(self, result, expected):
        fact = result['facts']['surface_proximity']
        self.assertEqual(fact['status'], 'measured', fact)
        self.assertEqual(fact['semantics'], 'current_evaluated_triangle_surfaces_world_metres')
        self.assertAlmostEqual(fact['value']['distance_m'], expected, delta=1e-14)
        return fact

    def test_g01_mixed_open_solid_unknown_preserves_surface_fact(self):
        self.set_pair(*open_slanted_pair())
        result = self.observe(['surface_proximity', 'pair_relation', 'solid_relation',
                               'surface_clearance', 'nearest_witness'])
        surface_fact = self.assert_surface_fact(result, math.sqrt(3) / 64)
        self.assertEqual(surface_fact['value']['topology'][0]['boundary_edge_count'], 4)
        self.assertEqual(result['status'], 'partial')
        for name in ('pair_relation', 'solid_relation', 'surface_clearance', 'nearest_witness'):
            self.assertEqual(result['facts'][name]['status'], 'unknown')
            self.assertEqual(result['facts'][name]['reason'], 'unsupported_solid_geometry')

    def test_g05_containment_surface_value_keeps_old_negative_escape(self):
        self.set_pair(box((0, 0, 0), (1, 1, 1), 'a'),
                      box((0, 0, 0), (4, 4, 4), 'b'))
        result = self.observe(['surface_proximity', 'surface_clearance', 'pair_relation'])
        self.assert_surface_fact(result, 1.5)
        self.assertLess(result['facts']['surface_clearance']['value'], 0)
        self.assertEqual(result['facts']['pair_relation']['value']['relation'], 'penetrating')

    def test_g07_known_distance_with_unpublished_witness_is_partial(self):
        left, right = previous.large_world_pair()
        self.set_pair(left, right)
        result = self.observe()
        fact = result['facts']['surface_proximity']
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(fact['status'], 'unknown')
        self.assertAlmostEqual(fact['value']['distance_m'],
                               previous.independent_corner_gap(left, right), delta=1e-14)
        self.assertEqual(fact['witness_status'], 'unknown')
        self.assertTrue(fact.get('reason') or fact.get('witness_reason'))

    def test_g09_surface_only_does_not_invoke_solid_or_sat_work(self):
        self.set_pair(*open_slanted_pair())
        with patch('human_eye_plugin.task_query.measure_pair_geometry',
                   side_effect=AssertionError('Unrequested solid calculation')), \
             patch.object(geometry, '_certified_solid_collision',
                          side_effect=AssertionError('Unrequested solid certification')), \
             patch.object(geometry, '_single_convex_collision_and_zero',
                          side_effect=AssertionError('Unrequested SAT')):
            result = self.observe()
        self.assert_surface_fact(result, math.sqrt(3) / 64)
        self.assertEqual(result['status'], 'observed')

    def test_g09_old_facts_do_not_compute_new_surface_fact(self):
        with patch('human_eye_plugin.task_query.measure_surface_proximity',
                   side_effect=AssertionError('Unrequested new surface calculation')):
            result = self.observe(LEGACY_FACTS)
        self.assertEqual(result['status'], 'observed')
        self.assertNotIn('surface_proximity', result['facts'])

    def test_g09_loose_vertices_bypass_full_mesh_pair_key_expansion(self):
        left, right = parallel_triangles()
        left = entity('a', np.vstack([left.vertices, [[0, 0, 1], [1000, 1000, 1000]]]),
                      left.faces)
        right = entity('b', np.vstack([right.vertices, [[0, 0, 0], [-1000, -1000, -1000]]]),
                       right.faces)
        self.set_pair(left, right)
        with patch('human_eye_plugin.scene_cache.SpatialSceneCache.pair_measurement',
                   side_effect=AssertionError('Loose vertices expanded into the pair cache key')):
            result = self.observe()
        self.assert_surface_fact(result, 1.)
        self.assertEqual(result['status'], 'observed')

    def test_g09_cache_reuse_binds_current_revision_and_geometry_change_invalidates(self):
        left, right = open_slanted_pair()
        self.set_pair(left, right)
        with patch('human_eye_plugin.task_query.measure_surface_proximity',
                   wraps=surface.measure_surface_proximity) as measured:
            initial = self.observe()
            again = self.observe()
            self.host.scene['revision'] = 'r2'
            revised = self.observe()
            self.set_pair(translated(left, (-1/64, -1/64, -1/64), 'a'), right, 'r3')
            updated = self.observe()
        self.assertEqual(measured.call_count, 2)
        self.assertEqual(initial['facts'], again['facts'])
        self.assertEqual(initial['facts'], revised['facts'])
        self.assertEqual(revised['binding']['scene_revision'], 'r2')
        self.assertNotEqual(initial['binding']['scene_fingerprint'],
                            revised['binding']['scene_fingerprint'])
        self.assertNotEqual(revised['binding']['scene_fingerprint'],
                            updated['binding']['scene_fingerprint'])
        self.assert_surface_fact(updated, math.sqrt(3) / 32)
        self.assertEqual(initial['binding']['runtime_source_sha256'],
                         updated['binding']['runtime_source_sha256'])

    def test_g09_mixed_legacy_demands_preserve_values_and_distinct_cache_entry(self):
        with patch('human_eye_plugin.task_query.measure_pair_geometry',
                   wraps=geometry.measure_pair_geometry) as old_measured, \
             patch('human_eye_plugin.task_query.measure_surface_proximity',
                   wraps=surface.measure_surface_proximity) as surface_measured:
            legacy = self.observe(LEGACY_FACTS)
            combined = self.observe(LEGACY_FACTS + ['surface_proximity'])
            again = self.observe(LEGACY_FACTS + ['surface_proximity'])
        self.assertEqual(old_measured.call_count, 1)
        self.assertEqual(surface_measured.call_count, 1)
        for name in LEGACY_FACTS:
            self.assertEqual(combined['facts'][name], legacy['facts'][name])
        self.assertEqual(again['facts'], combined['facts'])

    def test_g09_selected_capture_and_brief_encoding_are_single_pass(self):
        self.set_pair(*open_slanted_pair())
        scene = self.host.scene
        self.host = SelectedHost()
        self.host.scene = scene
        self.host.instances = {'a': '11', 'b': '12'}
        self.service = LiveSpatialService(self.service.config_path, host=self.host)
        with patch.object(self.host, 'capture_scene', side_effect=AssertionError('Full scene capture')):
            result = self.observe()
        self.assertEqual(len(self.host.selected_calls), 1)
        self.assertEqual(result['binding']['selected_count'], 2)
        with patch.object(mcp.json, 'dumps', wraps=json.dumps) as encoded:
            reply = mcp._tool_result(result, is_error=False, response_detail='brief')
        self.assertEqual(encoded.call_count, 1)
        self.assertEqual(json.loads(reply['content'][0]['text']), result)


if __name__ == '__main__':
    unittest.main()
