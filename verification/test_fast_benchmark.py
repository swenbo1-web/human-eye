"""Check benchmark oracles and evidence accounting, not timing expectations."""
import unittest

import numpy as np

from verification import benchmark_fast_v1 as bench


class BenchmarkEvidenceTests(unittest.TestCase):
    def test_independent_qr_svd_matches_affine_analytic_stretches(self):
        original = np.array([[[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]]])
        changed = original * np.array([1.7, 0.6, 1.])
        metrics = bench.qr_svd_metrics(original, changed)
        np.testing.assert_allclose(metrics["stretches"], [[1.7, 0.6]])
        np.testing.assert_allclose(metrics["area_ratio"], [1.02])

    def test_unknown_legacy_rows_are_not_counted_as_equivalent(self):
        numeric = {"stretches": np.array([[1.7, .6], [1.2, .8]]), "area_ratio": np.array([1.02, .96])}
        legacy = [{"state": "measured", "principal_stretches": [1.7, .6], "area_ratio": 1.02},
                  {"state": "unknown", "principal_stretches": None, "area_ratio": None}]
        result = bench.check_metrics(numeric, numeric, legacy)
        self.assertEqual(result["legacy_measured_rows_compared"], 1)
        self.assertEqual(result["legacy_unknown_rows_not_claimed_equivalent"], 1)
        self.assertEqual(result["independent_numeric_rows_compared"], 2)

    def test_numeric_disagreement_aborts_benchmark_instead_of_emitting_speed_claim(self):
        fast = {"stretches": np.array([[1.7, .6]]), "area_ratio": np.array([1.02])}
        oracle = {"stretches": np.array([[1.8, .6]]), "area_ratio": np.array([1.08])}
        legacy = [{"state": "measured", "principal_stretches": [1.7, .6], "area_ratio": 1.02}]
        with self.assertRaises(AssertionError):
            bench.check_metrics(fast, oracle, legacy)

    def test_seeded_inputs_and_independent_baselines_agree(self):
        a = bench.fixture(12, seed=991)
        b = bench.fixture(12, seed=991)
        for first, second in zip(a, b):
            np.testing.assert_array_equal(first, second)
        original, triangles, current, _ = a
        before, after = original[triangles], current[triangles]
        oracle = bench.qr_svd_metrics(before, after)
        old = bench.legacy_metrics(before.tolist(), after.tolist())
        result = bench.check_metrics(oracle, oracle, old)
        self.assertEqual(result["legacy_measured_rows_compared"], 12)


if __name__ == "__main__":
    unittest.main()
