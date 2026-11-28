"""Both kernels shipped in the desktop wheel must solve the same analytic gap."""
import unittest

from human_eye_plugin.surface_proximity import measure_surface_proximity
from verification.test_surface_proximity_pruning_001 import horizontal, triangles


class DesktopSolverDispatchTests(unittest.TestCase):
    def test_winner_and_source_indices_at_the_work_budget_boundary(self):
        for count, expected_solver in ((96, 'r3'), (97, '032')):
            with self.subTest(count=count):
                left = triangles('left', [horizontal(0, -3*i) for i in range(count)])
                right = triangles('right', [horizontal(1, 3*i) for i in range(count)])
                result = measure_surface_proximity(left, right, lambda stage: None,
                                                   retain_witness_triangles=True)
                self.assertEqual(result['work']['solver_path'], expected_solver)
                self.assertTrue(result['measurement_valid'])
                self.assertEqual(result['distance_m'], 1.0)
                self.assertEqual(result['direction_a_to_b'], [0.0, 0.0, 1.0])
                self.assertEqual(result['witness_triangle_indices'], [0, 0])
                self.assertEqual(result['point_a_world'][:2], result['point_b_world'][:2])
                self.assertEqual((result['point_a_world'][2], result['point_b_world'][2]), (0, 1))
