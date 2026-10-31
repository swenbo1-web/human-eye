"""Geometry-derived frame candidates must expose uncertainty and survive remeshing."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from human_eye_foveated_renderer import MeshEntity3D, SE3AlignmentMath
from human_eye_module1_operators.submodule_1_4_spatial_sniffer import SpatialAnomalySniffer, validate_local_axes


SIGNS = np.array([[-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
                  [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]], dtype=float)
FACES = np.array([[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
                  [0, 1, 5], [0, 5, 4], [2, 3, 7], [2, 7, 6],
                  [1, 2, 6], [1, 6, 5], [3, 0, 4], [3, 4, 7]], dtype=np.int32)


def box(size=(.8, .5, .2), rotation=None, center=(0., 0., 0.), **kwargs):
    rotation = np.eye(3) if rotation is None else rotation
    return MeshEntity3D("part", "#B", "Part", (SIGNS*np.asarray(size)/2) @ rotation.T+np.asarray(center),
                        FACES.copy(), None, (100, 120, 140), True, **kwargs)


def refine_one_triangle(mesh):
    """Change sampling density while preserving every point of the box surface."""
    payload = mesh.to_dict()
    payload.pop("local_axes")
    payload.pop("edges")
    vertices, faces = payload["vertices"], payload["faces"]
    a, b, c = mesh.vertices[faces.pop(2)]
    n, lookup = 16, {}
    for i in range(n+1):
        for j in range(n+1-i):
            lookup[i, j] = len(vertices)
            vertices.append((a+(b-a)*i/n+(c-a)*j/n).tolist())
    for i in range(n):
        for j in range(n-i):
            faces.append([lookup[i, j], lookup[i+1, j], lookup[i, j+1]])
            if j < n-i-1:
                faces.append([lookup[i+1, j], lookup[i+1, j+1], lookup[i, j+1]])
    return MeshEntity3D.from_dict(payload)


class MeshFrameProvenanceTests(unittest.TestCase):
    def test_explicit_identity_is_authoritative_even_for_a_square(self):
        mesh = box(size=(1., 1., .2), local_axes=np.eye(3))
        self.assertEqual(mesh.axes_source, "host")
        self.assertEqual(mesh.axes_confidence, "explicit")
        np.testing.assert_array_equal(mesh.local_axes, np.eye(3))

    def test_explicit_frame_and_pivot_roundtrip_without_precision_loss(self):
        rotation = SE3AlignmentMath.euler_xyz_to_matrix(13, 17, 33)
        mesh = box(rotation=rotation, local_axes=rotation.T.copy())
        mesh.pivot_world = np.array([.123456789123, -.125, .01])
        restored = MeshEntity3D.from_dict(json.loads(json.dumps(mesh.to_dict())))
        for name in ("vertices", "faces", "edges", "local_axes", "pivot_world"):
            np.testing.assert_array_equal(getattr(mesh, name), getattr(restored, name))
        self.assertEqual(restored.axes_source, "host")
        self.assertEqual(restored.axes_confidence, "explicit")

    def test_axis_aligned_rectangular_default_is_compatible(self):
        mesh = box()
        self.assertEqual(mesh.axes_source, "inferred_surface")
        self.assertEqual(mesh.axes_confidence, "geometry")
        np.testing.assert_array_equal(mesh.local_axes, np.eye(3))
        self.assertTrue(validate_local_axes(mesh)[0])

    def test_missing_frame_quarter_turn_is_measured_instead_of_certified(self):
        rotation = SE3AlignmentMath.euler_xyz_to_matrix(0, 0, 90)
        moving = box(size=(.3, .2, .14), rotation=rotation, center=(0, 0, .42))
        reference = box(size=(1.4, 1.2, .35), center=(0, 0, .175), local_axes=np.eye(3))
        reference.object_id, reference.mark_label, reference.is_focal_target = "base", "#A", False
        self.assertEqual(moving.axes_confidence, "geometry")
        self.assertAlmostEqual(abs(float(moving.local_axes[0] @ rotation[:, 0])), 1., places=12)
        probe = SpatialAnomalySniffer.probe_closest_clearance(moving, reference)
        self.assertFalse(probe.is_aligned_flush)
        self.assertEqual(probe.tangent_yaw_mismatch_deg, 90.)

    def test_legal_half_turn_still_has_zero_prescription(self):
        rotation = SE3AlignmentMath.euler_xyz_to_matrix(0, 0, 180)
        moving = box(size=(.3, .2, .14), rotation=rotation, center=(0, 0, .42))
        reference = box(size=(1.4, 1.2, .35), center=(0, 0, .175), local_axes=np.eye(3))
        reference.object_id, reference.mark_label = "base", "#A"
        probe = SpatialAnomalySniffer.probe_closest_clearance(moving, reference)
        self.assertTrue(probe.is_aligned_flush)
        self.assertEqual(probe.rotation_euler_deg_xyz, (0., 0., 0.))
        self.assertEqual(probe.axis_delta_m, (0., 0., 0.))

    def test_same_surface_partial_refinement_does_not_change_inferred_frame(self):
        rotation = SE3AlignmentMath.euler_xyz_to_matrix(13, 17, 33)
        original = box(rotation=rotation)
        refined = refine_one_triangle(original)
        self.assertEqual((len(original.vertices), len(refined.vertices)), (8, 161))
        self.assertEqual(original.axes_confidence, "geometry")
        self.assertEqual(refined.axes_confidence, "geometry")
        np.testing.assert_allclose(original.local_axes, refined.local_axes, atol=2e-13, rtol=0.)
        self.assertTrue(validate_local_axes(refined)[0])
        self.assertAlmostEqual(abs(float(refined.local_axes[0] @ rotation[:, 0])), 1., places=12)

    def test_vertex_face_order_changes_do_not_change_frame(self):
        rotation = SE3AlignmentMath.euler_xyz_to_matrix(-28, 47, 71)
        original = box(rotation=rotation)
        rng = np.random.default_rng(9201)
        permutation = rng.permutation(len(original.vertices))
        inverse = np.argsort(permutation)
        shuffled = MeshEntity3D("p", "#B", "Part", original.vertices[permutation],
                                inverse[original.faces[rng.permutation(len(original.faces))]],
                                None, (100, 120, 140))
        self.assertEqual(shuffled.axes_confidence, "geometry")
        np.testing.assert_allclose(original.local_axes, shuffled.local_axes, atol=2e-13, rtol=0.)

    def test_equal_dimensions_are_marked_ambiguous_and_remain_so_after_import(self):
        rotation = SE3AlignmentMath.euler_xyz_to_matrix(13, 17, 33)
        for size in ((1., 1., .2), (1., 1., 1.), (.8, .5, .5)):
            with self.subTest(size=size):
                mesh = box(size=size, rotation=rotation)
                self.assertEqual(mesh.axes_source, "ambiguous_geometry")
                self.assertEqual(mesh.axes_confidence, "ambiguous")
                restored = MeshEntity3D.from_dict(mesh.to_dict())
                self.assertEqual(restored.axes_confidence, "ambiguous")
                self.assertFalse(validate_local_axes(restored)[0])

    def test_zero_thickness_and_line_geometry_cannot_claim_trusted_axes(self):
        for size in ((1., .5, 0.), (1., 0., 0.)):
            with self.subTest(size=size):
                mesh = box(size=size)
                self.assertEqual(mesh.axes_confidence, "ambiguous")
                self.assertFalse(validate_local_axes(mesh)[0])

    def test_import_missing_edges_rebuilds_them_and_rejects_old_pca_authority(self):
        rotation = SE3AlignmentMath.euler_xyz_to_matrix(0, 0, 90)
        original = box(rotation=rotation)
        payload = original.to_dict()
        payload.pop("edges")
        payload["local_axes"] = np.eye(3).tolist()
        payload["axes_source"] = "inferred_pca"
        payload.pop("axes_confidence")
        restored = MeshEntity3D.from_dict(payload)
        self.assertGreater(len(restored.edges), 0)
        self.assertEqual(restored.axes_source, "inferred_surface")
        self.assertEqual(restored.axes_confidence, "geometry")
        self.assertAlmostEqual(abs(float(restored.local_axes[0] @ rotation[:, 0])), 1., places=12)

    def test_frame_provenance_changes_invalidate_geometry_tokens(self):
        mesh = box()
        before = mesh._compute_full_crc_token()
        state_before = mesh._compute_state_token()
        mesh.axes_confidence = "ambiguous"
        mesh.axes_reason = "host_removed_datum"
        self.assertNotEqual(before, mesh._compute_full_crc_token())
        self.assertNotEqual(state_before, mesh._compute_state_token())

    def test_rigid_transforms_preserve_source_confidence(self):
        mesh = box()
        rotation = SE3AlignmentMath.euler_xyz_to_matrix(13, -17, 33)
        transformed = mesh.rotated_around_pivot(rotation).translated((.1, .2, .3))
        self.assertEqual(transformed.axes_source, mesh.axes_source)
        self.assertEqual(transformed.axes_confidence, mesh.axes_confidence)
        self.assertEqual(transformed.axes_reason, mesh.axes_reason)
        np.testing.assert_allclose(transformed.local_axes, mesh.local_axes @ rotation.T, atol=1e-14)

    def test_translated_cache_rebuilds_mutated_output_and_preserves_valid_identity(self):
        mesh = box(local_axes=np.eye(3))
        delta = np.array([.17, -.23, .31])
        expected = mesh.vertices + delta
        cached = mesh.translated(delta)
        self.assertIs(mesh.translated(tuple(delta)), cached)
        cached.vertices[3, 1] += .4
        rebuilt = mesh.translated(tuple(delta))
        self.assertIsNot(rebuilt, cached)
        np.testing.assert_array_equal(rebuilt.vertices, expected)
        self.assertIs(mesh.translated(tuple(delta)), rebuilt)
        # The input array is not a live control for lazy triangle geometry.
        delta[:] = 9.
        for actual, indices in zip(rebuilt.tri_vertices, mesh.faces.T):
            np.testing.assert_array_equal(actual, expected[indices])
        for field in ("faces", "edges", "pivot_world"):
            with self.subTest(mutated_input=field):
                source = box(local_axes=np.eye(3))
                before = source._compute_full_crc_token()
                translated = source.translated((.1, .2, .3))
                if field == "pivot_world":
                    source.pivot_world[0] += .03
                else:
                    # Topology arrays are intentionally shared by rigid meshes.
                    values = getattr(source, field)
                    values[0] = np.roll(values[0], 1)
                self.assertNotEqual(source._compute_full_crc_token(), before)
                current = source.translated((.1, .2, .3))
                self.assertIsNot(current, translated)
                np.testing.assert_array_equal(current.vertices, source.vertices + (.1, .2, .3))
                np.testing.assert_array_equal(current.pivot_world, source.pivot_world + (.1, .2, .3))

    def test_rotated_cache_rebuilds_mutated_output_and_owns_matrix_key(self):
        mesh = box(center=(.3, -.2, .1), local_axes=np.eye(3))
        rotation = SE3AlignmentMath.euler_xyz_to_matrix(13., -17., 33.)
        pivot = mesh.pivot_world.copy()
        expected = (mesh.vertices - pivot) @ rotation.T + pivot
        cached = mesh.rotated_around_pivot(rotation)
        self.assertIs(mesh.rotated_around_pivot(rotation.copy()), cached)
        cached.vertices[4, 2] -= .3
        rebuilt = mesh.rotated_around_pivot(rotation.copy())
        self.assertIsNot(rebuilt, cached)
        np.testing.assert_array_equal(rebuilt.vertices, expected)
        self.assertIs(mesh.rotated_around_pivot(rotation.copy()), rebuilt)
        # Mutating the original command must cause a new transform, not a hit.
        rotation[:] = SE3AlignmentMath.euler_xyz_to_matrix(-7., 19., -41.)
        changed = mesh.rotated_around_pivot(rotation)
        self.assertIsNot(changed, rebuilt)
        np.testing.assert_array_equal(changed.vertices, (mesh.vertices - pivot) @ rotation.T + pivot)
        np.testing.assert_array_equal(rebuilt.vertices, expected)
        self.assertIs(mesh.rotated_around_pivot(rotation.copy()), changed)
        for field in ("faces", "edges", "pivot_world"):
            with self.subTest(mutated_output=field):
                source = box(local_axes=np.eye(3))
                cached_output = source.rotated_around_pivot(rotation)
                before = cached_output._compute_full_crc_token()
                if field == "pivot_world":
                    cached_output.pivot_world[0] += .05
                else:
                    # A detached replacement must also invalidate with equal shape.
                    values = getattr(cached_output, field).copy()
                    values[0] = np.roll(values[0], 1)
                    setattr(cached_output, field, values)
                self.assertNotEqual(cached_output._compute_full_crc_token(), before)
                current = source.rotated_around_pivot(rotation)
                self.assertIsNot(current, cached_output)
                np.testing.assert_array_equal(current.faces, source.faces)
                np.testing.assert_array_equal(current.edges, source.edges)
                np.testing.assert_array_equal(current.pivot_world, source.pivot_world)


if __name__ == "__main__":
    unittest.main(verbosity=2)
