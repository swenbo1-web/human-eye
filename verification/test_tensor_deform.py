"""Independent and analytic checks for cross-frame deformation summaries."""

import unittest

import numpy as np

from human_eye_fast.tensor_deform import compute_cross_frame_deformation_tensor


METRIC_FIELDS = (
    "max_principal_stretch",
    "min_principal_stretch",
    "max_area_strain",
    "max_normal_angle_deg",
    "max_centroid_displacement",
)
ONE_FACE = np.array([[0, 1, 2]])
UNIT = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]])
CENTERED = np.array([[-1., -1., 0.], [1., -1., 0.], [0., 2., 0.]])


def face_metrics(reference, current):
    old_edges = (reference[1:] - reference[0]).T
    new_edges = (current[1:] - current[0]).T
    _, chart = np.linalg.qr(old_edges, mode="reduced")
    gradient = np.linalg.solve(chart.T, new_edges.T).T
    high, low = np.linalg.svd(gradient, compute_uv=False)

    old_cross = np.cross(old_edges[:, 0], old_edges[:, 1])
    new_cross = np.cross(new_edges[:, 0], new_edges[:, 1])
    old_area = np.linalg.norm(old_cross)
    new_area = np.linalg.norm(new_cross)
    old_unit = old_cross / old_area
    new_unit = new_cross / new_area
    sine = np.linalg.norm(np.cross(old_unit, new_unit))
    cosine = np.dot(old_unit, new_unit)
    angle = np.degrees(np.arctan2(sine, cosine))
    displacement = np.linalg.norm(current.mean(axis=0) - reference.mean(axis=0))
    return high, low, abs(new_area / old_area - 1), angle, displacement


