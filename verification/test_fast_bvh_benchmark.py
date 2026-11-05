"""Regression checks for the BC benchmark's blocked exhaustive baseline."""

import unittest
from unittest.mock import patch

import numpy as np

from verification import benchmark_fast_bvh_clearance as benchmark


UNIT_TRIANGLE = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]])


class FullPairBenchmarkTests(unittest.TestCase):
    def query_three_blocks(self, triangles_b):
        vertices_b = np.concatenate(triangles_b)
        state = (UNIT_TRIANGLE, vertices_b)
        case = benchmark.Case("three_pairs", (state,), np.array([[0, 1, 2]]),
                              np.arange(len(vertices_b)).reshape(-1, 3))
        with patch.object(benchmark, "PAIR_BLOCK", 1):
            query = benchmark._FullPairQuery(case, state)
        with patch.object(benchmark, "_closest_pairs", wraps=benchmark._closest_pairs) as narrow:
            result = query.query()
        visited_b = [int(call.args[3][0]) for call in narrow.call_args_list]
        return result, visited_b

    def test_actual_intersection_stops_after_zero_block(self):
        crossing = np.array([[0.25, 0.25, -1.], [0.25, 0.25, 1.], [0.75, 0.25, 1.]])
        result, visited = self.query_three_blocks((UNIT_TRIANGLE + [0, 0, 3], crossing,
                                                   UNIT_TRIANGLE + [0, 0, 2]))
        self.assertEqual(result.distance_m, 0.)
        self.assertEqual((result.triangle_a, result.triangle_b), (0, 1))
        self.assertEqual(result.point_a, result.point_b)
        # This line segment is precisely the intersection of the two faces.
        x, y, z = result.point_a
        self.assertEqual((y, z), (0.25, 0.))
        self.assertGreaterEqual(x, 0.25)
        self.assertLessEqual(x, 0.5)
        self.assertEqual(visited, [0, 1])

    def test_positive_distance_visits_every_block_and_uses_later_minimum(self):
        result, visited = self.query_three_blocks(
            tuple(UNIT_TRIANGLE + [0, 0, height] for height in (3, 1, 2))
        )
        self.assertEqual(result.distance_m, 1.)
        self.assertEqual((result.triangle_a, result.triangle_b), (0, 1))
        x, y, z = result.point_a
        self.assertEqual(z, 0.)
        self.assertGreaterEqual(min(x, y), 0.)
        self.assertLessEqual(x + y, 1.)
        self.assertEqual(result.point_b, (x, y, 1.))
        self.assertEqual(visited, [0, 1, 2])


if __name__ == "__main__":
    unittest.main()
