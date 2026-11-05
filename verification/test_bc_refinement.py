"""Independent geometric properties of the archived, rejected refinement.

The candidate passed geometry checks but was not adopted because its timing
did not establish non-regression. Runtime uses the qualified implementation.
"""
import unittest
import numpy as np

from verification.baselines.bc_refinement_rejected import (
    _prepare_triangles, _projection_lower_distance, SurfaceIndex, surface_distance,
)
from verification.test_bc_acceptance import convex_pair_oracle, exhaustive_convex_oracle, surface_tolerance


class ProjectionBounds(unittest.TestCase):
    def test_arbitrary_normals_remain_lower_bounds(self):
        rng = np.random.default_rng(564913)
        for scale in (1e-6, 1., 1e6):
            a = rng.normal(size=(12,3,3)) * scale
            b = (rng.normal(size=(12,3,3)) + (0,0,4)) * scale
            shift = np.array((19., -27., 53.)) * scale
            a += shift; b += shift
            pa, pb = _prepare_triangles(a), _prepare_triangles(b)
            # A valid separating projection works along any axis, even one
            # which is unrelated to the plane or has non-unit length.
            pa.normals = rng.normal(size=(12,3)) * 3
            pb.normals = rng.normal(size=(12,3)) * .07
            pa.normals[0] = 0
            pb.normals[1] = 0
            actual = _projection_lower_distance(pa,pb,np.arange(12),np.arange(12))
            self.assertTrue(np.isfinite(actual).all())
            self.assertTrue((actual >= 0).all())
            for i in range(12):
                expected = convex_pair_oracle(a[i],b[i])[0]
                self.assertLessEqual(actual[i], expected + 1e-11 * scale)

    def test_degenerate_and_microscopic_separation(self):
        a = np.array([[(0,0,0),(1,0,0),(0,1,0)],
                      [(0,0,0),(0,0,0),(0,0,0)],
                      [(-1,0,0),(1,0,0),(1,0,0)]],dtype=float)
        for gap in (0.,1e-12,1e-9,.003):
            b = a + (0,0,gap)
            actual = _projection_lower_distance(_prepare_triangles(a),_prepare_triangles(b),
                                                np.arange(3),np.arange(3))
            self.assertTrue(np.isfinite(actual).all())
            self.assertTrue((actual <= gap + 1e-20).all())

    def test_updated_nonplanar_surfaces_keep_global_minimum(self):
        rng = np.random.default_rng(805721)
        faces = np.arange(24).reshape(8,3)
        a = rng.normal(size=(24,3))
        b = rng.normal(size=(24,3)) + (0,0,5)
        ia, ib = SurfaceIndex(a,faces), SurfaceIndex(b,faces)
        for phase in (0,1,2):
            va = a + (.07*phase,-.11*phase,0)
            vb = b + (0,0,-.33*phase)
            ia.update(va); ib.update(vb)
            actual = surface_distance(ia,ib)
            expected = exhaustive_convex_oracle(va,faces,vb,faces)[0]
            self.assertAlmostEqual(actual.distance_m, expected,
                                   delta=surface_tolerance(va,faces,vb,faces))
            for point, triangle in ((actual.point_a,va[faces[actual.triangle_a]]),
                                    (actual.point_b,vb[faces[actual.triangle_b]])):
                self.assertLessEqual(convex_pair_oracle(np.asarray(point)[None],triangle)[0],1e-10)


if __name__ == '__main__':
    unittest.main()
