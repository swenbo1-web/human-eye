"""Phase-aware offline regression with post-close artifacts made unavailable."""

import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import read_capture_candidate as candidate

check = candidate.qualification
ROOT = check.ROOT
CELL = ROOT / "verification/m4_surface_scan_continuity_001_fix1/episodes/C"


@contextlib.contextmanager
def before_response_phase(workspace, sequence, substitutions=None):
    """Deny any archive, closed-worker record or future call file access."""
    workspace = Path(workspace)
    original_read, original_open = Path.read_bytes, Path.open
    events_path = workspace / "WORKER_EVENTS.jsonl"
    lines = original_read(events_path).splitlines()
    events = [json.loads(line) for line in lines]
    prefix = b"".join(line + b"\n" for line, event in zip(lines, events)
                      if type(event.get("sequence")) is int and event["sequence"] <= sequence)
    replacements = {events_path: prefix, **(substitutions or {})}
    denied = []
    def available(path):
        blocked = "WIRE" in path.parts or path.name in ("WORKER_CLOSED.json", "FINAL.json")
        calls = [part for part in path.parts if part.startswith("call_") and part[5:].isdigit()]
        blocked = blocked or any(int(part[5:]) > sequence for part in calls)
        if blocked:
            denied.append(str(path))
            raise FileNotFoundError(2, "artifact unavailable before response/worker close", str(path))
    def read_phase(path):
        available(path)
        if path in replacements:
            return replacements[path]
        return original_read(path)
    def open_phase(path, mode="r", *args, **kwargs):
        available(path)
        if path in replacements:
            return io.BytesIO(replacements[path]) if "b" in mode else io.StringIO(replacements[path].decode("utf8"))
        return original_open(path, mode, *args, **kwargs)
    with patch.object(Path, "read_bytes", read_phase), patch.object(Path, "open", open_phase):
        yield denied


def actual_case():
    row = json.loads((CELL / "TURN_BASE.json").read_bytes())
    source = json.loads((CELL / "owner/INITIAL.json").read_bytes())
    audit = [json.loads(line) for line in (CELL / "owner/audit.jsonl").read_bytes().splitlines()]
    events = [json.loads(line) for line in (CELL / "owner/native/WORKER_EVENTS.jsonl").read_bytes().splitlines()]
    host = [event for event in events if row["started_ns"] <= event.get("started_ns", -1) <= row["ended_ns"]]
    return row, source, audit, host


