"""Independent planar references for the read-only support-plane solver.

Fixtures assert elementary plane distances, explicit translations and refusal
boundaries. No engine distance is used to construct an expected result.
"""
from __future__ import annotations

import copy
from fractions import Fraction
import math
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_plugin.support_plane_candidate import (
    CONTRACT_REVISION, REQUEST_SCHEMA, solve_support_plane_candidate,
    validate_support_plane_request,
)
from human_eye_plugin.geometry_safety import measure_pair_geometry as actual_pair_measurement
from verification.test_auto_router import box
from verification.test_concave_geometry import ring


def request(**changes):
    result = {"focal_id": "part", "reference_id": "base",
              "reference_triangle_index": 2, "direction_world": [0., 0., 1.],
              "target_clearance_m": .001, "clearance_tolerance_m": 1e-8}
    result.update(changes)
    return result


def host_frame(mesh, pivot=(0., 0., 0.)):
    mesh.update(axes_source="host", axes_confidence="explicit",
                axes_reason="independent_planar_fixture", pivot_world=list(pivot))
    return mesh


def flat_scene(gap=.004):
    center = (0., 0., .15 + gap)
    return {"revision": "support-plane-fixture-v1", "source": "independent_plane_fixture",
            "unit": "m", "coordinate_frame": "world", "meshes": [
                host_frame(box("base", [0, 0, 0], [.2, .2, .2])),
                host_frame(box("part", center, [.1, .1, .1], True), center)]}


def tilted_scene(angle_deg=1.):
    value = flat_scene()
    focal = value["meshes"][1]
    pivot = focal["pivot_world"]
    angle = math.radians(angle_deg)
    sine, cosine = math.sin(angle), math.cos(angle)
    for vertex in focal["vertices"]:
        x, z = vertex[0] - pivot[0], vertex[2] - pivot[2]
        vertex[0] = cosine * x + sine * z + pivot[0]
        vertex[2] = -sine * x + cosine * z + pivot[2]
    focal["local_axes"] = [[cosine, 0., -sine], [0., 1., 0.], [sine, 0., cosine]]
    return value


def slope_scene():
    value = flat_scene()
    value["meshes"][0]["vertices"] = [
        [-.1, -.1, -.1], [.1, -.1, -.1], [.1, .1, -.1], [-.1, .1, -.1],
        [-.1, -.1, -.05], [.1, -.1, .05], [.1, .1, .05], [-.1, .1, -.05]]
    value["meshes"][1] = host_frame(
        box("part", [0, 0, .03], [.02, .02, .02], True), [0, 0, .03])
    return value


def apply_translation(value, translation):
    value = copy.deepcopy(value)
    focal = next(m for m in value["meshes"] if m["object_id"] == "part")
    focal["vertices"] = [[vertex[k] + translation[k] for k in range(3)]
                         for vertex in focal["vertices"]]
    focal["pivot_world"] = [focal["pivot_world"][k] + translation[k] for k in range(3)]
    value["revision"] += "-translated"
    return value


def normal_gap(value, normal=(0., 0., 1.)):
    """Elementary independent support-plane formula, not a mesh distance kernel."""
    n = [Fraction.from_float(float(c)) for c in normal]
    def project(vertex):
        return sum(n[k] * Fraction.from_float(float(vertex[k])) for k in range(3))
    focal, reference = value["meshes"][1], value["meshes"][0]
    numerator = min(map(project, focal["vertices"])) - max(map(project, reference["vertices"]))
    return float(numerator) / math.sqrt(sum(float(c) ** 2 for c in n))


def tetra_scene(low_point):
    value = flat_scene()
    x, y, z = low_point
    vertices = [[x, y, z], [x-.015, y-.01, z+.02],
                [x+.015, y-.01, z+.02], [x, y+.015, z+.02]]
    centroid = np.mean(np.asarray(vertices), axis=0)
    faces = []
    for raw in ([0, 1, 2], [0, 3, 1], [0, 2, 3], [1, 3, 2]):
        tri = np.asarray([vertices[index] for index in raw])
        if np.dot(np.cross(tri[1] - tri[0], tri[2] - tri[0]), tri[0] - centroid) < 0:
            raw = list(reversed(raw))
        faces.append(raw)
    value["meshes"][1].update(vertices=vertices, faces=faces, edges=None)
    return value


