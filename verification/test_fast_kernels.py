"""Independent numerical checks for the trusted-array experimental kernels."""
import itertools
import time
import unittest
from fractions import Fraction

import numpy as np

from human_eye_fast.kernels import prepare_reference, deformation_metrics, triangle_box_mask
from human_eye_plugin.deformation_region import clipped


def qr_svd_metrics(old, new):
    old_edges = (old[1:] - old[0]).T
    new_edges = (new[1:] - new[0]).T
    _, upper = np.linalg.qr(old_edges, mode="reduced")
    gradient = np.linalg.solve(upper.T, new_edges.T).T
    stretches = np.linalg.svd(gradient, compute_uv=False)
    area = np.linalg.norm(np.cross(new_edges[:, 0], new_edges[:, 1])) / np.linalg.norm(np.cross(old_edges[:, 0], old_edges[:, 1]))
    return stretches, area


def rational_intersection(points, low, high):
    return clipped([tuple(Fraction(float(x)) for x in p) for p in points],
                   tuple(Fraction(float(x)) for x in low),
                   tuple(Fraction(float(x)) for x in high),
                   deadline_ns=time.perf_counter_ns() + 10_000_000_000)


class FastDeformationTests(unittest.TestCase):
    def test_affine_against_independent_qr_svd(self):
        rng = np.random.default_rng(99017)
        old = rng.normal(size=(400, 3, 3))
        transforms = rng.normal(size=(400, 3, 3))
        new = np.einsum("nij,nvj->nvi", transforms, old) + rng.normal(size=(400, 1, 3))
        reference = prepare_reference(old.reshape(-1, 3), np.arange(old.size // 3).reshape(-1, 3))
        result = deformation_metrics(reference, new.reshape(-1, 3))
        expected = [qr_svd_metrics(a, b) for a, b in zip(old, new)]
        np.testing.assert_allclose(result["stretches"], [v[0] for v in expected], rtol=5e-12, atol=5e-12)
        np.testing.assert_allclose(result["area_ratio"], [v[1] for v in expected], rtol=5e-12, atol=5e-12)

    def test_known_anisotropy_and_shear(self):
        old = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]])
        reference = prepare_reference(old, [[0, 1, 2]])
        for high, low in ((2., .5), (3., 2.), (.5, .25), (1., 1.)):
            new = old * [high, low, 1]
            result = deformation_metrics(reference, new)
            np.testing.assert_allclose(result["stretches"], [[high, low]], rtol=1e-14)
            np.testing.assert_allclose(result["area_ratio"], [high * low], rtol=1e-14)
        new = old.copy(); new[2, 0] = .75
        result = deformation_metrics(reference, new)
        expected = (np.sqrt(.75 ** 2 + 4) + np.array([.75, -.75])) / 2
        np.testing.assert_allclose(result["stretches"], [expected], rtol=1e-14)
        np.testing.assert_allclose(result["area_ratio"], [1.], rtol=1e-14)

    def test_rigid_and_permutation_invariance(self):
        old = np.array([[.2, -.3, .4], [1.2, .2, .6], [.3, .8, 1.]])
        q, _ = np.linalg.qr(np.random.default_rng(21).normal(size=(3, 3)))
        new = old @ q + [3, -2, 1]
        for order in itertools.permutations(range(3)):
            result = deformation_metrics(prepare_reference(old, [order]), new)
            np.testing.assert_allclose(result["stretches"], [[1., 1.]], atol=3e-15)
            np.testing.assert_allclose(result["area_ratio"], [1.], atol=3e-15)

    def test_collapse_and_undefined_reference(self):
        old = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]])
        reference = prepare_reference(old, [[0, 1, 2]])
        line = np.array([[0., 0., 0.], [1., 0., 0.], [2., 0., 0.]])
        result = deformation_metrics(reference, line)
        np.testing.assert_allclose(result["stretches"], [[np.sqrt(5), 0.]])
        np.testing.assert_equal(result["area_ratio"], [0.])
        result = deformation_metrics(reference, np.zeros((3, 3)))
        np.testing.assert_equal(result["stretches"], [[0., 0.]])
        result = deformation_metrics(prepare_reference(line, [[0, 1, 2]]), old)
        self.assertTrue(np.isnan(result["stretches"]).all())
        self.assertTrue(np.isnan(result["area_ratio"]).all())

    def test_tiny_large_reference_scaling(self):
        unit = np.array([[0., 0., 0.], [1., 0., 0.], [.2, .7, 0.]])
        for size in (1e-120, 1e-50, 1e50, 1e120):
            old = unit * size
            result = deformation_metrics(prepare_reference(old, [[0, 1, 2]]), old * [1.5, .5, 1])
            np.testing.assert_allclose(result["stretches"], [[1.5, .5]], rtol=5e-15)
            np.testing.assert_allclose(result["area_ratio"], [.75], rtol=5e-15)

    def test_thin_reference_is_evaluated(self):
        old = np.array([[0., 0., 0.], [1., 0., 0.], [.3, 1e-12, 0.]])
        result = deformation_metrics(prepare_reference(old, [[0, 1, 2]]), old * [2., .25, 1])
        np.testing.assert_allclose(result["stretches"], [[2., .25]], rtol=1e-13)
        np.testing.assert_allclose(result["area_ratio"], [.5], rtol=1e-13)

    def test_selected_faces_equal_full_batch(self):
        rng = np.random.default_rng(88)
        old = rng.normal(size=(150, 3)); new = old + rng.normal(0, .02, old.shape)
        reference = prepare_reference(old, np.arange(150).reshape(-1, 3))
        full = deformation_metrics(reference, new)
        ids = np.array([49, 3, 19, 0])
        partial = deformation_metrics(reference, new, ids)
        for key in full:
            np.testing.assert_array_equal(partial[key], full[key][ids])

    def test_empty_batches_and_selection(self):
        reference = prepare_reference(np.empty((0, 3)), np.empty((0, 3), dtype=int))
        result = deformation_metrics(reference, np.empty((0, 3)))
        self.assertEqual(result["stretches"].shape, (0, 2))
        self.assertEqual(result["area_ratio"].shape, (0,))


