"""Execution collision precision, full-feature clearance and bounded admission."""
import copy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from human_eye_module1_operators import MeshEntity3D, SE3AlignmentMath, SpatialAnomalySniffer
from human_eye_plugin.auto_router import HumanEyeAutoRouter, _validated_scene
from human_eye_plugin.geometry_safety import (
    COLLISION_TOLERANCE_M, measure_pair_geometry, work_budget_status,
)
from human_eye_plugin.host_runtime import GuardedHostRuntime
from verification.test_host_runtime import MutableHost, mesh


def prepare(runtime):
    return runtime.before_model(session_id="s", task_instruction="Measure clearance.",
                                focal_id="part", reference_id="base", messages=[])


def entity(item):
    return MeshEntity3D.from_dict(item)


class StrictCollisionTests(unittest.TestCase):
    def test_display_flush_tolerance_cannot_authorize_fifty_micrometre_penetration(self):
        host = MutableHost()
        candidate = entity(host.scene["meshes"][1]).translated([0, 0, -.10005])
        reference = entity(host.scene["meshes"][0])
        displayed = SpatialAnomalySniffer.probe_closest_clearance(candidate, reference)
        self.assertFalse(displayed.is_penetrating)
        self.assertEqual(displayed.signed_clearance_m, 0)
        strict = measure_pair_geometry(candidate, reference, need_clearance=True)
        self.assertTrue(strict["measurement_valid"])
        self.assertTrue(strict["is_penetrating"])
        self.assertAlmostEqual(strict["signed_clearance_m"], -5e-5, places=12)
        runtime = GuardedHostRuntime(host, quad_size=64)
        prepare(runtime)
        action = {"translation": [0, 0, -.10005]}
        self.assertFalse(runtime.preview_action(session_id="s", action=action)["allow_action"])
        blocked = runtime.execute_action(session_id="s", action=action)
        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["routing"]["reason_codes"], ["candidate_collision"])
        self.assertEqual(host.calls, 0)
        self.assertFalse(runtime.status["quarantined"])

    def test_unrounded_positive_fifty_micrometre_clearance(self):
        host = MutableHost()
        candidate = entity(host.scene["meshes"][1]).translated([0, 0, -.09995])
        measured = measure_pair_geometry(candidate, entity(host.scene["meshes"][0]), need_clearance=True)
        self.assertTrue(measured["measurement_valid"])
        self.assertFalse(measured["is_penetrating"])
        self.assertAlmostEqual(measured["signed_clearance_m"], 5e-5, places=12)
        self.assertFalse(measured["independent_ground_truth"])

    def test_exact_contact_and_separated_candidate_still_execute(self):
        for delta in (-.1, .05):
            with self.subTest(delta=delta):
                host = MutableHost()
                runtime = GuardedHostRuntime(host, quad_size=64)
                prepare(runtime)
                result = runtime.execute_action(session_id="s", action={"translation": [0, 0, delta]})
                self.assertTrue(result["verified"], result)
                self.assertEqual(result["routing"]["collision_tolerance_m"], COLLISION_TOLERANCE_M)

    def test_post_readback_rejects_submicrometre_collision_even_within_pose_tolerance(self):
        class DriftHost(MutableHost):
            def apply_transform(self, *args, **kwargs):
                result = super().apply_transform(*args, **kwargs)
                self.scene["meshes"][1] = entity(self.scene["meshes"][1]).translated([0, 0, -5e-7]).to_dict()
                return result
        host = DriftHost()
        runtime = GuardedHostRuntime(host, quad_size=64, readback_atol_m=1e-6)
        prepare(runtime)
        result = runtime.execute_action(session_id="s", action={"translation": [0, 0, -.1]})
        self.assertFalse(result["verified"])
        self.assertEqual(result["routing"]["reason_codes"], ["host_collision_detected"])
        self.assertTrue(runtime.status["quarantined"])

    def test_numerical_collision_tolerance_is_explicit_and_separate(self):
        host = MutableHost()
        candidate = entity(host.scene["meshes"][1]).translated([0, 0, -.1000000005])
        reference = entity(host.scene["meshes"][0])
        result = measure_pair_geometry(candidate, reference, need_clearance=True)
        self.assertFalse(result["is_penetrating"])
        self.assertLess(result["signed_clearance_m"], 0)
        self.assertAlmostEqual(result["collision_tolerance_m"], 1e-9)
        self.assertTrue(measure_pair_geometry(candidate, reference, collision_tolerance_m=0)["is_penetrating"])

    def test_raw_clearance_is_not_four_decimal_display_value(self):
        host = MutableHost()
        focal = entity(host.scene["meshes"][1]).translated([0, 0, .00001234567])
        result = measure_pair_geometry(focal, entity(host.scene["meshes"][0]), need_clearance=True)
        self.assertAlmostEqual(result["signed_clearance_m"], .10001234567, places=12)

    def test_rotated_box_clearance_uses_geometry(self):
        left = entity(mesh("left", [0, 0, 0], [1, 1, 1]))
        right = entity(mesh("right", [2, 0, 0], [1, 1, 1]))
        right = right.rotated_around_pivot(SE3AlignmentMath.euler_xyz_to_matrix(0, 0, 45))
        result = measure_pair_geometry(left, right, need_clearance=True)
        self.assertTrue(result["measurement_valid"])
        self.assertAlmostEqual(result["signed_clearance_m"], 1.5 - 2 ** -.5, places=12)

    def test_sparse_edge_hints_cannot_hide_skew_edge_clearance_or_reduce_budget(self):
        # Perpendicular 10 cm thick bars have an analytic 10 cm vertical gap.
        a = entity(mesh("a", [0, 0, 0], [2, .1, .1]))
        b = entity(mesh("b", [0, 0, 0], [2, .1, .1]))
        b = b.rotated_around_pivot(SE3AlignmentMath.euler_xyz_to_matrix(0, 0, 90)).translated([0, 0, .2])
        original = measure_pair_geometry(a, b, need_clearance=True)
        sparse = []
        for item in (a, b):
            serialized = item.to_dict()
            serialized["edges"] = [[0, 1]]
            sparse.append(entity(serialized))
        limited = measure_pair_geometry(*sparse, need_clearance=True)
        self.assertAlmostEqual(original["signed_clearance_m"], .1, places=12)
        self.assertAlmostEqual(limited["signed_clearance_m"], original["signed_clearance_m"], places=12)
        self.assertEqual(work_budget_status([a, b]), work_budget_status(sparse))

    def test_open_mesh_cannot_certify_collision_or_clearance(self):
        host = MutableHost()
        item = copy.deepcopy(host.scene["meshes"][1])
        item["faces"] = item["faces"][:-1]
        result = measure_pair_geometry(entity(item), entity(host.scene["meshes"][0]), need_clearance=True)
        self.assertFalse(result["measurement_valid"])
        self.assertIsNone(result["signed_clearance_m"])

    def test_bad_precision_options_do_not_silently_weaken_collision_gate(self):
        host = MutableHost()
        pair = [entity(item) for item in host.scene["meshes"]]
        for bad in (True, -.1, 1e-4, float("nan"), float("inf"), "0"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                measure_pair_geometry(*pair, collision_tolerance_m=bad)
        with self.assertRaises(ValueError):
            measure_pair_geometry(*pair, need_clearance=1)

    def test_numeric_kernel_failure_is_unknown_never_clear(self):
        host = MutableHost()
        pair = [entity(item) for item in host.scene["meshes"]]
        # Inject each actual numerical entry separately; a patch to only the
        # general evaluator cannot exercise the new single-component path.
        cases = (("_certified_solid_collision", False, 1e-9),
                 ("_certified_solid_collision", True, 0.0),
                 ("_single_convex_collision_and_zero", True, 1e-9))
        for entry, need_clearance, tolerance in cases:
            with self.subTest(entry=entry, need_clearance=need_clearance, tolerance=tolerance):
                with patch("human_eye_plugin.geometry_safety." + entry,
                           side_effect=FloatingPointError("numeric overflow")) as kernel:
                    result = measure_pair_geometry(*pair, need_clearance=need_clearance,
                                                   collision_tolerance_m=tolerance)
                kernel.assert_called_once()
                self.assertFalse(result["measurement_valid"])
                self.assertIsNone(result["is_penetrating"])
                self.assertIsNone(result["signed_clearance_m"])

    def test_resource_budget_blocks_before_any_solid_kernel(self):
        huge = SimpleNamespace(vertices=range(30_000), faces=range(60_000), edges=range(90_000))
        with patch("human_eye_plugin.geometry_safety._certified_solid_collision") as kernel:
            result = measure_pair_geometry(huge, huge, need_clearance=True)
        self.assertFalse(result["measurement_valid"])
        self.assertEqual(result["reason"], "geometry_resource_limit")
        self.assertGreaterEqual(result["work_budget"]["estimates"]["largest_float64_matrix_bytes"], 14_400_000_000)
        kernel.assert_not_called()

    def test_scene_work_budget_and_metadata_for_dictionary_or_entities(self):
        host = MutableHost()
        budget = work_budget_status(host.scene["meshes"])
        self.assertTrue(budget["within_budget"])
        self.assertEqual(budget, work_budget_status([entity(item) for item in host.scene["meshes"]]))
        many = [entity(mesh(str(i), [i, 0, 0], [1, 1, 1])) for i in range(60)]
        self.assertFalse(work_budget_status(many)["within_budget"])

    def test_router_resource_limit_precedes_probe_and_render(self):
        host = MutableHost()
        for item in host.scene["meshes"]:
            item["faces"] = (item["faces"] * 200)[:2000]
        with patch.object(SpatialAnomalySniffer, "probe_closest_clearance") as probe:
            result = HumanEyeAutoRouter(quad_size=64).handle_event({"event": "before_model",
                "session_id": "s", "scene": host.scene, "focal_id": "part", "reference_id": "base"})
        self.assertEqual(result["reason_codes"], ["geometry_resource_limit"])
        self.assertFalse(result["allow_action"])
        probe.assert_not_called()

    def test_optional_host_capability_is_fingerprinted_and_public(self):
        host = MutableHost()
        _, _, before = _validated_scene(host.scene)
        declaration = {"schema_version": "1.0", "operation": "rigid_transform", "supported": True,
                       "scope": "independent_static_rigid_meshes", "reasons": []}
        host.scene["host_execution"] = declaration
        normalized, _, after = _validated_scene(host.scene)
        self.assertNotEqual(before, after)
        self.assertEqual(normalized["host_execution"], declaration)
        prepared = prepare(GuardedHostRuntime(host, quad_size=64))
        self.assertEqual(json.loads(prepared["routing"]["context_text"])["host_execution"], declaration)

    def test_declared_host_rejection_prevents_preview_and_apply(self):
        host = MutableHost()
        host.scene["host_execution"] = {"schema_version": "1.0", "operation": "rigid_transform",
            "supported": False, "scope": "independent_static_rigid_meshes",
            "reasons": [{"object_id": "part", "object_name": "part", "reason": "parented_mesh"}]}
        runtime = GuardedHostRuntime(host, quad_size=64)
        prepare(runtime)
        result = runtime.execute_action(session_id="s", action={"translation": [0, 0, .1]})
        self.assertFalse(result["executed"])
        self.assertFalse(runtime.status["quarantined"])
        self.assertEqual(host.calls, 0)

    def test_invalid_or_inconsistent_host_capability_fails_scene_validation(self):
        original = MutableHost().scene
        declaration = {"schema_version": "1.0", "operation": "rigid_transform", "supported": True,
                       "scope": "independent_static_rigid_meshes", "reasons": []}
        for bad in (None, {}, {**declaration, "supported": "yes"},
                    {**declaration, "supported": False},
                    {**declaration, "reasons": [{"reason": "something"}]},
                    {**declaration, "scope": "all_edits"}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                _validated_scene({**original, "host_execution": bad})


if __name__ == "__main__":
    unittest.main()
