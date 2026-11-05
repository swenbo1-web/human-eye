"""Analytic and independent convex-hull checks for world-space clearance."""

from itertools import combinations
from math import sqrt
import unittest

import numpy as np

from human_eye_fast.fast_bvh_clearance import SurfaceIndex, surface_distance


UNIT = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]])
ONE = np.array([[0, 1, 2]])
EPS = np.finfo(np.float64).eps


def simplices(vertex_count):
    return tuple(
        np.array(list(combinations(range(vertex_count), size)))
        for size in range(2, min(vertex_count, 4) + 1)
    )


DIFFERENCE_SIMPLICES = simplices(9)
TRIANGLE_SIMPLICES = simplices(3)


def origin_to_hull(vertices, subsets):
    """Distance to small convex hulls using affine-simplex projections and SVD.

    In R^3 any hull point belongs to a simplex of at most four vertices. An
    optimum on a simplex boundary is covered by a smaller simplex. Thus we
    can project onto each affine span and test the simplex weights directly.
    """
    best = np.min(np.linalg.norm(vertices, axis=-1), axis=-1)
    for subset in subsets:
        points = vertices[..., subset, :]
        base = points[..., 0, :]
        columns = (points[..., 1:, :] - base[..., None, :]).swapaxes(-1, -2)
        left, singular, right = np.linalg.svd(columns, full_matrices=False)
        independent = singular[..., -1] > 8 * EPS * singular[..., 0]
        projected = -(left.swapaxes(-1, -2) @ base[..., None])[..., 0]
        coordinates = projected / np.where(independent[..., None], singular, 1.)
        free_weights = (right.swapaxes(-1, -2) @ coordinates[..., None])[..., 0]
        weights = np.concatenate(
            (1. - free_weights.sum(axis=-1, keepdims=True), free_weights), axis=-1
        )
        feasible = independent & np.all(weights >= -32 * EPS, axis=-1)

        # Roundoff near a boundary may produce a tiny negative weight. Evaluate
        # an actual convex combination even in that case.
        weights = np.maximum(weights, 0.)
        weights /= weights.sum(axis=-1, keepdims=True)
        closest = np.einsum("...i,...ij->...j", weights, points)
        distance = np.where(feasible, np.linalg.norm(closest, axis=-1), np.inf)
        best = np.minimum(best, distance.min(axis=-1))
    return best


def exhaustive_distance(vertices_a, faces_a, vertices_b, faces_b):
    a = vertices_a[faces_a]
    b = vertices_b[faces_b]
    # Minkowski difference of two triangular convex hulls is the convex hull
    # of all nine vertex differences. Test every pair without BVH or pruning.
    difference = a[:, None, :, None, :] - b[None, :, None, :, :]
    hulls = difference.reshape(len(a), len(b), 9, 3)
    return float(origin_to_hull(hulls, DIFFERENCE_SIMPLICES).min())


def tolerance(points):
    scale = np.linalg.norm(np.ptp(points, axis=0))
    return 1e-10 * scale + 32 * EPS * np.max(np.abs(points))


