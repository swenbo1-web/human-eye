"""Reviewer-owned clearance checks using an independent convex-support oracle.

The oracle enumerates nonempty vertex supports and solves the closest points
between their affine hulls. It does not import candidate narrow-phase helpers,
use a BVH, or copy the candidate point/triangle and segment algorithms.
Run: python -B -m unittest verification.test_bc_acceptance -v
"""
from itertools import combinations
import math
import numbers
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _supports(count):
    return tuple(ids for size in range(1, count + 1)
                 for ids in combinations(range(count), size))


def convex_pair_oracle(points_a, points_b):
    """Distance between two convex hulls of at most three points each.

For each support pair, anchor the first point of each support and solve a
direct least-squares problem. Direct LS avoids the squared condition number
of normal equations. At least one minimal optimal support has a unique
affine-hull minimizer, so enumerating all supports also handles degenerate
and intersecting hulls where the full-support LS solution is not feasible.
Tiny negative barycentric roundoff is clipped; the *actual feasible convex
combination* is then evaluated anew. This is a float64 numerical oracle.
"""
    a = np.asarray(points_a, dtype=np.float64).reshape(-1, 3)
    b = np.asarray(points_b, dtype=np.float64).reshape(-1, 3)
    origin = a[0].copy()
    relative = np.concatenate((a - origin, b - origin))
    scale = float(np.max(np.abs(relative)))
    if scale == 0:
        return 0.0, origin.copy(), origin.copy()
    a = (a - origin) / scale
    b = (b - origin) / scale
    best = math.inf
    best_a = best_b = None
    for ia in _supports(len(a)):
        pa = a[list(ia)]
        for ib in _supports(len(b)):
            pb = b[list(ib)]
            count_a = len(pa) - 1
            directions = np.concatenate((pa[1:] - pa[0], -(pb[1:] - pb[0])), axis=0).T
            if directions.shape[1]:
                x = np.linalg.lstsq(directions, pb[0] - pa[0], rcond=None)[0]
            else:
                x = np.empty(0)
            wa = np.r_[1.0 - np.sum(x[:count_a]), x[:count_a]]
            wb = np.r_[1.0 - np.sum(x[count_a:]), x[count_a:]]
            if min(float(np.min(wa)), float(np.min(wb))) < -1e-12:
                continue
            wa = np.maximum(wa, 0.0)
            wb = np.maximum(wb, 0.0)
            wa /= np.sum(wa)
            wb /= np.sum(wb)
            qa = wa @ pa
            qb = wb @ pb
            distance = float(np.linalg.norm(qa - qb)) * scale
            if distance < best:
                best, best_a, best_b = distance, origin + scale * qa, origin + scale * qb
    return best, best_a, best_b


def exhaustive_convex_oracle(vertices_a, triangles_a, vertices_b, triangles_b):
    """Quality-only all-pairs reference; deliberately not a timing baseline."""
    va = np.asarray(vertices_a, dtype=np.float64)
    vb = np.asarray(vertices_b, dtype=np.float64)
    best = (math.inf, None, None, None, None)
    for ia, face_a in enumerate(triangles_a):
        for ib, face_b in enumerate(triangles_b):
            distance, qa, qb = convex_pair_oracle(va[face_a], vb[face_b])
            if distance < best[0]:
                best = distance, ia, ib, qa, qb
    return best


def surface_tolerance(va, fa, vb, fb):
    points = np.concatenate((np.asarray(va)[np.asarray(fa)].reshape(-1, 3),
                             np.asarray(vb)[np.asarray(fb)].reshape(-1, 3)))
    span = float(np.max(np.ptp(points, axis=0)))
    magnitude = float(np.max(np.abs(points)))
    return 1e-10 * max(span, np.finfo(float).tiny) + 32 * np.finfo(float).eps * magnitude


