"""Collect actual diagnostic phases and preserve preparation/repair costs."""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def read(name):
    return json.loads((HERE / name).read_bytes())


def main():
    phases = {}
    for path in sorted((HERE / "private/processes").glob("*.controller.json")):
        label = path.name.removesuffix(".controller.json")
        phases[label] = {"controller": json.loads(path.read_bytes()),
                         "worker_tree": read("private/processes/" + label + ".json")}
    decomposition = read("DECOMPOSITION.json")
    surface = read("SURFACE_RESULTS.json")
    repair = read("SURFACE_METADATA_REPAIR.json")
    qa = read("METER_QA.json")
    verification = read("INDEPENDENT_VERIFY.json")
    interpretation = read("OBJECTIVE_INTERPRETATION.json")
    reused = read("REUSED_INPUTS.json")
    files = [path for path in (HERE / "private").rglob("*") if path.is_file()]
    report = {
        "cycle_id": "M6-SHAPE-OBJECTIVE-001", "phases": phases,
        "sequential_controller_main_wall_sum_s": sum(
            row["controller"]["main_wall_s_including_worker_before_write"] for row in phases.values()),
        "phase_worker_tree_CPU_sum_s": sum(row["worker_tree"]["tree_cpu_s"] for row in phases.values()),
        "phase_outer_controller_lifetime_CPU_before_final_write_sum_s": sum(
            row["controller"]["process_lifetime_before_final_write"]["cpu_s"] for row in phases.values()),
        "aggregation": "phases sequential; worker startup/exit in outer tree; stages and own metrics below nested in phases",
        "measurement_limits": "controller main excludes imports/final write/exit; lifecycle CPU queried before write; tree discovery50ms may miss brief children; simultaneous tree peak sampled",
        "decomposition": {key: value for key, value in decomposition.items()
                          if key in ("stages", "main_wall_s_before_final_write", "main_CPU_s_before_final_write",
                                     "bootstrap_to_final_report_wall_s", "bootstrap_to_final_report_CPU_s", "own_process_at_end")},
        "surface_first_run": {key: value for key, value in surface.items()
                              if key in ("timings", "wall_s_before_report_write", "CPU_s_before_report_write", "own_process_before_report_write")},
        "meter_QA": {key: value for key, value in qa.items()
                     if any(part in key.lower() for part in ("wall", "cpu", "cost", "resource", "process", "timing"))},
        "metadata_only_repair": repair,
        "independent_verification": {key: value for key, value in verification.items()
                                     if any(part in key.lower() for part in ("wall", "cpu", "resource", "process", "timing", "repeated"))},
        "additional_JSON_interpretation": {key: value for key, value in interpretation.items()
                                           if any(part in key.lower() for part in ("wall", "cpu", "cost", "resource", "process", "measurement"))},
        "reused_input_identity_verification": {
            key: value for key, value in reused.items() if key != "reused_input_files"},
        "finalization_cost_record": "FINAL_CHECKS.json records final JSON/integrity/manifest work separately; Git and handoff costs remain unmeasured",
        "preparation": {
            "decomposition_read_incident": decomposition["preparation_read_incident"],
            "surface_snapshot_schema_read": surface["preflight_snapshot_schema_read"],
            "surface_read_static_check_commands_wall_s": [.1972837, .3597553, .1490226, .1608752, .157778,
                                                          .1638052, .1621268, .1589158, .1525341, .1511005, .2704059],
            "meter_default_python_static_check_failure": {"tool_process_wall_s": .2146325,
                "error": "default WindowsApps python -m py_compile exited1 with empty output",
                "recovery": "used existing CPU venv ast.parse successfully", "scientific_operations": 0,
                "CPU_and_peak": None},
            "meter_read_static_review_commands_wall_s": [.1140402, 1.5807334, .1404355, .1629615, .1105545,
                                                          .1540738, .4531128, .1483316, .1429558, .1674212, .149627],
            "scope": "read/static-check command windows, includes reported3-array snapshot schema inspection after PLAN written and before final freeze; CPU/peak unmeasured",
        },
        "failures_and_recovery": {
            "phase_process_failures": [name for name, row in phases.items() if row["worker_tree"]["returncode"] != 0],
            "surface_report_metadata_defect": "initial counts accessor mismatched metric schema; fixed after actual first run",
            "original_payload_unchanged": repair["original_scientific_payload_sha256"] == repair["postrepair_scientific_payload_sha256"],
            "distance_recomputations_for_repair": 0,
            "summary_status_matching_recovery": read("SUMMARY_RECOVERY.json"),
        },
        "storage": {"private_files": len(files), "private_bytes": sum(path.stat().st_size for path in files),
                    "old_inputs_and_runtime_reused_readonly": True},
        "actual_scope": {"decomposition_cases": 306, "surface_cases": 6, "saved_candidate_comparisons": 24,
                         "surface_directions": 48, "first_run_point_triangle_queries": 18432,
                         "training": 0, "model_forwards": 0, "new_repair_candidates": 0,
                         "threshold_search": 0, "Bunny_arrays_or_scores": 0,
                         "Blender_or_product": 0, "paid_API": 0, "new_geometry_sources": 0,
                         "installation": 0, "formal_online_benchmark": 0,
                         "paper_reference": "read supplied PointCleanNet section5 by web, outside array experiment cost"},
        "missing": ["whole authoring/review/tool/model interaction wall/CPU and monetary cost",
                    "preparation command CPU/peak and final controller writes/exit",
                    "full continuous-surface and full-source-domain guarantees",
                    "native-unit full product/coupling task cost"],
    }
    (HERE / "COSTS.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                                     encoding="utf-8", newline="\n")
    print(json.dumps({"phases": len(phases), "wall_s": report["sequential_controller_main_wall_sum_s"],
                      "worker_tree_CPU_s": report["phase_worker_tree_CPU_sum_s"],
                      "controller_CPU_s": report["phase_outer_controller_lifetime_CPU_before_final_write_sum_s"]}))


if __name__ == "__main__":
    main()
