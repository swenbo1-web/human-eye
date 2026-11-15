"""Collect actual process ledgers and nested scientific/installation costs."""

import json
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent


def main():
    started, cpu = time.perf_counter(), time.process_time()
    phases = {}
    for path in sorted((HERE / "private/processes").glob("*.controller.json")):
        label = path.name.removesuffix(".controller.json")
        phases[label] = {"controller": json.loads(path.read_bytes()),
                         "worker_tree": json.loads(path.with_name(label + ".json").read_bytes())}
    nested = {}
    for name in ("SOURCE_INDEX.json", "ENVIRONMENT.json", "INPUT_INDEX.json", "TETRAHEDRON_CHECK.json",
                 "MODEL_OUTPUTS.json", "EVALUATION.json", "INDEPENDENT_VERIFY.json", "SUMMARY.json"):
        path = HERE / name
        if path.exists():
            report = json.loads(path.read_bytes())
            nested[name] = {key: value for key, value in report.items()
                            if any(word in key.lower() for word in ("timing", "wall", "cpu", "process", "import", "resource", "measurement"))}
    model = json.loads((HERE / "MODEL_OUTPUTS.json").read_bytes())
    method_costs = {method: {"wall_s": 0.0, "CPU_s": 0.0, "timings": {}} for method in model["methods"]}
    for case in model["cases"]:
        for method, result in case["methods"].items():
            row = method_costs[method]
            row["wall_s"] += result["main_wall_s"]
            row["CPU_s"] += result["main_CPU_s"]
            for stage, values in result["timings"].items():
                target = row["timings"].setdefault(stage, {"wall_s": 0.0, "CPU_s": 0.0, "calls": 0})
                for key in target:
                    target[key] += values[key]
    files = [path for path in (HERE / "private").rglob("*") if path.is_file()]
    report = {"cycle_id": "M6-SHAPE-PRETRAIN-001", "phases": phases,
              "sequential_controller_main_wall_sum_s": sum(row["controller"]["main_wall_s_including_worker_before_write"] for row in phases.values()),
              "compute_controller_main_wall_excluding_prepare_s": sum(row["controller"]["main_wall_s_including_worker_before_write"] for row in phases.values() if row["controller"]["phase"] != "prepare"),
              "worker_tree_CPU_sum_s": sum(row["worker_tree"]["tree_cpu_s"] for row in phases.values()),
              "controller_lifetime_CPU_sum_s": sum(row["controller"]["process_lifetime_before_final_write"]["cpu_s"] for row in phases.values()),
              "nested_costs": nested, "inference_method_costs": method_costs,
              "aggregation": "root phases sequential; nested stages and method costs are contained in enclosing phase, do not add twice",
              "limits": "tree discovery50ms and simultaneous peak sampled; self process peaks and lifecycle CPU also recorded; final serialization/write/exit outside self windows",
              "preparation_and_review_tool_costs": {
                  "root_read_path_failures": ["guessed dataset.py absent", "Windows rg *.py path glob os error123, recovered with -g directories"],
                  "inference_agent_AST_command_wall_s": [0.1655555, 0.1494785],
                  "inference_agent_evaluation_static_audit_wall_s": 0.2275901,
                  "inference_agent_early_ENVIRONMENT_read": "missing before preparation, nested wall/CPU/peak unknown",
                  "evaluation_agent_read_tool_wall_s": [2.2, 2.1, 1.7],
                  "evaluation_agent_AST_command_wall_s": [0.1603754, 0.220926],
                  "QA_agent_known_static_and_read_command_wall_s": [0.1475804, 0.1651334, 0.1532244, 0.1959821, 0.1943968, 0.1601141, 0.1833569, 0.1878736, 0.1790345, 0.1471036],
                  "evaluation_agent_final_report_reads_wall_s": [1.5, 1.5],
                  "QA_agent_final_direction_arithmetic": {"checks": 666, "tool_wall_s": 1.4504481,
                       "body_wall_s": 1.2884946, "CPU_s": 0.296875, "peak_RSS": None,
                       "initial_report_read_tool_wall_s": 0.1945376, "new_forwards_or_queries": 0},
                  "inference_agent_final_report_read_wall_s": [0.1588631, 0.1856042],
                  "late_readonly_review_failures": [
                      {"operation": "QA stdin direction arithmetic script parse", "exitcode": 1, "tool_wall_s": 0.1642852,
                       "array_reads_or_forwards_or_queries": 0, "recovery": "rewrote dictionary and reran pure saved-output arithmetic"},
                      {"operation": "inference report review opened COSTS before collector publication", "exitcode": 1, "tool_wall_s": 0.1588631,
                       "array_reads_or_forwards": 0, "recovery": "reviewed available completed JSON; final costs collected afterward"}],
                  "unmeasured": "some earlier nested tool walls, all preparation command CPU/RSS, authoring/model interaction and monetary cost",
                  "precompute_RNG_amendment": "same seed1729 reset per case/method, before arrays or forward; initial and amended plan commits retained",
                  "pip_rerun_guard": "actual target install succeeded, old site pyc writes since task start0; executed source archived, later -B child guard added"},
              "failures": {"phase_process_failures": [label for label, row in phases.items() if row["worker_tree"]["returncode"] != 0],
                           "model_case_failures": model["failures"],
                           "final_byte_audit_recovery": json.loads((HERE / "FINALIZATION_RECOVERY.json").read_bytes()),
                           "quality_failure": "Pointfilter direct transfer fails original shape gates; retained scientific result"},
              "actual_operations": {"fixed_dent_screen_cases": 37, "case_method_predictions": model.get("completed_case_methods"),
                                    "main_network_forward_batches": model.get("network_forward_batches"),
                                    "main_network_forward_query_count": model.get("network_forward_query_count"),
                                    "official_check_unique_queries": 256, "official_check_repeated_forward_queries": 4,
                                    "official_check_forward_batches": 5, "training": 0, "old_network_retuning": 0,
                                    "other_model_candidates": 0, "Bunny_arrays_or_scores": 0,
                                    "Blender_product_asset_edits": 0, "Google": 0, "paid_API": 0},
              "storage": {"private_file_count_including_dependency_target": len(files),
                          "private_bytes_including_dependency_target": sum(path.stat().st_size for path in files)},
              "performance_scope": "CPU singlethread quality screen, machine exclusivity unverified; complete product pipeline, native-unit performance and same-quality20pct speedup not measured",
              "finalization_cost_reference": "FINAL_CHECKS.json includes final old-input/runtime/evidence byte hashing and manifest preparation window separately",
              "collector_wall_s_before_write": time.perf_counter() - started,
              "collector_CPU_s_before_write": time.process_time() - cpu}
    (HERE / "COSTS.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf8", newline="\n")
    print(json.dumps({"phases": len(phases), "wall_s": report["sequential_controller_main_wall_sum_s"],
                      "compute_wall_s": report["compute_controller_main_wall_excluding_prepare_s"],
                      "tree_CPU_s": report["worker_tree_CPU_sum_s"]}))


if __name__ == "__main__":
    main()
