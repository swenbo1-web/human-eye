"""Read existing stopped-batch artifacts without running an engine or renderer."""
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
RUN = BATCH / "runs" / "main_p01_A"


def read(path):
    return json.loads(Path(path).read_bytes().decode("utf-8-sig"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    frozen = read(BATCH / "FROZEN.json")
    outer = read(BATCH / "RESULTS.json")
    result = read(RUN / "RESULT.json")
    trace = [json.loads(line) for line in (RUN / "TRACE.jsonl").read_bytes().splitlines()]
    rows = outer["rows"]
    first = rows[0]
    checks = {}

    def check(name, condition):
        checks[name] = bool(condition)
        if not condition:
            raise ValueError(name)

    check("first_slot_identity", first["id"] == "main_p01_A")
    check("controller_first_slot_failed", first["status"] == "failed")
    check("controller_failure_is_binding", first["error"]["message"] == "child_process_or_output_binding")
    check("controller_returncode_zero", first["returncode"] == 0)
    check("worker_report_completed", result["status"] == "completed")
    check("output_directory_agrees", Path(first["output_directory"]).resolve() == RUN.resolve()
          == Path(result["output_directory"]).resolve())
    trace_pids = sorted({entry["process_id"] for entry in trace})
    check("trace_worker_pid_agrees", trace_pids == [result["process_id"]])
    check("controller_worker_pid_differ", first["process_id"] != result["process_id"])
    check("eleven_main_not_run", len(rows) == 12 and all(row["status"] == "not_run" for row in rows[1:]))
    check("two_controls_not_run", len(outer["controls"]) == 2
          and all(row["status"] == "not_run" for row in outer["controls"]))
    check("no_comparative_time_claim", outer["summary"]["net_time_benefit"] is None)
    check("controller_gates_false", all(outer["summary"][key] is False for key in (
        "author_engineering_gate", "full_cost_gate", "main_workload_qualified", "control_qualified")))
    source_mismatches = [path for path, expected in frozen["runtime_sources"].items()
                         if digest(path) != expected]
    check("all_frozen_source_bytes_unchanged", not source_mismatches)

    # This module only reads published files and counts existing owner/RGB pixels.
    # It imports neither the coverage solver nor the renderer/product.
    spec = importlib.util.spec_from_file_location("active_coverage_002_readback", BATCH / "validate.py")
    validator = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = validator
    spec.loader.exec_module(validator)
    facts = validator.validate_run(RUN, "A", "main")
    event_counts = Counter(entry["event"] for entry in trace)
    check("six_durable_render_attempts", event_counts["render_attempt"] == 6
          == first["render_attempts"] == facts["render_attempts"])
    check("six_actual_render_completions", event_counts["render_complete"] == 6
          == result["metrics"]["raster_completed"] == facts["render_completed"])
    check("six_frame_readbacks", event_counts["frame_complete"] == 6
          == facts["validator_PNG_decodes"] == len(result["frames"]))
    actual_pixel_rows = sum(len(frame["pixel_rows"]) for frame in result["frames"])
    check("thirty_six_runtime_pixel_rows", actual_pixel_rows == 36
          == result["metrics"]["pixel_tests"] == facts["pixel_tests"])
    check("thirty_six_independent_readback_pixel_rows", facts["validator_pixel_tests"] == 36)
    check("fixed_six_view_order", facts["views"] == ["SCENE", "TOP", "LEFT", "RIGHT", "FRONT", "BACK"])
    repeat = result["repeat_query"]
    check("same_state_repeat_zero_new_render", repeat["new_render_attempts"] == 0
          == facts["repeat_query_new_render_attempts"] and repeat["state_before"] == repeat["state_after"]
          and repeat["render_attempts_before"] == repeat["render_attempts_after"] == 6)
    check("worker_old_evidence_audit_clear", result["audit"]["forbidden_old_evidence_reads"] == 0
          == result["audit"]["forbidden_old_writes"])

    input_paths = {Path(path) for path in frozen["runtime_sources"]}
    input_paths.update(Path(path) for path in frozen["parent_post_run_reference_only"])
    input_paths.update(path for path in RUN.rglob("*") if path.is_file())
    input_paths.update({BATCH / "RESULTS.json", BATCH / "FROZEN.json", BATCH / "BATCH_STARTED.json",
                        HERE / "LAUNCHER_METADATA.json", Path(__file__).resolve()})
    for name in ("STATIC_ADMISSION.md", "STATIC_RESULT.md", "PREPARATION_ADJUSTMENTS.md"):
        input_paths.add(HERE / name)
    report = {
        "schema": "m4_active_coverage_002_stopped_batch_review_v1",
        "decision": "strict_failed_stop_preserved",
        "checks": checks,
        "all_checks_passed": all(checks.values()),
        "scope": "Existing artifact SHA and pure readback only. No engine, solver, renderer or benchmark execution.",
        "new_engine_processes": 0,
        "new_render_attempts": 0,
        "additional_formal_samples": 0,
        "frozen_source_count": len(frozen["runtime_sources"]),
        "source_mismatches": source_mismatches,
        "controller": {
            "first_slot": first["id"], "first_slot_status": first["status"],
            "error": first["error"]["message"], "returncode": first["returncode"],
            "Popen_pid": first["process_id"], "worker_pid": result["process_id"],
            "trace_process_ids": trace_pids, "output_directory_agrees": True,
            "main_counts": dict(Counter(row["status"] for row in rows)),
            "control_counts": dict(Counter(row["status"] for row in outer["controls"])),
            "stop": outer["stop"], "first_failed_slot_elapsed_ns": first["elapsed_ns"],
            "elapsed_scope": "Failed slot original interval retained, including the binding failure. It is not a completed-arm performance sample."
        },
        "worker_artifact_review": {
            "reported_status": result["status"], "trace_event_counts": dict(event_counts),
            "runtime_pixel_rows": actual_pixel_rows,
            "frozen_validator_pure_readback_passed": True,
            "facts": facts
        },
        "pid_provenance": {
            "actual_parent_child_lineage": "unknown",
            "hypothesis": "A Windows venv launcher followed by its base interpreter is consistent with local executable and pyvenv metadata.",
            "limit": "The batch records no OS parent-child PID evidence. Local metadata alone does not establish that PID20368 is a descendant of PID23456.",
            "strict_status_reclassified": False,
            "metadata": "LAUNCHER_METADATA.json"
        },
        "conclusions": {
            "paired_B_evidence": "not_run",
            "pixel_shortfall_control": "not_run",
            "adaptive_main_scheduling": "not_run",
            "net_time_benefit": None,
            "comparative_performance": "unproven",
            "controller_summary": outer["summary"]
        },
        "inputs_sha256": {str(path.resolve()): digest(path) for path in sorted(input_paths)}
    }
    (HERE / "FINAL_REVIEW.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"checks": len(checks), "all_passed": report["all_checks_passed"],
                      "source_count": report["frozen_source_count"],
                      "input_bindings": len(report["inputs_sha256"]),
                      "strict_status": report["decision"], "raster_attempts": facts["render_attempts"],
                      "runtime_pixel_rows": actual_pixel_rows, "parent_child_pid": "unknown"}))


if __name__ == "__main__":
    main()
