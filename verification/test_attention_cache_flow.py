"""Real router/service observation caching never bypasses fresh execution gates."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin.auto_router import HumanEyeAutoRouter
from human_eye_plugin.geometry_safety import measure_pair_geometry
from human_eye_plugin.host_runtime import GuardedHostRuntime
from human_eye_plugin.live_service import LiveSpatialService
from verification.test_auto_router import action, box, observation, scene
from verification.test_live_service import SelfLockingHost


def facts(result):
    return json.loads(result["context_text"])


class AttentionCacheRouterFlowTests(unittest.TestCase):
    def setUp(self):
        self.router = HumanEyeAutoRouter(quad_size=64)

    def observe(self, **changes):
        return self.router.handle_event(observation(include_image=False, **changes))

    def test_changed_task_reuses_measurements_without_reusing_authority_token(self):
        first = self.observe(task_instruction="first")
        with patch("human_eye_plugin.auto_router.measure_pair_geometry", side_effect=AssertionError("duplicate work")):
            second = self.observe(task_instruction="second")
        self.assertEqual(second["route"], "engine", second)
        self.assertFalse(second["cache_hit"])
        self.assertNotEqual(first["observation_id"], second["observation_id"])
        self.assertEqual(facts(second)["measurement_cache"]["hits"], 1)
        self.assertEqual(facts(second)["measurement_cache"]["misses"], 0)
        self.assertEqual(facts(second)["attention"]["reason_codes"], ["image_not_requested"])

    def test_third_object_change_only_recomputes_affected_pair(self):
        value = scene()
        # Keep the third object inside the exact near-contact query. Far
        # objects now have conservative bounds, not cached exact distances.
        value["meshes"].append(box("third", [.28, 0, .35], [.2, .2, .2]))
        self.observe(scene=value)
        value["meshes"][2] = MeshEntity3D.from_dict(value["meshes"][2]).translated([.01, 0, 0]).to_dict()
        value["revision"] = "r2"
        with patch("human_eye_plugin.auto_router.measure_pair_geometry", wraps=measure_pair_geometry) as measured:
            result = self.observe(scene=value)
        self.assertEqual(result["route"], "engine", result)
        self.assertEqual(measured.call_count, 1)
        self.assertEqual(measured.call_args.args[1].object_id, "third")
        self.assertEqual(facts(result)["measurement_cache"]["hits"], 1)
        self.assertEqual(facts(result)["scene_memory"]["changes"]["transform"], ["third"])

    def test_same_revision_changed_geometry_cannot_reuse_measurement(self):
        self.observe()
        value = scene()
        value["meshes"][1] = MeshEntity3D.from_dict(value["meshes"][1]).translated([0, 0, .01]).to_dict()
        result = self.observe(scene=value)
        self.assertEqual(facts(result)["measurement_cache"]["misses"], 1)
        self.assertAlmostEqual(facts(result)["measurement"]["signed_clearance_m"], .11)

    def test_scene_source_and_axis_provenance_invalidate_measurements(self):
        self.observe()
        source = scene()
        source["source"] = "different-host-provenance"
        changed_source = self.observe(scene=source)
        self.assertEqual(facts(changed_source)["measurement_cache"]["misses"], 1)
        source["meshes"][1]["axes_reason"] = "new axis provenance reason"
        changed_axis = self.observe(scene=source)
        self.assertEqual(facts(changed_axis)["measurement_cache"]["misses"], 1)

    def test_history_survives_roundtrip_with_frame_bound(self):
        for i in range(20):
            self.observe(scene=scene(revision=str(i)), task_instruction=str(i))
        state = self.router.export_state()
        restored = HumanEyeAutoRouter(quad_size=64)
        restored.import_state(state)
        self.assertEqual(restored.scene_cache.stats()["frames"], 16)
        self.assertEqual(restored.scene_cache.snapshot(0)["revision"], "4")
        self.assertEqual(restored.scene_cache.snapshot()["revision"], "19")
        self.assertEqual(restored.scene_cache.stats()["measurement_entries"], 0)

    def test_candidate_gate_computes_even_after_successful_memo_hit(self):
        self.observe(task_instruction="first")
        warmed = self.observe(task_instruction="second")
        self.assertEqual(facts(warmed)["measurement_cache"]["hits"], 1)
        with patch("human_eye_plugin.auto_router.measure_pair_geometry", side_effect=RuntimeError("evaluator down")) as measured:
            checked = self.router.handle_event(action(warmed))
        self.assertEqual(measured.call_count, 1)
        self.assertEqual(checked["reason_codes"], ["engine_error"])
        self.assertFalse(checked["allow_action"])

    def test_pending_readback_cannot_use_warm_memo_to_hide_engine_failure(self):
        observed = self.observe()
        self.assertTrue(self.router.handle_event(action(observed))["allow_action"])
        with patch("human_eye_plugin.auto_router.measure_pair_geometry", side_effect=RuntimeError("evaluator down")):
            result = self.observe(task_instruction="measure while pending")
        self.assertEqual(result["reason_codes"], ["engine_error"])
        persisted = dict(self.router.export_state()["sessions"])["a"]
        self.assertIsNotNone(persisted["pending"])
        self.assertIsNone(persisted["observation"])

    def test_post_action_readback_skips_measurement_memo(self):
        observed = self.observe()
        self.assertTrue(self.router.handle_event(action(observed))["allow_action"])
        pending = dict(self.router.export_state()["sessions"])["a"]["pending"]
        actual = scene(revision="r2")
        actual["meshes"][1] = pending["candidate"]
        with patch.object(self.router.scene_cache, "pair_measurement", side_effect=AssertionError("memo used after action")), \
                patch("human_eye_plugin.auto_router.measure_pair_geometry", wraps=measure_pair_geometry) as measured:
            result = self.router.handle_event(observation(scene=actual, event="after_action", include_image=False))
        self.assertEqual(result["route"], "engine", result)
        self.assertGreaterEqual(measured.call_count, 2)
        self.assertEqual(facts(result)["measurement_cache"]["hits"], 0)

    def test_corrupt_optional_history_does_not_clear_pending(self):
        observed = self.observe()
        self.router.handle_event(action(observed))
        state = self.router.export_state()
        expected = copy.deepcopy(dict(state["sessions"])["a"]["pending"])
        state["scene_memory"] = {"schema_version": "bad", "forged_allow_action": True}
        restored = HumanEyeAutoRouter(quad_size=64)
        restored.import_state(state)
        self.assertEqual(restored.scene_cache.stats()["frames"], 0)
        self.assertEqual(dict(restored.export_state()["sessions"])["a"]["pending"], expected)
        result = restored.handle_event(action(observed))
        self.assertEqual(result["reason_codes"], ["action_pending_readback"])


class AttentionCacheServiceFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.path = self.base / "config.json"
        self.path.write_text(json.dumps({"schema_version": "1.0", "enabled": True,
            "project_root": str(Path(__file__).resolve().parents[1]), "state_file": "state.json",
            "audit_file": "events.jsonl", "quad_size": 64}), encoding="utf-8")
        self.host = SelfLockingHost()
        self.service = LiveSpatialService(self.path, host=self.host)

    def observe(self, task, service=None):
        return (service or self.service).observe("s", task_instruction=task,
            focal_id="part", reference_id="base", include_image=False)

    def test_same_instance_reuses_computation_across_runtime_reloads(self):
        self.observe("first")
        with patch("human_eye_plugin.auto_router.measure_pair_geometry", side_effect=RuntimeError("evaluator down")):
            second = self.observe("second")
        self.assertEqual(second["status"], "observed", second)
        self.assertEqual(facts(second["routing"])["measurement_cache"]["hits"], 1)
        self.assertEqual(self.host.captures, 2)

    def test_fresh_instance_cannot_load_measurement_memo_from_disk(self):
        self.observe("first")
        other = LiveSpatialService(self.path, host=self.host)
        with patch("human_eye_plugin.auto_router.measure_pair_geometry", side_effect=RuntimeError("evaluator down")):
            second = self.observe("different task", service=other)
        self.assertEqual(second["status"], "blocked", second)
        self.assertEqual(second["routing"]["reason_codes"], ["engine_error"])

    def test_host_geometry_change_recomputed_and_old_gap_not_reused(self):
        self.observe("first")
        self.host.scene["meshes"][1] = MeshEntity3D.from_dict(self.host.scene["meshes"][1]).translated([0, 0, .02]).to_dict()
        result = self.observe("first")
        self.assertEqual(result["status"], "observed", result)
        self.assertAlmostEqual(facts(result["routing"])["measurement"]["signed_clearance_m"], .12)
        self.assertEqual(facts(result["routing"])["measurement_cache"]["misses"], 1)

    def test_corrupt_optional_history_does_not_clear_inflight_or_quarantine(self):
        self.observe("first")
        state_path = self.base / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["runtime"]["router"]["scene_memory"] = {"corrupt": True}
        state["inflight"] = {"operation_id": "uncertain-operation", "session_id": "s", "started": 1.0}
        state["runtime"]["quarantine"] = {"reason": "host_execution_uncertain", "last_checked_revision": "r1"}
        state_path.write_text(json.dumps(state), encoding="utf-8")
        result = self.observe("later")
        self.assertEqual(result["status"], "host_quarantined")
        persisted = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["inflight"], state["inflight"])
        self.assertEqual(persisted["runtime"]["quarantine"], state["runtime"]["quarantine"])
        self.assertEqual(self.host.captures, 1)

    def test_runtime_quarantine_survives_cache_discard(self):
        runtime = GuardedHostRuntime(self.host, quad_size=64)
        runtime.before_model(session_id="s", task_instruction="measure", focal_id="part", reference_id="base",
            messages=[], include_image=False)
        runtime._quarantine_host("manual-test-uncertainty", "r1")
        state = runtime.export_state()
        state["router"]["scene_memory"] = {"corrupt": True}
        restored = GuardedHostRuntime(self.host, quad_size=64)
        restored.import_state(state)
        self.assertTrue(restored.status["quarantined"])
        self.assertEqual(restored.router.scene_cache.stats()["frames"], 0)
        result = restored.execute_action(session_id="s", action={"translation": [0, 0, .1]})
        self.assertEqual(result["status"], "host_quarantined")
        self.assertEqual(self.host.calls, 0)


if __name__ == "__main__":
    unittest.main()
