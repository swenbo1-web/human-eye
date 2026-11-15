"""Collect phase-tree, controller and nested stage costs for the fixed study."""

import ctypes
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from process_runner import process_metrics


def read(name):
    return json.loads((HERE / name).read_bytes())


def main():
    started, cpu_started = time.perf_counter(), time.process_time()
    phases = {}
    for path in sorted((HERE / "private/processes").glob("*.controller.json")):
        label = path.name.removesuffix(".controller.json")
        worker = read("private/processes/" + label + ".json")
        controller = json.loads(path.read_bytes())
        phases[label] = {"worker_tree": worker, "controller": controller}
    audit, retrieval, trace = read("INPUT_AUDIT.json"), read("RETRIEVAL_RESULTS.json"), read("FROZEN_TRACE.json")
    report = {
        "cycle_id": "M6-SHAPE-OBSERVE-001",
        "phases": phases,
        "sequential_controller_main_wall_sum_s": sum(
            row["controller"]["wall_s_including_worker_before_write"] for row in phases.values()),
        "phase_worker_tree_CPU_sum_s": sum(row["worker_tree"]["tree_cpu_s"] for row in phases.values()),
        "phase_outer_controller_lifetime_CPU_before_final_write_sum_s": sum(
            row["controller"]["process_lifetime_before_final_write"]["cpu_s"] for row in phases.values()),
        "aggregation_scope": "each phase executed sequentially; stage CPU/wall below are nested breakdowns inside phase trees",
        "phase_controller_scope": "main wall excludes bootstrap/final report write; lifecycle CPU separately queried before final write; worker tree includes worker startup and exit",
        "tree_limit": "Toolhelp discovery every50ms can miss brief descendants; simultaneous tree working-set peak is sampled, individual process lifetime peaks retained",
        "input_audit": {"stages": audit["timings"],
                        "bootstrap_to_report_wall_s": audit["wall_s_before_final_report_write"],
                        "bootstrap_to_report_CPU_s": audit["cpu_s_before_final_report_write"],
                        "process_lifetime_before_report": audit["process_metrics_before_final_report_write"]},
        "retrieval": {"stages": retrieval["stages"],
                      "after_import_to_report_wall_s": retrieval["wall_s_after_imports_before_report"],
                      "after_import_to_report_CPU_s": retrieval["cpu_s_after_imports_before_report"],
                      "process_lifetime_before_report": retrieval["process_metrics_before_report"],
                      "sampled_queries_per_descriptor": 22272, "witness_queries_per_descriptor": 6,
                      "descriptors": 2, "k": 5,
                      "repeat_verification_queries": 24, "new_unique_QA_queries": 0},
        "frozen_trace": {"stages": trace["timings"], "process": trace["own_process_at_end"],
                         "actual_forwards": trace["actual_forward_calls"], "limit": 12},
        "visualization": {key: value for key, value in read("GEOMETRY_EVIDENCE.json").items()
                          if key in ("timings", "own_process_at_end")},
        "preselection": {"measured_body": read("EVIDENCE_PLAN.json")["costs"],
                         "tool_process_wall_s": 3.2507795,
                         "outer_tree_CPU_and_peak": None},
        "independent_verification_nested_in_verify_phase": {
            key: value for key, value in read("INDEPENDENT_VERIFY.json").items()
            if any(part in key.lower() for part in ("wall", "cpu", "own_process"))},
        "additional_audit_review": {
            key: value for key, value in read("AUDIT_REVIEW.json").items()
            if any(part in key.lower() for part in ("wall", "cpu", "measurement", "process", "cost"))},
        "reused_input_identity_verification": {
            key: value for key, value in read("REUSED_INPUTS.json").items()
            if key not in ("reused_input_files",)},
        "final_B_report_review": {"tool_process_wall_s": .2188803,
                                  "CPU_and_peak": None, "new_queries": 0},
        "synthetic_metric_and_tie_QA": {"tool_process_wall_s": .3576385,
                                       "CPU_and_peak": None, "observations_loaded": 0},
        "historical_planning_preflight": {"costs": read("PLANNING_PREFLIGHT.json")["cost"],
                                          "part_of_current_phase_sum": False},
        "formal_execution_failures": [name for name, row in phases.items()
                                      if row["worker_tree"]["returncode"] != 0],
        "runtime": {"mode": "reuse frozen CPU venv, singlethread", "torch": "2.15.0+cpu",
                    "numpy": "2.3.5", "installs": 0, "new_source_downloads": 0,
                    "rendering": "existing primary Python with Pillow"},
        "limits_and_nonexecution": {"observations": 348, "sampling_per_case": 64,
                                    "frozen_forwards": trace["actual_forward_calls"],
                                    "training": 0, "threshold_searches": 0, "Bunny_arrays": 0,
                                    "Google_or_paid_API": 0, "shared_GUI": 0, "product_actions": 0,
                                    "repair_execution": 0, "coupling_queries": 0, "online_benchmark": 0},
        "missing": ["whole authoring and tool-interaction wall/CPU and monetary costs",
                    "preselection and synthetic QA full outer-tree CPU/peak",
                    "controller final serialization and exit after own queries",
                    "some read-only review tool-shell costs",
                    "OS cache state and unrelated machine load",
                    "full-source neighbors beyond each saved context",
                    "native-unit coupling and complete product task acceptance"],
    }
    ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    private_files = [path for path in (HERE / "private").rglob("*") if path.is_file()]
    report["new_private_storage"] = {"files": len(private_files),
                                     "bytes": sum(path.stat().st_size for path in private_files),
                                     "reused_environment_and_old_data_not_copied": True}
    report["cost_collection_before_final_write"] = {
        "wall_s": time.perf_counter() - started, "main_CPU_s": time.process_time() - cpu_started,
        "own_process_lifetime": process_metrics(ctypes.windll.kernel32.GetCurrentProcess())}
    delivery_audit = HERE / "DELIVERY_AUDIT_LOG.json"
    if delivery_audit.exists():
        report["delivery_audit"] = json.loads(delivery_audit.read_bytes())
    (HERE / "COSTS.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                                     encoding="utf-8", newline="\n")
    print(json.dumps({"phases": len(phases), "wall_s": report["sequential_controller_main_wall_sum_s"],
                      "worker_tree_CPU_s": report["phase_worker_tree_CPU_sum_s"],
                      "controller_lifetime_CPU_s": report["phase_outer_controller_lifetime_CPU_before_final_write_sum_s"]}))


if __name__ == "__main__":
    main()
