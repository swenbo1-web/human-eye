"""Independent final checks for image policy and execution authority separation."""
import copy
import unittest
from unittest.mock import patch

from human_eye_plugin.auto_router import HumanEyeAutoRouter, _validated_scene
from human_eye_plugin.host_runtime import GuardedHostRuntime
from verification.test_auto_router import observation, scene
from verification.test_host_runtime import MutableHost


class FinalBoundaryTests(unittest.TestCase):
    def test_raw_scene_counts_are_rejected_before_numpy_allocates_geometry(self):
        class OversizedList(list):
            def __init__(self, size):
                super().__init__()
                self.size = size
            def __len__(self):
                return self.size
            def __array__(self, *args, **kwargs):
                raise AssertionError("Oversized geometry reached NumPy allocation")
        for field, size in (("vertices", 500_001), ("faces", 1_000_001), ("edges", 37)):
            with self.subTest(field=field):
                actual = scene()
                actual["meshes"][0][field] = OversizedList(size)
                with self.assertRaises(ValueError):
                    _validated_scene(actual)

    def test_text_observation_is_sufficient_for_geometry_gate_and_keeps_post_text_only(self):
        host = MutableHost()
        runtime = GuardedHostRuntime(host, quad_size=64)
        with patch("human_eye_plugin.auto_router._render_scene_canvas_prepared") as renderer:
            observed = runtime.before_model(session_id="s", task_instruction="Measure.",
                focal_id="part", reference_id="base", messages=[], include_image=False,
                supports_images=False)
            self.assertIsNone(observed["routing"]["image"])
            result = runtime.execute_action(session_id="s", action={"translation": [0, 0, .01]})
        self.assertTrue(result["verified"])
        self.assertIsNone(result["routing"]["image"])
        renderer.assert_not_called()
        self.assertEqual(host.captures, 3)

    def test_image_mode_switch_invalidates_prior_token_without_changing_collision_policy(self):
        router = HumanEyeAutoRouter(quad_size=64)
        text = router.handle_event(observation(include_image=False))
        image = router.handle_event(observation(include_image=True))
        old_token = router.handle_event({**observation(), "event": "before_action",
            "observation_id": text["observation_id"], "action": {"translation": [0, 0, .01]}})
        self.assertFalse(old_token["allow_action"])
        self.assertEqual(old_token["reason_codes"], ["stale_or_missing_observation"])
        allowed = router.handle_event({**observation(), "event": "before_action",
            "observation_id": image["observation_id"], "action": {"translation": [0, 0, .01]}})
        self.assertTrue(allowed["allow_action"])
        self.assertEqual(allowed["collision_tolerance_m"], text["collision_tolerance_m"])
        self.assertEqual(allowed["collision_tolerance_m"], image["collision_tolerance_m"])

    def test_text_cache_persistence_cannot_skip_fresh_host_revision_check(self):
        host = MutableHost()
        runtime = GuardedHostRuntime(host, quad_size=64)
        runtime.before_model(session_id="s", task_instruction="Measure.", focal_id="part",
            reference_id="base", messages=[], include_image=False)
        restored = GuardedHostRuntime(host, quad_size=64)
        restored.import_state(runtime.export_state())
        host.scene["revision"] = "editor_changed_after_text_observation"
        result = restored.execute_action(session_id="s", action={"translation": [0, 0, .01]})
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["routing"]["reason_codes"], ["stale_or_missing_observation"])
        self.assertEqual(host.calls, 0)
        self.assertFalse(restored.status["quarantined"])

    def test_missing_image_does_not_weaken_strict_penetration_rejection(self):
        host = MutableHost()
        runtime = GuardedHostRuntime(host, quad_size=64)
        with patch("human_eye_plugin.auto_router._render_scene_canvas_prepared") as renderer:
            runtime.before_model(session_id="s", task_instruction="Measure.", focal_id="part",
                reference_id="base", messages=[], include_image=False)
            result = runtime.execute_action(session_id="s", action={"translation": [0, 0, -.10005]})
        renderer.assert_not_called()
        self.assertEqual(result["routing"]["reason_codes"], ["candidate_collision"])
        self.assertEqual(host.calls, 0)

    def test_text_observation_still_checks_full_scene_work_budget(self):
        actual = scene()
        extra = copy.deepcopy(actual["meshes"][0])
        extra["object_id"] = "heavy_third_mesh"
        extra["mark_label"] = "#heavy"
        extra["is_focal_target"] = False
        extra["faces"] = (extra["faces"] * 200)[:2000]
        actual["meshes"].append(extra)
        with patch("human_eye_plugin.auto_router.SpatialAnomalySniffer.probe_closest_clearance") as probe:
            result = HumanEyeAutoRouter(quad_size=64).handle_event(observation(scene=actual, include_image=False))
        self.assertEqual(result["reason_codes"], ["geometry_resource_limit"])
        self.assertFalse(result["allow_action"])
        probe.assert_not_called()


if __name__ == "__main__":
    unittest.main()
