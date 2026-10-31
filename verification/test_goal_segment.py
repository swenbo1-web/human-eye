"""Candidate geometry is independently constrained before any live execution."""
import copy
import math
import unittest
from unittest.mock import patch

from human_eye_plugin.goal_segment import (
    CLEARANCE_SEGMENT_REQUEST_SCHEMA, clearance_segment_goal,
    solve_clearance_candidate, validate_clearance_segment_request,
)
from human_eye_plugin.task_verification import evaluate_spatial_goal
from verification.test_auto_router import box


def segment_request(**changes):
    value = {"focal_id": "part", "reference_id": "base", "axis": "+z",
             "target_clearance_m": .001, "clearance_tolerance_m": 1e-6}
    value.update(changes)
    return value


def clearance_scene(gap=.004, axis="+z"):
    coordinate, sign = {"+x": (0, 1), "-x": (0, -1), "+y": (1, 1),
                        "-y": (1, -1), "+z": (2, 1), "-z": (2, -1)}[axis]
    center = [0., 0., 0.]
    center[coordinate] = sign * (.1 + .05 + gap)
    meshes = [box("base", [0, 0, 0], [.2, .2, .2]),
              box("part", center, [.1, .1, .1], True)]
    for mesh, pivot in zip(meshes, ([0., 0., 0.], center)):
        mesh.update(axes_source="host", axes_confidence="explicit",
                    axes_reason="fixture_explicit_frame", pivot_world=list(pivot))
    return {"revision": "test-scene-1", "source": "pure_solver_fixture",
            "unit": "m", "coordinate_frame": "world", "meshes": meshes}


def translated(value, translation):
    value = copy.deepcopy(value)
    focal = value["meshes"][1]
    focal["vertices"] = [[p[k] + translation[k] for k in range(3)] for p in focal["vertices"]]
    focal["pivot_world"] = [focal["pivot_world"][k] + translation[k] for k in range(3)]
    value["revision"] += "-translated"
    return value


