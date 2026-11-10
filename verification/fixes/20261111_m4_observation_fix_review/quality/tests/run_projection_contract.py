"""Finite SYNTHETIC packager contract checks; no run, model or geometry backend.

Invoke twice with the same script, once per explicitly SHA-bound packager.
The archived packager is expected to fail two semantic assertions. Its nonzero
test outcome is retained, not converted into a new-behavior pass. Import/I/O
errors never count as reproducing that expected semantic failure.
"""
import argparse
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import traceback
import unittest

REVISION = Path(__file__).resolve().parent.parent
PACKAGER = None
OUT = None
EVIDENCE = {"synthetic": True, "formal_consumers": 0, "model_calls": 0,
    "Blender_calls": 0, "product_calls": 0, "GO_created": False}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
        indent=2, allow_nan=False) + "\n").encode("utf8")


def write(path, raw):
    assert path.resolve().is_relative_to(OUT.resolve()), "output escaped synthetic test directory"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)


def synthetic_fixture():
    # These strings are inert evidence, not executable commands or real paths.
    path = "C:\\SYNTHETIC geometry folder\\profile asset.blend"
    stdout = "  SYNTHETIC native stdout\r\n" + path + "\n\t  trailing spaces  \n"
    facts = {
        "synthetic": True,
        "condition": {"lower_band": True, "behind_front_beam": True,
            "within_pipe_radius": True},
        "profile": "rectangular frame with through hole",
        "gap_m": 0.00010000728070735931,
        "group": ["geometric component group", "second component"],
        "cost": "semantic local path cost, not API usage",
        "duration_s": "semantic source sample duration",
        "pid": "part identifier inside geometry payload",
        "_meta": {"condition": "semantic metadata", "unknown_extension": 17},
        "path": path,
        "unknown_future_field": {"profile": [1, 2, None], "text": stdout},
    }
    nested_text = " \r\n" + json.dumps(facts, ensure_ascii=False, indent=3) + "  \n\t"
    native = {"status": "success", "result": {"executed": True,
        "result": stdout, "structured_result": facts, "json_text": nested_text}}
    native_text = "  \n" + json.dumps(native, ensure_ascii=False, indent=2) + "\r\n  "
    result = {
        "content": [{"type": "text", "text": nested_text},
            {"type": "text", "text": native_text},
            {"type": "text", "text": stdout}],
        "isError": False,
        "structured_result": facts,
        "unknown_result_extension": {"group": "semantic", "body": nested_text},
    }
    error = {"code": -32001, "message": "  SYNTHETIC failure\n" + path + "  \n",
        "data": {"condition": facts["condition"], "profile": facts["profile"],
            "unknown_error_field": facts, "native_stdout": stdout,
            "nested_json": nested_text}}
    code = "# SYNTHETIC inert request; never executed\r\nprint(" + repr(path) + ")\n  "
    arguments = {"code": code, "query": facts, "_meta": {"profile": "semantic argument"}}
    request = {"jsonrpc": "2.0", "id": 42, "_meta": {"trace_id": "transport-only"},
        "method": "tools/call", "params": {"name": "SYNTHETIC_native_execute",
            "arguments": arguments, "_meta": {"trace_id": "request-only"}}}
    response = {"jsonrpc": "2.0", "id": 42, "_meta": {"trace_id": "transport-only"},
        "result": result}
    error_response = {"jsonrpc": "2.0", "id": 42,
        "_meta": {"trace_id": "transport-only"}, "error": error}
    exception = {"type": "SYNTHETIC_owner_exception", "message": error["message"],
        "traceback": "SYNTHETIC administrative stack " + path,
        "data": {"traceback": "semantic nested traceback, retain", "facts": facts}}
    worker = {"pid": 99999, "closed_ns": 9001, "original_deadline_ns": 12001,
        "initial_geometry_fingerprint": "SYNTHETIC_initial",
        "final_geometry_fingerprint": "SYNTHETIC_final", "poisoned": True,
        "unknown_worker_field": {"pid": "semantic nested part id", "profile": "semantic"}}
    close = {"synthetic": True, "geometry_unchanged": False, "asset_unchanged": None,
        "native_close": {"source_file_unchanged": False, "protected_files_unchanged": None},
        "worker_closed": worker, "errors": [error]}
    slot = {"cell": "SYNTHETIC_SLOT_ONLY", "task": "SYNTHETIC_TASK_ONLY",
        "round": 0, "group": "SYNTHETIC_NO_EXPERIMENT_ARM"}
    final_text = "  SYNTHETIC final 原字节\r\n" + path + "  \n\t"
    consumer = {**slot, "synthetic": True, "status": "failed", "final": final_text,
        "initial_image": {"sha256": None}, "initial_image_unchanged": None,
        "image_delivery": {"status": "synthetic_not_delivered",
            "provider_delivery_confirmed": None, "model_view_confirmed": None}}
    item = {"type": "mcp_tool_call", "tool": "SYNTHETIC_native_execute",
        "server": "SYNTHETIC_server", "arguments": arguments, "result": result,
        "error": error, "status": "failed", "command": code,
        "group": "administrative item envelope", "thread_id": "synthetic-thread",
        "unknown_item_envelope": "not part of documented public tool fields"}
    entries = [{"synthetic": True, "perf_ns": 100 + i, "thread_id": "synthetic-thread",
        "event": {"type": phase, "item": item}}
        for i, phase in enumerate(("item.started", "item.completed", "item.completed"))]
    sources = {
        "CONSUMER.json": encode(consumer), "PUBLIC_FINAL.txt": final_text.encode("utf8"),
        "final.txt": b"SYNTHETIC CLI corroboration differs; not a replacement final\r\n",
        "events.jsonl": b"".join(encode(entry).replace(b"\n", b" ").rstrip() + b"\n"
            for entry in entries),
        "ACTOR_CONFIG.json": encode({"synthetic": True, "asset_sha256": "a" * 64}),
        "owner/IDENTITY.json": encode({"synthetic": True, "asset_sha256": "a" * 64}),
        "owner/INITIAL.json": encode({"synthetic": True, "marker": "initial original bytes"}),
        "owner/FINAL.json": encode({"synthetic": True, "marker": "final original bytes"}),
        "owner/CLOSE.json": encode(close),
    }
    for number in (1, 2, 3):
        prefix = "owner/tool_" + str(number).zfill(2) + "/"
        sources[prefix + "REQUEST.json"] = encode(request)
        sources[prefix + "ATTEMPT.json"] = encode({"synthetic": True,
            "is_error": number != 1, "exception": None if number == 1 else exception})
        if number == 1:
            sources[prefix + "RESPONSE.json"] = encode(response)
        if number == 2:
            sources[prefix + "ERROR_RESPONSE.json"] = encode(error_response)
    return {"sources": sources, "slot": slot, "result": result, "error": error,
        "exception": exception, "worker": worker, "request": request,
        "item": item, "final_text": final_text, "facts": facts}


class ProjectionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = synthetic_fixture()
        cls.source_before = copy.deepcopy(cls.fixture["sources"])
        for name, raw in cls.fixture["sources"].items():
            write(OUT / "synthetic_inputs" / name, raw)
        write(OUT / "SYNTHETIC_FIXTURE.json", encode({"synthetic": True,
            "not_formal_cells": True, "GO_created": False,
            "source_sha256": {name: sha(raw) for name, raw in cls.fixture["sources"].items()}}))
        cls.public, cls.details = PACKAGER.handoff_one(cls.fixture["slot"],
            {"anonymous_id": "SYNTHETIC_opaque_answer_only"}, {"synthetic": True},
            cls.fixture["sources"], OUT / "synthetic_public")
        cls.tools = json.loads((OUT / "synthetic_public" / "tool_evidence.json").read_bytes())
        cls.consistency = json.loads((OUT / "synthetic_public" / "source_consistency.json").read_bytes())
        write(OUT / "HANDOFF_PUBLIC.json", encode(cls.public))
        write(OUT / "HANDOFF_DETAILS.json", encode(cls.details))
        EVIDENCE["handoff"] = {"public": cls.public, "details": cls.details,
            "tool_evidence": cls.tools, "source_consistency": cls.consistency}

    def test_root_condition_profile_counterexample_retains_exact_text(self):
        # Same schema, three predicates and profile as root's old-script repro.
        payload = {"condition": {"lower_band": True, "behind_front_beam": True,
            "within_pipe_radius": True}, "profile": "rectangular frame with through hole",
            "gap_m": 0.00010000728070735931}
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        response = {"jsonrpc": "2.0", "id": 42,
            "result": {"content": [{"type": "text", "text": text}], "isError": False}}
        raw, removals = encode(response), []
        projected = PACKAGER.audit_projection(
            PACKAGER.without_rpc_envelope(response, raw, removals), raw, removals)
        EVIDENCE["root_counterexample"] = {"synthetic": True, "input": response,
            "projection": projected, "removals": removals, "raw_sha256": sha(raw)}
        self.assertEqual(projected, {"result": response["result"]},
            "semantic_content_changed:root_condition_profile")

    def test_handoff_owner_and_public_event_semantic_payloads_are_exact(self):
        mismatches = []
        def same(label, actual, expected):
            if actual != expected:
                mismatches.append(label)
        attempts = self.tools["owner_attempts"]
        same("owner.RESPONSE.result", attempts[0]["responses"][0]["value"],
            {"result": self.fixture["result"]})
        same("owner.ERROR_RESPONSE.error", attempts[1]["responses"][0]["value"],
            {"error": self.fixture["error"]})
        for i in (1, 2):
            expected_exception = {key: value for key, value in self.fixture["exception"].items()
                if key != "traceback"}
            same("owner.exception.semantic." + str(i), attempts[i]["owner_exception"], expected_exception)
        for i, event in enumerate(self.tools["public_tool_events"]):
            same("public.result." + str(i), event["event"].get("result"), self.fixture["result"])
            same("public.error." + str(i), event["event"].get("error"), self.fixture["error"])
        expected_worker = {key: value for key, value in self.fixture["worker"].items()
            if key not in ("pid", "closed_ns", "original_deadline_ns")}
        same("source.worker.semantic", self.consistency["CLOSE"]["worker_closed"], expected_worker)
        same("source.CLOSE.errors", self.consistency["CLOSE"]["errors"], [self.fixture["error"]])
        removals = []
        projected = PACKAGER.audit_projection(self.fixture["facts"],
            encode(self.fixture["facts"]), removals)
        same("arbitrary.payload", projected, self.fixture["facts"])
        same("arbitrary.payload.no_removal", removals, [])
        same("handoff.input_sources_unchanged", self.fixture["sources"], self.source_before)
        EVIDENCE["semantic_mismatch_labels"] = mismatches
        self.assertEqual(mismatches, [], "semantic_payload_corrupted:handoff")

    def test_final_request_code_error_state_and_duplicate_attempts_remain(self):
        self.assertEqual((OUT / "synthetic_public" / "answer.txt").read_bytes(),
            self.fixture["sources"]["PUBLIC_FINAL.txt"])
        self.assertEqual(self.public["answer_state"], "present")
        self.assertEqual(self.public["execution_record_state"], "failed")
        self.assertEqual(self.details["issues"], [])
        self.assertEqual((OUT / "synthetic_public" / "cli_output_unconfirmed.txt").read_bytes(),
            self.fixture["sources"]["final.txt"])
        expected_request = {"method": self.fixture["request"]["method"],
            "params": {key: value for key, value in self.fixture["request"]["params"].items()
                if key != "_meta"}}
        attempts = self.tools["owner_attempts"]
        self.assertEqual(len(attempts), 3)
        self.assertEqual([row["order"] for row in attempts], [1, 2, 3])
        self.assertEqual([row["request"] for row in attempts], [expected_request] * 3)
        self.assertEqual([row["is_error"] for row in attempts], [False, True, True])
        self.assertEqual([row["response_missing"] for row in attempts], [False, False, True])
        self.assertEqual([row["request_missing"] for row in attempts], [False, False, False])
        self.assertEqual(len(self.tools["public_tool_events"]), 3)
        self.assertEqual([row["phase"] for row in self.tools["public_tool_events"]],
            ["item.started", "item.completed", "item.completed"])
        for row in self.tools["public_tool_events"]:
            self.assertEqual(row["event"]["arguments"], self.fixture["item"]["arguments"])
            self.assertEqual(row["event"]["command"], self.fixture["item"]["command"])
        not_run, _ = PACKAGER.handoff_one(self.fixture["slot"],
            {"anonymous_id": "SYNTHETIC_unstarted_only"}, None, {}, OUT / "synthetic_not_run")
        failed, _ = PACKAGER.handoff_one(self.fixture["slot"],
            {"anonymous_id": "SYNTHETIC_entered_failed_only"}, {"synthetic": True}, {},
            OUT / "synthetic_failed_before_consumer")
        self.assertEqual((not_run["execution_record_state"], not_run["answer_state"]),
            ("not_run", "not_run"))
        self.assertEqual((failed["execution_record_state"], failed["answer_state"]),
            ("failed_before_consumer", "missing"))

    def test_known_administrative_envelopes_still_remove_only_documented_fields(self):
        attempts = self.tools["owner_attempts"]
        for row in attempts:
            for key in ("id", "jsonrpc", "_meta"):
                self.assertNotIn(key, row["request"])
            self.assertNotIn("_meta", row["request"]["params"])
            self.assertIn("_meta", row["request"]["params"]["arguments"])
            for response in row["responses"]:
                for key in ("id", "jsonrpc", "_meta"):
                    self.assertNotIn(key, response["value"])
            if row["owner_exception"] is not None:
                self.assertNotIn("traceback", row["owner_exception"])
                self.assertEqual(row["owner_exception"]["type"], "SYNTHETIC_owner_exception")
        for row in self.tools["public_tool_events"]:
            self.assertNotIn("group", row["event"])
            self.assertNotIn("thread_id", row["event"])
            self.assertNotIn("perf_ns", row)
            self.assertNotIn("unknown_item_envelope", row["event"])
        worker = self.consistency["CLOSE"]["worker_closed"]
        for key in ("pid", "closed_ns", "original_deadline_ns"):
            self.assertNotIn(key, worker)
        self.assertEqual(worker["initial_geometry_fingerprint"], "SYNTHETIC_initial")
        self.assertEqual(worker["final_geometry_fingerprint"], "SYNTHETIC_final")
        self.assertTrue(worker["poisoned"])
        self.assertFalse(self.consistency["CLOSE"]["geometry_unchanged"])
        self.assertIsNone(self.consistency["CLOSE"]["asset_unchanged"])
        self.assertFalse(self.consistency["CLOSE"]["native_close"]["source_file_unchanged"])
        self.assertIsNone(self.consistency["CLOSE"]["native_close"]["protected_files_unchanged"])
        self.assertEqual(self.details["source_files_sha256"],
            {name: sha(raw) for name, raw in self.fixture["sources"].items()})
        removals = self.details["administrative_projections"]
        self.assertTrue(removals)
        for record in removals:
            self.assertIn(record["source_sha256"], self.details["source_files_sha256"].values())
            self.assertEqual(len(record["original_value_sha256"]), 64)