class TensorDeformationTests(unittest.TestCase):
    def test_connected_mesh_matches_independent_qr_svd_and_geometry(self):
        rng = np.random.default_rng(117009)
        reference = rng.normal(size=(9, 3))
        faces = np.array([[0, i, i + 1] for i in (5, 1, 3, 7, 2, 6, 4)])
        frames = reference + rng.normal(scale=0.4, size=(5, *reference.shape))
        actual = compute_cross_frame_deformation_tensor(
            frames, faces, reference_vertices=reference, top_k=3
        )

        samples = np.array([
            [face_metrics(reference[face], frame[face]) for face in faces]
            for frame in frames
        ])
        expected = samples.max(axis=0)
        expected[:, 1] = samples[:, :, 1].min(axis=0)
        for field, values in zip(METRIC_FIELDS, expected.T):
            with self.subTest(field=field):
                np.testing.assert_allclose(actual[field], values, rtol=5e-12, atol=5e-12)

        high, low, strain, angle, displacement = expected.T
        diagonal = np.linalg.norm(np.ptp(reference, axis=0))
        score = np.maximum(abs(high - 1), abs(low - 1))
        score += 2 * strain + 3 * angle / 180 + displacement / diagonal
        np.testing.assert_allclose(actual["score"], score, rtol=5e-12, atol=5e-12)
        order = sorted(range(len(faces)), key=lambda face_id: (-score[face_id], face_id))
        np.testing.assert_array_equal(actual["witness_triangle_ids"], order[:3])

    def test_equal_area_anisotropy_ranks_above_undeformed_face(self):
        reference = np.vstack((CENTERED, CENTERED))
        faces = np.arange(6).reshape(2, 3)
        current = reference.copy()
        current[3:] *= [2., 0.5, 1.]
        result = compute_cross_frame_deformation_tensor([reference, current], faces, top_k=1)

        np.testing.assert_allclose(result["max_principal_stretch"], [1., 2.], atol=1e-14)
        np.testing.assert_allclose(result["min_principal_stretch"], [1., 0.5], atol=1e-14)
        for field in METRIC_FIELDS[2:]:
            np.testing.assert_allclose(result[field], [0., 0.], atol=1e-14)
        np.testing.assert_allclose(result["score"], [0., 1.], atol=1e-14)
        np.testing.assert_array_equal(result["witness_triangle_ids"], [1])

    def test_explicit_reference_differs_from_first_frame(self):
        frames = [CENTERED * 2]
        explicit = compute_cross_frame_deformation_tensor(
            frames, ONE_FACE, reference_vertices=CENTERED
        )
        implicit = compute_cross_frame_deformation_tensor(frames, ONE_FACE)
        for field, explicit_value, implicit_value in zip(
            METRIC_FIELDS, (2., 2., 3., 0., 0.), (1., 1., 0., 0., 0.)
        ):
            with self.subTest(field=field):
                np.testing.assert_allclose(explicit[field], [explicit_value], atol=1e-14)
                np.testing.assert_allclose(implicit[field], [implicit_value], atol=1e-14)

    def test_rigid_rotation_and_centroid_translation(self):
        cosine, sine = -0.5, np.sqrt(3) / 2
        rotation = np.array([[1, 0, 0], [0, cosine, -sine], [0, sine, cosine]])
        moved = CENTERED @ rotation.T + [0., 3., 4.]
        result = compute_cross_frame_deformation_tensor([CENTERED, moved], ONE_FACE)
        for field, value in zip(METRIC_FIELDS, (1., 1., 0., 120., 5.)):
            with self.subTest(field=field):
                np.testing.assert_allclose(result[field], [value], atol=5e-13)

    def test_collapse_and_degenerate_reference(self):
        line = np.array([[0., 0., 0.], [1., 0., 0.], [2., 0., 0.]])
        reference = np.vstack((UNIT, line))
        faces = np.arange(6).reshape(2, 3)
        other_face = UNIT + [0., 0., 3.]
        collapsed_to_line = np.vstack((line, other_face))
        collapsed_to_point = np.vstack((np.zeros((3, 3)), other_face))
        result = compute_cross_frame_deformation_tensor(
            [collapsed_to_line, collapsed_to_point], faces, reference_vertices=reference
        )
        for field, value in zip(METRIC_FIELDS[:4], (np.sqrt(5), 0., 1., np.nan)):
            with self.subTest(field=field):
                np.testing.assert_allclose(result[field], [value, np.nan], equal_nan=True)
        np.testing.assert_allclose(
            result["max_centroid_displacement"], [np.sqrt(5) / 3, np.sqrt(86) / 3]
        )
        self.assertTrue(np.isfinite(result["score"][0]))
        self.assertTrue(np.isnan(result["score"][1]))
        np.testing.assert_array_equal(result["witness_triangle_ids"], [0])

        rotated = np.vstack((UNIT * [1., -1., -1.], other_face))
        mixed = compute_cross_frame_deformation_tensor(
            [collapsed_to_line, rotated, collapsed_to_point], faces, reference_vertices=reference
        )
        np.testing.assert_allclose(mixed["max_normal_angle_deg"], [180., np.nan], equal_nan=True)

    def test_oblique_collinearity_survives_normal_scaling(self):
        line = np.array([[0., 0., 0.], [1., 3., 5.], [3., 9., 15.]])
        for exponent in (-550, 0, 550):
            with self.subTest(exponent=exponent):
                scaled_line = np.ldexp(line, exponent)
                scaled_unit = np.ldexp(UNIT, exponent)
                collapsed = compute_cross_frame_deformation_tensor(
                    [scaled_line], ONE_FACE, reference_vertices=scaled_unit
                )
                np.testing.assert_allclose(collapsed["max_principal_stretch"], [np.sqrt(350)])
                np.testing.assert_array_equal(collapsed["min_principal_stretch"], [0.])
                np.testing.assert_array_equal(collapsed["max_area_strain"], [1.])
                np.testing.assert_array_equal(collapsed["max_normal_angle_deg"], [np.nan])

                degenerate = compute_cross_frame_deformation_tensor(
                    [scaled_unit], ONE_FACE, reference_vertices=scaled_line
                )
                for field in (*METRIC_FIELDS[:4], "score"):
                    np.testing.assert_array_equal(degenerate[field], [np.nan])
                self.assertEqual(degenerate["witness_triangle_ids"].size, 0)
                np.testing.assert_allclose(
                    np.ldexp(degenerate["max_centroid_displacement"], -exponent),
                    [np.sqrt(530) / 3],
                )

    def test_displacement_score_is_invariant_to_length_units(self):
        reference = np.vstack((CENTERED, CENTERED))
        faces = np.arange(6).reshape(2, 3)
        current = np.vstack((CENTERED + [0, 0, 2], CENTERED * [2., 0.5, 1.]))
        for scale in (1e-120, 1., 1e120):
            with self.subTest(scale=scale):
                result = compute_cross_frame_deformation_tensor(
                    np.stack((reference, current)) * scale, faces, top_k=1
                )
                np.testing.assert_allclose(
                    result["max_centroid_displacement"] / scale, [2., 0.], atol=5e-14
                )
                np.testing.assert_allclose(result["score"], [2 / np.sqrt(13), 1.], atol=5e-14)
                np.testing.assert_array_equal(result["witness_triangle_ids"], [1])

    def test_top_k_ties_are_stable_at_cutoff_and_keep_face_ids(self):
        reference = np.tile(UNIT, (8, 1))
        faces = np.arange(24).reshape(8, 3)[::-1]
        current = reference.copy()
        current[faces, 2] += np.array([2., 5., 5., 0., 5., 6., 1., 3.])[:, None]
        frames = [reference, current]
        limited = compute_cross_frame_deformation_tensor(frames, faces, top_k=3)
        full = compute_cross_frame_deformation_tensor(frames, faces, top_k=20)
        empty = compute_cross_frame_deformation_tensor(frames, faces, top_k=0)

        np.testing.assert_array_equal(limited["witness_triangle_ids"], [5, 1, 2])
        np.testing.assert_array_equal(full["witness_triangle_ids"], [5, 1, 2, 4, 7, 0, 6, 3])
        self.assertEqual(empty["witness_triangle_ids"].size, 0)
        for field in (*METRIC_FIELDS, "score"):
            np.testing.assert_array_equal(empty[field], full[field])

    def test_empty_frames_and_empty_topology(self):
        no_frames = np.empty((0, len(UNIT), 3))
        for reference in (None, UNIT):
            result = compute_cross_frame_deformation_tensor(
                no_frames, ONE_FACE, reference_vertices=reference
            )
            for field in (*METRIC_FIELDS, "score"):
                np.testing.assert_array_equal(result[field], [np.nan])
            self.assertEqual(result["witness_triangle_ids"].size, 0)

        no_faces = np.empty((0, 3), dtype=int)
        result = compute_cross_frame_deformation_tensor([UNIT], no_faces)
        for field in (*METRIC_FIELDS, "score", "witness_triangle_ids"):
            self.assertEqual(result[field].shape, (0,))


if __name__ == "__main__":
    unittest.main()
