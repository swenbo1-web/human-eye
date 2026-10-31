"""Trace evidence must survive failures without fabricating usage or duration."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import contextvars
import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from human_eye_plugin.telemetry import (RequestTrace, annotate, current_trace,
    process_peak_rss, raw_record_digest, record_usage, span, summarize_traces,
    best_effort_trace, safe_request_trace)
from human_eye_plugin import telemetry
from verification.analyze_request_traces import analyze_paths


class RequestTraceTests(unittest.TestCase):
    def test_inert_calls_without_active_request(self):
        self.assertIsNone(current_trace())
        self.assertFalse(annotate(status="none"))
        self.assertFalse(record_usage())
        with span("capture") as span_id:
            self.assertIsNone(span_id)

    def test_correlation_and_inclusive_nested_span_ids(self):
        rows = []
        with RequestTrace("observe", writer=rows.append, experiment_id="e", trial_id="t",
                session_id="s", request_id="r", implementation_revision="rev") as trace:
            with span("queue_wait", kind="queue") as outer:
                with span("capture", kind="host", source_name="host_blender"):
                    self.assertTrue(annotate(observation_id="o", scene_revision="v", include_image=False))
            trace.set_outcome("verified")
        row = rows[0]
        self.assertEqual(row["request_id"], "r")
        self.assertEqual(row["correlation"]["observation_id"], "o")
        self.assertEqual(row["correlation"]["scene_revision"], "v")
        self.assertEqual(row["spans"][1]["parent_span_id"], outer)
        self.assertGreaterEqual(row["spans"][0]["duration_ns"], row["spans"][1]["duration_ns"])
        self.assertGreaterEqual(row["duration_ns"], row["spans"][0]["duration_ns"])
        self.assertEqual(trace.delivery_status, "delivered")
        self.assertIsNone(current_trace())
        json.dumps(row, allow_nan=False)

    def test_nested_requests_restore_parent_and_identify_parent_span(self):
        with RequestTrace("outer") as parent:
            with span("host_call") as parent_span:
                with RequestTrace("inner") as child:
                    self.assertIs(current_trace(), child)
                    with span("capture"):
                        pass
                self.assertIs(current_trace(), parent)
                self.assertEqual(child.record["parent_trace_id"], parent.trace_id)
                self.assertEqual(child.record["parent_span_id"], parent_span)
                self.assertIsNone(child.record["spans"][0]["parent_span_id"])
        self.assertIsNone(current_trace())

    def test_failed_stage_and_request_keep_duration_and_clean_context(self):
        rows = []
        with self.assertRaisesRegex(RuntimeError, "private text"):
            with RequestTrace("transform", writer=rows.append):
                with span("apply", kind="host"):
                    raise RuntimeError("private text must never enter trace")
        row = rows[0]
        self.assertEqual(row["outcome"], "error")
        self.assertEqual(row["spans"][0]["outcome"], "error")
        self.assertIsInstance(row["duration_ns"], int)
        self.assertIsInstance(row["spans"][0]["duration_ns"], int)
        self.assertEqual(row["error_type"], "RuntimeError")
        self.assertNotIn("private text", json.dumps(row))
        self.assertIsNone(current_trace())

    def test_writer_failure_does_not_replace_completed_mutation(self):
        def broken_writer(row):
            self.assertIsNone(current_trace())
            raise OSError("disk full")
        did_mutate = []
        with RequestTrace("transform", writer=broken_writer) as trace:
            did_mutate.append(True)
            trace.set_outcome("verified")
        self.assertEqual(did_mutate, [True])
        self.assertEqual(trace.record["outcome"], "verified")
        self.assertEqual(trace.delivery_status, "failed")

    def test_false_writer_result_is_delivery_failure_only(self):
        with RequestTrace("observe", writer=lambda row: False) as trace:
            pass
        self.assertEqual(trace.delivery_status, "failed")
        self.assertEqual(trace.record["outcome"], "completed")

    def test_writer_failure_preserves_original_operation_error(self):
        with self.assertRaisesRegex(ValueError, "operation"):
            with RequestTrace("transform", writer=lambda row: 1 / 0) as trace:
                raise ValueError("operation")
        self.assertEqual(trace.record["error_type"], "ValueError")

    def test_record_is_immutable_copy(self):
        with RequestTrace("observe") as trace:
            annotate(status="ok")
        row = trace.record
        row["annotations"]["status"] = "changed"
        self.assertEqual(trace.record["annotations"]["status"], "ok")
        self.assertFalse(trace.annotate(status="late"))
        self.assertFalse(trace.record_usage())
        self.assertFalse(trace.set_outcome("late"))

    def test_unknown_usage_is_none_and_has_explicit_single_response_scope(self):
        with RequestTrace("observe") as trace:
            self.assertTrue(record_usage())
        row = trace.record["usage"][0]
        for key in ("input_tokens", "output_tokens", "cached_input_tokens", "reasoning_tokens", "total_tokens"):
            self.assertIsNone(row[key])
        self.assertFalse(row["usage_available"])
        self.assertIsNone(row["total_includes_reasoning"])
        self.assertEqual(row["scope"], "single_provider_response")

    def test_reported_usage_has_origin_and_subset_semantics(self):
        provider_record = {"input": 100, "output": 40, "total": 140}
        digest = raw_record_digest(provider_record)
        with RequestTrace("model", scope="provider_request") as trace:
            self.assertTrue(trace.record_usage(provider="example", model="fixed", source="provider_response",
                input_tokens=100, output_tokens=40, total_tokens=140, cached_input_tokens=50,
                reasoning_tokens=30, total_includes_reasoning=True, raw_record_sha256=digest,
                provider_request_id="provider-r", step_index=0))
        row = trace.record["usage"][0]
        self.assertEqual(row["total_tokens"], 140)
        self.assertEqual(row["reasoning_semantics"], "subset_of_output_tokens")
        self.assertEqual(row["raw_record_sha256"], digest)
        self.assertEqual(row["source"], "provider_response")

    def test_known_zero_is_different_from_missing(self):
        with RequestTrace("observe") as trace:
            self.assertTrue(record_usage(source="provider_response", input_tokens=0, output_tokens=0,
                total_tokens=0, total_includes_reasoning=True))
        self.assertTrue(trace.record["usage"][0]["usage_available"])
        self.assertEqual(trace.record["usage"][0]["total_tokens"], 0)

    def test_malformed_usage_cannot_fail_operation_or_partially_append(self):
        bad = [{"input_tokens": -1}, {"input_tokens": True}, {"input_tokens": 1.2},
            {"source": "provider", "input_tokens": 2, "cached_input_tokens": 3},
            {"source": "provider", "output_tokens": 1, "reasoning_tokens": 2},
            {"source": "provider", "input_tokens": 2, "output_tokens": 3, "total_tokens": 6,
             "total_includes_reasoning": True}, {"input_tokens": 5},
            {"raw_record_sha256": "secret"}, {"total_includes_reasoning": 1}, {"step_index": -1}]
        with RequestTrace("transform") as trace:
            for kwargs in bad:
                self.assertFalse(trace.record_usage(**kwargs))
            trace.set_outcome("verified")
        self.assertEqual(trace.record["usage"], [])
        self.assertEqual(trace.record["outcome"], "verified")
        self.assertIn("invalid_usage_record", trace.record["telemetry_issues"])

    def test_metadata_allowlist_blocks_private_payloads_and_invalid_numbers(self):
        with RequestTrace("observe") as trace:
            for kwargs in ({"prompt": "secret"}, {"mesh": [1]}, {"status": "\nsecret"},
                           {"input_bytes": float("nan")}, {"status": {"private": "x"}}):
                self.assertFalse(trace.annotate(**kwargs))
            self.assertFalse(trace.annotate(status="would partially append", prompt="secret"))
            self.assertFalse(trace.set_outcome("\nprivate"))
            with span("private invalid stage"):
                pass
            with span("capture", kind=[]):
                pass
        self.assertEqual(trace.record["annotations"], {})
        self.assertEqual(trace.record["spans"], [])
        self.assertNotIn("secret", json.dumps(trace.record))

    def test_retry_is_explicit_and_not_assumed_an_independent_model_step(self):
        with RequestTrace("model", request_id="attempt-2", attempt_index=1,
                          retry_of_request_id="attempt-1") as trace:
            pass
        row = trace.record
        self.assertEqual(row["attempt_index"], 1)
        self.assertEqual(row["retry_of_request_id"], "attempt-1")
        self.assertEqual(row["duration_scope"], "one_request_attempt_wall_clock")

    def test_duration_uses_monotonic_clock_even_with_unreliable_wall_clock(self):
        with patch("human_eye_plugin.telemetry.time.perf_counter_ns", side_effect=[100, 110, 150, 180]):
            with RequestTrace("observe") as trace:
                with span("capture"):
                    pass
        self.assertEqual(trace.record["duration_ns"], 80)
        self.assertEqual(trace.record["spans"][0]["duration_ns"], 40)

    def test_peak_memory_is_explicitly_process_lifetime_not_request(self):
        rss = process_peak_rss()
        self.assertEqual(rss["scope"], "process_lifetime_peak")
        self.assertTrue(rss["bytes"] is None or type(rss["bytes"]) is int)
        with RequestTrace("observe") as trace:
            pass
        self.assertEqual(trace.record["peak_rss"]["scope"], "process_lifetime_peak")

    def test_invalid_constructor_and_reuse_rejected_before_work(self):
        for kwargs in ({"operation": "private\n"}, {"operation": "ok", "scope": "kernel_as_model"},
                       {"operation": "ok", "attempt_index": True}, {"operation": "ok", "writer": "no"}):
            with self.assertRaises(ValueError):
                RequestTrace(**kwargs)
        trace = RequestTrace("ok")
        with trace:
            pass
        with self.assertRaises(RuntimeError):
            with trace:
                pass

    def test_thread_contexts_and_concurrency_are_isolated(self):
        barrier = threading.Barrier(2)
        def worker(name):
            with RequestTrace("observe", session_id=name) as trace:
                barrier.wait(timeout=5)
                with span("capture"):
                    self.assertEqual(current_trace().record["correlation"]["session_id"], name)
                barrier.wait(timeout=5)
            self.assertIsNone(current_trace())
            return trace.record
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows = list(pool.map(worker, ["a", "b"]))
        self.assertNotEqual(rows[0]["trace_id"], rows[1]["trace_id"])
        self.assertEqual([r["concurrency"]["max_observed"] for r in rows], [2, 2])

    def test_async_contexts_do_not_parent_unrelated_tasks(self):
        async def work(name):
            with RequestTrace("observe", session_id=name) as trace:
                with span("outer") as outer:
                    await asyncio.sleep(0)
                    with span("inner"):
                        self.assertIs(current_trace(), trace)
                self.assertEqual(trace.record["spans"][1]["parent_span_id"], outer)
            return trace.record
        async def run():
            return await asyncio.gather(work("a"), work("b"))
        rows = asyncio.run(run())
        self.assertEqual([row["parent_trace_id"] for row in rows], [None, None])
        self.assertIsNone(current_trace())


class TraceSummaryTests(unittest.TestCase):
    def row(self, **kwargs):
        with RequestTrace("observe", aggregation_key="same-fixture", implementation_revision="v1", **kwargs) as trace:
            with span("capture", kind="host"):
                pass
        return trace.record

    def test_unlabelled_records_not_pooled_and_duplicates_not_double_counted(self):
        with RequestTrace("observe") as trace:
            pass
        row = self.row()
        report = summarize_traces([trace.record, row, row, {}, None])
        self.assertEqual(report["excluded"]["missing_aggregation_key"], 1)
        self.assertEqual(report["excluded"]["duplicate_trace"], 1)
        self.assertEqual(report["excluded"]["invalid_record"], 2)
        self.assertEqual(report["groups"][0]["requests"]["count"], 1)

    def test_percentile_interpolation_and_single_call_scope(self):
        rows = [self.row() for _ in range(3)]
        for row, milliseconds in zip(rows, [1, 5, 9]):
            row["duration_ns"] = milliseconds * 1_000_000
        report = summarize_traces(rows)
        self.assertEqual(len(report["groups"]), 1)
        group = report["groups"][0]
        self.assertEqual(group["requests"]["p50_ms"], 5)
        self.assertAlmostEqual(group["requests"]["p95_ms"], 8.6)
        self.assertAlmostEqual(group["requests"]["p99_ms"], 8.92)
        self.assertEqual(group["unknown_usage_records"], 3)
        self.assertNotIn("total_tokens", group)
        self.assertEqual(group["stages"][0]["scope"], "stage_call_inclusive_wall_clock")

    def test_revision_cache_failure_retry_and_concurrency_are_not_pooled(self):
        rows = [self.row() for _ in range(6)]
        rows[1]["correlation"]["implementation_revision"] = "v2"
        rows[2]["annotations"]["cache_hit"] = True
        rows[3]["outcome"] = "error"
        rows[4]["attempt_index"] = 1
        rows[5]["concurrency"]["max_observed"] = 4
        self.assertEqual(len(summarize_traces(rows)["groups"]), 6)

    def test_gpu_submit_and_completed_gpu_spans_keep_distinct_kinds(self):
        with RequestTrace("observe", aggregation_key="fixture") as trace:
            with span("kernel", kind="gpu_submission"):
                pass
            with span("kernel", kind="gpu_synchronized"):
                pass
        stages = summarize_traces([trace.record])["groups"][0]["stages"]
        self.assertEqual({s["kind"] for s in stages}, {"gpu_submission", "gpu_synchronized"})
        self.assertTrue(all(s["scope"] != "model_inference" for s in stages))

    def test_provider_identity_and_step_counts_are_not_mixed(self):
        rows = []
        for model, steps in [("one", 1), ("two", 1), ("one", 2)]:
            with RequestTrace("model", aggregation_key="fixture", scope="provider_request") as trace:
                for step in range(steps):
                    trace.record_usage(provider="p", model=model, source="provider_response", input_tokens=1, step_index=step)
            rows.append(trace.record)
        self.assertEqual(len(summarize_traces(rows)["groups"]), 3)

    def test_usage_aggregation_preserves_missing_fields_and_deduplicates_provider_response(self):
        rows = []
        for provider_id, output in [("a", 2), ("b", None), ("a", 2)]:
            with RequestTrace("model", aggregation_key="fixture", scope="provider_request") as trace:
                trace.record_usage(provider="p", model="m", source="provider_response",
                    provider_request_id=provider_id, input_tokens=3, output_tokens=output)
            rows.append(trace.record)
        group = summarize_traces(rows)["groups"][0]
        self.assertEqual(group["duplicate_provider_usage_records"], 1)
        usage = group["provider_usage"][0]
        self.assertEqual(usage["fields"]["input_tokens"]["known_value_sum"], 6)
        self.assertTrue(usage["fields"]["input_tokens"]["complete"])
        self.assertEqual(usage["fields"]["output_tokens"]["known_value_sum"], 2)
        self.assertFalse(usage["fields"]["output_tokens"]["complete"])
        self.assertEqual(usage["fields"]["output_tokens"]["unknown_records"], 1)
        self.assertIsNone(usage["fields"]["total_tokens"]["known_value_sum"])

    def test_analysis_reads_only_explicit_logs_and_records_bad_json_by_line(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "trace.jsonl"
            path.write_text(json.dumps(self.row()) + "\ninvalid private text\n", encoding="utf-8")
            report = analyze_paths([path])
        self.assertEqual(report["read_issues"], [{"file": "trace.jsonl", "line": 2, "issue": "invalid_json_record"}])
        self.assertNotIn("private text", json.dumps(report))
        self.assertEqual(report["groups"][0]["requests"]["count"], 1)

    def test_analysis_accepts_audit_wrappers_and_ignores_operational_events(self):
        row = self.row()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "events.jsonl"
            path.write_text("\n".join(json.dumps(item) for item in [
                {"event": "observe", "status": "ok"},
                {"event": "request_trace", "trace": row},
                {"event": "host_mutation", "executed": True},
                {"event": "request_trace", "trace": None}]) + "\n", encoding="utf-8")
            report = analyze_paths([path])
        self.assertEqual(report["ignored_operational_records"], 2)
        self.assertEqual(report["wrapped_trace_records"], 2)
        self.assertEqual(report["excluded"]["invalid_record"], 1)
        self.assertEqual(report["groups"][0]["requests"]["count"], 1)

    def test_incomplete_spans_and_requests_not_given_zero_duration(self):
        row = self.row()
        row["duration_ns"] = None
        report = summarize_traces([row])
        self.assertEqual(report["groups"], [])
        self.assertEqual(report["excluded"]["unfinished_request"], 1)


class BestEffortTraceTests(unittest.TestCase):
    def assert_clean(self):
        self.assertIsNone(current_trace())
        self.assertIsNone(telemetry._CURRENT_SPAN.get())
        self.assertEqual(telemetry._ACTIVE, set())

    def test_alias_and_normal_trace(self):
        self.assertIs(safe_request_trace, best_effort_trace)
        rows = []
        with safe_request_trace("observe", writer=rows.append) as trace:
            self.assertIs(current_trace(), trace)
            with span("capture"):
                pass
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["outcome"], "completed")
        self.assert_clean()

    def test_constructor_failure_still_runs_business_once(self):
        changed = []
        with safe_request_trace("observe", session_id="x" * 300) as trace:
            self.assertIsNone(trace)
            changed.append(True)
        self.assertEqual(changed, [True])
        self.assert_clean()

    def test_patched_constructor_failure_keeps_original_business_exception(self):
        with patch("human_eye_plugin.telemetry.RequestTrace", side_effect=OSError("metadata unavailable")):
            with self.assertRaisesRegex(ValueError, "business exception"):
                with safe_request_trace("transform") as trace:
                    self.assertIsNone(trace)
                    raise ValueError("business exception")
        self.assert_clean()

    def test_entry_failure_before_and_after_original_entry_is_cleaned(self):
        original_enter = RequestTrace.__enter__
        for partially_entered in (False, True):
            def broken_enter(trace):
                if partially_entered:
                    original_enter(trace)
                raise OSError("entry failure")
            with self.subTest(partially_entered=partially_entered):
                with patch.object(RequestTrace, "__enter__", broken_enter):
                    with safe_request_trace("transform") as trace:
                        self.assertIsNone(trace)
                        self.assertIsNone(current_trace())
                        self.assertEqual(telemetry._ACTIVE, set())
                self.assert_clean()

    def test_exit_failure_before_and_after_original_exit_keeps_completed_work(self):
        original_exit = RequestTrace.__exit__
        for finished in (False, True):
            rows, changed = [], []
            def broken_exit(trace, *args):
                if finished:
                    original_exit(trace, *args)
                raise OSError("exit failure")
            with self.subTest(finished=finished):
                with patch.object(RequestTrace, "__exit__", broken_exit):
                    with safe_request_trace("transform", writer=rows.append):
                        changed.append(True)
                self.assertEqual(changed, [True])
                self.assertEqual(len(rows), int(finished))
                self.assert_clean()

    def test_exit_failure_never_replaces_original_business_exception(self):
        original_exit = RequestTrace.__exit__
        for finished in (False, True):
            def broken_exit(trace, *args):
                if finished:
                    original_exit(trace, *args)
                raise OSError("trace exit failure")
            with patch.object(RequestTrace, "__exit__", broken_exit):
                with self.assertRaisesRegex(ValueError, "business error"):
                    with safe_request_trace("transform"):
                        raise ValueError("business error")
            self.assert_clean()

    def test_writer_failure_not_retried(self):
        calls = []
        def writer(row):
            calls.append(row)
            raise OSError("no disk")
        with safe_request_trace("transform", writer=writer) as trace:
            trace.set_outcome("verified")
        self.assertEqual(len(calls), 1)
        self.assertEqual(trace.delivery_status, "failed")
        self.assertEqual(trace.record["outcome"], "verified")
        self.assert_clean()

    def test_timing_fault_during_original_exit_does_not_escape(self):
        manager = safe_request_trace("transform")
        trace = manager.__enter__()
        trace.set_outcome("verified")
        with patch("human_eye_plugin.telemetry.time.perf_counter_ns", side_effect=OSError("clock failed")):
            manager.__exit__(None, None, None)
        self.assertEqual(trace.record["outcome"], "verified")
        self.assert_clean()

    def test_failed_child_does_not_remove_concurrently_active_other_thread(self):
        ready, done = threading.Event(), threading.Event()
        def other_worker():
            with RequestTrace("parallel") as other:
                ready.set()
                self.assertTrue(done.wait(timeout=5))
                return other
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(other_worker)
            self.assertTrue(ready.wait(timeout=5))
            with telemetry._ACTIVE_LOCK:
                before = set(telemetry._ACTIVE)
            try:
                with patch.object(RequestTrace, "__enter__", side_effect=OSError("entry failed")):
                    with safe_request_trace("child") as trace:
                        self.assertIsNone(trace)
                        self.assertEqual(telemetry._ACTIVE, before)
            finally:
                done.set()
            future.result(timeout=5)
        self.assert_clean()

    def test_parent_context_and_active_registration_survive_child_entry_failure(self):
        original_enter = RequestTrace.__enter__
        with RequestTrace("parent") as parent:
            with span("parent_stage") as parent_span:
                def broken_enter(trace):
                    original_enter(trace)
                    raise OSError("child failure")
                with patch.object(RequestTrace, "__enter__", broken_enter):
                    with safe_request_trace("child") as child:
                        self.assertIsNone(child)
                        self.assertIs(current_trace(), parent)
                        self.assertEqual(telemetry._CURRENT_SPAN.get(), parent_span)
                        self.assertEqual(telemetry._ACTIVE, {parent})
            self.assertIs(current_trace(), parent)
        self.assert_clean()

    def test_parent_context_survives_child_exit_after_original_exit_raised(self):
        original_exit = RequestTrace.__exit__
        with RequestTrace("parent") as parent:
            with span("parent_stage") as parent_span:
                def broken_exit(trace, *args):
                    original_exit(trace, *args)
                    raise OSError("already cleaned child")
                with patch.object(RequestTrace, "__exit__", broken_exit):
                    with safe_request_trace("child"):
                        pass
                self.assertIs(current_trace(), parent)
                self.assertEqual(telemetry._CURRENT_SPAN.get(), parent_span)
                self.assertEqual(telemetry._ACTIVE, {parent})
        self.assert_clean()


if __name__ == "__main__":
    unittest.main()