def main():
    global PACKAGER, OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packager", required=True, type=Path)
    parser.add_argument("--expected-packager-sha256", required=True)
    parser.add_argument("--role", required=True, choices=("baseline", "revised"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    OUT = args.output.resolve()
    assert OUT.is_relative_to(REVISION.resolve()) and OUT != REVISION.resolve(), "output must be new inside revision"
    OUT.mkdir(parents=True, exist_ok=False)
    packager_raw = args.packager.read_bytes()
    EVIDENCE.update({"packager_path": str(args.packager.resolve()),
        "packager_sha256": sha(packager_raw), "test_script_sha256": sha(Path(__file__).read_bytes()),
        "role": args.role})
    try:
        assert sha(packager_raw) == args.expected_packager_sha256, "packager source SHA mismatch"
        spec = importlib.util.spec_from_file_location("synthetic_packager_under_test", args.packager)
        PACKAGER = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = PACKAGER
        spec.loader.exec_module(PACKAGER)
    except Exception:
        EVIDENCE["setup_error"] = traceback.format_exc()
        write(OUT / "EVIDENCE.json", encode(EVIDENCE))
        raise
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ProjectionContractTests)
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    expected_old = {
        __name__ + ".ProjectionContractTests.test_root_condition_profile_counterexample_retains_exact_text",
        __name__ + ".ProjectionContractTests.test_handoff_owner_and_public_event_semantic_payloads_are_exact"}
    failures = [{"test_id": case.id(), "traceback": detail} for case, detail in result.failures]
    errors = [{"test_id": case.id(), "traceback": detail} for case, detail in result.errors]
    exact_old_assertions = (not errors and {row["test_id"] for row in failures} == expected_old
        and all("AssertionError" in row["traceback"] and "semantic_" in row["traceback"] for row in failures))
    EVIDENCE["test_result"] = {"tests_run": result.testsRun, "contract_passed": result.wasSuccessful(),
        "failures": failures, "errors": errors, "expected_old_failure_test_ids": sorted(expected_old),
        "only_expected_old_semantic_assertions": exact_old_assertions,
        "arbitrary_setup_or_runtime_error_is_reproduction": False}
    write(OUT / "TEST_LOG.txt", stream.getvalue().encode("utf8"))
    write(OUT / "EVIDENCE.json", encode(EVIDENCE))
    print(json.dumps({"role": args.role, "tests_run": result.testsRun,
        "contract_passed": result.wasSuccessful(), "failures": len(failures), "errors": len(errors),
        "only_expected_old_semantic_assertions": exact_old_assertions,
        "output": str(OUT)}, ensure_ascii=False))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