class SupportPlaneRequestTests(unittest.TestCase):
    def test_schema_required_intent_and_bounded_defaults(self):
        self.assertEqual(set(REQUEST_SCHEMA["required"]), set(request()))
        self.assertFalse(REQUEST_SCHEMA["additionalProperties"])
        self.assertIsInstance(CONTRACT_REVISION, str)
        normalized = validate_support_plane_request(request())
        self.assertEqual(normalized["max_step_translation_m"], .01)
        self.assertEqual(normalized["max_total_translation_m"], .04)
        self.assertNotIn("max_steps", normalized)
        self.assertNotIn("max_duration_s", normalized)
        for field in request():
            altered = request()
            altered.pop(field)
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_support_plane_request(altered)

    def test_direction_is_normalized_without_modifying_callers_request(self):
        supplied = request(direction_world=[3., 0., 4.])
        before = copy.deepcopy(supplied)
        result = validate_support_plane_request(supplied)
        self.assertEqual(supplied, before)
        self.assertEqual(result["direction_world"], [.6, 0., .8])
        result["direction_world"][0] = 42
        self.assertEqual(supplied, before)

    def test_direction_hypot_handles_large_finite_components(self):
        result = validate_support_plane_request(request(direction_world=[1e308, 0., 1e308]))
        self.assertAlmostEqual(math.hypot(*result["direction_world"]), 1., places=14)
        self.assertTrue(all(math.isfinite(c) for c in result["direction_world"]))

    def test_malformed_direction_rejects_boolean_strings_nonfinite_and_zero(self):
        values = ([0., 0., 0.], [True, 0., 1.], [0., False, 1.], [0., 0., "1"],
                  [0., 1.], [0., 0., 1., 0.], "0,0,1", [0., 0., float("inf")],
                  [0., float("nan"), 1.], [0., 0., 10 ** 1000])
        for direction in values:
            with self.subTest(direction=str(direction)[:60]), self.assertRaises(ValueError):
                validate_support_plane_request(request(direction_world=direction))

    def test_triangle_selector_is_a_strict_nonnegative_integer(self):
        for invalid in (True, False, -1, 2., "2", None):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_support_plane_request(request(reference_triangle_index=invalid))

    def test_targets_tolerance_and_motion_limits_reject_invalid_numbers(self):
        for field in ("target_clearance_m", "clearance_tolerance_m",
                      "max_step_translation_m", "max_total_translation_m"):
            for invalid in (True, False, "0.001", float("nan"), float("inf"), -1., 10 ** 1000):
                with self.subTest(field=field, invalid=type(invalid).__name__), self.assertRaises(ValueError):
                    validate_support_plane_request(request(**{field: invalid}))
        for field, maximum in (("max_step_translation_m", 1.), ("max_total_translation_m", 4.)):
            for invalid in (0., maximum + .01):
                with self.subTest(field=field, invalid=invalid), self.assertRaises(ValueError):
                    validate_support_plane_request(request(**{field: invalid}))

    def test_explicit_identities_and_extra_execution_fields_are_rejected(self):
        for changed in ({"focal_id": "base"}, {"focal_id": " "}, {"reference_id": "a"*257},
                        {"execute": True}, {"max_steps": 2}, {"max_duration_s": 3},
                        {"request_id": "not_execution_authority"}, {"axis": "+z"}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                validate_support_plane_request(request(**changed))

    def test_zero_target_and_zero_tolerance_remain_explicit(self):
        normalized = validate_support_plane_request(request(target_clearance_m=0., clearance_tolerance_m=0.))
        self.assertEqual(normalized["target_clearance_m"], 0.)
        self.assertEqual(normalized["clearance_tolerance_m"], 0.)


class SupportPlanePositiveTests(unittest.TestCase):
    def assert_no_authority(self, result):
        for field in ("execution_authority", "whole_scene_collision_certified",
                      "swept_path_certified", "task_success_certified", "ground_truth_independent"):
            self.assertIs(result[field], False, field)
        self.assertIs(result["requires_fresh_execution_gate"], True)

    def test_flat_pair_produces_exact_independent_displacement(self):
        scene = flat_scene()
        result = solve_support_plane_candidate(scene, request())
        self.assertEqual(result["status"], "candidate", result)
        current = normal_gap(scene)
        self.assertAlmostEqual(result["current_clearance_m"], current, places=14)
        self.assertAlmostEqual(result["candidate"]["translation"][2], .001-current, places=14)
        self.assertEqual(result["candidate"]["translation"][:2], [0., 0.])
        self.assertEqual(result["candidate"]["rotation_euler_deg"], [0., 0., 0.])
        self.assert_no_authority(result)

    def test_one_degree_tilt_uses_lowest_actual_surface_feature(self):
        scene = tilted_scene()
        result = solve_support_plane_candidate(scene, request())
        self.assertEqual(result["status"], "candidate", result)
        expected = normal_gap(scene)
        self.assertAlmostEqual(result["current_clearance_m"], expected, places=14)
        self.assertNotAlmostEqual(expected, .004, places=5)
        self.assertAlmostEqual(result["candidate"]["translation"][2], .001-expected, places=14)
        changed = apply_translation(scene, result["candidate"]["translation"])
        self.assertAlmostEqual(normal_gap(changed), .001, places=14)

    def test_sloped_wedge_uses_normal_distance_not_vertical_difference(self):
        scene = slope_scene()
        result = solve_support_plane_candidate(scene, request(max_step_translation_m=.1,
                                                            max_total_translation_m=.2))
        self.assertEqual(result["status"], "candidate", result)
        expected = normal_gap(scene, (-.5, 0., 1.))
        self.assertAlmostEqual(expected, .015/math.sqrt(1.25), places=14)
        self.assertAlmostEqual(result["current_clearance_m"], expected, places=14)
        self.assertNotAlmostEqual(result["current_clearance_m"], .015, places=5)
        expected_dz = (.001-expected)*math.sqrt(1.25)
        self.assertAlmostEqual(result["candidate"]["translation"][2], expected_dz, places=14)
        changed = apply_translation(scene, result["candidate"]["translation"])
        self.assertAlmostEqual(normal_gap(changed, (-.5, 0., 1.)), .001, places=14)

    def test_arbitrary_world_direction_has_expected_tangent_and_normal_motion(self):
        result = solve_support_plane_candidate(flat_scene(), request(direction_world=[1., 0., 2.]))
        self.assertEqual(result["status"], "candidate", result)
        expected_z = .001-normal_gap(flat_scene())
        translation = result["candidate"]["translation"]
        self.assertAlmostEqual(translation[0], expected_z/2, places=14)
        self.assertEqual(translation[1], 0.)
        self.assertAlmostEqual(translation[2], expected_z, places=14)

    def test_scaling_direction_preserves_physical_candidate(self):
        outputs = [solve_support_plane_candidate(flat_scene(), request(direction_world=d))
                   for d in ([1., 0., 2.], [3., 0., 6.], [-1., 0., -2.])]
        for result in outputs:
            self.assertEqual(result["status"], "candidate", result)
            for actual, expected in zip(result["candidate"]["translation"], outputs[0]["candidate"]["translation"]):
                self.assertAlmostEqual(actual, expected, places=14)

    def test_step_and_total_clip_euclidean_motion_not_axis_components(self):
        for step, total, expected in ((.001, .04, .001), (.01, .0005, .0005)):
            result = solve_support_plane_candidate(flat_scene(), request(direction_world=[1., 0., 2.],
                        max_step_translation_m=step, max_total_translation_m=total))
            self.assertEqual(result["status"], "candidate", result)
            self.assertTrue(result["step_clipped"])
            self.assertAlmostEqual(math.hypot(*result["candidate"]["translation"]), expected, places=14)
            changed = apply_translation(flat_scene(), result["candidate"]["translation"])
            actual_motion = max(math.hypot(*(new[k]-old[k] for k in range(3)))
                                for old, new in zip(flat_scene()["meshes"][1]["vertices"],
                                                    changed["meshes"][1]["vertices"]))
            self.assertLessEqual(actual_motion, expected)
            self.assertLess(abs(normal_gap(changed)-.001), abs(normal_gap(flat_scene())-.001))

    def test_increasing_gap_and_already_satisfied_zero_motion(self):
        current = normal_gap(flat_scene())
        away = solve_support_plane_candidate(flat_scene(), request(target_clearance_m=.01))
        self.assertEqual(away["status"], "candidate", away)
        self.assertAlmostEqual(away["candidate"]["translation"][2], .01-current, places=14)
        satisfied = solve_support_plane_candidate(flat_scene(), request(target_clearance_m=current,
                                                                       clearance_tolerance_m=0.))
        self.assertEqual(satisfied["status"], "goal_satisfied", satisfied)
        self.assertTrue(satisfied["goal_satisfied"])
        self.assertIsNone(satisfied["candidate"])
        self.assert_no_authority(satisfied)

    def test_exact_triangle_boundary_witness_is_valid(self):
        scene = tetra_scene((.1, .1, .104))
        result = solve_support_plane_candidate(scene, request())
        self.assertEqual(result["status"], "candidate", result)
        self.assertAlmostEqual(result["current_clearance_m"], .004, places=14)

    def test_candidate_does_not_modify_or_retain_input_aliases(self):
        scene, supplied = flat_scene(), request()
        before = copy.deepcopy((scene, supplied))
        result = solve_support_plane_candidate(scene, supplied)
        self.assertEqual(result["status"], "candidate", result)
        self.assertEqual((scene, supplied), before)
        result["request"]["direction_world"][0] = 100
        result["candidate"]["translation"][0] = 100
        self.assertEqual((scene, supplied), before)

    def test_scene_identity_and_binding_are_present_without_authority(self):
        result = solve_support_plane_candidate(flat_scene(), request())
        self.assertEqual(result["scene_revision"], "support-plane-fixture-v1")
        self.assertEqual(result["scene_source"], "independent_plane_fixture")
        self.assertEqual(result["focal_id"], "part")
        self.assertEqual(result["reference_id"], "base")
        self.assertEqual(len(result["scene_fingerprint"]), 64)
        self.assertEqual(len(result["feature_signature"]), 64)
        self.assert_no_authority(result)

    def test_feature_binding_survives_supported_axial_translation(self):
        first = solve_support_plane_candidate(flat_scene(), request(max_step_translation_m=.001))
        self.assertEqual(first["status"], "candidate", first)
        changed = apply_translation(flat_scene(), first["candidate"]["translation"])
        second = solve_support_plane_candidate(changed, request(),
                    expected_feature_signature=first["feature_signature"])
        self.assertIn(second["status"], ("candidate", "goal_satisfied"), second)
        self.assertEqual(second["feature_signature"], first["feature_signature"])


class SupportPlaneBoundaryTests(unittest.TestCase):
    def assert_no_candidate(self, result):
        self.assertIsNone(result["candidate"], result)
        self.assertNotEqual(result["status"], "candidate", result)
        self.assertFalse(result["execution_authority"])
        self.assertFalse(result["goal_satisfied"])

    def test_outside_selected_finite_triangle_does_not_switch_to_other_triangle(self):
        scene = tetra_scene((-.08, .08, .104))
        self.assertAlmostEqual(normal_gap(scene), .004, places=14)
        result = solve_support_plane_candidate(scene, request())
        self.assert_no_candidate(result)
        self.assertIn(result["status"], ("unsupported", "unknown"))

    def test_far_tangent_pair_has_no_support_plane_witness(self):
        scene = apply_translation(flat_scene(), [.4, 0., 0.])
        result = solve_support_plane_candidate(scene, request())
        self.assert_no_candidate(result)

    def test_candidate_leaving_finite_face_is_refused(self):
        result = solve_support_plane_candidate(flat_scene(), request(direction_world=[1., 0., .01],
            max_step_translation_m=1., max_total_translation_m=1.))
        self.assert_no_candidate(result)

    def test_open_duplicate_reversed_and_degenerate_meshes_are_unsupported(self):
        for role in (0, 1):
            for kind in ("open", "duplicate", "reverse", "degenerate"):
                scene = flat_scene()
                mesh = scene["meshes"][role]
                if kind == "open":
                    mesh["faces"].pop()
                elif kind == "duplicate":
                    mesh["faces"][0] = list(mesh["faces"][1])
                elif kind == "reverse":
                    mesh["faces"] = [list(reversed(face)) for face in mesh["faces"]]
                else:
                    mesh["vertices"][1] = list(mesh["vertices"][0])
                with self.subTest(role=role, kind=kind):
                    self.assert_no_candidate(solve_support_plane_candidate(scene, request()))

    def test_closed_concave_ring_is_outside_first_convex_domain(self):
        scene = flat_scene()
        concave = ring().to_dict()
        concave.update(object_id="base", mark_label="#base", name="base")
        scene["meshes"][0] = concave
        result = solve_support_plane_candidate(scene, request(reference_triangle_index=0))
        self.assert_no_candidate(result)

    def test_wrong_face_initial_contact_and_penetration_do_not_get_candidates(self):
        cases = [(flat_scene(), request(reference_triangle_index=0)),
                 (flat_scene(gap=-.001), request()), (flat_scene(gap=0.), request())]
        for scene, supplied in cases:
            with self.subTest(gap=normal_gap(scene)):
                self.assert_no_candidate(solve_support_plane_candidate(scene, supplied))

    def test_parallel_and_unresolvable_near_parallel_directions_are_refused(self):
        for direction in ([1., 0., 0.], [1., 0., 1e-300]):
            with self.subTest(direction=direction):
                self.assert_no_candidate(solve_support_plane_candidate(flat_scene(),
                    request(direction_world=direction)))

    def test_unrepresentable_clipped_step_has_no_false_progress(self):
        result = solve_support_plane_candidate(flat_scene(), request(max_step_translation_m=1e-300))
        self.assert_no_candidate(result)
        self.assertIn(result["status"], ("precision_floor", "unknown", "unsupported"))

    def test_stale_feature_signature_refuses_candidate(self):
        result = solve_support_plane_candidate(flat_scene(), request(), expected_feature_signature="0"*64)
        self.assert_no_candidate(result)
        self.assertEqual(result["status"], "feature_changed", result)

    def test_invalid_feature_signature_and_missing_pair_are_input_errors(self):
        for invalid in (True, "short", "Z"*64):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                solve_support_plane_candidate(flat_scene(), request(), expected_feature_signature=invalid)
        with self.assertRaises(ValueError):
            solve_support_plane_candidate(flat_scene(), request(focal_id="absent"))
        with self.assertRaises(ValueError):
            solve_support_plane_candidate(flat_scene(), request(reference_triangle_index=1000))

    def test_scene_unit_or_coordinate_frame_is_not_silently_converted(self):
        for changes in ({"unit": "mm"}, {"coordinate_frame": "local"}):
            scene = flat_scene()
            scene.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                solve_support_plane_candidate(scene, request())

    def test_untrusted_frame_or_explicit_host_restriction_never_creates_candidate(self):
        scene = flat_scene()
        scene["meshes"][1]["axes_source"] = "inferred"
        self.assert_no_candidate(solve_support_plane_candidate(scene, request()))
        scene = flat_scene()
        scene["host_execution"] = {"schema_version": "1.0", "operation": "rigid_transform",
            "supported": False, "scope": "independent_static_rigid_meshes",
            "reasons": [{"object_id": "part", "object_name": "part", "reason": "modifiers_present"}]}
        self.assert_no_candidate(solve_support_plane_candidate(scene, request()))

    def test_zero_target_is_valid_input_but_outside_first_positive_gap_solver(self):
        result = solve_support_plane_candidate(flat_scene(), request(target_clearance_m=0.))
        self.assert_no_candidate(result)
        self.assertEqual(result["status"], "unsupported", result)
        self.assertEqual(result["reason_codes"], ["positive_target_clearance_required"])

    def test_boolean_and_string_vertex_coordinates_are_not_coerced(self):
        for invalid in (True, False, "0.05"):
            scene = flat_scene()
            scene["meshes"][1]["vertices"][0][0] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                solve_support_plane_candidate(scene, request())

    def test_pair_work_limit_refuses_before_exact_predicates_and_kernel(self):
        scene = flat_scene()
        scene["meshes"][1]["vertices"].extend([[0., 0., .2]]*57)
        with patch("human_eye_plugin.support_plane_candidate.measure_pair_geometry") as kernel, \
                patch("human_eye_plugin.support_plane_candidate._validated_scene") as conversion:
            result = solve_support_plane_candidate(scene, request())
        self.assert_no_candidate(result)
        self.assertEqual(result["status"], "unknown", result)
        self.assertIn("resource_limit", result["reason_codes"][0])
        kernel.assert_not_called()
        conversion.assert_not_called()

    def test_whole_input_resource_limit_precedes_conversion(self):
        scene = flat_scene()
        obstacle = host_frame(box("obstacle", [0., 0., -.3], [.1, .1, .1]))
        obstacle["vertices"].extend([[0., 0., -.3]]*2040)
        scene["meshes"].append(obstacle)
        with patch("human_eye_plugin.support_plane_candidate._validated_scene") as conversion:
            result = solve_support_plane_candidate(scene, request())
        self.assert_no_candidate(result)
        self.assertEqual(result["status"], "unknown", result)
        self.assertIn("resource_limit", result["reason_codes"][0])
        conversion.assert_not_called()

    def test_geometry_kernel_budget_refusal_remains_unknown(self):
        with patch("human_eye_plugin.support_plane_candidate.work_budget_status", return_value={"within_budget": False}), \
                patch("human_eye_plugin.support_plane_candidate.measure_pair_geometry") as kernel:
            result = solve_support_plane_candidate(flat_scene(), request())
        self.assert_no_candidate(result)
        self.assertEqual(result["status"], "unknown", result)
        kernel.assert_not_called()

    def test_rational_bit_resource_limit_does_not_enter_strict_kernel(self):
        scene = flat_scene()
        scene["meshes"][1]["vertices"][0][0] = 1e-300
        with patch("human_eye_plugin.support_plane_candidate.measure_pair_geometry") as kernel:
            result = solve_support_plane_candidate(scene, request())
        self.assert_no_candidate(result)
        self.assertIn("resource_limit", result["reason_codes"][0])
        kernel.assert_not_called()

    def test_unknown_or_invalid_current_strict_distance_never_satisfies_goal(self):
        cases = [{"measurement_valid": False, "reason": "unsupported_solid_geometry"},
                 {"measurement_valid": True, "is_penetrating": False, "signed_clearance_m": float("nan")},
                 {"measurement_valid": True, "is_penetrating": False, "signed_clearance_m": True},
                 {"measurement_valid": True, "is_penetrating": True, "signed_clearance_m": -.001}]
        for fake in cases:
            with self.subTest(fake=fake), patch("human_eye_plugin.support_plane_candidate.measure_pair_geometry", return_value=fake):
                result = solve_support_plane_candidate(flat_scene(), request(clearance_tolerance_m=1.))
            self.assert_no_candidate(result)
            self.assertEqual(result["status"], "unknown", result)

    def test_generous_goal_tolerance_cannot_hide_current_metric_disagreement(self):
        fake = {"measurement_valid": True, "is_penetrating": False, "signed_clearance_m": .1}
        with patch("human_eye_plugin.support_plane_candidate.measure_pair_geometry", return_value=fake):
            result = solve_support_plane_candidate(flat_scene(), request(clearance_tolerance_m=1.))
        self.assert_no_candidate(result)
        self.assertEqual(result["status"], "unknown", result)
        self.assertIn("disagrees", result["reason_codes"][0])

    def test_large_world_origin_cannot_launder_metric_disagreement(self):
        scene = flat_scene()
        for mesh in scene["meshes"]:
            for vertex in mesh["vertices"]:
                vertex[0] += 1e12
            mesh["pivot_world"][0] += 1e12
        fake = {"measurement_valid": True, "is_penetrating": False, "signed_clearance_m": .0041}
        with patch("human_eye_plugin.support_plane_candidate.measure_pair_geometry", return_value=fake):
            result = solve_support_plane_candidate(scene, request(clearance_tolerance_m=1.))
        self.assert_no_candidate(result)
        self.assertEqual(result["status"], "unknown", result)
        self.assertIn("disagrees", result["reason_codes"][0])

    def test_candidate_kernel_disagreement_or_unknown_cannot_publish_candidate(self):
        for fake in ({"measurement_valid": False},
                     {"measurement_valid": True, "is_penetrating": False, "signed_clearance_m": .01},
                     {"measurement_valid": True, "is_penetrating": True, "signed_clearance_m": -.001}):
            calls = []
            def differing_candidate(focal, reference, **kwargs):
                calls.append(1)
                return actual_pair_measurement(focal, reference, **kwargs) if len(calls)==1 else fake
            with self.subTest(fake=fake), patch("human_eye_plugin.support_plane_candidate.measure_pair_geometry", side_effect=differing_candidate):
                result = solve_support_plane_candidate(flat_scene(), request())
            self.assert_no_candidate(result)
            self.assertEqual(result["status"], "unknown", result)
            self.assertEqual(len(calls), 2)

    def test_known_current_and_candidate_kernel_exceptions_return_unknown(self):
        for position in (1, 2):
            for error_type in (ValueError, IndexError, TypeError, AttributeError,
                               FloatingPointError, OverflowError):
                calls = []
                def failing_kernel(focal, reference, **kwargs):
                    calls.append(1)
                    if len(calls)==position:
                        raise error_type("synthetic strict-kernel failure")
                    return actual_pair_measurement(focal, reference, **kwargs)
                with self.subTest(position=position, error=error_type.__name__), \
                        patch("human_eye_plugin.support_plane_candidate.measure_pair_geometry", side_effect=failing_kernel):
                    result = solve_support_plane_candidate(flat_scene(), request())
                self.assert_no_candidate(result)
                self.assertEqual(result["status"], "unknown", result)
                self.assertEqual(result["reason_codes"], ["strict_pair_measurement_failed"])
                self.assertEqual(len(calls), position)

    def test_additional_obstacle_is_not_misrepresented_as_whole_scene_certified(self):
        scene = flat_scene()
        scene["meshes"].append(host_frame(box("obstacle", [0., 0., .105], [.01, .01, .005])))
        result = solve_support_plane_candidate(scene, request())
        self.assertEqual(result["status"], "candidate", result)
        self.assertFalse(result["whole_scene_collision_certified"])
        self.assertFalse(result["execution_authority"])
        self.assertTrue(result["requires_fresh_execution_gate"])

    def test_reference_triangle_topology_change_stops_feature_binding(self):
        scene = flat_scene()
        first = solve_support_plane_candidate(scene, request())
        self.assertEqual(first["status"], "candidate", first)
        scene["meshes"][0]["faces"][2], scene["meshes"][0]["faces"][3] = \
            scene["meshes"][0]["faces"][3], scene["meshes"][0]["faces"][2]
        changed = solve_support_plane_candidate(scene, request(),
            expected_feature_signature=first["feature_signature"])
        self.assert_no_candidate(changed)
        self.assertEqual(changed["status"], "feature_changed", changed)

    def test_disconnected_closed_components_cannot_claim_single_convex_support(self):
        scene = flat_scene()
        left, right = box("left", [-.15, 0., 0.], [.1, .1, .2]), box("right", [.15, 0., 0.], [.1, .1, .2])
        scene["meshes"][0].update(vertices=left["vertices"]+right["vertices"],
            faces=left["faces"]+[[i+8 for i in face] for face in right["faces"]], edges=None)
        self.assert_no_candidate(solve_support_plane_candidate(scene, request()))


if __name__ == "__main__":
    unittest.main()
