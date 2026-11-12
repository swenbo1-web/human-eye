"""Run the bounded offline scan/display regression set and preserve attempts."""

from __future__ import annotations

import ast
import hashlib
import importlib
import inspect
import io
import json
from pathlib import Path
import sys
import time
import unittest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))

TARGETS = (
    "verification.m4_surface_scan_compact_facts_001.semantics.test_compact_semantics",
    "verification.m4_surface_scan_001.tests.test_entry",
    "verification.m4_surface_scan_001.tests.test_surface_scan",
    "verification.m4_surface_scan_001_opt1.tests.test_entry",
    "verification.test_live_spatial_mcp",
    "verification.test_task_brief_independent",
    "verification.test_structure_task_brief",
    "verification.test_segment_brief_independent",
    "verification.test_mcp_request_isolation.FramingAndEnvelopeTests",
    "verification.test_mcp_request_isolation.PublicationIsolationTests",
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def main():
    attempts = HERE / "attempts"
    attempts.mkdir(exist_ok=True)
    index = 1
    while (attempts / f"run_{index:02d}").exists():
        index += 1
    folder = attempts / f"run_{index:02d}"
    folder.mkdir()
    source = ROOT / "human_eye_plugin/live_spatial_mcp.py"
    before = source.read_bytes()
    ast.parse(before.decode("utf8"))
    output = io.StringIO()
    segment = importlib.import_module("verification.test_segment_brief_independent")
    segment.BASELINE = Path("D:/hefe/verification/fixes/20261030_v1_agent_entry")
    fixture_sources = []
    for name, expected in segment.WIRE_SHA256.items():
        path = segment.BASELINE / name
        data = path.read_bytes()
        assert sha(data) == expected
        fixture_sources.append(dict(path=str(path), bytes=len(data), sha256=sha(data)))
    started = time.perf_counter_ns()
    loader = unittest.TestLoader()
    selected = list(flatten(unittest.TestSuite(loader.loadTestsFromName(target) for target in TARGETS)))
    external_schema_case = "verification.m4_surface_scan_001.tests.test_entry.EntryTests.test_schema_matches_new_and_existing_threshold_contracts"
    excluded = [test.id() for test in selected if test.id() == external_schema_case]
    assert excluded == [external_schema_case]
    suite = unittest.TestSuite(test for test in selected if test.id() != external_schema_case)
    result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
    ended = time.perf_counter_ns()
    unchanged = before == source.read_bytes()
    record = {
        "schema": "surface_scan_compact_semantics_run_v1",
        "run": index,
        "python": sys.executable,
        "isolation": "-I -B -X utf8",
        "new_Blender_model_business_API_runs": 0,
        "targets": list(TARGETS),
        "predefined_suite_method_count": len(selected),
        "old_schema_methods_not_executed_in_python312": excluded,
        "schema_equivalent_case_notes": "The original EntryTests schema method is omitted from the Python 3.12 suite. Its positive and negative contract cases are included in the new exported-schema test, validated by the existing Python 3.14 jsonschema runtime.",
        "schema_environment_reason": "Candidate dependency Python 3.12 has no jsonschema. Existing cached jsonschema/rpds binary supports Python 3.14, used only for exported-schema validation.",
        "fixture_adaptation": {"module": "verification.test_segment_brief_independent", "constant": "BASELINE",
                               "read_only_sources": fixture_sources, "original_test_source_unchanged": True},
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "expected_failures": len(result.expectedFailures),
        "unexpected_successes": len(result.unexpectedSuccesses),
        "successful": result.wasSuccessful() and unchanged,
        "source_unchanged_during_run": unchanged,
        "product_source_sha256": sha(before),
        "test_source_sha256": sha((HERE / "test_compact_semantics.py").read_bytes()),
        "runner_source_sha256": sha(Path(__file__).read_bytes()),
        "elapsed_ns": ended - started,
        "failures_detail": [{"test": test.id(), "traceback": message} for test, message in result.failures],
        "errors_detail": [{"test": test.id(), "traceback": message} for test, message in result.errors],
        "learning_context": {"context_bound": False, "host_epoch": 5, "rebind_required": True},
        "scope": "Synthetic/mock host offline tests and existing local entry help checks. No new model consumers or Blender execution.",
    }
    tests = importlib.import_module("verification.m4_surface_scan_compact_facts_001.semantics.test_compact_semantics")
    record["external_schema_validation"] = tests.SCHEMA_RECORDS
    old_entry = importlib.import_module("verification.m4_surface_scan_001.tests.test_entry")
    record["old_schema_method_source_sha256"] = sha(inspect.getsource(
        old_entry.EntryTests.test_schema_matches_new_and_existing_threshold_contracts).encode("utf8"))
    record["old_schema_module_source_sha256"] = sha(Path(old_entry.__file__).read_bytes())
    record["validator_script_sha256"] = sha((HERE / "validate_schema.py").read_bytes())
    source_input = json.dumps(tests.SCHEMA_REQUESTS, ensure_ascii=False, indent=2) + "\n"
    (folder / "SCHEMA_INPUT.json").write_text(source_input, encoding="utf8")
    record["exported_schema_input_sha256"] = sha(source_input.encode("utf8"))
    module_prefix = "verification.m4_surface_scan_compact_facts_001.semantics.test_compact_semantics."
    selected_ids = [test.id() for test in selected if test.id() != external_schema_case]
    record["new_candidate_methods"] = sum(name.startswith(module_prefix) for name in selected_ids)
    record["existing_regression_methods"] = sum(not name.startswith(module_prefix) for name in selected_ids)
    record["executed_method_ids"] = selected_ids
    (folder / "STDOUT.txt").write_text(output.getvalue(), encoding="utf8", newline="\n")
    (folder / "RESULT.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    summary = {key: record[key] for key in ("run", "tests_run", "new_candidate_methods", "existing_regression_methods",
               "failures", "errors", "skipped", "successful", "source_unchanged_during_run", "product_source_sha256")}
    summary["external_schema_cases"] = sum(row["check_count"] for row in tests.SCHEMA_RECORDS)
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if record["successful"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
