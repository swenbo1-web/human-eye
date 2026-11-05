"""Independent checks for the two query-axis BC projection experiments.

Decimal checks enclose projections of the original binary64 inputs, not
projections recomputed by a candidate helper. They sample finite magnitudes
and are not a proof for every floating-point input. Whole-surface checks use
the separate convex-support oracle, never the adopted A implementation.
"""

from decimal import Decimal, localcontext
import importlib.util
from pathlib import Path
import sys
import unittest

import numpy as np

from verification.test_bc_acceptance import (
    convex_pair_oracle, exhaustive_convex_oracle, surface_tolerance,
)


ROOT = Path(__file__).resolve().parents[1]
VARIANTS = ("bc_projected_bounds", "bc_projected_faces", "bc_projected_order",
            "bc_projected_compact", "bc_projected_beam")


def _load(name):
    module_name = "_independent_projection_check_" + name
    spec = importlib.util.spec_from_file_location(
        module_name, ROOT / "verification/candidates" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _intervals(module, index, axis, origin):
    result = module._projected_bounds(index, axis, origin)
    # The node-only experiment returns a list of levels; the other returns
    # (that list, per-face intervals). No geometric calculation is shared.
    return (result, None) if isinstance(result, list) else result


def _decimal_projection(point, axis, origin):
    return sum((Decimal.from_float(float(value)) - Decimal.from_float(float(offset)))
               * Decimal.from_float(float(component))
               for value, component, offset in zip(point, axis, origin))


def _geometry():
    rng = np.random.default_rng(690371)
    triangles = rng.normal(size=(9, 3, 3))
    triangles[0, 1:] = triangles[0, 0]  # Point triangle.
    triangles[1] = ((-1.25, .5, -.75), (0., .5, -.75), (2., .5, -.75))  # Exact line.
    vertices = triangles.reshape(-1, 3)
    faces = np.arange(len(vertices), dtype=np.int32).reshape(-1, 3)
    # Uneven leaf sizes and shuffled original IDs exercise packed-to-source mapping.
    return vertices, faces[rng.permutation(len(faces))][:, ::-1]


class ProjectedBoundsChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modules = {name: _load(name) for name in VARIANTS}

    def _assert_enclosure(self, low, high, projections):
        self.assertTrue(np.isfinite(low) and np.isfinite(high))
        self.assertLessEqual(Decimal.from_float(float(low)), min(projections))
        self.assertGreaterEqual(Decimal.from_float(float(high)), max(projections))

    def _check_all_intervals(self, module, vertices, faces, axis, origin):
        index = module.SurfaceIndex(vertices, faces)
        nodes, face_bounds = _intervals(module, index, axis, origin)
        self.assertEqual(len(nodes), len(index._bounds))
        ordered_original = vertices[faces[index._order]]
        projections = [[_decimal_projection(point, axis, origin) for point in triangle]
                       for triangle in ordered_original]
        stops = np.r_[index._starts[1:], len(faces)]
        leaf_faces = [list(range(int(start), int(stop)))
                      for start, stop in zip(index._starts, stops)]
        for depth, (lower, upper) in enumerate(nodes):
            descendants = len(leaf_faces) // len(lower)
            self.assertEqual(len(lower), len(upper))
            for node_id, (low, high) in enumerate(zip(lower, upper)):
                packed_ids = [face for leaf in leaf_faces[node_id * descendants:(node_id + 1) * descendants]
                              for face in leaf]
                values = [value for face in packed_ids for value in projections[face]]
                with self.subTest(depth=depth, node=node_id):
                    self._assert_enclosure(low, high, values)
        if face_bounds is not None:
            lower, upper = face_bounds
            self.assertEqual(len(lower), len(faces))
            for face, values in enumerate(projections):
                with self.subTest(face=face):
                    self._assert_enclosure(lower[face], upper[face], values)
        return nodes

    def test_decimal_enclosures_arbitrary_axes_scales_and_common_origin(self):
        vertices, faces = _geometry()
        translation = np.array((1e6, -1e6, 1e6))
        configurations = [(scale, np.zeros(3)) for scale in (1e-150, 1e-50, 1., 1e50, 1e150)]
        configurations += [(1e-5, translation), (1., translation), (1e150, translation)]
        axes = (np.array((.7, -.2, .9)), np.array((-3., 1., 2.)),
                np.array((1e-100, -3e-100, 2e-100)), np.array((1e100, 2e100, -1e100)))
        with localcontext() as context:
            context.prec = 1000
            for name, module in self.modules.items():
                for scale, shift in configurations:
                    a = vertices * scale + shift
                    b = (vertices + (3.25, -2.75, 4.5)) * scale + shift
                    origin = np.array((.125, -.75, 1.125)) * scale + shift
                    for axis in axes:
                        with self.subTest(candidate=name, scale=scale, translated=bool(shift.any()),
                                          axis=axis.tolist()):
                            self._check_all_intervals(module, a, faces, axis, origin)
                            # The exact same origin is used for the other object;
                            # independently centering it would change these values.
                            self._check_all_intervals(module, b, faces, axis, origin)

    def test_zero_axis_contributes_no_separating_distance(self):
        vertices, faces = _geometry()
        for name, module in self.modules.items():
            with self.subTest(candidate=name):
                a = module.SurfaceIndex(vertices, faces)
                b = module.SurfaceIndex(vertices + (19., -27., 53.), faces)
                axis = np.zeros(3)
                origin = np.array((1e6, -1e6, 1e6))
                nodes_a, _ = _intervals(module, a, axis, origin)
                nodes_b, _ = _intervals(module, b, axis, origin)
                for (la, ha), (lb, hb) in zip(nodes_a, nodes_b):
                    self.assertTrue((la <= 0).all() and (ha >= 0).all())
                    self.assertTrue((lb <= 0).all() and (hb >= 0).all())
                    gaps = np.maximum(np.maximum(la[:, None] - hb, lb - ha[:, None]), 0)
                    np.testing.assert_array_equal(gaps, np.zeros_like(gaps))
                # Production uses an outward-rounded norm, which also leaves
                # the zero-axis contribution zero instead of producing NaN.
                length = np.nextafter(module._length(axis) * module._BOUND_ROUNDING, np.inf)
                self.assertEqual(float(gaps[0, 0] / length), 0.)

    def test_updated_surfaces_match_convex_oracle_and_real_witnesses(self):
        rng = np.random.default_rng(580419)
        a = rng.normal(size=(15, 3)) * .35
        b = rng.normal(size=(15, 3)) * .35 + (0, 0, 4.)
        a[1:3] = a[0]  # Include a point feature among nondegenerate faces.
        b[3:6] = ((-.25, 0., 4.), (.125, 0., 4.), (.5, 0., 4.))  # Exact line feature.
        faces_a = np.arange(15, dtype=np.int32).reshape(5, 3)[[3, 0, 4, 1, 2]]
        faces_b = np.arange(15, dtype=np.int32).reshape(5, 3)[[1, 4, 2, 0, 3]][:, ::-1]
        phases = [(a + phase * rng.normal(size=a.shape) * .025,
                   np.roll(b, phase, axis=1) + phase * rng.normal(size=b.shape) * .025)
                  for phase in range(3)]
        for scale, shift in ((1e-6, np.zeros(3)), (1., np.zeros(3)),
                             (1., np.array((1e6, -1e6, 1e6)))):
            states = [(va * scale + shift, vb * scale + shift) for va, vb in phases]
            # Oracle answers are computed once from the original geometry and
            # reused for the two candidates, never inferred from candidate A.
            expected = [exhaustive_convex_oracle(va, faces_a, vb, faces_b)[0] for va, vb in states]
            for name, module in self.modules.items():
                ia = module.SurfaceIndex(states[0][0], faces_a)
                ib = module.SurfaceIndex(states[0][1], faces_b)
                for phase, ((va, vb), answer) in enumerate(zip(states, expected)):
                    with self.subTest(candidate=name, scale=scale, translated=bool(shift.any()), phase=phase):
                        before = va.copy(), vb.copy()
                        ia.update(va)
                        ib.update(vb)
                        result = module.surface_distance(ia, ib)
                        tolerance = surface_tolerance(va, faces_a, vb, faces_b)
                        self.assertGreater(result.distance_m, 0.)
                        self.assertAlmostEqual(result.distance_m, answer, delta=tolerance)
                        for point, source, faces, face_id in (
                            (result.point_a, va, faces_a, result.triangle_a),
                            (result.point_b, vb, faces_b, result.triangle_b),
                        ):
                            self.assertIsInstance(face_id, (int, np.integer))
                            self.assertTrue(0 <= face_id < len(faces))
                            self.assertTrue(np.isfinite(point).all())
                            membership = convex_pair_oracle(np.asarray(point)[None], source[faces[face_id]])[0]
                            self.assertLessEqual(membership, tolerance)
                        distance_between_witnesses = np.linalg.norm(np.subtract(result.point_a, result.point_b))
                        self.assertAlmostEqual(distance_between_witnesses, result.distance_m, delta=tolerance)
                        np.testing.assert_array_equal(va, before[0])
                        np.testing.assert_array_equal(vb, before[1])


if __name__ == "__main__":
    unittest.main()
