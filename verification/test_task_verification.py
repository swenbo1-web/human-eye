"""Goals must describe the actual task, separately from executing an action."""
import copy
import json
import math
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_module1_operators import MeshEntity3D, SE3AlignmentMath, SpatialAnomalySniffer
from human_eye_plugin.task_verification import evaluate_spatial_goal
from verification.test_auto_router import box, scene


def gap_goal(**changes):
    goal = {"focal_id": "part", "reference_id": "base",
            "target_clearance_m": 0.1, "clearance_tolerance_m": 1e-8}
    goal.update(changes)
    return goal


def posed_scene(z=0.35, yaw=0, tilt=0):
    value = scene()
    part = MeshEntity3D.from_dict(box("part", [0, 0, z], [.3, .2, .1], True))
    if yaw or tilt:
        part = part.rotated_around_pivot(SE3AlignmentMath.euler_xyz_to_matrix(tilt, 0, yaw))
    value["meshes"][1] = part.to_dict()
    return value


class SpatialGoalTests(unittest.TestCase):
    def test_exact_gap_task_success_is_explicitly_engine_derived(self):
        result = evaluate_spatial_goal(scene(), gap_goal())
        self.assertTrue(result["task_succeeded"], result)
        self.assertEqual(result["status"], "goal_satisfied")
        self.assertEqual(result["evaluator_source"], "human_eye_engine_geometry")
        self.assertFalse(result["ground_truth_independent"])
        self.assertNotIn("action_verified", result)
        self.assertEqual(result["scene_revision"], "r1")
        self.assertEqual(len(result["scene_fingerprint"]), 64)

    def test_safe_pose_can_fail_task(self):
        result = evaluate_spatial_goal(posed_scene(z=.45), gap_goal())
        self.assertTrue(result["measurement_valid"])
        self.assertTrue(result["checks"]["pair_nonpenetrating"]["passed"])
        self.assertFalse(result["task_succeeded"])
        self.assertIn("target_clearance_not_met", result["reason_codes"])

    def test_sub_flush_positive_gap_does_not_become_zero_goal(self):
        value = posed_scene(z=.25005)
        rounded = SpatialAnomalySniffer.probe_closest_clearance(
            *[MeshEntity3D.from_dict(value["meshes"][i]) for i in (1, 0)])
        self.assertEqual(rounded.signed_clearance_m, 0)
        result = evaluate_spatial_goal(value, gap_goal(target_clearance_m=0, clearance_tolerance_m=1e-6))
        self.assertFalse(result["task_succeeded"])
        self.assertAlmostEqual(result["measurements"]["signed_clearance_m"], .00005, places=10)

    def test_fifty_micrometre_penetration_fails_even_generous_target_tolerance(self):
        result = evaluate_spatial_goal(posed_scene(z=.24995),
            gap_goal(target_clearance_m=0, clearance_tolerance_m=.001))
        self.assertTrue(result["measurement_valid"])
        self.assertFalse(result["task_succeeded"])
        self.assertTrue(result["measurements"]["is_penetrating"])
        self.assertIn("pair_penetrating", result["reason_codes"])

    def test_angle_only_goal_is_valid_and_checks_requested_metric(self):
        value = posed_scene(yaw=5)
        result = evaluate_spatial_goal(value, {"focal_id": "part", "reference_id": "base",
            "max_tangent_yaw_mismatch_deg": .5})
        self.assertTrue(result["measurement_valid"], result)
        self.assertFalse(result["task_succeeded"])
        self.assertAlmostEqual(result["measurements"]["tangent_yaw_mismatch_deg"], 5, places=6)

    def test_tilt_goal_and_all_requested_goals_are_required(self):
        result = evaluate_spatial_goal(posed_scene(tilt=3),
            gap_goal(clearance_tolerance_m=.02, max_contact_normal_angle_deg=.5))
        self.assertTrue(result["checks"]["clearance"]["passed"], result)
        self.assertFalse(result["checks"]["contact_normal"]["passed"])
        self.assertFalse(result["task_succeeded"])

    def test_sub_millidegree_yaw_is_not_rounded_to_success(self):
        result = evaluate_spatial_goal(posed_scene(yaw=.0003),
            {"focal_id": "part", "reference_id": "base", "max_tangent_yaw_mismatch_deg": .0001})
        self.assertFalse(result["task_succeeded"], result)
        self.assertAlmostEqual(result["measurements"]["tangent_yaw_mismatch_deg"], .0003, places=7)

    def test_sub_millidegree_normal_angle_is_not_rounded_to_success(self):
        result = evaluate_spatial_goal(posed_scene(tilt=.0003),
            {"focal_id": "part", "reference_id": "base", "max_contact_normal_angle_deg": .0001})
        self.assertFalse(result["task_succeeded"], result)
        self.assertAlmostEqual(result["measurements"]["contact_normal_angle_deg"], .0003, places=7)

    def test_yaw_symmetry_policy_is_respected(self):
        value = scene()
        value["meshes"][1] = box("part", [0, 0, .35], [.2, .2, .1], True)
        part = MeshEntity3D.from_dict(value["meshes"][1]).rotated_around_pivot(
            SE3AlignmentMath.euler_xyz_to_matrix(0, 0, 90))
        value["meshes"][1] = part.to_dict()
        goal = {"focal_id": "part", "reference_id": "base", "max_tangent_yaw_mismatch_deg": .001}
        self.assertFalse(evaluate_spatial_goal(value, dict(goal, yaw_symmetry_order=1))["task_succeeded"])
        self.assertTrue(evaluate_spatial_goal(value, dict(goal, yaw_symmetry_order=4))["task_succeeded"])

    def test_world_pivot_position_uses_exported_origin_not_bbox_center(self):
        value = posed_scene()
        value["meshes"][1]["pivot_world"] = [.02, .03, .4]
        goal = {"focal_id": "part", "reference_id": "base",
                "target_focal_pivot_world_m": [.02, .03, .4], "position_tolerance_m": 0}
        result = evaluate_spatial_goal(value, goal)
        self.assertTrue(result["task_succeeded"], result)
        self.assertEqual(result["checks"]["position"]["absolute_error_m"], 0)

    def test_position_error_is_world_euclidean_distance(self):
        goal = {"focal_id": "part", "reference_id": "base",
                "target_focal_pivot_world_m": [.003, .004, .35], "position_tolerance_m": .0049}
        result = evaluate_spatial_goal(posed_scene(), goal)
        self.assertFalse(result["task_succeeded"])
        self.assertAlmostEqual(result["checks"]["position"]["absolute_error_m"], .005)

    def test_missing_explicit_pivot_is_unavailable_not_invented(self):
        value = scene()
        value["meshes"][1].pop("pivot_world", None)
        result = evaluate_spatial_goal(value, {"focal_id": "part", "reference_id": "base",
            "target_focal_pivot_world_m": [0, 0, .35], "position_tolerance_m": .01})
        self.assertFalse(result["task_succeeded"])
        self.assertFalse(result["measurement_valid"])
        self.assertEqual(result["status"], "measurement_unavailable")
        self.assertIn("focal_pivot_unavailable", result["reason_codes"])

    def test_axis_ambiguity_does_not_block_pure_distance_or_position(self):
        value = posed_scene()
        value["meshes"][1]["axes_confidence"] = "ambiguous"
        value["meshes"][1]["axes_source"] = "unverified_imported_frame"
        for goal in (gap_goal(), {"focal_id": "part", "reference_id": "base",
             "target_focal_pivot_world_m": [0, 0, .35], "position_tolerance_m": 1e-8}):
            result = evaluate_spatial_goal(value, goal)
            self.assertTrue(result["task_succeeded"], result)
            self.assertIsNone(result["axes_valid"])

    def test_angular_goal_requires_valid_axes(self):
        value = posed_scene()
        value["meshes"][1]["axes_confidence"] = "ambiguous"
        value["meshes"][1]["axes_source"] = "unverified_imported_frame"
        result = evaluate_spatial_goal(value, gap_goal(max_tangent_yaw_mismatch_deg=1))
        self.assertFalse(result["task_succeeded"])
        self.assertFalse(result["measurement_valid"])
        self.assertFalse(result["axes_valid"])
        self.assertIn("angular_measurement_invalid", result["reason_codes"])

    def test_open_geometry_is_unknown_and_no_angular_probe_runs(self):
        value = scene()
        value["meshes"][1]["faces"] = value["meshes"][1]["faces"][:-2]
        with patch("human_eye_plugin.task_verification.SpatialAnomalySniffer.probe_closest_clearance") as probe:
            result = evaluate_spatial_goal(value, gap_goal(max_contact_normal_angle_deg=1))
        probe.assert_not_called()
        self.assertFalse(result["task_succeeded"])
        self.assertFalse(result["measurement_valid"])

    def test_resource_exhausted_geometry_remains_unknown_before_angle_probe(self):
        value = scene()
        for mesh in value["meshes"]:
            mesh["faces"] *= 100
        with patch("human_eye_plugin.task_verification.SpatialAnomalySniffer.probe_closest_clearance") as probe:
            result = evaluate_spatial_goal(value, gap_goal(max_contact_normal_angle_deg=1))
        probe.assert_not_called()
        self.assertFalse(result["measurement_valid"])
        self.assertFalse(result["task_succeeded"])

    def test_pair_goal_does_not_claim_to_evaluate_third_party_collision(self):
        value = scene()
        value["meshes"].append(box("obstacle", [0, 0, .35], [.2, .1, .05]))
        result = evaluate_spatial_goal(value, gap_goal())
        self.assertTrue(result["task_succeeded"], result)
        self.assertTrue(result["evaluation_scope"].startswith("known_mesh_pair_"))
        self.assertNotIn("scene_collision_free", result)

    def test_angular_probe_failure_cannot_pass_other_valid_goals(self):
        with patch("human_eye_plugin.task_verification.SpatialAnomalySniffer.probe_closest_clearance",
                   side_effect=RuntimeError("unavailable")):
            result = evaluate_spatial_goal(scene(), gap_goal(max_contact_normal_angle_deg=1))
        self.assertFalse(result["task_succeeded"])
        self.assertFalse(result["measurement_valid"])
        self.assertTrue(result["checks"]["clearance"]["passed"])

    def test_deep_penetration_cannot_succeed_as_an_angular_only_task(self):
        value = posed_scene(z=.1)
        result = evaluate_spatial_goal(value, {"focal_id": "part", "reference_id": "base",
            "max_contact_normal_angle_deg": 180, "max_tangent_yaw_mismatch_deg": 180})
        self.assertFalse(result["task_succeeded"])
        self.assertIn("pair_penetrating", result["reason_codes"])

    def test_no_silent_identity_or_name_fallback(self):
        for goal in (gap_goal(focal_id="missing"), gap_goal(reference_id="part"),
                     gap_goal(focal_id=""), gap_goal(reference_id=" ")):
            with self.assertRaises(ValueError):
                evaluate_spatial_goal(scene(), goal)

    def test_units_coordinate_frame_and_revision_are_validated(self):
        for change in ({"unit": "cm"}, {"coordinate_frame": "local"}, {"revision": ""}):
            value = scene()
            value.update(change)
            with self.assertRaises(ValueError):
                evaluate_spatial_goal(value, gap_goal())

    def test_goal_requires_paired_targets_and_at_least_one_goal(self):
        malformed = [None, [], {"focal_id": "part", "reference_id": "base"},
            gap_goal(clearance_tolerance_m=None), gap_goal(extra="unknown"),
            {"focal_id": "part", "reference_id": "base", "target_clearance_m": .1},
            {"focal_id": "part", "reference_id": "base", "clearance_tolerance_m": .1},
            {"focal_id": "part", "reference_id": "base", "target_focal_pivot_world_m": [0, 0, 0]},
            gap_goal(position_tolerance_m=.1)]
        for goal in malformed:
            with self.subTest(goal=goal), self.assertRaises(ValueError):
                evaluate_spatial_goal(scene(), goal)

    def test_numeric_constraints_reject_bool_nan_infinity_negative_and_strings(self):
        for key, values in {
            "target_clearance_m": (True, "0.1", math.nan, math.inf, -1, 10**1000),
            "clearance_tolerance_m": (True, math.nan, -1, "1"),
            "max_contact_normal_angle_deg": (False, math.inf, -1, 181),
            "max_tangent_yaw_mismatch_deg": (True, math.nan, -1, 181),
            "yaw_symmetry_order": (True, 0, 3, 2.0, "2"),
        }.items():
            for value in values:
                with self.subTest(key=key, value=str(value)[:30]), self.assertRaises(ValueError):
                    evaluate_spatial_goal(scene(), gap_goal(**{key: value}))

    def test_position_coordinates_and_tolerances_reject_malformed_values(self):
        for position, tolerance in (([0, 0], .1), ([0, True, 0], .1),
                                    ([0, math.nan, 0], .1), ([0, 0, 0], -1),
                                    ([0, 0, 0], False), ("000", .1)):
            with self.assertRaises(ValueError):
                evaluate_spatial_goal(scene(), gap_goal(target_focal_pivot_world_m=position,
                    position_tolerance_m=tolerance))

    def test_input_and_result_are_detached_and_json_serializable(self):
        value, goal = posed_scene(), gap_goal()
        original = copy.deepcopy((value, goal))
        result = evaluate_spatial_goal(value, goal)
        result["goal"]["target_clearance_m"] = 99
        self.assertEqual((value, goal), original)
        json.dumps(result, allow_nan=False)

    def test_geometry_failure_or_invalid_result_never_succeeds(self):
        for measurement in ({"measurement_valid": False},
                {"measurement_valid": True, "signed_clearance_m": math.nan, "is_penetrating": False},
                {"measurement_valid": True, "signed_clearance_m": .1, "is_penetrating": None}):
            with patch("human_eye_plugin.task_verification.measure_pair_geometry", return_value=measurement):
                result = evaluate_spatial_goal(scene(), gap_goal())
            self.assertFalse(result["task_succeeded"])
            self.assertFalse(result["measurement_valid"])
        with patch("human_eye_plugin.task_verification.measure_pair_geometry", side_effect=RuntimeError("failed")):
            result = evaluate_spatial_goal(scene(), gap_goal())
        self.assertFalse(result["task_succeeded"])
        self.assertEqual(result["reason_codes"], ["geometry_measurement_failed"])


if __name__ == "__main__":
    unittest.main()
