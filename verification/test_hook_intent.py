"""Local hook contracts; these simulations never count as actual host firing."""
import json
import unittest
from unittest.mock import patch

from human_eye_plugin.live_hooks import route_live_hook, SPATIAL_TRANSFORM
from human_eye_plugin.telemetry import current_trace
from verification.test_live_hooks import HookService


class HookIntentTests(unittest.TestCase):
    def event(self, prompt="move the cube", kind="UserPromptSubmit", **fields):
        return {"hook_event_name": kind, "session_id": "host-session", "prompt": prompt,
            "turn_id": "real-turn", "tool_use_id": "real-call", "tool_name": SPATIAL_TRANSFORM,
            "tool_input": {"action": {"focal_id": "part", "reference_id": "base",
                "translation": [0, 0, .1]}}, **fields}

    def invoke(self, event, service=None):
        service = service or HookService()
        result = route_live_hook(event, service, invocation_source="manual_probe")
        return service, result

    def test_ordinary_and_2d_prompts_do_not_observe_even_with_background_tool_fields(self):
        for prompt in ("翻译这段文章。", "读取Blender截图里的文字。", "Describe this photo of a 3D model."):
            with self.subTest(prompt=prompt):
                service, result = self.invoke(self.event(prompt))
                self.assertEqual(result, {})
                self.assertEqual(service.calls, [])
                skips = [fields for args, fields in service.records if args == ("host_hook_skip",)]
                self.assertEqual(len(skips), 1)
                self.assertFalse(skips[0]["scene_read"])

    def test_unknown_is_silent_without_capture_and_explicit_kind_can_correct(self):
        service, result = self.invoke(self.event("do that again"))
        self.assertEqual(service.calls, [])
        self.assertEqual(result, {})
        skips = [fields for args, fields in service.records if args == ("host_hook_skip",)]
        self.assertEqual(len(skips), 1)
        self.assertEqual(skips[0]["status"], "intent_unknown")
        self.assertEqual(skips[0]["intent"]["kind"], "unknown")
        self.assertFalse(skips[0]["scene_read"])
        self.assertFalse(skips[0]["engine_invoked"])
        traces = [fields["trace"] for args, fields in service.records if args == ("request_trace",)]
        self.assertEqual(traces[0]["outcome"], "intent_unknown")
        corrected, _ = self.invoke(self.event("do that again", task_kind="spatial_3d"))
        self.assertEqual([row[0] for row in corrected.calls], ["observe"])

    def test_bad_metadata_does_not_fall_back_to_guessing_spatial_text(self):
        service, result = self.invoke(self.event(task_kind={"kind": "spatial_3d"}))
        self.assertEqual(service.calls, [])
        self.assertEqual(result, {})
        intent = [fields for args, fields in service.records if args == ("host_hook_skip",)][0]["intent"]
        self.assertEqual(intent["source"], "invalid_host_metadata")

    def test_unknown_followup_does_not_inherit_spatial_task_or_replay_motion(self):
        service = HookService()
        self.invoke(self.event("move the cube"), service)
        before = len(service.calls)
        _, result = self.invoke(self.event("继续"), service)
        self.assertEqual(result, {})
        self.assertEqual(len(service.calls), before)

    def test_spatial_prompt_observes_once_and_stays_text_only(self):
        service, result = self.invoke(self.event("检查插销与孔之间的间隙。"))
        self.assertEqual([row[0] for row in service.calls], ["observe"])
        self.assertFalse(service.calls[0][2]["include_image"])
        context = json.loads(result["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(context["task_intent"]["kind"], "spatial_3d")
        self.assertEqual(context["delivery"], "text_only_hook_no_native_image")
        self.assertNotIn("not_inline", json.dumps(context))

    def test_pre_action_is_checked_regardless_of_prompt_intent_or_metadata(self):
        for task_kind in ("image_2d", "general", "unknown", {}):
            with self.subTest(task_kind=task_kind):
                service, result = self.invoke(self.event("read a photo", "PreToolUse", task_kind=task_kind))
                self.assertEqual([row[0] for row in service.calls], ["preview"])
                self.assertNotIn("permissionDecision", result["hookSpecificOutput"])

    def test_post_action_retains_tool_delivery_without_duplicate_capture(self):
        for response in (None, {"execution_verified": True}, {"error": "readback failed"}):
            with self.subTest(response=response):
                service, result = self.invoke(self.event("explain a function", "PostToolUse",
                    task_kind="general", tool_response=response))
                self.assertEqual(service.calls, [])
                self.assertEqual(result, {})
                skips = [fields for args, fields in service.records if args == ("host_hook_skip",)]
                self.assertEqual(len(skips), 1)
                self.assertEqual(skips[0]["status"], "tool_result_delivery_retained")
                self.assertFalse(skips[0]["scene_read"])

    def test_real_host_ids_enter_trace_without_renaming_or_fabrication(self):
        service, _ = self.invoke(self.event())
        traces = [fields["trace"] for args, fields in service.records if args == ("request_trace",)]
        self.assertEqual(len(traces), 1)
        self.assertEqual(traces[0]["correlation"]["turn_id"], "real-turn")
        self.assertEqual(traces[0]["correlation"]["tool_use_id"], "real-call")
        self.assertEqual(traces[0]["correlation"]["session_id"], "codex:host-session")
        self.assertIsNone(current_trace())
        missing, _ = self.invoke(self.event(turn_id=None, tool_use_id=None))
        trace = [fields["trace"] for args, fields in missing.records if args == ("request_trace",)][0]
        self.assertIsNone(trace["correlation"]["turn_id"])
        self.assertIsNone(trace["correlation"]["tool_use_id"])

    def test_logging_failure_never_changes_checked_pre_action_disposition(self):
        service = HookService()
        with patch.object(service, "record_event", side_effect=OSError("audit unavailable")):
            _, result = self.invoke(self.event(kind="PreToolUse"), service)
        self.assertEqual([row[0] for row in service.calls], ["preview"])
        self.assertNotIn("permissionDecision", result["hookSpecificOutput"])

    def test_trace_constructor_failure_does_not_repeat_host_work(self):
        with patch("human_eye_plugin.telemetry.RequestTrace", side_effect=OSError("trace unavailable")):
            service, _ = self.invoke(self.event())
        self.assertEqual([row[0] for row in service.calls], ["observe"])
        self.assertIsNone(current_trace())

    def test_pre_action_failure_still_denies_when_prompt_is_native(self):
        service = HookService()
        service.fail = True
        _, result = self.invoke(self.event("read this photo", "PreToolUse", task_kind="image_2d"), service)
        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")


if __name__ == "__main__":
    unittest.main()
