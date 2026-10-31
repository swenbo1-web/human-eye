"""Hook wire formats, persistent receipts, and subprocess behavior."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from human_eye_plugin.agent_hooks import route_hook_event


ROOT = Path(__file__).resolve().parents[1]


class FakeRouter:
    """Isolate the hook transport contract from renderer computation."""
    calls: list[dict] = []

    def __init__(self, **kwargs):
        self.state = {"sessions": {}, "counter": 0}
        self.mode = kwargs.get("mode")

    def export_state(self):
        return copy.deepcopy(self.state)

    def import_state(self, state):
        self.state = copy.deepcopy(state)

    def handle_event(self, event):
        self.calls.append(copy.deepcopy(event))
        session = event["session_id"]
        previous = self.state["sessions"].get(session)
        if not event.get("scene") or self.mode == "off":
            return {"route": "native", "allow_action": None}
        if event["event"] == "before_action":
            valid = previous is not None and event.get("observation_id") == previous
            return {"route": "engine" if valid else "blocked", "allow_action": valid,
                    "context_text": "Current pose delta was checked." if valid else "A current observation is required.",
                    "requires_reobserve": not valid, "observation_id": previous if valid else None,
                    "scene_revision": event["scene"]["revision"], "image": {"data": "never-deliver-this-as-text"}}
        self.state["counter"] += 1
        observation = "observation-" + str(self.state["counter"])
        self.state["sessions"][session] = observation
        return {"route": "engine", "context_text": "Measured snapshot evidence.", "observation_id": observation,
                "scene_revision": event["scene"]["revision"], "allow_action": None,
                "image": {"data": "never-deliver-this-as-text"}}


class AgentHooksTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.config = {"scene_file": "scene.json", "state_file": "state.json", "mode": "auto",
                       "focal_id": "part", "reference_id": "fixture",
                       "spatial_tools": {"mcp__spatial_host__transform": {"action_path": "action"}}}
        self.scene = {"revision": "1", "unit": "m", "coordinate_frame": "world", "meshes": []}
        self.write_scene()
        self.config_path = self.base / "config.json"
        self.config_path.write_text(json.dumps(self.config), encoding="utf-8")
        FakeRouter.calls.clear()

    def write_scene(self):
        (self.base / "scene.json").write_text(json.dumps(self.scene), encoding="utf-8")

    def event(self, name="UserPromptSubmit", session="s1", **kwargs):
        event = {"hook_event_name": name, "session_id": session, "prompt": "Check the assembly.",
                 "tool_name": "mcp__spatial_host__transform", "tool_use_id": "call-1",
                 "tool_input": {"action": {"translation": [0.1, 0, 0]}}}
        event.update(kwargs)
        return event

    def route(self, event, agent="codex", config=None):
        return route_hook_event(event, config or self.config, agent=agent, config_dir=self.base, router_factory=FakeRouter)

    def state(self):
        return json.loads((self.base / "state.json").read_text(encoding="utf-8"))

    def test_unlisted_tool_is_native_without_reading_scene_or_state(self):
        (self.base / "scene.json").write_text("broken", encoding="utf-8")
        result = self.route(self.event("PreToolUse", tool_name="Bash", tool_input={"command": "blender arbitrary script"}))
        self.assertEqual(result, {})
        self.assertEqual(FakeRouter.calls, [])
        self.assertFalse((self.base / "state.json").exists())

    def test_unsupported_event_is_native(self):
        self.assertEqual(self.route(self.event("PermissionRequest")), {})

    def test_prompt_delivers_text_with_explicit_no_image_disclosure_for_both_hosts(self):
        for agent in ("codex", "claude"):
            with self.subTest(agent=agent):
                result = self.route(self.event(), agent)
                output = result["hookSpecificOutput"]
                self.assertEqual(output["hookEventName"], "UserPromptSubmit")
                self.assertIn("text only", output["additionalContext"])
                self.assertNotIn("never-deliver-this-as-text", json.dumps(result))
                self.assertNotIn("permissionDecision", output)
        self.assertEqual(set(self.state()["sessions"]), {"codex:s1", "claude:s1"})

    def test_persistent_observation_is_used_in_later_process_equivalent_instance(self):
        self.route(self.event())
        result = self.route(self.event("PreToolUse"))
        self.assertNotIn("permissionDecision", result["hookSpecificOutput"])
        called = FakeRouter.calls[-1]
        self.assertEqual(called["event"], "before_action")
        self.assertEqual(called["observation_id"], "observation-1")
        self.assertEqual(called["action"], {"translation": [0.1, 0, 0], "rotation_euler_deg": [0.0, 0.0, 0.0], "focal_id": "part", "reference_id": "fixture"})
        self.assertEqual(self.state()["sessions"]["codex:s1"]["pending"]["tool_use_id"], "call-1")

    def test_no_observation_registered_action_is_denied(self):
        result = self.route(self.event("PreToolUse"))
        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_session_and_host_observations_do_not_cross(self):
        self.route(self.event())
        for session, agent in (("s2", "codex"), ("s1", "claude")):
            result = self.route(self.event("PreToolUse", session=session), agent)
            self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_pending_action_serializes_sessions_using_one_connector(self):
        self.route(self.event())
        self.route(self.event(session="s2"))
        self.route(self.event("PreToolUse"))
        result = self.route(self.event("PreToolUse", session="s2", tool_use_id="call-2"))
        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("awaiting host scene readback", result["hookSpecificOutput"]["additionalContext"])

    def test_unchanged_post_snapshot_requires_reobserve_and_clears_receipt(self):
        self.route(self.event())
        self.route(self.event("PreToolUse"))
        calls_before = len(FakeRouter.calls)
        result = self.route(self.event("PostToolUse"))
        self.assertIn("not certified", result["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(len(FakeRouter.calls), calls_before)
        self.assertNotIn("observation_id", self.state()["sessions"]["codex:s1"])
        self.assertNotIn("pending", self.state()["sessions"]["codex:s1"])
        self.assertEqual(self.route(self.event("PreToolUse"))["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_new_revision_post_reobserves_without_replaying_action(self):
        self.route(self.event())
        self.route(self.event("PreToolUse"))
        self.scene["revision"] = "2"
        self.write_scene()
        result = self.route(self.event("PostToolUse"))
        self.assertEqual(result["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        self.assertEqual(FakeRouter.calls[-1]["event"], "after_action")
        self.assertNotIn("action", FakeRouter.calls[-1])
        self.assertNotIn("pending", self.state()["sessions"]["codex:s1"])

    def test_unmatched_post_does_not_erase_pending_action(self):
        self.route(self.event())
        self.route(self.event("PreToolUse"))
        self.route(self.event("PostToolUse", tool_use_id="another-call"))
        self.assertEqual(self.state()["sessions"]["codex:s1"]["pending"]["tool_use_id"], "call-1")

    def test_failed_post_never_certifies_new_scene(self):
        self.route(self.event())
        self.route(self.event("PreToolUse"))
        self.scene["revision"] = "2"
        self.write_scene()
        result = self.route(self.event("PostToolUseFailure"))
        self.assertIn("not certified", result["hookSpecificOutput"]["additionalContext"])
        self.assertNotIn("observation_id", self.state()["sessions"]["codex:s1"])

    def test_malformed_registered_actions_fail_closed(self):
        for action in ({}, {"translation": [1, 2]}, {"translation": [True, 0, 0]}, {"translation": "x"}, {"rotation_euler_deg": [0, float("inf"), 0]}, {"translation": [0, 0, 0], "scale": [2, 2, 2]}):
            with self.subTest(action=action):
                result = self.route(self.event("PreToolUse", tool_input={"action": action}))
                self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_missing_tool_call_id_is_denied_before_router_mutation(self):
        self.route(self.event())
        calls = len(FakeRouter.calls)
        result = self.route(self.event("PreToolUse", tool_use_id=None))
        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(len(FakeRouter.calls), calls)

    def test_effective_action_ids_are_used_for_pre_and_post_checks(self):
        self.route(self.event())
        self.route(self.event("PreToolUse", tool_input={"action": {"translation": [0, 0, 0], "focal_id": "other-part", "reference_id": "other-fixture"}}))
        self.assertEqual(FakeRouter.calls[-1]["focal_id"], "other-part")
        self.scene["revision"] = "2"
        self.write_scene()
        self.route(self.event("PostToolUse"))
        self.assertEqual(FakeRouter.calls[-1]["focal_id"], "other-part")
        self.assertEqual(FakeRouter.calls[-1]["reference_id"], "other-fixture")

    def test_corrupt_state_blocks_only_registered_actions(self):
        (self.base / "state.json").write_text("invalid", encoding="utf-8")
        self.assertEqual(self.route(self.event("PreToolUse"))["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(self.route(self.event("PreToolUse", tool_name="Read")), {})

    def test_model_cannot_choose_scene_or_state_paths(self):
        self.route(self.event(scene_file="other.json", state_file="other-state.json"))
        self.assertTrue((self.base / "state.json").exists())
        self.assertFalse((self.base / "other-state.json").exists())

    def test_shared_scene_and_state_path_is_rejected(self):
        config = dict(self.config, state_file="scene.json")
        self.assertEqual(self.route(self.event("PreToolUse"), config=config)["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(json.loads((self.base / "scene.json").read_text())["revision"], "1")

    def test_pending_action_metadata_survives_bounded_session_eviction(self):
        self.route(self.event())
        self.route(self.event("PreToolUse"))
        for index in range(35):
            self.route(self.event(session="new-" + str(index)))
        sessions = self.state()["sessions"]
        self.assertLessEqual(len(sessions), 32)
        self.assertIn("pending", sessions["codex:s1"])

    def test_session_metadata_is_bounded_without_pending_action(self):
        for index in range(35):
            self.route(self.event(session="new-" + str(index)))
        self.assertEqual(len(self.state()["sessions"]), 32)

    def test_unverified_post_quarantines_other_sessions_until_fresh_observation(self):
        self.route(self.event())
        self.route(self.event(session="s2"))
        self.route(self.event("PreToolUse"))
        self.route(self.event("PostToolUse"))
        self.assertIn("quarantine", self.state())
        result = self.route(self.event("PreToolUse", session="s2"))
        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        unchanged = self.route(self.event(session="s2"))
        self.assertIn("no current observation", unchanged["hookSpecificOutput"]["additionalContext"])
        self.scene["revision"] = "2"
        self.write_scene()
        # A new file alone cannot authorize a stale session observation.
        self.assertEqual(self.route(self.event("PreToolUse", session="s2"))["hookSpecificOutput"]["permissionDecision"], "deny")
        self.route(self.event(session="s2"))
        self.assertNotIn("quarantine", self.state())
        approved = self.route(self.event("PreToolUse", session="s2", tool_use_id="call-2"))
        self.assertNotIn("permissionDecision", approved["hookSpecificOutput"])

    def test_missing_snapshot_cannot_reuse_cached_scene(self):
        self.route(self.event())
        (self.base / "scene.json").unlink()
        calls = len(FakeRouter.calls)
        self.route(self.event())
        self.assertEqual(len(FakeRouter.calls), calls)
        self.assertIn("quarantine", self.state())
        self.assertNotIn("observation_id", self.state()["sessions"]["codex:s1"])
        self.assertEqual(self.route(self.event("PreToolUse"))["hookSpecificOutput"]["permissionDecision"], "deny")
        self.write_scene()
        same = self.route(self.event())
        self.assertIn("no current observation", same["hookSpecificOutput"]["additionalContext"])

    def test_wrong_post_receipt_recovers_only_after_new_revision_observation(self):
        self.route(self.event())
        self.route(self.event("PreToolUse"))
        self.route(self.event("PostToolUse", tool_use_id="wrong"))
        self.scene["revision"] = "2"
        self.write_scene()
        self.route(self.event())
        state = self.state()
        self.assertNotIn("quarantine", state)
        self.assertNotIn("pending", state["sessions"]["codex:s1"])
        self.assertNotIn("permissionDecision", self.route(self.event("PreToolUse", tool_use_id="recovered"))["hookSpecificOutput"])

    def test_unverified_engine_observation_does_not_clear_connector_quarantine(self):
        class UnverifiedRouter(FakeRouter):
            def handle_event(self, event):
                return dict(super().handle_event(event), requires_reobserve=True, measurement_valid=False)

        self.route(self.event())
        self.route(self.event("PreToolUse"))
        self.route(self.event("PostToolUse"))
        self.scene["revision"] = "2"
        self.write_scene()
        result = route_hook_event(self.event(), self.config, agent="codex", config_dir=self.base, router_factory=UnverifiedRouter)
        self.assertIn("hookSpecificOutput", result)
        state = self.state()
        self.assertIn("quarantine", state)
        self.assertNotIn("observation_id", state["sessions"]["codex:s1"])
        denied = self.route(self.event("PreToolUse"))
        self.assertEqual(denied["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_cli_missing_config_still_denies_explicitly_declared_tool(self):
        command = [sys.executable, "-m", "human_eye_plugin.agent_hooks", "--agent", "codex", "--config", str(self.base / "missing.json"), "--spatial-tool", "mcp__spatial_host__transform"]
        for tool, deny in (("mcp__spatial_host__transform", True), ("Bash", False)):
            result = subprocess.run(command, input=json.dumps(self.event("PreToolUse", tool_name=tool)), cwd=ROOT, text=True, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            output = json.loads(result.stdout)
            self.assertEqual(output.get("hookSpecificOutput", {}).get("permissionDecision") == "deny", deny)
            self.assertEqual(result.stderr, "")

    def test_real_router_cli_persists_observation_and_validates_host_readback(self):
        # Closed, explicitly framed meshes exercise the actual engine, while
        # the temporary snapshot is our local stand-in for a host connector.
        from verification.test_certification_contracts import contact_pair
        focal, reference = contact_pair()
        self.scene["meshes"] = [focal.to_dict(), reference.to_dict()]
        self.write_scene()
        self.config.update(focal_id="#B", reference_id="#A", quad_size=64)
        self.config_path.write_text(json.dumps(self.config), encoding="utf-8")
        command = [sys.executable, "-m", "human_eye_plugin.agent_hooks", "--agent", "codex", "--config", str(self.config_path), "--spatial-tool", "mcp__spatial_host__transform"]

        def invoke(event):
            process = subprocess.run(command, input=json.dumps(event), cwd=ROOT, text=True, capture_output=True, timeout=30)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(process.stderr, "")
            return json.loads(process.stdout)

        observed = invoke(self.event())
        self.assertIn("text only", observed["hookSpecificOutput"]["additionalContext"])
        first_observation = self.state()["sessions"]["codex:s1"]["observation_id"]
        action_event = self.event("PreToolUse", tool_input={"action": {"translation": [0.0, 0.0, 0.01]}})
        approved = invoke(action_event)
        self.assertNotIn("permissionDecision", approved["hookSpecificOutput"])
        self.assertIn("terminal_geometry_only", approved["hookSpecificOutput"]["additionalContext"])
        self.scene["meshes"][0] = focal.translated([0.0, 0.0, 0.01]).to_dict()
        self.scene["revision"] = "2"
        self.write_scene()
        readback = invoke(self.event("PostToolUse"))
        self.assertNotIn("host_action_mismatch", readback["hookSpecificOutput"]["additionalContext"])
        state = self.state()["sessions"]["codex:s1"]
        self.assertNotIn("pending", state)
        self.assertNotEqual(state["observation_id"], first_observation)

    def test_real_router_readback_failure_blocks_other_sessions_and_recovers(self):
        from human_eye_plugin.auto_router import HumanEyeAutoRouter
        from verification.test_certification_contracts import contact_pair
        focal, reference = contact_pair()
        self.scene["meshes"] = [focal.to_dict(), reference.to_dict()]
        self.write_scene()
        self.config.update(focal_id="#B", reference_id="#A", quad_size=64)

        def route(event):
            return route_hook_event(event, self.config, agent="codex", config_dir=self.base, router_factory=HumanEyeAutoRouter)

        route(self.event())
        route(self.event(session="s2"))
        action_event = self.event("PreToolUse", tool_input={"action": {"translation": [0.0, 0.0, 0.01]}})
        self.assertNotIn("permissionDecision", route(action_event)["hookSpecificOutput"])
        route(self.event("PostToolUse"))  # stale file does not prove host execution
        self.assertEqual(route(self.event("PreToolUse", session="s2"))["hookSpecificOutput"]["permissionDecision"], "deny")
        self.scene["revision"] = "2"
        self.write_scene()
        route(self.event(session="s2"))
        recovered = route(self.event("PreToolUse", session="s2", tool_use_id="new-call", tool_input={"action": {"translation": [0.0, 0.0, 0.01]}}))
        self.assertNotIn("permissionDecision", recovered["hookSpecificOutput"])

    def test_real_router_missing_snapshot_invalidates_all_observations(self):
        from human_eye_plugin.auto_router import HumanEyeAutoRouter
        from verification.test_certification_contracts import contact_pair
        focal, reference = contact_pair()
        self.scene["meshes"] = [focal.to_dict(), reference.to_dict()]
        self.write_scene()
        self.config.update(focal_id="#B", reference_id="#A", quad_size=64)

        def route(event):
            return route_hook_event(event, self.config, agent="codex", config_dir=self.base, router_factory=HumanEyeAutoRouter)

        route(self.event())
        route(self.event(session="s2"))
        (self.base / "scene.json").unlink()
        route(self.event())
        self.assertTrue(all("observation_id" not in item for item in self.state()["sessions"].values()))
        self.write_scene()
        denied = route(self.event("PreToolUse", session="s2", tool_input={"action": {"translation": [0.0, 0.0, 0.01]}}))
        self.assertEqual(denied["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_concurrent_processes_preserve_all_session_state(self):
        script = ("import json,sys; from pathlib import Path; sys.path.insert(0,'verification'); "
                  "from test_agent_hooks import FakeRouter; from human_eye_plugin.agent_hooks import route_hook_event; "
                  "p=Path(sys.argv[1]); route_hook_event({'hook_event_name':'UserPromptSubmit','session_id':sys.argv[2],'prompt':'Inspect'},json.loads(p.read_text()),agent='codex',config_dir=p.parent,router_factory=FakeRouter)")
        processes = [subprocess.Popen([sys.executable, "-c", script, str(self.config_path), "parallel-" + str(i)], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for i in range(3)]
        for process in processes:
            stdout, stderr = process.communicate(timeout=30)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertEqual(stdout, "")
        state = self.state()
        self.assertEqual(len(state["sessions"]), 3)
        self.assertEqual(state["router_state"]["counter"], 3)
        self.assertEqual(list(self.base.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