def actual_runner():
    path = check.HERE.parent / "engineering/run_candidate.py"
    spec = importlib.util.spec_from_file_location("_fix1_phase_runner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CapturePhaseTests(unittest.TestCase):
    def test_original_reader_fails_at_actual_unavailable_archive(self):
        _, _, _, host = actual_case()
        workspace = CELL / "owner/native"
        with before_response_phase(workspace, host[0]["sequence"]) as denied:
            with self.assertRaises(FileNotFoundError):
                check.read_capture(workspace, host[0])
        self.assertEqual(len(denied), 1)
        self.assertTrue(denied[0].endswith("WIRE\\INDEX.json") or denied[0].endswith("WIRE/INDEX.json"))

    def test_real_runner_entry_uses_only_available_capture_outputs(self):
        row, source, _, host = actual_case()
        workspace = CELL / "owner/native"
        proxy = types.SimpleNamespace(read_capture=candidate.read_capture, verify_c_turn=check.verify_c_turn)
        with before_response_phase(workspace, host[0]["sequence"]) as denied:
            result = actual_runner().verify_business(copy.deepcopy(row), CELL, source, proxy)
        self.assertEqual(denied, [])
        self.assertEqual((result["matches"], result["new_kernel_calls"], result["actual_host_capture_count"]), (71, 112, 1))
        self.assertEqual(result["capture_report"]["wire_sources"], [])
        original = json.loads((CELL / "RESULTS.json").read_bytes())
        self.assertFalse(original["passed_before_publication"])
        self.assertEqual(original["execution_counts"], {"planned": 3, "attempted": 1, "completed": 0, "failed": 1, "not_run": 2})

    def test_current_outputs_equal_later_wire_without_becoming_send_evidence(self):
        _, _, _, host = actual_case()
        workspace = CELL / "owner/native"
        with before_response_phase(workspace, host[0]["sequence"]) as denied:
            current = candidate.read_capture(workspace, host[0])
        archived = check.read_capture(workspace, host[0])
        for field in ("sequence", "script_sha256", "delta", "retained_resources", "resource_origins"):
            self.assertEqual(current[field], archived[field])
        self.assertEqual(denied, [])
        self.assertEqual(current["wire_sources"], [])
        self.assertTrue(current["capture_sources"])
        self.assertIn("before response send", current["evidence_phase"])
        number = host[0]["sequence"]
        call = workspace / ("call_" + str(number))
        request = json.loads((workspace / ("WIRE/%03d/REQUEST.bin" % number)).read_bytes())
        response = json.loads((workspace / ("WIRE/%03d/RESPONSE.bin" % number)).read_bytes())
        code = candidate.logical_bytes((call / "SCRIPT.py").read_bytes(), expected_sha=host[0]["script_sha256"])
        stdout = candidate.logical_bytes((call / "stdout.txt").read_bytes(), expected_size=host[0]["stdout_bytes"])
        self.assertEqual(code, request["params"]["code"].encode("utf8"))
        self.assertEqual(stdout, response["result"]["result"].encode("utf8"))

    def test_historical_repeat_and_edit_resolve_zero_resource_outputs(self):
        prior = ROOT / "verification/m4_surface_scan_compact_facts_001/engineering/run_01"
        record = json.loads((prior / "RESULTS.json").read_bytes())
        audit = [json.loads(line) for line in (prior / "audit.jsonl").read_bytes().splitlines()]
        for label, turn, state in (("base_brief", "REPEAT", "base"), ("edit_default", "EDIT", "edit")):
            row = copy.deepcopy(next(row for row in record["business"] if row["state"] == label))
            row["request"]["params"]["arguments"].pop("response_detail", None)
            source = json.loads((prior / (state + "_ACTUAL_SNAPSHOT.json")).read_bytes())
            host = row["work_events"]
            with self.subTest(turn=turn), before_response_phase(prior / "native", host[0]["sequence"]) as denied:
                capture = candidate.read_capture(prior / "native", host[0])
                result = check.verify_c_turn(row["body"], audit, host, source, turn, row["request"], capture=capture)
            self.assertEqual(denied, [])
            self.assertEqual(result["capture_report"]["transmitted_resources_this_capture"], 0)
            self.assertEqual(result["capture_report"]["resolved_resource_count"], 24)
            self.assertEqual(result["matches"], check.EXPECTED_MATCHES[turn])
            self.assertEqual(result["new_kernel_calls"], check.EXPECTED_KERNELS[turn])

    def test_available_output_or_event_tampering_rejected(self):
        _, _, _, host = actual_case()
        workspace = CELL / "owner/native"
        event = host[0]
        call = workspace / ("call_" + str(event["sequence"]))
        for filename in ("SCRIPT.py", "stdout.txt", "stderr.txt"):
            path = call / filename
            changed = path.read_bytes() + b"tampered"
            with self.subTest(file=filename), before_response_phase(workspace, event["sequence"], {path: changed}):
                with self.assertRaisesRegex(AssertionError, "unique_worker_text_reconstruction"):
                    candidate.read_capture(workspace, event)
        for field, value in (("terminal_geometry_and_file_checks_passed", False), ("script_error", {"type": "fail"}),
                             ("changed_or_new_PNG_files", ["unexpected.png"]), ("render_events_after", 1)):
            events_path = workspace / "WORKER_EVENTS.jsonl"
            events = [json.loads(line) for line in events_path.read_bytes().splitlines() if json.loads(line).get("sequence", 999) <= event["sequence"]]
            selected = next(row for row in events if row.get("sequence") == event["sequence"])
            selected[field] = value
            replacement = b"".join(json.dumps(row).encode("utf8") + b"\n" for row in events)
            reason = "completed_worker_output" if field == "script_error" else "worker_output_terminal_protection" if field == "terminal_geometry_and_file_checks_passed" else "worker_output_zero_images"
            with self.subTest(event_field=field), before_response_phase(workspace, event["sequence"], {events_path: replacement}):
                with self.assertRaisesRegex(AssertionError, reason):
                    candidate.read_capture(workspace, selected)

    def test_same_size_output_tampering_rejected_by_active_validator(self):
        row, source, audit, host = actual_case()
        event = host[0]
        workspace = CELL / "owner/native"
        stdout_path = workspace / ("call_" + str(event["sequence"])) / "stdout.txt"
        logical = candidate.logical_bytes(stdout_path.read_bytes(), expected_size=event["stdout_bytes"])
        variants = (b'"scale_length":1.0', b'"scale_length": 1.0')
        token = next(token for token in variants if token in logical)
        changed = logical.replace(token, token.replace(b"1.0", b"2.0"), 1)
        self.assertEqual(len(logical), len(changed))
        with before_response_phase(workspace, event["sequence"], {stdout_path: changed}) as denied:
            capture = candidate.read_capture(workspace, event)
            with self.assertRaisesRegex(AssertionError, "capture_unit_scale"):
                check.verify_c_turn(row["body"], audit, host, source, "BASE", row["request"], capture=capture)
        self.assertEqual(denied, [])

    def test_text_reconstruction_is_bounded_and_preserves_content(self):
        raw = b"one\r\ntwo\r\n"
        expected = b"one\ntwo\n"
        self.assertEqual(candidate.logical_bytes(raw, expected_size=len(expected)), expected)
        self.assertEqual(candidate.logical_bytes(raw, expected_sha=check.digest(expected)), expected)
        self.assertEqual(candidate.logical_bytes(raw, expected_size=len(raw)), raw)
        with self.assertRaisesRegex(AssertionError, "unique_worker_text_reconstruction"):
            candidate.logical_bytes(raw)
        with self.assertRaisesRegex(AssertionError, "unique_worker_text_reconstruction"):
            candidate.logical_bytes(raw, expected_size=1)


def main():
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CapturePhaseTests))
    attempt = len(list(HERE.glob("PHASE_TEST_*.json"))) + 1
    summary = {"schema": "capture_phase_offline_regression_v1", "attempt": attempt,
               "test_methods": result.testsRun, "passed": result.wasSuccessful(),
               "failures": len(result.failures), "errors": len(result.errors), "new_live_API_calls": 0,
               "fixture_scope": "actual failed FIX1 C BASE plus historical zero-resource repeat/edit output; archives and closed records denied during candidate validation"}
    (HERE / ("PHASE_TEST_%02d.json" % attempt)).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf8", newline="\n")
    (HERE / ("PHASE_TEST_%02d.txt" % attempt)).write_text(stream.getvalue(), encoding="utf8", newline="\n")
    print(json.dumps(summary))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
