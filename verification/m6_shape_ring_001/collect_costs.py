"""Collect actual process windows and marginal costs of the four fixed scores."""

import json
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent


def read(name):
    return json.loads((HERE / name).read_bytes())


def main():
    started, cpu = time.perf_counter(), time.process_time()
    phases = {}
    for path in sorted((HERE / "private/processes").glob("*.controller.json")):
        label = path.name.removesuffix(".controller.json")
        phases[label] = {"controller": json.loads(path.read_bytes()),
                         "worker_tree": read("private/processes/" + label + ".json")}
    residuals, calibration, evaluation = (read(name) for name in ("RESIDUALS.json", "CALIBRATION.json", "EVALUATION.json"))
    reports = {}
    for name in ("ENVIRONMENT.json", "RESIDUALS.json", "SYNTHETIC_QA.json", "CALIBRATION.json", "EVALUATION.json", "INDEPENDENT_VERIFY.json", "SUMMARY.json"):
        if (HERE / name).exists():
            report = read(name)
            reports[name] = {key: value for key, value in report.items()
                             if any(term in key.lower() for term in ("timing", "wall", "cpu", "process", "resource", "cache", "cost", "measurement"))}
    fit_cost = residuals["timings"]
    branch_fit = {branch: fit_cost[branch + "_robust_quadratic_fit"] for branch in ("solid", "ring")}
    common = {stage: row for stage, row in fit_cost.items() if stage not in ("solid_robust_quadratic_fit", "ring_robust_quadratic_fit")}
    configurations = ("solid_point", "ring_point", "solid_cluster", "ring_cluster")
    calibration_timings, evaluation_timings = calibration["timings"], evaluation["timings"]
    config_stage_names = {configuration: ["score_" + configuration, "case_evaluation_" + configuration,
                         "group_ranking_" + configuration, "group_operations_" + configuration]
                          for configuration in configurations}
    all_evaluation_specific = {name for names in config_stage_names.values() for name in names}
    calibration_specific = {branch + suffix for branch in ("solid", "ring")
                            for suffix in ("_normal_point_scores", "_normal_components_and_scores")}
    shared_evaluation = {key: row for key, row in evaluation_timings.items() if key not in all_evaluation_specific}
    shared_calibration = {key: row for key, row in calibration_timings.items() if key not in calibration_specific}
    config_costs = {}
    for configuration in configurations:
        branch, kind = configuration.split("_")
        stages = {key: evaluation_timings[key] for key in config_stage_names[configuration]}
        stages[branch + "_normal_point_scores"] = calibration_timings[branch + "_normal_point_scores"]
        if kind == "cluster":
            stages[branch + "_normal_components_and_scores"] = calibration_timings[branch + "_normal_components_and_scores"]
            stages["score_" + branch + "_point"] = evaluation_timings["score_" + branch + "_point"]
        marginal_wall = sum(row["wall_s"] for row in stages.values())
        marginal_CPU = sum(row["CPU_s"] for row in stages.values())
        complete = {}
        for metric, controller_key in (("wall_s", "main_wall_s_including_worker_before_write"), ("CPU_s", None)):
            total = sum(row[metric] for row in common.values()) + branch_fit[branch][metric]
            total += sum(row[metric] for row in shared_calibration.values()) + sum(row[metric] for row in shared_evaluation.values())
            total += sum(row[metric] for row in stages.values())
            if controller_key:
                for phase_name, timed in (("fit", fit_cost), ("calibrate", calibration_timings), ("evaluate", evaluation_timings)):
                    outer = next(row["controller"][controller_key] for row in phases.values() if row["controller"]["phase"] == phase_name)
                    total += max(0.0, outer - sum(row[metric] for row in timed.values()))
                total += sum(row["controller"][controller_key] for row in phases.values()
                             if row["controller"]["phase"] not in ("fit", "calibrate", "evaluate"))
            else:
                for phase_name, timed in (("fit", fit_cost), ("calibrate", calibration_timings), ("evaluate", evaluation_timings)):
                    outer = next(row["worker_tree"]["tree_cpu_s"] for row in phases.values() if row["controller"]["phase"] == phase_name)
                    total += max(0.0, outer - sum(row[metric] for row in timed.values()))
                total += sum(row["worker_tree"]["tree_cpu_s"] for row in phases.values()
                             if row["controller"]["phase"] not in ("fit", "calibrate", "evaluate"))
            complete[metric] = total
        config_costs[configuration] = {"marginal_stages": stages, "marginal_wall_s": marginal_wall,
              "marginal_CPU_s": marginal_CPU, "complete_measured_component_composition": complete,
              "scope": "wall and CPU compositions include shared/import/QA/report context and joint calibration/save windows, conservative measured-component compositions rather than independently executed cold runs"}
    private_files = [path for path in (HERE / "private").rglob("*") if path.is_file()]
    result = {"cycle_id": "M6-SHAPE-RING-001", "phases": phases,
              "sequential_controller_wall_sum_s": sum(row["controller"]["main_wall_s_including_worker_before_write"] for row in phases.values()),
              "worker_tree_CPU_sum_s": sum(row["worker_tree"]["tree_cpu_s"] for row in phases.values()),
              "controller_lifetime_CPU_sum_s": sum(row["controller"]["process_lifetime_before_final_write"]["cpu_s"] for row in phases.values()),
              "maximum_sampled_tree_RSS_bytes": max(row["worker_tree"]["tree_sampled_peak_working_set_bytes"] for row in phases.values()),
              "nested_reports": reports, "shared_geometry_stages": common, "branch_fit_costs": branch_fit,
              "configuration_cost_definition": "four score marginals follow the shared two-residual computation; independent complete costs are measured component sums, no separate cold benchmark",
              "four_configuration_costs": config_costs,
              "calibration_and_score_marginals": calibration.get("timings", {}),
              "evaluation_and_cluster_marginals": evaluation.get("timings", {}),
              "aggregation": "phases are sequential. Nested stages, per-config and branch costs are included within phase totals and must not be added twice. BFS/cache preparation counted once, reads and reuse retained.",
              "preparation_costs": {"frozen_metadata_contract_copy": read("PLAN.json")["preparation_window"],
                  "fit_agent_AST_command_wall_s": [0.1695621, 0.1643651],
                  "fit_agent_whitelist_read": "functions outer1.5s only, nested wall/CPU/peak unmeasured",
                  "QA_agent_known_static_read_command_wall_s": [0.1724867, 0.1544913, 0.1861405, 0.1530529, 0.1502667, 0.1507813],
                  "QA_agent_later_known_command_wall_s": [0.245644, 0.1547159, 0.1560657],
                  "fit_agent_readonly_audit": {"checks": 4544, "tool_wall_s": [0.1978237, 0.8489392],
                      "array_audit_body_wall_s": 0.5354348, "CPU_s": 0.53125, "peak_RSS": None},
                  "fit_agent_final_cost_audit": {"final_checks": 8,
                      "tool_wall_s": [0.1644744, 0.1430969, 0.2431917, 0.2101551, 0.1683347, 0.2151876],
                      "recovered_readonly_failure": "collector CPU composition expanded from named stages to shared complete context during audit, old-formula assertion failed and final definition passed",
                      "new_scientific_scores": 0, "CPU_or_peak": None},
                  "evaluation_agent_AST_command_wall_s": [0.1700668, 0.1792222],
                  "evaluation_agent_JSON_review_command_wall_s": 0.2405485,
                  "evaluation_agent_final_report_review_command_wall_s": [0.1773159, 0.199232, 0.2055769],
                  "QA_agent_final_summary_review": {"checks": 631, "tool_wall_s": [1.5134532, 0.2104186],
                      "body_wall_s": 0.0462042, "body_CPU_s": 0.046875, "peak_RSS": None,
                      "new_fit_or_score_runs": 0},
                  "evaluation_agent_source_review": "functions outer1.7s, nested command wall/CPU/peak unmeasured",
                  "early_source_read_failure": "evaluate.py read before author creation, exit1, scientific arrays/forwards0",
                  "unknown": "some early source-read nested walls, command CPU/peak, complete authoring/tool/model interaction and monetary cost"},
              "failures_and_recovery": {"phase_failures": [name for name, row in phases.items() if row["worker_tree"]["returncode"] != 0],
                  "synthetic_QA": "first report serialization encountered NumPy bool; original source archived, passed values explicitly converted to Python bool without changing assertions or tolerances",
                  "scientific_case_failures": residuals.get("failures", []),
                  "finalization": read("FINALIZATION_RECOVERY.json") if (HERE / "FINALIZATION_RECOVERY.json").exists() else None},
              "storage": {"private_files": len(private_files), "private_bytes": sum(path.stat().st_size for path in private_files)},
              "actual_scope": {"cases": 348, "normal_controls": 42, "fit_branches": 2, "score_configurations": 4,
                  "training": 0, "new_network_forwards": 0, "repair_outputs": 0, "Bunny_arrays_or_scores": 0,
                  "new_sources_or_cases": 0, "installations": 0, "Blender_asset_product": 0, "Google_or_paid_API": 0},
              "limits": "singlethread existing CPU environment, machine exclusivity unverified. Process tree discovery and simultaneous peak sampled50ms. Self and controller final writes/exit partly outside own windows.",
              "missing": ["complete product/native-unit cost", "formal same-quality speedup benchmark", "some preparation CPU/peak and whole authoring/money"],
              "collector_wall_s_before_write": time.perf_counter() - started,
              "collector_CPU_s_before_write": time.process_time() - cpu,
              "final_integrity_cost_reference": "FINAL_CHECKS.json"}
    (HERE / "COSTS.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf8", newline="\n")
    print(json.dumps({"phases": len(phases), "wall_s": result["sequential_controller_wall_sum_s"],
                      "tree_CPU_s": result["worker_tree_CPU_sum_s"], "peak_RSS_bytes": result["maximum_sampled_tree_RSS_bytes"]}))


if __name__ == "__main__":
    main()