def box(lower, upper):
    x0, y0, z0 = lower
    x1, y1, z1 = upper
    vertices = np.array(((x0,y0,z0), (x1,y0,z0), (x1,y1,z0), (x0,y1,z0),
                         (x0,y0,z1), (x1,y0,z1), (x1,y1,z1), (x0,y1,z1)), dtype=float)
    faces = np.array(((0,2,1), (0,3,2), (4,5,6), (4,6,7),
                      (0,1,5), (0,5,4), (1,2,6), (1,6,5),
                      (2,3,7), (2,7,6), (3,0,4), (3,4,7)), dtype=np.int32)
    return vertices, faces


TRIANGLE = np.array(((0, 1, 2),), dtype=np.int32)


class OracleSelfChecks(unittest.TestCase):
    def test_analytic_feature_cases(self):
        cases = (
            ([(2,2,1)], [(0,0,0), (1,0,0), (0,1,0)], math.sqrt(5.5)),
            ([(-1,0,0), (1,0,0), (0,-.1,0)],
             [(.9,-1,1), (.9,1,1), (.9,0,2)], 1.),
            ([(-1,-1,0), (1,-1,0), (0,1,0)],
             [(0,0,-1), (.2,0,1), (-.2,.5,1)], 0.),
            ([(0,0,0), (2,0,0), (0,2,0)],
             [(.1,.1,0), (.2,.1,0), (.1,.2,0)], 0.),
            ([(-1,0,0), (1,0,0), (1,0,0)],
             [(0,-1,0), (0,1,0), (0,1,0)], 0.),
            ([(0,0,0), (0,0,0), (0,0,0)],
             [(1,2,2), (1,2,2), (1,2,2)], 3.),
        )
        for a, b, expected in cases:
            with self.subTest(expected=expected, a=a):
                distance, qa, qb = convex_pair_oracle(a, b)
                self.assertAlmostEqual(distance, expected, delta=1e-12)
                self.assertAlmostEqual(float(np.linalg.norm(qa - qb)), expected, delta=1e-12)

    def test_oracle_scaling_order_and_slender_support(self):
        a = np.array(((-1000,0,0), (1000,0,0), (0,.00001,0)), dtype=float)
        b = np.array(((0,.00001,.0001),) * 3, dtype=float)
        for factor in (1e-6, 1., 1e6):
            shift = np.array((2.1, -3.4, 5.6)) * factor
            actual = convex_pair_oracle(a[[2,0,1]] * factor + shift,
                                        b * factor + shift)[0]
            self.assertAlmostEqual(actual, .0001 * factor, delta=2e-12 * factor)


class IndependentClearanceChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from human_eye_fast.fast_bvh_clearance import SurfaceIndex, surface_distance
        cls.Index = SurfaceIndex
        cls.distance = staticmethod(surface_distance)

    def assert_result(self, result, va, fa, vb, fb, expected=None, positive=False):
        va, vb = np.asarray(va, dtype=float), np.asarray(vb, dtype=float)
        fa, fb = np.asarray(fa, dtype=np.int32), np.asarray(fb, dtype=np.int32)
        if len(fa) == 0 or len(fb) == 0:
            self.assertEqual(result.distance_m, math.inf)
            for field in ('triangle_a', 'triangle_b', 'point_a', 'point_b'):
                self.assertIsNone(getattr(result, field), field)
            return
        tol = surface_tolerance(va, fa, vb, fb)
        if expected is None:
            expected = exhaustive_convex_oracle(va, fa, vb, fb)[0]
        self.assertTrue(math.isfinite(result.distance_m))
        self.assertGreaterEqual(result.distance_m, 0.)
        if positive:
            self.assertGreater(result.distance_m, 0., 'Positive analytic gap was collapsed to zero')
        self.assertAlmostEqual(result.distance_m, expected, delta=tol)
        for field, faces in (('triangle_a', fa), ('triangle_b', fb)):
            index = getattr(result, field)
            self.assertIsInstance(index, numbers.Integral)
            self.assertGreaterEqual(index, 0)
            self.assertLess(index, len(faces))
        qa, qb = np.asarray(result.point_a), np.asarray(result.point_b)
        self.assertEqual(qa.shape, (3,))
        self.assertEqual(qb.shape, (3,))
        self.assertTrue(np.isfinite(qa).all() and np.isfinite(qb).all())
        self.assertLessEqual(convex_pair_oracle(qa[None], va[fa[result.triangle_a]])[0], tol)
        self.assertLessEqual(convex_pair_oracle(qb[None], vb[fb[result.triangle_b]])[0], tol)
        self.assertAlmostEqual(float(np.linalg.norm(qa - qb)), result.distance_m, delta=tol)

    def check(self, va, fa, vb, fb, expected=None, positive=False):
        va, vb = np.asarray(va, dtype=float), np.asarray(vb, dtype=float)
        fa, fb = np.asarray(fa, dtype=np.int32), np.asarray(fb, dtype=np.int32)
        before = [x.copy() for x in (va, fa, vb, fb)]
        result = self.distance(self.Index(va, fa), self.Index(vb, fb))
        self.assert_result(result, va, fa, vb, fb, expected, positive)
        for actual, original in zip((va, fa, vb, fb), before):
            np.testing.assert_array_equal(actual, original)
        return result

    def test_outside_projection_and_edge_edge(self):
        self.check([(2,2,1)] * 3, TRIANGLE,
                   [(0,0,0), (1,0,0), (0,1,0)], TRIANGLE, math.sqrt(5.5))
        self.check([(-1,0,0), (1,0,0), (0,-.1,0)], TRIANGLE,
                   [(.9,-1,1), (.9,1,1), (.9,0,2)], TRIANGLE, 1.)

    def test_crossing_coplanar_and_touching(self):
        a = np.array(((-1,-1,0), (1,-1,0), (0,1,0)), dtype=float)
        cases = (
            [(0,0,-1), (.2,0,1), (-.2,.5,1)],
            [(-.1,-.1,0), (.1,-.1,0), (0,.1,0)],
            [(1,-1,0), (2,-1,0), (1,-2,0)],
            [(-1,-1,0), (1,-1,0), (0,-2,0)],
        )
        for b in cases:
            with self.subTest(b=b):
                self.check(a, TRIANGLE, b, TRIANGLE, 0.)

    def test_closed_boxes_isolated_vertices_and_reindexing(self):
        va, fa = box((0,0,0), (1,1,1))
        vb, fb = box((2,0,0), (3,1,1))
        va = np.vstack((va, (2,.5,.5), (2.5,.5,.5), (1e4,1e4,1e4)))
        self.check(va, fa, vb, fb, 1.)
        rng = np.random.default_rng(73211)
        order = rng.permutation(len(va))
        inverse = np.argsort(order)
        fa_permuted = inverse[fa[rng.permutation(len(fa))]][:, ::-1]
        self.check(vb, fb[::-1], va[order], fa_permuted, 1.)

    def test_nested_and_interpenetrating_closed_surfaces(self):
        outside, fo = box((-2,-2,-2), (2,2,2))
        inside, fi = box((-1,-1,-1), (1,1,1))
        self.check(outside, fo, inside, fi, 1.)
        displaced, fd = box((1,-1,-1), (3,1,1))
        self.check(outside, fo, displaced, fd, 0.)

    def test_top32_centroid_trap_and_face_identity(self):
        a = np.array(((0,0,0), (1,0,0), (0,1,0)), dtype=float)
        triangles = []
        for i in range(32):
            x = .03 * (i % 8)
            y = .04 * (i // 8)
            triangles.append(((x,y,2), (x+.02,y,2), (x,y+.02,2)))
        triangles.append(((0,0,1), (1000,0,1), (1000,1,1)))
        vertices = np.asarray(triangles, dtype=float).reshape(-1, 3)
        faces = np.arange(len(vertices), dtype=np.int32).reshape(-1, 3)
        result = self.check(a, TRIANGLE, vertices, faces, 1.)
        self.assertEqual(result.triangle_b, 32)

    def test_degenerate_slender_nearly_parallel_and_empty(self):
        cases = (
            ([(0,0,0)] * 3, [(1,2,2)] * 3, 3.),
            ([(-1,0,0), (1,0,0), (1,0,0)], [(0,-1,0), (0,1,0), (0,1,0)], 0.),
            ([(-2,0,0), (2,0,0), (2,0,0)], [(-1,1e-5,0), (1,1.0001e-5,0), (1,1.0001e-5,0)], 1e-5),
            ([(-1000,0,0), (1000,0,0), (0,.00001,0)], [(0,.00001,.0001)] * 3, .0001),
        )
        for a, b, expected in cases:
            with self.subTest(expected=expected):
                self.check(a, TRIANGLE, b, TRIANGLE, expected)
        empty = np.empty((0, 3), dtype=np.int32)
        self.check(np.empty((0,3)), empty, [(0,0,0)] * 3, TRIANGLE)
        self.check([(0,0,0)] * 3, TRIANGLE, np.empty((0,3)), empty)

    def test_micro_gap_not_zero_and_similarity_invariance(self):
        a = np.array(((0,0,0), (1,0,0), (0,1,0)), dtype=float)
        for gap in (1e-6, 1e-9, 1e-12):
            self.check(a, TRIANGLE, a + (0,0,gap), TRIANGLE, gap, positive=True)
        rng = np.random.default_rng(84229)
        rotation, _ = np.linalg.qr(rng.normal(size=(3,3)))
        for scale in (1e-6, 1., 1e6):
            shift = scale * np.array((4.7, -3.1, 8.6))
            va = (a @ rotation.T) * scale + shift
            vb = ((a + (0,0,.003)) @ rotation.T) * scale + shift
            self.check(va, TRIANGLE, vb, TRIANGLE, .003 * scale, positive=True)
        offset = np.array((1e9, -2e9, .5e9))
        self.check(a + offset, TRIANGLE, a + offset + (0,0,.002), TRIANGLE, positive=True)

    def test_same_surface_retriangulation_and_duplicate_faces(self):
        vertices = np.array(((0,0,0), (2,0,0), (2,2,0), (0,2,0)), dtype=float)
        original = np.array(((0,1,2), (0,2,3)), dtype=np.int32)
        other_diagonal = np.array(((0,1,3), (1,2,3)), dtype=np.int32)
        for fa in (original, other_diagonal, np.vstack((other_diagonal, other_diagonal[::-1]))):
            self.check(vertices, fa, vertices + (0,0,.017), original, .017)

    def test_random_small_surfaces_against_convex_oracle(self):
        for seed in (12893, 43991, 82037):
            rng = np.random.default_rng(seed)
            a = rng.uniform(-1, 1, size=(12,3))
            b = rng.uniform(-1, 1, size=(15,3)) + (1.1, -.3, .7)
            fa = np.arange(len(a), dtype=np.int32).reshape(-1,3)
            fb = np.arange(len(b), dtype=np.int32).reshape(-1,3)
            with self.subTest(seed=seed):
                self.check(a, fa, b, fb)
                self.check(b, fb[::-1], a, fa[::-1])

    def test_refit_changes_both_surfaces_and_preserves_original_ids(self):
        rng = np.random.default_rng(52319)
        a = rng.uniform(-1,1,size=(12,3))
        b = rng.uniform(-1,1,size=(12,3)) + (0,0,3)
        faces = np.arange(12,dtype=np.int32).reshape(-1,3)
        ia, ib = self.Index(a, faces), self.Index(b, faces)
        for phase in (0, 1, 2, 1, 0):
            va = a + np.array((.13*phase, -.07*phase, .03*phase))
            vb = b + np.array((-.11*phase, .08*phase, -.27*phase))
            va = va.copy()
            vb = vb.copy()
            va[3, 2] += .12 * phase
            vb[7, 0] -= .09 * phase
            ia.update(va)
            ib.update(vb)
            self.assert_result(self.distance(ia,ib), va,faces,vb,faces)


if __name__ == '__main__':
    unittest.main()