class ClearanceRequestTests(unittest.TestCase):
    def test_defaults_are_bounded_and_required_intent_has_no_default(self):
        normalized = validate_clearance_segment_request(segment_request())
        self.assertEqual(normalized["max_steps"], 4)
        self.assertEqual(normalized["max_duration_s"], 5)
        self.assertEqual(normalized["max_step_translation_m"], .01)
        self.assertEqual(normalized["max_total_translation_m"], .04)
        self.assertEqual(set(CLEARANCE_SEGMENT_REQUEST_SCHEMA["oneOf"][0]["required"]), set(segment_request()))
        for field in segment_request():
            missing = segment_request()
            missing.pop(field)
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_clearance_segment_request(missing)

    def test_numbers_reject_booleans_strings_nonfinite_and_negative(self):
        for field in ("target_clearance_m", "clearance_tolerance_m",
                      "max_step_translation_m", "max_total_translation_m", "max_duration_s"):
            for invalid in (True, False, "0.001", float("nan"), float("inf"), -1, 10 ** 1000):
                with self.subTest(field=field, invalid=type(invalid).__name__), self.assertRaises(ValueError):
                    validate_clearance_segment_request(segment_request(**{field: invalid}))

    def test_motion_and_time_budgets_are_positive_and_bounded(self):
        for field, maximum in (("max_step_translation_m", 1),
                               ("max_total_translation_m", 4), ("max_duration_s", 30)):
            for invalid in (0, maximum + .01):
                with self.subTest(field=field, invalid=invalid), self.assertRaises(ValueError):
                    validate_clearance_segment_request(segment_request(**{field: invalid}))

    def test_step_count_is_strict_integer(self):
        for invalid in (True, False, 0, 9, 1.0, "2"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_clearance_segment_request(segment_request(max_steps=invalid))

    def test_identity_axis_and_extra_fields_are_explicit(self):
        for changes in ({"focal_id": "base"}, {"focal_id": " "}, {"reference_id": "x" * 257},
                        {"axis": "z"}, {"axis": [0, 0, 1]}, {"axis": True},
                        {"force": True}, {"request_id": "not_solver_authority"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_clearance_segment_request(segment_request(**changes))

    def test_zero_targets_and_tolerances_are_not_defaulted_away(self):
        value = validate_clearance_segment_request(segment_request(
            target_clearance_m=0, clearance_tolerance_m=0))
        self.assertEqual(value["target_clearance_m"], 0)
        self.assertEqual(value["clearance_tolerance_m"], 0)

    def test_separate_goal_contains_no_solver_budget_or_action(self):
        self.assertEqual(clearance_segment_goal(segment_request()), {
            "focal_id": "part", "reference_id": "base",
            "target_clearance_m": .001, "clearance_tolerance_m": 1e-6})


class ClearanceCandidateTests(unittest.TestCase):
    def test_all_six_axes_solve_against_independent_expected_displacement(self):
        for axis, coordinate, sign in (("+x", 0, 1), ("-x", 0, -1), ("+y", 1, 1),
                                       ("-y", 1, -1), ("+z", 2, 1), ("-z", 2, -1)):
            with self.subTest(axis=axis):
                result = solve_clearance_candidate(clearance_scene(axis=axis), segment_request(axis=axis))
                self.assertEqual(result["status"], "candidate", result)
                self.assertAlmostEqual(result["current_clearance_m"], .004, places=12)
                expected = [0., 0., 0.]
                expected[coordinate] = sign * -.003
                for actual, wanted in zip(result["candidate"]["translation"], expected):
                    self.assertAlmostEqual(actual, wanted, places=12)
                self.assertEqual(result["candidate"]["rotation_euler_deg"], [0., 0., 0.])

    def test_candidate_does_not_claim_authority_or_task_success(self):
        result = solve_clearance_candidate(clearance_scene(), segment_request())
        for field in ("execution_authority", "whole_scene_collision_certified",
                      "swept_path_certified", "task_success_certified", "ground_truth_independent"):
            self.assertIs(result[field], False)
        self.assertIs(result["requires_fresh_execution_gate"], True)
        self.assertEqual(result["scene_revision"], "test-scene-1")
        self.assertEqual(result["scene_source"], "pure_solver_fixture")
        self.assertEqual(result["measurement_kind"], "exact")
        self.assertEqual(len(result["scene_fingerprint"]), 64)

    def test_independent_goal_verifier_accepts_readonly_application_of_candidate(self):
        initial = clearance_scene()
        request = segment_request()
        result = solve_clearance_candidate(initial, request)
        changed = translated(initial, result["candidate"]["translation"])
        goal = evaluate_spatial_goal(changed, clearance_segment_goal(request))
        self.assertTrue(goal["task_succeeded"], goal)
        # This is a pure geometry check, not a live-host movement claim.
        self.assertEqual(initial["revision"], "test-scene-1")

    def test_zero_goal_targets_contact_without_invented_negative_gap(self):
        result = solve_clearance_candidate(clearance_scene(), segment_request(target_clearance_m=0))
        self.assertEqual(result["status"], "candidate", result)
        self.assertGreaterEqual(result["predicted_plane_clearance_m"], 0)
        self.assertAlmostEqual(result["candidate"]["translation"][2], -.004, places=12)

    def test_already_satisfied_returns_no_action(self):
        result = solve_clearance_candidate(clearance_scene(), segment_request(target_clearance_m=.004))
        self.assertEqual(result["status"], "goal_satisfied", result)
        self.assertIsNone(result["candidate"])
        self.assertTrue(result["goal_satisfied"])
        self.assertFalse(result["task_success_certified"])

    def test_increasing_gap_moves_away(self):
        result = solve_clearance_candidate(clearance_scene(), segment_request(target_clearance_m=.01))
        self.assertEqual(result["status"], "candidate", result)
        self.assertAlmostEqual(result["candidate"]["translation"][2], .006, places=12)

    def test_step_limit_and_total_limit_both_clip_candidate(self):
        for step, total, expected in ((.002, .04, .002), (.01, .001, .001)):
            with self.subTest(step=step, total=total):
                result = solve_clearance_candidate(clearance_scene(), segment_request(
                    max_step_translation_m=step, max_total_translation_m=total))
                self.assertTrue(result["step_clipped"])
                self.assertAlmostEqual(result["proposed_translation_m"], expected, places=12)
                self.assertGreater(result["predicted_absolute_error_m"], 0)

    def test_unrepresentable_step_stops_without_candidate(self):
        result = solve_clearance_candidate(clearance_scene(), segment_request(
            max_step_translation_m=1e-300))
        self.assertEqual(result["status"], "precision_floor", result)
        self.assertEqual(result["reason_codes"], ["no_representable_progress"])
        self.assertIsNone(result["candidate"])

    def test_small_clearance_is_not_rounded_to_zero_flush(self):
        result = solve_clearance_candidate(clearance_scene(gap=1e-7), segment_request(
            target_clearance_m=5e-8, clearance_tolerance_m=1e-9))
        self.assertEqual(result["status"], "candidate", result)
        self.assertAlmostEqual(result["current_clearance_m"], 1e-7, places=14)
        self.assertAlmostEqual(result["candidate"]["translation"][2], -5e-8, places=14)

    def test_feature_signature_survives_allowed_axial_translation(self):
        value = clearance_scene()
        first = solve_clearance_candidate(value, segment_request(max_step_translation_m=.001))
        changed = translated(value, first["candidate"]["translation"])
        second = solve_clearance_candidate(changed, segment_request(),
            expected_feature_signature=first["feature_signature"])
        self.assertEqual(second["status"], "candidate", second)
        self.assertEqual(first["feature_signature"], second["feature_signature"])
        self.assertNotEqual(first["scene_fingerprint"], second["scene_fingerprint"])

    def test_tangent_overlap_change_is_a_feature_stop(self):
        value = clearance_scene()
        first = solve_clearance_candidate(value, segment_request())
        changed = translated(value, [.01, 0, 0])
        second = solve_clearance_candidate(changed, segment_request(),
            expected_feature_signature=first["feature_signature"])
        self.assertEqual(second["status"], "feature_changed")
        self.assertIsNone(second["candidate"])

    def test_face_topology_reordering_changes_contact_binding(self):
        value = clearance_scene()
        first = solve_clearance_candidate(value, segment_request())
        value["meshes"][1]["faces"] = list(reversed(value["meshes"][1]["faces"]))
        second = solve_clearance_candidate(value, segment_request(),
            expected_feature_signature=first["feature_signature"])
        self.assertEqual(second["status"], "feature_changed")

    def test_diagonal_nearest_distance_is_not_a_face_gap(self):
        value = translated(clearance_scene(), [.3, 0, 0])
        result = solve_clearance_candidate(value, segment_request())
        self.assertEqual(result["reason_codes"], ["positive_face_overlap_required"])
        self.assertIsNone(result["candidate"])

    def test_wrong_side_and_penetration_are_unsupported(self):
        cases = [(clearance_scene(), segment_request(axis="-z")),
                 (clearance_scene(gap=-.001), segment_request())]
        for value, request in cases:
            result = solve_clearance_candidate(value, request)
            self.assertEqual(result["reason_codes"], ["faces_not_separated_in_requested_axis"])
            self.assertIsNone(result["candidate"])

    def test_open_duplicate_and_wrong_winding_surfaces_fail_exact_box_proof(self):
        for kind in ("open", "duplicate", "winding", "dent"):
            value = clearance_scene()
            focal = value["meshes"][1]
            if kind == "open":
                focal["faces"].pop()
            elif kind == "duplicate":
                focal["faces"][1] = focal["faces"][0][:]
            elif kind == "winding":
                focal["faces"][0] = list(reversed(focal["faces"][0]))
            else:
                focal["vertices"][0][0] += .001
            with self.subTest(kind=kind):
                result = solve_clearance_candidate(value, segment_request())
                self.assertEqual(result["reason_codes"], ["exact_axis_box_boundary_required"])
                self.assertIsNone(result["candidate"])

    def test_non_world_axis_box_does_not_pass_by_aabb(self):
        value = clearance_scene()
        sine, cosine = math.sin(.1), math.cos(.1)
        for vertex in value["meshes"][1]["vertices"]:
            x, y = vertex[:2]
            vertex[0], vertex[1] = cosine * x - sine * y, sine * x + cosine * y
        result = solve_clearance_candidate(value, segment_request())
        self.assertEqual(result["reason_codes"], ["exact_axis_box_boundary_required"])

    def test_generous_goal_tolerance_cannot_hide_disagreeing_geometry(self):
        fake = {"measurement_valid": True, "is_penetrating": False, "signed_clearance_m": .1}
        with patch("human_eye_plugin.goal_segment.measure_pair_geometry", return_value=fake):
            result = solve_clearance_candidate(clearance_scene(), segment_request(clearance_tolerance_m=1))
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["reason_codes"], ["face_gap_disagrees_with_strict_clearance"])
        self.assertFalse(result["goal_satisfied"])

    def test_unknown_strict_metric_never_produces_candidate(self):
        for fake in ({"measurement_valid": False},
                     {"measurement_valid": True, "is_penetrating": False, "signed_clearance_m": float("nan")},
                     {"measurement_valid": True, "is_penetrating": True, "signed_clearance_m": -.001}):
            with patch("human_eye_plugin.goal_segment.measure_pair_geometry", return_value=fake):
                result = solve_clearance_candidate(clearance_scene(), segment_request())
            self.assertEqual(result["status"], "unknown")
            self.assertIsNone(result["candidate"])

    def test_strict_metric_failure_is_unknown(self):
        with patch("human_eye_plugin.goal_segment.measure_pair_geometry", side_effect=ValueError("unsupported")):
            result = solve_clearance_candidate(clearance_scene(), segment_request())
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["error_type"], "ValueError")

    def test_untrusted_axes_and_host_capability_do_not_produce_candidate(self):
        value = clearance_scene()
        value["meshes"][1]["axes_source"] = "inferred"
        result = solve_clearance_candidate(value, segment_request())
        self.assertEqual(result["reason_codes"], ["rigid_frame_unavailable"])
        value = clearance_scene()
        value["host_execution"] = {"schema_version": "1.0", "operation": "rigid_transform",
            "supported": False, "scope": "independent_static_rigid_meshes",
            "reasons": [{"object_id": "part", "object_name": "part", "reason": "modifiers_present"}]}
        result = solve_clearance_candidate(value, segment_request())
        self.assertEqual(result["reason_codes"], ["host_rigid_execution_unsupported"])

    def test_inputs_are_not_mutated_or_retained_as_result_aliases(self):
        value, request = clearance_scene(), segment_request()
        before = copy.deepcopy((value, request))
        result = solve_clearance_candidate(value, request)
        self.assertEqual((value, request), before)
        result["request"]["target_clearance_m"] = 42
        self.assertEqual(request["target_clearance_m"], .001)

    def test_missing_objects_or_invalid_feature_binding_raise(self):
        with self.assertRaises(ValueError):
            solve_clearance_candidate(clearance_scene(), segment_request(focal_id="absent"))
        for invalid in (True, "short", "Z" * 64):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                solve_clearance_candidate(clearance_scene(), segment_request(),
                    expected_feature_signature=invalid)


if __name__ == "__main__":
    unittest.main()