def box(low, high):
    x, y, z = low
    u, v, w = high
    vertices = np.array([
        [x, y, z], [u, y, z], [u, v, z], [x, v, z],
        [x, y, w], [u, y, w], [u, v, w], [x, v, w],
    ], dtype=np.float64)
    quads = ((0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
             (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))
    faces = np.array([face for a, b, c, d in quads for face in ((a, b, c), (a, c, d))])
    return vertices, faces


class SurfaceDistanceTests(unittest.TestCase):
    def check_witness(self, result, va, fa, vb, fb, expected):
        domain = np.concatenate((va[fa].reshape(-1, 3), vb[fb].reshape(-1, 3)))
        atol = tolerance(domain)
        self.assertTrue(np.isfinite(result.distance_m))
        self.assertGreaterEqual(result.distance_m, 0.)
        self.assertAlmostEqual(result.distance_m, expected, delta=atol)

        for triangle_id, point, vertices, faces in (
            (result.triangle_a, result.point_a, va, fa),
            (result.triangle_b, result.point_b, vb, fb),
        ):
            self.assertIsInstance(triangle_id, (int, np.integer))
            self.assertTrue(0 <= triangle_id < len(faces))
            self.assertEqual(np.shape(point), (3,))
            self.assertTrue(np.all(np.isfinite(point)))
            triangle = vertices[faces[triangle_id]]
            residual = origin_to_hull(triangle - point, TRIANGLE_SIMPLICES)
            self.assertLessEqual(residual, tolerance(triangle))

        witness_gap = np.linalg.norm(np.asarray(result.point_a) - np.asarray(result.point_b))
        self.assertAlmostEqual(witness_gap, result.distance_m, delta=atol)

    def check_meshes(self, va, fa, vb, fb, expected):
        result = surface_distance(SurfaceIndex(va, fa), SurfaceIndex(vb, fb))
        self.check_witness(result, va, fa, vb, fb, expected)
        return result

    def check_triangles(self, a, b, expected):
        return self.check_meshes(
            np.asarray(a, dtype=np.float64), ONE, np.asarray(b, dtype=np.float64), ONE, expected
        )

    def test_separated_and_point_face_projection(self):
        self.check_triangles(UNIT, UNIT + [0., 0., 2.], 2.)
        point = np.tile([0.25, 0.25, 1.], (3, 1))
        inside = self.check_triangles(UNIT, point, 1.)
        np.testing.assert_allclose(inside.point_a, [0.25, 0.25, 0.], atol=1e-14)

        point = np.tile([2., 2., 1.], (3, 1))
        outside = self.check_triangles(UNIT, point, sqrt(5.5))
        np.testing.assert_allclose(outside.point_a, [0.5, 0.5, 0.], atol=1e-14)

    def test_edge_edge_interior_minimum(self):
        a = [[-2., 0., 0.], [2., 0., 0.], [-2., -2., -1.]]
        b = [[0., -2., 1.], [0., 2., 1.], [2., 2., 2.]]
        result = self.check_triangles(a, b, 1.)
        np.testing.assert_allclose(result.point_a, [0., 0., 0.], atol=1e-14)
        np.testing.assert_allclose(result.point_b, [0., 0., 1.], atol=1e-14)

    def test_parallel_and_nearly_parallel_long_edges(self):
        a = np.array([[-2048., 0., 0.], [2048., 0., 0.], [-2048., 0., 0.]])
        self.check_triangles(a, a + [100., 3., 4.], 5.)
        # Both endpoints miss the closest point by more than the protocol's
        # tolerance. The almost parallel directions have a zero Gram
        # determinant in float64 if formed by subtracting squared dot products.
        dy = 2. ** -18
        gap = 2. ** -22
        b = a + [[0., -dy, gap], [0., dy, gap], [0., -dy, gap]]
        for first, second in ((a, b), (b, a)):
            with self.subTest(swapped=first is b):
                result = self.check_triangles(first, second, gap)
                self.assertAlmostEqual(result.distance_m, gap, delta=1e-12)
                self.assertAlmostEqual(result.point_a[0], 0., delta=1e-9)
                self.assertAlmostEqual(result.point_b[0], 0., delta=1e-9)

    def test_shifted_rotated_nearly_parallel_edges(self):
        along = np.array([0.36, 0.48, -0.8])
        across = np.array([-0.8, 0.6, 0.])
        normal = np.array([0.48, 0.64, 0.6])
        tilt, gap = 2. ** -18, 2. ** -22
        a = np.array([-2048., 2048., -2048.])[:, None] * along
        b = a + 1000. * along + np.array([-tilt, tilt, -tilt])[:, None] * across + gap * normal
        # The centerline crossing lies inside both segments. Subtracting
        # independently formed line parameters can lose their common shift.
        for first, second in ((a, b), (b, a)):
            with self.subTest(swapped=first is b):
                result = self.check_triangles(first, second, gap)
                self.assertAlmostEqual(result.distance_m, gap, delta=1e-11)
                actual = np.linalg.norm(np.subtract(result.point_a, result.point_b))
                self.assertAlmostEqual(actual, gap, delta=1e-11)

    def test_vertex_edge_coplanar_and_noncoplanar_contact(self):
        coplanar = [[-2., -1., 0.], [2., -1., 0.], [0., 1., 0.]]
        coplanar_fractional = [[-2., -1., 0.], [2., -1., 0.], [0., 2., 0.]]
        piercer = [[0.25, 0.25, -1.], [0.25, 0.25, 1.], [0.375, 0.25, 1.]]
        cases = (
            ("vertex", UNIT, [[0., 0., 0.], [-1., 0., 1.], [0., -1., 1.]]),
            ("edge", UNIT, [[0.25, 0., 0.], [0.75, 0., 0.], [0.25, -1., 1.]]),
            ("coplanar interior", UNIT, UNIT * 0.25 + [0.25, 0.25, 0.]),
            ("coplanar crossing", coplanar, [[-2., 0., 0.], [2., 0., 0.], [0., -2., 0.]]),
            ("coplanar fractional crossing", coplanar_fractional,
             [[-2., 1., 0.], [2., 1., 0.], [0., -2., 0.]]),
            ("edge through triangle interior", UNIT, piercer),
            ("degenerate segment through interior", UNIT, [piercer[0], piercer[1], piercer[0]]),
        )
        for name, a, b in cases:
            with self.subTest(case=name):
                self.assertEqual(self.check_triangles(a, b, 0.).distance_m, 0.)

    def test_crossing_and_nested_box_surfaces(self):
        outer = box([-2.] * 3, [2.] * 3)
        inner = box([-1.] * 3, [1.] * 3)
        self.check_meshes(*outer, *inner, 1.)
        a = box([0.] * 3, [1.] * 3)
        b = box([0.5, 0.25, 0.25], [1.5, 0.75, 0.75])
        self.assertEqual(self.check_meshes(*a, *b, 0.).distance_m, 0.)

    def test_isolated_vertex_and_object_index_permutations(self):
        va, fa = box([0.] * 3, [1.] * 3)
        vb, fb = box([2., 0., 0.], [3., 1., 1.])
        va = np.vstack((va, [2., 0.5, 0.5]))
        self.check_meshes(va, fa, vb, fb, 1.)
        self.check_meshes(vb, fb, va, fa, 1.)

        va = np.vstack((va, UNIT + [80., 60., -40.]))
        fa = np.vstack((fa, [9, 10, 11], fa[6]))
        rng = np.random.default_rng(29569)
        permutation_a = rng.permutation(len(va))
        permutation_b = rng.permutation(len(vb))
        va = va[permutation_a]
        vb = vb[permutation_b]
        fa = np.argsort(permutation_a)[fa[rng.permutation(len(fa)), ::-1]]
        fb = np.argsort(permutation_b)[fb[rng.permutation(len(fb)), ::-1]]
        self.check_meshes(va, fa, vb, fb, 1.)
        self.check_meshes(vb, fb, va, fa, 1.)

    def test_top32_centroids_cannot_discard_the_true_nearest_face(self):
        origins = np.column_stack((np.arange(32) / 32, np.zeros(32), np.full(32, 2.)))
        short = UNIT[None] * 0.25 + origins[:, None, :]
        long = np.array([[0., 0., 1.], [1000., 0., 1.], [1000., 1., 1.]])
        vb = np.vstack((short.reshape(-1, 3), long))
        fb = np.arange(len(vb)).reshape(-1, 3)[::-1]
        result = self.check_meshes(UNIT, ONE, vb, fb, 1.)
        self.assertEqual(result.triangle_b, 0)

    def test_thin_triangles_and_positive_microgaps(self):
        width = 2. ** -30
        gap = 2. ** -42
        skinny = [[0., 0., 0.], [1., 0., 0.], [1., width, 0.]]
        point = np.tile([0.75, width / 4, gap], (3, 1))
        result = self.check_triangles(skinny, point, gap)
        self.assertGreater(result.distance_m, 0.)
        self.assertAlmostEqual(result.distance_m / gap, 1., delta=1e-9)

        # Parallel tilted planes have overlapping AABBs despite a positive
        # gap, so the intersection path must preserve the gap as well.
        tilted = UNIT + np.column_stack((np.zeros((3, 2)), UNIT[:, 0]))
        other = tilted * 0.25 + [0.125, 0.125, 0.125 + gap]
        result = self.check_triangles(tilted, other, gap / sqrt(2.))
        self.assertGreater(result.distance_m, 0.)
        self.assertAlmostEqual(result.distance_m / gap, 1. / sqrt(2.), delta=1e-4)

        origin = [2. ** 30, -(2. ** 31), 2. ** 29]
        represented_gap = 2. ** -15
        a = UNIT + origin
        b = a + [0., 0., represented_gap]
        result = self.check_triangles(a, b, represented_gap)
        self.assertAlmostEqual(result.distance_m / represented_gap, 1., delta=1e-9)

    def test_rigid_transform_and_scales(self):
        rotation = np.array([[0.36, -0.8, 0.48], [0.48, 0.6, 0.64], [-0.8, 0., 0.6]])
        point = np.tile([0.25, 0.25, 0.125], (3, 1))
        for scale in (1e-6, 1., 1e6):
            with self.subTest(scale=scale):
                a = (UNIT @ rotation.T + [32., -64., 16.]) * scale
                b = (point @ rotation.T + [32., -64., 16.]) * scale
                self.check_triangles(a, b, 0.125 * scale)

    def test_surface_retriangulation(self):
        square = np.array([
            [0., 0., 0.], [1., 0., 0.], [1., 1., 0.], [0., 1., 0.], [0.5, 0.5, 0.]
        ])
        diagonal_a = np.array([[0, 1, 2], [0, 2, 3]])
        diagonal_b = np.array([[0, 1, 3], [1, 2, 3]])
        fan = np.array([[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]])
        other = square + [0.25, 0.125, 0.0625]
        for fa, fb in ((diagonal_a, diagonal_a), (diagonal_b, fan), (fan, diagonal_b)):
            self.check_meshes(square, fa, other, fb, 0.0625)

    def test_random_triangle_soups_match_independent_all_pairs_oracle(self):
        for seed in (7609, 137007, 819133):
            rng = np.random.default_rng(seed)
            for case, offset in enumerate((0., 0.4, 1.5, 3., 6.)):
                with self.subTest(seed=seed, case=case):
                    na, nb = rng.integers(2, 6, size=2)
                    va = rng.normal(size=(3 * na, 3))
                    vb = rng.normal(size=(3 * nb, 3)) + [0., 0., offset]
                    if case in (1, 3):
                        va[2] = va[0]
                        vb[1:3] = vb[0]
                    # Shuffle triangle rows, keeping the injected degeneracies.
                    fa = np.arange(len(va)).reshape(-1, 3)[rng.permutation(na)]
                    fb = np.arange(len(vb)).reshape(-1, 3)[rng.permutation(nb)]
                    expected = exhaustive_distance(va, fa, vb, fb)
                    self.check_meshes(va, fa, vb, fb, expected)
                    self.check_meshes(vb, fb, va, fa, expected)

    def test_refit_both_objects_preserves_original_triangle_ids(self):
        faces = np.arange(3 * 64).reshape(-1, 3)[::-1]
        offsets = np.column_stack((8. * np.arange(64), np.zeros(64), np.full(64, -10.)))
        base_a = (UNIT[None] + offsets[:, None]).reshape(-1, 3)
        base_b = base_a + [0., 0., 20.]
        index_a = SurfaceIndex(base_a, faces)
        index_b = SurfaceIndex(base_b, faces)
        for state, (face_a, face_b) in enumerate(((1, 62), (50, 3), (1, 62))):
            with self.subTest(state=state):
                location = [1000. + state, 0.25 * state, 0.]
                gap = 2. ** -(4 + state)
                va = base_a + [0., 0., -0.25 * state]
                vb = base_b + [0., 0., 0.25 * state]
                va[faces[face_a]] = UNIT + location
                vb[faces[face_b]] = UNIT + location + [0., 0., gap]
                index_a.update(va)
                index_b.update(vb)
                result = surface_distance(index_a, index_b)
                self.check_witness(result, va, faces, vb, faces, gap)
                self.assertEqual((result.triangle_a, result.triangle_b), (face_a, face_b))

    def test_empty_surfaces_have_no_witness(self):
        empty = SurfaceIndex(UNIT, np.empty((0, 3), dtype=int))
        nonempty = SurfaceIndex(UNIT, ONE)
        for a, b in ((empty, nonempty), (nonempty, empty), (empty, empty)):
            result = surface_distance(a, b)
            self.assertEqual(result.distance_m, np.inf)
            self.assertEqual(
                (result.triangle_a, result.triangle_b, result.point_a, result.point_b),
                (None, None, None, None),
            )


if __name__ == "__main__":
    unittest.main()
