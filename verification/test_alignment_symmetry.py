"""Regression checks for task-specific long-edge symmetry and cache isolation.

The frozen blind-test inputs are read as regression fixtures; their responses,
scores and protocol are never rewritten by this test.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "verification" / "blind_test"))

from geometry import build_meshes, score_pose
import human_eye_foveated_renderer as core
from human_eye_module1_operators.submodule_1_3_se3_alignment_math import SE3AlignmentMath
from human_eye_module1_operators.submodule_1_4_spatial_sniffer import SpatialAnomalySniffer
from human_eye_module1_operators.submodule_1_5_alignment_verifier import SpatialAlignmentVerifier
from human_eye_module1_operators.submodule_1_6_quad_compositor import QuadCognitiveCanvasCompositor


MATHS = (core.SE3AlignmentMath, SE3AlignmentMath)
PIPELINES = (
    (core.SpatialAnomalySniffer, core.SpatialAlignmentVerifier),
    (SpatialAnomalySniffer, SpatialAlignmentVerifier),
)
CASES_PATH = ROOT / "verification" / "blind_test" / "runs" / "20261021_01" / "private" / "cases.json"


class AlignmentSymmetryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = {case["scene_id"]: case for case in json.loads(CASES_PATH.read_text(encoding="utf-8"))}
        cls.normal_a = np.array([0., 0., -1.])
        cls.normal_b = np.array([0., 0., 1.])
        cls.eye = np.eye(3)

    def test_rectangles_accept_half_turn_and_reject_quarter_turn(self):
        for math_impl in MATHS:
            for yaw, expected in ((0, True), (180, True), (-180, True), (90, False), (-90, False)):
                with self.subTest(implementation=math_impl.__module__, yaw=yaw):
                    axes = math_impl.euler_xyz_to_matrix(0, 0, yaw).T.copy()
                    tilt, residual, passed = math_impl.verify_triad_alignment_residuals(
                        self.eye, self.normal_a, self.normal_b, axes, self.eye)
                    self.assertEqual(passed, expected)
                    self.assertEqual(tilt, 0.)
                    self.assertEqual(residual, 0. if expected else 90.)

    def test_explicit_four_fold_and_legacy_flags_remain_available(self):
        for math_impl in MATHS:
            for yaw in (0, 90, -90, 180):
                axes = math_impl.euler_xyz_to_matrix(0, 0, yaw).T.copy()
                for kwargs in ({"yaw_symmetry_order": 4}, {"allow_z4_symmetry": True}):
                    with self.subTest(implementation=math_impl.__module__, yaw=yaw, kwargs=kwargs):
                        self.assertTrue(math_impl.verify_triad_alignment_residuals(
                            self.eye, self.normal_a, self.normal_b, axes, self.eye, **kwargs)[2])
            half_turn = math_impl.euler_xyz_to_matrix(0, 0, 180).T.copy()
            for kwargs in ({"yaw_symmetry_order": 1}, {"allow_z4_symmetry": False}):
                self.assertFalse(math_impl.verify_triad_alignment_residuals(
                    self.eye, self.normal_a, self.normal_b, half_turn, self.eye, **kwargs)[2])

    def test_invalid_and_conflicting_symmetry_rejected_by_all_math_entrypoints(self):
        for math_impl in MATHS:
            for invalid in (0, 3, -1, True, 2.0, "2"):
                for name in ("compute_full_triad_alignment", "compute_full_triad_alignment_batch", "compute_full_triad_alignment_batch_simd"):
                    with self.subTest(implementation=math_impl.__module__, invalid=invalid, entrypoint=name):
                        with self.assertRaises(ValueError):
                            getattr(math_impl, name)(self.normal_a, self.normal_b, self.eye, self.eye, yaw_symmetry_order=invalid)
                with self.assertRaises(ValueError):
                    math_impl.verify_triad_alignment_residuals(
                        self.eye, self.normal_a, self.normal_b, self.eye, self.eye, yaw_symmetry_order=invalid)
            with self.assertRaises(ValueError):
                math_impl.compute_full_triad_alignment(self.normal_a, self.normal_b, self.eye, self.eye,
                    allow_z4_symmetry=True, yaw_symmetry_order=2)

    def test_scalar_cache_separates_one_two_and_four_fold(self):
        for math_impl in MATHS:
            half_axes = math_impl.euler_xyz_to_matrix(0, 0, 180).T.copy()
            quarter_axes = math_impl.euler_xyz_to_matrix(0, 0, 90).T.copy()
            for order in (4, 2, 1, 4, 2):
                for axes, expected in ((half_axes, 180. if order == 1 else 0.),
                                       (quarter_axes, 0. if order == 4 else 90.)):
                    result = math_impl.compute_full_triad_alignment(
                        self.normal_a, self.normal_b, axes, self.eye, yaw_symmetry_order=order)
                    self.assertEqual(result[-1], expected)

    def test_per_pair_batch_and_simd_match_scalar_exactly(self):
        rng = np.random.default_rng(48208)
        rotations_a, rotations_b = [], []
        for _ in range(24):
            rb = SE3AlignmentMath.euler_xyz_to_matrix(*rng.uniform(-35, 35, 3))
            ra = rb @ SE3AlignmentMath.euler_xyz_to_matrix(*rng.uniform(-70, 70, 3))
            rotations_a.append(ra)
            rotations_b.append(rb)
        rotations_a, rotations_b = np.array(rotations_a), np.array(rotations_b)
        normals_a, normals_b = np.ascontiguousarray(-rotations_a[:, :, 2]), np.ascontiguousarray(rotations_b[:, :, 2])
        axes_a, axes_b = np.ascontiguousarray(rotations_a.transpose(0, 2, 1)), np.ascontiguousarray(rotations_b.transpose(0, 2, 1))
        for math_impl in MATHS:
            for order in (1, 2, 4):
                scalar = [math_impl.compute_full_triad_alignment(na, nb, aa, bb, yaw_symmetry_order=order)
                          for na, nb, aa, bb in zip(normals_a, normals_b, axes_a, axes_b)]
                expected = [np.array([row[i] for row in scalar]) for i in range(5)]
                for name in ("compute_full_triad_alignment_batch", "compute_full_triad_alignment_batch_simd"):
                    actual = getattr(math_impl, name)(normals_a, normals_b, axes_a, axes_b, yaw_symmetry_order=order)
                    for index, (a, e) in enumerate(zip(actual, expected)):
                        with self.subTest(implementation=math_impl.__module__, order=order, entrypoint=name, field=index):
                            np.testing.assert_array_equal(a, e)
                if order == 2:
                    for before, rb, result in zip(rotations_a, rotations_b, scalar):
                        final = result[0] @ before
                        self.assertAlmostEqual(abs(float(final[:, 0] @ rb[:, 0])), 1., places=12)
                        self.assertAlmostEqual(float(final[:, 2] @ rb[:, 2]), 1., places=12)

    def test_shared_frame_batch_and_default_match_explicit_two_fold(self):
        for math_impl in MATHS:
            rotation = math_impl.euler_xyz_to_matrix(14, -11, 64)
            axes = rotation.T.copy()
            normals_a = np.repeat((-rotation[:, 2])[None, :], 3, axis=0)
            normals_b = np.repeat(self.normal_b[None, :], 3, axis=0)
            for name in ("compute_full_triad_alignment_batch", "compute_full_triad_alignment_batch_simd"):
                default = getattr(math_impl, name)(normals_a, normals_b, axes, self.eye)
                explicit = getattr(math_impl, name)(normals_a, normals_b, axes, self.eye, yaw_symmetry_order=2)
                for a, e in zip(default, explicit):
                    np.testing.assert_array_equal(a, e)
                single = math_impl.compute_full_triad_alignment(normals_a[0], normals_b[0], axes, self.eye)
                for i, value in enumerate(single):
                    np.testing.assert_array_equal(default[i], np.repeat(np.asarray(value)[None], 3, axis=0))

    def test_probe_cache_cannot_certify_quarter_turn_for_rectangles(self):
        for sniffer, _ in PIPELINES:
            case = copy.deepcopy(self.cases["S001"])
            case["focal"]["center"] = case["target"]["center"]
            case["focal"]["rotation"] = SE3AlignmentMath.euler_xyz_to_matrix(0, 0, 90).tolist()
            reference, focal = build_meshes(case)[:2]
            for order in (4, 2, 4, 2):
                probe = sniffer.probe_closest_clearance(focal, reference, yaw_symmetry_order=order)
                self.assertEqual(probe.yaw_symmetry_order, order)
                self.assertEqual(probe.is_aligned_flush, order == 4)
                self.assertEqual(probe.tangent_yaw_mismatch_deg, 0. if order == 4 else 90.)

    def test_new_six_dof_prescriptions_satisfy_independent_long_edge_goal(self):
        for scene_id in ("S006", "S010"):
            case = self.cases[scene_id]
            for sniffer, verifier in PIPELINES:
                with self.subTest(scene=scene_id, implementation=sniffer.__module__):
                    reference, focal = build_meshes(case)[:2]
                    # Exercise the same mesh and recheck cache in both orders.
                    for order in (4, 2, 4, 2):
                        aligned, report = verifier.execute_alignment_and_recheck(focal, reference, yaw_symmetry_order=order)
                        independent = score_pose(case, aligned.local_axes.T, aligned.vertices.mean(axis=0))
                        self.assertTrue(report.verification_passed)
                        self.assertEqual(report.pre_probe.yaw_symmetry_order, order)
                        self.assertEqual(report.post_probe.yaw_symmetry_order, order)
                        self.assertEqual(independent["success"], order == 2)
                        self.assertAlmostEqual(independent["rotation_error_deg"], 0. if order == 2 else 90., places=5)

    def test_legal_half_turn_negative_control_remains_exact_zero_action(self):
        case = self.cases["S012"]
        for sniffer, verifier in PIPELINES:
            reference, focal = build_meshes(case)[:2]
            probe = sniffer.probe_closest_clearance(focal, reference)
            aligned, report = verifier.execute_alignment_and_recheck(focal, reference)
            self.assertTrue(probe.is_aligned_flush)
            self.assertEqual(probe.rotation_euler_deg_xyz, (0., 0., 0.))
            self.assertEqual(probe.axis_delta_m, (0., 0., 0.))
            self.assertTrue(report.verification_passed)
            np.testing.assert_array_equal(aligned.vertices, focal.vertices)
            np.testing.assert_array_equal(aligned.local_axes, focal.local_axes)

    def test_compositor_frame_cache_and_telemetry_keep_symmetry_isolated(self):
        for compositor in (core.QuadCognitiveCanvasCompositor, QuadCognitiveCanvasCompositor):
            meshes = build_meshes(self.cases["S006"])
            renderer = compositor(quad_size=64)
            eye, target = np.array([2.4, -2.5, 1.85]), np.array([0., 0., .55])
            frames = {}
            prescriptions = {}
            for order in (2, 4, 2, 4):
                image, telemetry = renderer.render_quad_cognitive_canvas(meshes, eye, target, yaw_symmetry_order=order)
                self.assertEqual(telemetry["yaw_symmetry_order"], order)
                self.assertEqual(telemetry["clearance_probe"]["yaw_symmetry_order"], order)
                state = renderer._ensure_quad_frame_state(meshes, eye, target, yaw_symmetry_order=order)
                self.assertEqual(state[9][0].yaw_symmetry_order, order)
                prescriptions[order] = state[9][0].rotation_matrix_3x3.copy()
                if order in frames:
                    np.testing.assert_array_equal(np.asarray(image), frames[order])
                frames[order] = np.asarray(image).copy()
            # The scene itself is unchanged, so pixels may match; its action
            # prescription must still differ between the two symmetry tasks.
            self.assertFalse(np.allclose(prescriptions[2], prescriptions[4]))
            self.assertNotEqual(renderer._make_frame_cache_key(meshes, eye, target, yaw_symmetry_order=2),
                                renderer._make_frame_cache_key(meshes, eye, target, yaw_symmetry_order=4))


if __name__ == "__main__":
    unittest.main(verbosity=2)
