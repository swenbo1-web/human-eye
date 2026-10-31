"""V1 capability preflight and live capture/verification integration contracts."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest

from human_eye_plugin.auto_router import _validated_scene
from human_eye_plugin.host_runtime import GuardedHostRuntime
from human_eye_plugin.live_service import LiveSpatialService
from verification.test_blender_host_contracts import host_fixture, BlenderHostError
from verification.test_host_runtime import MutableHost
from verification.test_live_service import SelfLockingHost


class ExecutionCapabilityTests(unittest.TestCase):
    def test_legacy_scene_shape_preserved_until_transport_requests_metadata(self):
        host, _, _, _ = host_fixture()
        legacy = host.capture_scene()
        self.assertNotIn("host_execution", legacy)
        host.execution_metadata = True
        current = host.capture_scene()
        self.assertTrue(current["host_execution"]["supported"])
        self.assertNotEqual(legacy["revision"], current["revision"])
        stripped = copy.deepcopy(current)
        stripped.pop("host_execution")
        stripped["revision"] = legacy["revision"]
        self.assertEqual(stripped, legacy)

    def test_every_execution_guard_is_disclosed_and_prevents_all_assignments(self):
        kinds = ("parent", "children", "constraints", "modifiers", "animation",
                 "data_animation", "rigid_body", "rigid_body_constraint", "shape_keys",
                 "linked", "mode", "locks", "nonuniform", "mirror", "shear")
        for kind in kinds:
            with self.subTest(kind=kind):
                host, focal, reference, _ = host_fixture()
                host.execution_metadata = True
                target = reference  # An unrelated mesh must also constrain the write.
                if kind == "parent": target.parent = focal
                elif kind == "children": target.children = [focal]
                elif kind in {"constraints", "modifiers"}:
                    setattr(target, kind, [NS(name="modifier", type="BEVEL")])
                elif kind == "animation": target.animation_data = NS()
                elif kind == "data_animation": target.data.animation_data = NS()
                elif kind in {"rigid_body", "rigid_body_constraint"}: setattr(target, kind, NS())
                elif kind == "shape_keys": target.data.shape_keys = NS()
                elif kind == "linked": target.library = NS(filepath="read_only_library.blend")
                elif kind == "mode": target.mode = "EDIT"
                elif kind == "locks": target.lock_location = (True, False, False)
                elif kind == "nonuniform": target._matrix_world[0][0] = 2
                elif kind == "mirror": target._matrix_world[0][0] = -1
                elif kind == "shear": target._matrix_world[0][1] = .2
                scene = host.capture_scene()
                capability = scene["host_execution"]
                self.assertFalse(capability["supported"])
                self.assertTrue(capability["reasons"])
                self.assertTrue(all(item["object_id"] == host.object_id(target) for item in capability["reasons"]))
                _validated_scene(scene)
                runtime = GuardedHostRuntime(host, quad_size=64)
                observed = runtime.before_model(session_id="s", task_instruction="Inspect.",
                    focal_id=host.object_id(focal), reference_id=host.object_id(reference), messages=[])
                facts = json.loads(observed["routing"]["context_text"])
                self.assertEqual(facts["host_execution"], capability)
                preview = runtime.preview_action(session_id="s", action={"translation": [0, 0, .01]})
                self.assertFalse(preview.get("allow_action"))
                result = runtime.execute_action(session_id="s", action={"translation": [0, 0, .01]})
                self.assertFalse(result["verified"])
                self.assertFalse(runtime.status["quarantined"])
                self.assertEqual(focal.assignments + reference.assignments, 0)
                with self.assertRaises(BlenderHostError):
                    host.apply_transform({"focal_id": host.object_id(focal), "translation": [0, 0, .01]},
                                         scene["revision"])
                self.assertEqual(focal.assignments + reference.assignments, 0)

    def test_capability_scene_fingerprint_matches_blender_write_boundary(self):
        host, focal, _, _ = host_fixture()
        host.execution_metadata = True
        scene = host.capture_scene()
        normalized, _, fingerprint = _validated_scene(scene)
        self.assertEqual(normalized, scene)
        result = host.apply_transform({"focal_id": host.object_id(focal), "translation": [0, 0, .01]},
                                      scene["revision"], fingerprint)
        self.assertTrue(result["receipt"]["host_execution_verified"])

    def test_result_exposes_execution_success_without_claiming_task_goal(self):
        host = MutableHost()
        runtime = GuardedHostRuntime(host, quad_size=64)
        runtime.before_model(session_id="s", task_instruction="Reach a chosen target.",
                             focal_id="part", reference_id="base", messages=[])
        result = runtime.execute_action(session_id="s", action={"translation": [0, 0, .05]})
        self.assertTrue(result["verified"])
        self.assertTrue(result["execution_verified"])
        self.assertEqual(result["goal_evaluation"], "not_requested")
        blocked = runtime.execute_action(session_id="missing", action={"translation": [0, 0, .05]})
        self.assertFalse(blocked["execution_verified"])
        self.assertEqual(blocked["goal_evaluation"], "not_requested")

    def make_service(self, directory, host):
        config = Path(directory) / "live.json"
        config.write_text(json.dumps({"schema_version": "1.0", "project_root": str(Path(__file__).resolve().parents[1]),
            "state_file": "state.json", "audit_file": "events.jsonl", "quad_size": 64}), encoding="utf-8")
        return LiveSpatialService(config, host=host)

    def test_live_observe_captures_once_but_transform_still_captures_fresh(self):
        with tempfile.TemporaryDirectory() as temp:
            host = SelfLockingHost()
            service = self.make_service(temp, host)
            observed = service.observe("s", focal_id="part", reference_id="base")
            self.assertEqual(observed["status"], "observed")
            self.assertEqual(host.captures, 1)
            before = host.captures
            result = service.transform("s", {"focal_id": "part", "reference_id": "base", "translation": [0, 0, .01]})
            self.assertTrue(result["execution_verified"])
            # Automatic preparation + execution recapture + independent readback.
            self.assertEqual(host.captures - before, 3)

    def test_live_unsupported_declaration_does_not_leave_inflight_or_quarantine(self):
        with tempfile.TemporaryDirectory() as temp:
            host = SelfLockingHost()
            host.scene["host_execution"] = {"schema_version": "1.0", "operation": "rigid_transform",
                "supported": False, "scope": "independent_static_rigid_meshes",
                "reasons": [{"object_id": "base", "object_name": "base", "reason": "modifiers_present"}]}
            service = self.make_service(temp, host)
            action = {"focal_id": "part", "reference_id": "base", "translation": [0, 0, .01]}
            preview = service.preview_action("s", action)
            self.assertFalse(preview["allow_action"])
            result = service.transform("s", action)
            self.assertEqual(result["status"], "blocked")
            self.assertFalse(result["execution_verified"])
            self.assertEqual(host.calls, 0)
            state = json.loads((Path(temp) / "state.json").read_text(encoding="utf-8"))
            self.assertIsNone(state["inflight"])
            self.assertFalse(service.status()["quarantined"])

    def test_execution_does_not_reuse_service_observation_if_host_changes(self):
        class MovingHost(SelfLockingHost):
            def capture_scene(self):
                if self.captures == 1:
                    self.scene["revision"] = "external_editor_changed_scene"
                return super().capture_scene()
        with tempfile.TemporaryDirectory() as temp:
            host = MovingHost()
            service = self.make_service(temp, host)
            result = service.transform("s", {"focal_id": "part", "reference_id": "base", "translation": [0, 0, .01]})
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["routing"]["reason_codes"], ["stale_or_missing_observation"])
            self.assertEqual(host.calls, 0)
            self.assertFalse(service.status()["quarantined"])


if __name__ == "__main__":
    unittest.main()