class FastRegionTests(unittest.TestCase):
    def test_seeded_triangle_box_matches_exact_rational_clipping(self):
        rng = np.random.default_rng(81029)
        # Dyadic inputs make the independent rational oracle straightforward.
        points = rng.integers(-24, 25, (400, 3, 3)).astype(float) / 8
        low = np.array([-.75, -.5, -.25]); high = np.array([1.25, .75, 1.5])
        actual = triangle_box_mask(points, low, high)
        expected = [rational_intersection(p, low, high) for p in points]
        np.testing.assert_array_equal(actual, expected)
        self.assertTrue(actual.any()); self.assertTrue((~actual).any())

    def test_overlapping_aabb_is_not_sufficient(self):
        points = np.array([[[1., 3., 0.], [3., 1., 0.], [3., 3., 0.]],
                           [[.5, .5, 0.], [2., .5, 0.], [.5, 2., 0.]]])
        np.testing.assert_array_equal(triangle_box_mask(points, [-1]*3, [1]*3), [False, True])

    def test_closed_face_edge_and_vertex_contact(self):
        points = np.array([[[1., 0., 0.], [1., .5, 0.], [1., 0., .5]],
                           [[1., 1., -2.], [1., 1., 2.], [3., 3., 0.]],
                           [[1., 1., 1.], [2., 1., 1.], [1., 2., 1.]]])
        np.testing.assert_array_equal(triangle_box_mask(points, [-1]*3, [1]*3), [True]*3)

    def test_point_and_segment_degeneracy(self):
        points = np.array([[[0., 0., 0.]]*3, [[2., 0., 0.]]*3,
                           [[-2., 0., 0.], [2., 0., 0.], [0., 0., 0.]],
                           [[2., -1., 0.], [2., 1., 0.], [2., 0., 0.]],
                           [[2., 0., 0.], [0., 2., 0.], [1., 1., 0.]]])
        actual = triangle_box_mask(points, [-1]*3, [1]*3)
        np.testing.assert_array_equal(actual, [True, False, True, False, True])
        np.testing.assert_array_equal(actual, [rational_intersection(p, [-1]*3, [1]*3) for p in points])

    def test_permutations_and_translation(self):
        points = np.array([[[-2., .25, .5], [2., .75, -.5], [0., 2., .5]],
                           [[1., 3., 0.], [3., 1., 0.], [3., 3., 0.]]])
        expected = triangle_box_mask(points, [-1]*3, [1]*3)
        for order in itertools.permutations(range(3)):
            actual = triangle_box_mask(points[:, order] + [1024, -512, 256],
                                       np.array([-1]*3) + [1024, -512, 256],
                                       np.array([1]*3) + [1024, -512, 256])
            np.testing.assert_array_equal(actual, expected)

    def test_empty_input(self):
        self.assertEqual(triangle_box_mask(np.empty((0, 3, 3)), [-1]*3, [1]*3).shape, (0,))


if __name__ == "__main__":
    unittest.main()
