"""Bounded independent PT checks, to run only in the granted CPU window."""
import json
import math
from pathlib import Path
import unittest

import numpy as np

from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin import geometry_safety as geometry
from verification.perf030_002_cases import leaf_cases, triangle_truth
from verification.test_concave_geometry import box, entity, ring


ROOT = Path(__file__).resolve().parents[1]


class Perf030DualTests(unittest.TestCase):
    def test_ten_leaf_cases_against_exact_represented_inputs(self):
        cases = leaf_cases()
        self.assertEqual(len(cases), 10)
        for case in cases:
            with self.subTest(case=case['name']):
                truth = triangle_truth(case['point'], case['triangle'])
                expected = float(truth['distance_sq'])
                actual = geometry._point_triangle_min_sq(case['point'][None, :], case['triangle'][None, :, :])
                self.assertTrue(math.isfinite(actual))
                self.assertAlmostEqual(actual, expected, delta=max(8 * math.ulp(expected), 1e-30))
                if truth['distance_sq'] > 0:
                    self.assertGreater(actual, 0)

    def test_original_twelve_analytic_pairs(self):
        cases = json.loads((ROOT / 'verification/fixes/perf030_001/inputs.json').read_text('utf8'))['cases']
        self.assertEqual(len(cases), 12)
        for case in cases:
            with self.subTest(case=case['name']):
                pair = [MeshEntity3D.from_dict(value) for value in case['meshes']]
                result = geometry.measure_pair_geometry(*pair, need_clearance=True)
                if case['group'] == 'reject':
                    self.assertFalse(result['measurement_valid'])
                    self.assertEqual(result['reason'], 'geometry_resource_limit')
                    continue
                self.assertTrue(result['measurement_valid'], result)
                self.assertAlmostEqual(result['signed_clearance_m'], case['expected_clearance_m'], delta=1e-14)
                distance, point_a, point_b = geometry._surface_distance_with_witness(*pair)
                self.assertAlmostEqual(distance, case['expected_clearance_m'], delta=1e-14)
                self.assertAlmostEqual(math.dist(point_a, point_b), distance, delta=1e-9)
                for point, mesh in zip((point_a, point_b), pair):
                    minimum = min(triangle_truth(point, mesh.vertices[face])['distance_sq'] for face in mesh.faces)
                    self.assertLessEqual(minimum, 1e-18)

    def test_witness_priority_across_original_64_point_block(self):
        parts = [box((3 * index, 0, 0), (1, 1, 1), 'part') for index in range(9)]
        left = entity('a', np.vstack([part.vertices for part in parts]),
                      np.vstack([part.faces + 8 * index for index, part in enumerate(parts)]))
        right = box((12, 0, 3), (26, 2, 1), 'b')
        distance, point_a, point_b = geometry._surface_distance_with_witness(left, right)
        self.assertEqual(distance, 2.)
        self.assertEqual(point_a, [-.5, -.5, .5])
        self.assertEqual(point_b, [-.5, -.5, 2.5])

    def test_positive_near_tie_clearance_and_original_surface(self):
        for offset in (0., 2.0 ** -40):
            with self.subTest(offset=offset):
                pair = box((offset, 0, 0)), ring()
                distance, point_a, point_b = geometry._surface_distance_with_witness(*pair)
                self.assertAlmostEqual(distance, .019 - offset, delta=1e-14)
                self.assertAlmostEqual(math.dist(point_a, point_b), distance, delta=1e-9)
                for point, mesh in zip((point_a, point_b), pair):
                    minimum = min(triangle_truth(point, mesh.vertices[face])['distance_sq'] for face in mesh.faces)
                    self.assertLessEqual(minimum, 1e-18)


if __name__ == '__main__':
    unittest.main()
