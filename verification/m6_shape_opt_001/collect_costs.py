"""Collect measured phase costs without adding nested processes twice."""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / "m6_shape_train_001"


def read(path):
    return json.loads(path.read_bytes())


def main():
    training = read(HERE / "TRAIN_LOG.json")
    calibration = read(HERE / "LOC_CALIBRATION.json")
    online = read(HERE / "ONLINE_RESULTS.json")
    phases = {}
    for phase in ("train", "calibrate", "evaluate", "summarize", "render",
                  "render_recovery_01", "render_recovery_02", "online"):
        worker = read(HERE / "private/processes" / (phase + ".json"))
        controller = read(HERE / "private/processes" / (phase + ".controller.json"))
        expected_failure = phase in ("render", "render_recovery_01")
        if not expected_failure and (worker["status"] != "completed" or worker["returncode"] != 0):
            raise ValueError("incomplete_phase_" + phase)
        phases[phase] = {"worker_process_tree": worker, "outer_controller": controller,
                         "preserved_recoverable_failure": expected_failure}
    environment = read(PRIOR / "ENVIRONMENT_LOCK.json")
    private_files = [path for path in (HERE / "private").rglob("*") if path.is_file()]
    audit_costs = {}
    for name in ("INDEPENDENT_VERIFY.json", "ONLINE_AUDIT.json", "DIAGNOSTIC_RESULTS.json",
                 "PRIOR_IDENTITY_VERIFY.json"):
        path = HERE / name
        if path.exists():
            audit = read(path)
            audit_costs[name] = {
                key: value for key, value in audit.items()
                if any(term in key.lower() for term in ("wall", "cpu", "measurement", "resources", "process_metrics"))
            }
    report = {
        "cycle_id": "M6-SHAPE-OPT-001",
        "scope": "one optimization training, one calibration, all saved soft/hard evaluations, render and finite paired online probe",
        "phase_costs": phases,
        "sequential_phase_wall_sum_including_each_controller_s": sum(
            item["outer_controller"]["wall_s_including_worker_before_write"] for item in phases.values()),
        "sequential_phase_worker_tree_cpu_sum_s": sum(
            item["worker_process_tree"]["tree_cpu_s"] for item in phases.values()),
        "sequential_phase_outer_controller_main_window_cpu_sum_s": sum(
            item["outer_controller"]["controller_cpu_s_excluding_worker"] for item in phases.values()),
        "sequential_phase_outer_controller_lifetime_cpu_before_final_write_sum_s": sum(
            item["outer_controller"]["controller_process"]["cpu_s"] for item in phases.values()),
        "aggregation": "each phase is sequential; online phase tree includes all six workers and its driver, whose individual costs are nested breakdowns",
        "controller_measurement_scope": "main-window wall and CPU exclude bootstrap and final controller JSON write; process-lifetime CPU is separately queried before that final write",
        "tree_measurement_limit": "descendants discovered every50ms with handles retained through exit; brief unseen descendants can be missed; simultaneous peak is sampled",
        "training": {
            "optimization_training_runs": 1, "historical_first_round_runs": 1,
            "completed_steps": training["steps_completed"], "main_wall_s": training["main_wall_s"],
            "main_cpu_s": training["main_cpu_s"], "stages": training["timings"],
            "budget_loop_wall_s": training["budget_elapsed_s_including_soft_evaluations"],
            "actual_python_peak_working_set_bytes": training["actual_python_process_metrics_at_end"]["peak_working_set_bytes"],
            "loss_objectives_differ_from_first_round": True,
        },
        "calibration": calibration,
        "online": {
            key: online[key] for key in ("worker_processes", "completed_calls", "cold_calls", "warm_calls",
                                         "method_statistics", "paired_differences",
                                         "paired_warm_model_minus_MLS_wall_s")
        },
        "online_full_report": str(HERE / "ONLINE_RESULTS.json"),
        "online_driver_wall_and_CPU": {
            key: value for key, value in online.items()
            if key.startswith("driver_") or key.startswith("paired_cold")
        },
        "synthetic_QA": read(HERE / "MODEL_QA.json"),
        "additional_static_checks": {
            "evaluation_import_and_synthetic_classification_tool_wall_s": 1.4365,
            "evaluation_import_and_synthetic_classification_CPU_s": None,
            "model_QA_tool_wall_s": 5.1588438,
            "model_QA_outer_CPU_and_peak": None,
            "formal_training_updates_in_synthetic_QA": 0,
        },
        "environment": {
            "mode": "reused locked original CPU venv read-only", "install_runs": 0,
            "new_wheel_downloads": 0, "new_public_source_downloads": 0,
            "prior_lock_path": str(PRIOR / "ENVIRONMENT_LOCK.json"),
            "torch": "2.15.0+cpu", "numpy": "2.3.5", "python": "3.12.14",
            "CUDA": None, "prior_lock": environment,
        },
        "private_storage_before_cost_report": {
            "file_count": len(private_files), "bytes": sum(path.stat().st_size for path in private_files),
            "includes_geometry_candidates_weights_scores_online_outputs_and_logs": True,
            "reused_old_venv_and_data_not_copied": True,
        },
        "historical_costs": {
            "path": str(PRIOR / "COSTS.json"),
            "previous_install_and_first_training_retained": True,
            "previous_installer_descendant_CPU_RSS_still_missing": True,
        },
        "readonly_audit_reports": [str(HERE / name) for name in
                                   ("INDEPENDENT_VERIFY.json", "ONLINE_AUDIT.json", "DIAGNOSTIC_RESULTS.json")],
        "readonly_audit_costs_separate_from_phase_sum": audit_costs,
        "readonly_audit_scope": "individual reports describe their own timed blocks; independent arithmetic audit short-lived git child CPU was not separately measured",
        "unmeasured": [
            "whole authoring, tool interaction, read-only source review, final packaging and callback costs",
            "model/provider monetary fees and complete research monetary cost",
            "some pretraining synthetic/static-check outer CPU and peak memory",
            "native-coordinate coupling and complete product task cost",
            "OS file-cache state and unrelated machine load",
        ],
        "coupling": {"status": "unknown_coordinate_semantics", "new_validation_calls": 0,
                     "new_endpoint_queries": 0, "physical_units": "unconfirmed",
                     "complete_task_extra_p95_gate": "unknown", "includes_coupling": False},
        "shared_GUI_calls": 0, "paid_API_calls": 0, "product_or_M5_actions": 0,
        "Bunny_model_MLS_scores": 0,
    }
    (HERE / "COSTS.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                                     encoding="utf-8", newline="\n")
    print(json.dumps({"cost_phases": len(phases), "training_steps": training["steps_completed"],
                      "sequential_phase_wall_s": report["sequential_phase_wall_sum_including_each_controller_s"]}))


if __name__ == "__main__":
    main()
