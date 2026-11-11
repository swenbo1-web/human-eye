"""Run only synthetic profile-API and static QA boundary checks."""

import argparse
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import traceback
import types
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
HELPER = BATCH / "entry/qa_instrumentation.py"
NATIVE = BATCH / "entry/qa_native.py"
TEST = HERE / "test_profile_switch.py"
ANALYSIS = BATCH / "analysis/analyze_saved.py"
SCHEDULE = BATCH / "SCHEDULE.json"
OLD_NATIVE = BATCH.parent / "m4_relation_selected_evidence_001/entry/qa_native.py"
ENTRY = BATCH / "entry/run_entry.py"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    with path.open("x", encoding="utf8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--expected-helper-sha256", required=True)
    parser.add_argument("--expected-entry-sha256", required=True)
    arguments = parser.parse_args()
    output = HERE / arguments.output
    assert output.parent.resolve() == HERE.resolve() and output.name not in (".", "..")
    output.mkdir(exist_ok=False)
    helper_raw, native_raw, test_raw = HELPER.read_bytes(), NATIVE.read_bytes(), TEST.read_bytes()
    analysis_raw, schedule_raw = ANALYSIS.read_bytes(), SCHEDULE.read_bytes()
    old_native_raw = OLD_NATIVE.read_bytes()
    entry_raw = ENTRY.read_bytes()
    assert sha(helper_raw) == arguments.expected_helper_sha256
    assert sha(entry_raw) == arguments.expected_entry_sha256
    (output / "HELPER_SOURCE.py").write_bytes(helper_raw)
    (output / "NATIVE_SOURCE.py").write_bytes(native_raw)
    (output / "TEST_SOURCE.py").write_bytes(test_raw)
    (output / "ENTRY_SOURCE.py").write_bytes(entry_raw)
    real_profile = sys.getprofile()
    attempts = []

    def forbidden(*args, **kwargs):
        attempts.append("external process/network/signal")
        raise AssertionError(attempts[-1])

    stdout, stderr, test_log = io.StringIO(), io.StringIO(), io.StringIO()
    result, error, evidence = None, None, {}
    try:
        with ExitStack() as stack, redirect_stdout(stdout), redirect_stderr(stderr):
            for name in ("Popen", "run", "call", "check_call", "check_output"):
                stack.enter_context(patch.object(subprocess, name, side_effect=forbidden))
            for name in ("system", "kill"):
                stack.enter_context(patch.object(os, name, side_effect=forbidden))
            for name in ("socket", "create_connection"):
                stack.enter_context(patch.object(socket, name, side_effect=forbidden))
            helper = types.ModuleType("_latency_attribution_profile_QA")
            helper.__file__ = str(HELPER)
            sys.modules[helper.__name__] = helper
            exec(compile(helper_raw, str(HELPER), "exec", dont_inherit=True), helper.__dict__)
            module = types.ModuleType("_latency_attribution_profile_tests")
            module.__file__ = str(TEST)
            module.QA = helper
            module.NATIVE_SOURCE = native_raw
            module.ENTRY_SOURCE = entry_raw
            module.EVIDENCE = {}
            analyzer = types.ModuleType("_latency_saved_analysis_for_synthetic_checks")
            analyzer.__file__ = str(ANALYSIS)
            sys.modules[analyzer.__name__] = analyzer
            exec(compile(analysis_raw, str(ANALYSIS), "exec", dont_inherit=True), analyzer.__dict__)
            module.ANALYZER = analyzer
            module.SCHEDULE = json.loads(schedule_raw)
            sys.modules[module.__name__] = module
            exec(compile(test_raw, str(TEST), "exec", dont_inherit=True), module.__dict__)
            suite = unittest.defaultTestLoader.loadTestsFromTestCase(module.ProfileSwitchTests)
            result = unittest.TextTestRunner(stream=test_log, verbosity=2).run(suite)
            evidence = module.EVIDENCE
            json.dumps(evidence, allow_nan=False)
    except BaseException:
        error = traceback.format_exc()
    for name, content in (("STDOUT.txt", stdout.getvalue()), ("STDERR.txt", stderr.getvalue()), ("TESTS.txt", test_log.getvalue())):
        (output / name).write_text(content, encoding="utf8", newline="\n")
    if error:
        (output / "RUNNER_EXCEPTION.txt").write_text(error, encoding="utf8", newline="\n")
    profile_unchanged = sys.getprofile() is real_profile
    sources_unchanged = (HELPER.read_bytes() == helper_raw and NATIVE.read_bytes() == native_raw
                         and TEST.read_bytes() == test_raw and ANALYSIS.read_bytes() == analysis_raw
                         and SCHEDULE.read_bytes() == schedule_raw and OLD_NATIVE.read_bytes() == old_native_raw)
    sources_unchanged = sources_unchanged and ENTRY.read_bytes() == entry_raw
    passed = bool(result and result.wasSuccessful() and not error and not attempts and profile_unchanged and sources_unchanged)
    summary = {"cycle_id": "M4-DEFAULT-LATENCY-ATTRIBUTION-001", "synthetic": True,
        "passed": passed, "test_methods": 0 if result is None else result.testsRun,
        "failures": [] if result is None else [{"test": test.id(), "traceback": failure} for test, failure in result.failures],
        "errors": [] if result is None else [{"test": test.id(), "traceback": failure} for test, failure in result.errors],
        "runner_exception": error, "real_process_profile_unchanged": profile_unchanged,
        "helper_source_sha256": sha(helper_raw), "native_source_sha256": sha(native_raw),
        "analysis_source_sha256": sha(analysis_raw), "schedule_sha256": sha(schedule_raw),
        "old_native_source_sha256": sha(old_native_raw),
        "entry_source_sha256": sha(entry_raw),
        "test_source_sha256": sha(test_raw), "runner_sha256": sha(Path(__file__).read_bytes()),
        "all_tested_sources_unchanged": sources_unchanged, "external_operation_attempts": attempts,
        "model_consumers": 0, "Blender_sessions": 0, "product_business_processes": 0,
        "scope": "actual QA helper with a private fake sys profile API and fake host samples; static native protection/cleanup checks"}
    save(output / "RESULTS.json", summary)
    save(output / "EVIDENCE.json", evidence)
    print(json.dumps(summary, ensure_ascii=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
