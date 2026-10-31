"""Geometry-based regressions for signed-clearance filtering and real rollback."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest
from unittest import mock

import numpy as np

from human_eye_module1_operators.submodule_1_4_spatial_sniffer import SpatialAnomalySniffer
from module_3_3_closed_loop_control_engine import (
    ClosedLoopActionController, ECBFSafetyShieldReport, ServoFSMState,
)
from verification.blind_test.geometry import build_meshes, euler_matrix, score_pose


def plane_case(center_z=.44):
    return {
        "reference": {"center": [0, 0, .175], "rotation": np.eye(3).tolist(), "size": [1.4, 1.2, .35]},
        "focal": {"center": [0, 0, center_z], "rotation": np.eye(3).tolist(), "size": [.28, .20, .14]},
        "target": {"plane_point": [0, 0, .35], "normal": [0, 0, 1],
                   "rotation": np.eye(3).tolist(), "center": [0, 0, .42]},
        "occluders": [],
    }


def action(translation, euler=(0, 0, 0), **extra):
    return {"focal_mark": "#B", "reference_mark": "#A",
            "rotation_euler_deg_xyz": list(euler), "translation_xyz_m": list(translation), **extra}


class ECBFRecoveryTests(unittest.TestCase):
    def setUp(self):
        ClosedLoopActionController._CTRL_STEP_CACHE.clear()
        ClosedLoopActionController._ECBF_SHIELD_CACHE.clear()

    def apply(self, case, args, controller=None):
        meshes = build_meshes(case)
        controller = controller or ClosedLoopActionController()
        moved, report, fsm = controller.apply_se3_prescription_and_recheck(
            meshes[1], meshes[0], mcp_arguments=args, scene_meshes=meshes,
            enable_ecbf_shield=True)
        score = score_pose(case, moved.local_axes.T, moved.vertices.mean(axis=0))
        return meshes, controller, moved, report, fsm, score

    def test_outward_penetration_recovery_preserves_direction_and_pose(self):
        case = plane_case(.41)
        _, controller, moved, report, _, score = self.apply(case, action((0, 0, .01)))
        self.assertTrue(score["success"], score)
        self.assertGreater(report.applied_translation_m[2], 0)
        self.assertFalse(controller._last_ecbf_report.barrier_activated)
        np.testing.assert_array_equal(moved.local_axes, np.eye(3))

    def test_inward_command_from_penetration_is_projected_outward(self):
        case = plane_case(.41)
        _, controller, _, report, _, score = self.apply(case, action((0, 0, -.02)))
        self.assertTrue(score["success"], score)
        self.assertGreater(report.applied_translation_m[2], 0)
        self.assertTrue(controller._last_ecbf_report.barrier_activated)

    def test_gap_overshoot_preserves_tangent_without_unexecuted_rotation(self):
        case = plane_case()
        _, controller, moved, report, _, score = self.apply(case, action((.003, -.002, -.08)))
        self.assertTrue(score["success"], score)
        np.testing.assert_allclose(report.applied_translation_m, [.003, -.002, -.02], atol=1e-12)
        shield = controller._last_ecbf_report
        np.testing.assert_array_equal(shield.safe_filtered_twist_6d[3:], np.zeros(3))
        self.assertAlmostEqual(shield.predicted_next_clearance_mm,
                               float((moved.vertices[:4, 2] - .35).mean()) * 1000, places=8)

    def test_exact_contact_blocks_inward_and_allows_outward_motion(self):
        case = plane_case(.42)
        for dz, expected in ((-.02, 0.0), (.01, .01)):
            with self.subTest(dz=dz):
                _, _, moved, report, _, score = self.apply(case, action((0, 0, dz)))
                self.assertAlmostEqual(report.applied_translation_m[2], expected, places=10)
                self.assertFalse(score["penetrating"])
                self.assertGreaterEqual(float(moved.vertices[:4, 2].min()), .35 - 1e-10)

    def test_sloped_reference_filters_in_its_outward_frame(self):
        case = plane_case()
        rotation = euler_matrix([27, 0, 17])
        for key in ("reference", "focal"):
            case[key]["center"] = (rotation @ np.asarray(case[key]["center"])).tolist()
            case[key]["rotation"] = rotation.tolist()
        for key in ("plane_point", "normal", "center"):
            case["target"][key] = (rotation @ np.asarray(case["target"][key])).tolist()
        case["target"]["rotation"] = rotation.tolist()
        translation = rotation @ np.array([.002, 0, -.08])
        _, _, moved, _, _, score = self.apply(case, action(translation))
        self.assertTrue(score["success"], score)
        np.testing.assert_allclose(moved.local_axes.T, rotation, atol=1e-12)

    def test_failed_prediction_returns_original_pose_and_zero_applied_action(self):
        case = plane_case()
        case["focal"]["rotation"] = euler_matrix([5, -3, 8]).tolist()
        meshes = build_meshes(case)
        controller = ClosedLoopActionController()
        unsafe = ECBFSafetyShieldReport(
            nominal_twist_6d=np.array([0, 0, -.1, 0, 0, 0]),
            safe_filtered_twist_6d=np.array([0, 0, -.1, 0, 0, 0]),
            barrier_activated=False, jamming_shield_activated=False,
            predicted_next_clearance_mm=0, normal_overshoot_removed_mm=0,
            tangential_null_space_preservation_ratio=1, summary_message="injected local prediction error")
        with mock.patch.object(controller, "filter_action_with_ecbf_and_jamming_shield", return_value=unsafe):
            moved, report, fsm = controller.apply_se3_prescription_and_recheck(
                meshes[1], meshes[0], mcp_arguments=action((0, 0, -.1), (-5, 3, -8)),
                scene_meshes=meshes, enable_ecbf_shield=True)
        self.assertIs(moved, meshes[1])
        np.testing.assert_array_equal(moved.local_axes, np.asarray(case["focal"]["rotation"]).T)
        self.assertEqual(report.applied_translation_m, (0.0, 0.0, 0.0))
        self.assertEqual(report.applied_rotation_euler_deg, (0.0, 0.0, 0.0))
        self.assertFalse(report.verification_passed)
        self.assertEqual(fsm.current_state, ServoFSMState.EMERGENCY_SAFE_ROLLBACK)
        self.assertEqual(controller.rollback_count, 1)
        self.assertTrue(controller._last_ecbf_report.rollback_performed)
        self.assertEqual(len(controller._inflight_twist_ring), 0)

    def test_scene_obstacle_collision_rolls_back_and_bypasses_stale_cache(self):
        case = plane_case()
        meshes = build_meshes(case)
        controller = ClosedLoopActionController()
        args = action((.10, 0, -.02))
        moved, _, _ = controller.apply_se3_prescription_and_recheck(
            meshes[1], meshes[0], mcp_arguments=args, scene_meshes=meshes, enable_ecbf_shield=True)
        self.assertIsNot(moved, meshes[1])
        blocked_case = copy.deepcopy(case)
        blocked_case["occluders"] = [{"center": [.24, 0, .48], "rotation": np.eye(3).tolist(),
                                     "size": [.12, .14, .20]}]
        obstacle = build_meshes(blocked_case)[2]
        moved, report, fsm = controller.apply_se3_prescription_and_recheck(
            meshes[1], meshes[0], mcp_arguments=args, scene_meshes=[*meshes, obstacle],
            enable_ecbf_shield=True)
        self.assertIs(moved, meshes[1])
        self.assertFalse(report.verification_passed)
        self.assertIn("#C", report.summary_message)
        self.assertEqual(fsm.current_state, ServoFSMState.EMERGENCY_SAFE_ROLLBACK)

    def test_partial_recovery_is_retained_and_not_labelled_as_rollback(self):
        case = plane_case(.40)
        _, controller, moved, report, fsm, score = self.apply(
            case, action((0, 0, 0)), ClosedLoopActionController(ecbf_gamma=.5))
        self.assertTrue(score["penetrating"])
        self.assertGreater(report.applied_translation_m[2], 0)
        self.assertGreater(moved.vertices[:, 2].mean(), .40)
        self.assertEqual(controller.rollback_count, 0)
        self.assertEqual(fsm.current_state, ServoFSMState.FINE_LEVELING_SERVO)

    def test_rollback_restores_quantizer_residuals_and_ipc_output(self):
        case = plane_case()
        case["occluders"] = [{"center": [.24, 0, .48], "rotation": np.eye(3).tolist(),
                              "size": [.12, .14, .20]}]
        meshes = build_meshes(case)
        controller = ClosedLoopActionController(
            enable_zero_copy_ipc=True, trans_quantization_step_m=.001)
        controller._trans_residual_m[:] = [.0002, -.0001, .0001]
        before = controller._trans_residual_m.copy()
        controller._mcp_ipc_engine.arena.publish_tensor(2, np.zeros_like(meshes[1].vertices))
        moved, report, _ = controller.apply_se3_prescription_and_recheck(
            meshes[1], meshes[0], mcp_arguments=action((.1003, .0002, -.0203)),
            scene_meshes=meshes, enable_ecbf_shield=True)
        self.assertIs(moved, meshes[1])
        self.assertFalse(report.verification_passed)
        np.testing.assert_array_equal(controller._trans_residual_m, before)
        output, _ = controller._mcp_ipc_engine.arena.resolve_tensor_view(2)
        np.testing.assert_array_equal(output, meshes[1].vertices)

    def test_symmetry_orders_and_cached_replays_keep_the_requested_pose(self):
        case = plane_case()
        case["focal"]["rotation"] = euler_matrix([0, 0, 90]).tolist()
        meshes = build_meshes(case)
        controller = ClosedLoopActionController()
        for order in (2, 4, 2):
            with self.subTest(order=order):
                moved, _, _ = controller.apply_se3_prescription_and_recheck(
                    meshes[1], meshes[0], mcp_arguments={"yaw_symmetry_order": order},
                    enable_ecbf_shield=True)
                if order == 2:
                    self.assertLess(abs(float(moved.local_axes[0, 1])), 1e-8)
                else:
                    self.assertAlmostEqual(abs(float(moved.local_axes[0, 1])), 1.0, places=8)

    def test_frozen_blind_penetration_regressions_recover(self):
        fixtures = Path(__file__).parent / "blind_test/runs/20261021_01/private/cases.json"
        if not fixtures.exists():
            self.skipTest("Frozen first-round cases not included in this checkout")
        cases = json.loads(fixtures.read_text(encoding="utf-8"))
        selected = [case for case in cases if case["scene_id"] in ("S021", "S022", "S024", "S025")]
        self.assertEqual(len(selected), 4)
        for case in selected:
            with self.subTest(scene=case["scene_id"]):
                meshes = build_meshes(case)
                probe = SpatialAnomalySniffer.probe_closest_clearance(meshes[1], meshes[0])
                _, _, _, report, _, score = self.apply(
                    case, action(probe.axis_delta_m, probe.rotation_euler_deg_xyz))
                self.assertTrue(score["success"], score)
                self.assertGreater(report.applied_translation_m[2], 0)


if __name__ == "__main__":
    unittest.main()
