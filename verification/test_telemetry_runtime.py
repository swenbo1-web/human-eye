"""Stage instrumentation must preserve host transactions and execution safety."""
import json
import unittest
from unittest.mock import patch

from human_eye_plugin.auto_router import HumanEyeAutoRouter
from human_eye_plugin.host_runtime import GuardedHostRuntime
from human_eye_plugin.telemetry import RequestTrace, current_trace
from verification.test_auto_router import observation
from verification.test_host_runtime import MutableHost


class RuntimeTelemetryTests(unittest.TestCase):
    def setUp(self):
        self.host = MutableHost()
        self.runtime = GuardedHostRuntime(self.host, quad_size=64)

    def prepare(self, **changes):
        args = dict(session_id="s", task_instruction="private user instruction",
            focal_id="part", reference_id="base", messages=[], include_image=False)
        args.update(changes)
        return self.runtime.before_model(**args)

    def execute(self, **changes):
        args = dict(session_id="s", action={"translation": [0, 0, .1]})
        args.update(changes)
        return self.runtime.execute_action(**args)

    def test_execution_uses_existing_trace_and_independent_capture_counts(self):
        self.prepare()
        rows = []
        with RequestTrace("transform", writer=rows.append) as trace:
            result = self.execute()
            self.assertIs(current_trace(), trace)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(self.host.calls, 1)
        self.assertEqual(self.host.captures, 3)
        self.assertEqual(len(rows), 1)
        record = rows[0]
        stages = {s["name"] for s in record["spans"]}
        self.assertTrue({"host.execute_action", "host.capture_before_action", "host.execution_gate",
            "geometry.before_action_gate", "geometry.candidate_collision", "host.mutation",
            "host.readback_capture", "host.readback_verify", "geometry.post_action_check"} <= stages)
        self.assertTrue(record["annotations"]["mutation_started"])
        self.assertTrue(record["annotations"]["mutation_completed"])
        self.assertTrue(record["annotations"]["execution_verified"])
        self.assertEqual(record["correlation"]["scene_revision"], "r2")
        self.assertNotIn("private user instruction", json.dumps(record))
        self.assertNotIn("vertices", json.dumps(record))

    def test_observation_render_and_encoding_stages_are_actual_work_only(self):
        with RequestTrace("observe") as text_trace:
            self.prepare()
        text_stages = {s["name"] for s in text_trace.record["spans"]}
        self.assertTrue({"host.capture", "scene.validate", "scene.hash", "cache.scene_history",
                         "measurement.display_probe", "measurement.exact_clearance",
                         "observation.context_encode"} <= text_stages)
        self.assertNotIn("render.scene_canvas", text_stages)
        self.assertNotIn("encoding.png", text_stages)
        with RequestTrace("observe") as image_trace:
            self.prepare(include_image=True)
        image_stages = {s["name"] for s in image_trace.record["spans"]}
        self.assertTrue({"render.scene_canvas", "render.attention", "encoding.png", "encoding.base64"} <= image_stages)

    def test_cached_observation_does_not_claim_new_measurement_or_render(self):
        router = HumanEyeAutoRouter(quad_size=64)
        event = observation(include_image=False)
        router.handle_event(event)
        with RequestTrace("observe") as trace:
            result = router.handle_event(event)
        self.assertTrue(result["cache_hit"])
        self.assertTrue(trace.record["annotations"]["cache_hit"])
        names = {s["name"] for s in trace.record["spans"]}
        self.assertNotIn("measurement.exact_clearance", names)
        self.assertNotIn("render.scene_canvas", names)

    def test_disabled_instrumentation_does_not_create_request_authority(self):
        self.assertIsNone(current_trace())
        self.prepare()
        self.assertEqual(self.execute()["status"], "verified")
        self.assertIsNone(current_trace())
        self.assertEqual(self.host.calls, 1)
        self.assertEqual(self.host.captures, 3)

    def test_telemetry_entry_or_annotation_failure_does_not_change_mutation_result(self):
        self.prepare()
        with patch("human_eye_plugin.auto_router._span", side_effect=OSError("clock unavailable")), \
             patch("human_eye_plugin.auto_router._annotate", side_effect=RuntimeError("sink unavailable")):
            result = self.execute()
        self.assertEqual(result["status"], "verified")
        self.assertEqual(self.host.calls, 1)
        self.assertEqual(self.host.captures, 3)
        self.assertFalse(self.runtime.status["quarantined"])

    def test_telemetry_exit_failure_does_not_make_completed_write_retryable(self):
        class BadStage:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                raise OSError("timing collection unavailable")
        self.prepare()
        with patch("human_eye_plugin.auto_router._span", side_effect=lambda *a, **k: BadStage()):
            result = self.execute()
        self.assertEqual(result["status"], "verified")
        self.assertEqual(self.host.calls, 1)

    def test_failed_host_operation_keeps_uncertainty_and_reports_failed_stage(self):
        self.prepare()
        self.host.mode = "partial_failure"
        with RequestTrace("transform") as trace:
            result = self.execute()
        self.assertEqual(result["status"], "host_execution_uncertain")
        self.assertEqual(self.host.calls, 1)
        stages = [s for s in trace.record["spans"] if s["name"] == "host.mutation"]
        self.assertEqual(len(stages), 1)
        self.assertEqual(stages[0]["outcome"], "error")
        self.assertEqual(stages[0]["error_type"], "RuntimeError")
        self.assertIsInstance(stages[0]["duration_ns"], int)
        self.assertNotIn("host.readback_capture", {s["name"] for s in trace.record["spans"]})
        self.assertTrue(self.runtime.status["quarantined"])

    def test_failed_host_operation_not_hidden_by_failed_stage_finalization(self):
        class BadStage:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                raise OSError("timing failure")
        self.prepare()
        self.host.mode = "partial_failure"
        with patch("human_eye_plugin.auto_router._span", side_effect=lambda *a, **k: BadStage()):
            result = self.execute()
        self.assertEqual(result["status"], "host_execution_uncertain")
        self.assertEqual(result["error_type"], "RuntimeError")
        self.assertTrue(self.runtime.status["quarantined"])

    def test_rejected_action_does_not_have_a_mutation_stage(self):
        self.prepare()
        with RequestTrace("transform") as trace:
            result = self.execute(action={"translation": [0, 0, -.25]})
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(self.host.calls, 0)
        self.assertNotIn("host.mutation", {s["name"] for s in trace.record["spans"]})
        self.assertEqual(trace.record["annotations"]["route"], "blocked")

    def test_readback_failure_retains_actual_failed_capture_timing(self):
        self.prepare()
        self.host.mode = "readback_failure"
        with RequestTrace("transform") as trace:
            result = self.execute()
        self.assertEqual(result["status"], "host_readback_uncertain")
        self.assertEqual(self.host.calls, 1)
        self.assertEqual(self.host.captures, 3)
        stage = next(s for s in trace.record["spans"] if s["name"] == "host.readback_capture")
        self.assertEqual(stage["outcome"], "error")
        self.assertTrue(self.runtime.status["quarantined"])


if __name__ == "__main__":
    unittest.main()
