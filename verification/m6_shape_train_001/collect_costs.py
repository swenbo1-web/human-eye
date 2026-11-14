"""Collect measured research costs and preserve unsupported scopes explicitly."""
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(Path(path).read_bytes())


def main():
    environment = read(HERE / "ENVIRONMENT_LOCK.json")
    training = read(HERE / "TRAIN_LOG.json")
    baseline = read(HERE / "BASELINE_RESULTS.json")
    online = read(HERE / "ONLINE_RESULTS.json")
    process_records = [read(file) for file in sorted((HERE / "private/processes").glob("*.json"))]
    outer = {record["label"]: record for record in process_records}
    public_runs = read(HERE / "PUBLIC_RUN_LOG.json")
    public_bytes = sum(file.stat().st_size for file in (HERE / "private/public_data").rglob("*") if file.is_file())
    venv_bytes = sum(file.stat().st_size for file in (HERE / "private/venv").rglob("*") if file.is_file())
    private_bytes = sum(file.stat().st_size for file in (HERE / "private").rglob("*") if file.is_file())
    output = {"cycle_id": "M6-SHAPE-TRAIN-001", "measurement_status": "measured_worker_intervals_with_explicit_gaps",
              "framework": {"torch": "2.15.0+cpu", "numpy": "2.3.5", "official_CPU_wheels_locked": True,
                            "setup_outer_wall_s": environment["setup_outer_wall_s"], "wheel_bytes": environment["downloaded_wheel_bytes"],
                            "venv_bytes_at_install": environment["venv_bytes"], "venv_bytes_current": venv_bytes,
                            "setup_tree_CPU_s": None, "setup_tree_peak_RSS_bytes": None,
                            "gap": "initial runner measured only Windows venv launcher proxies; actual installer descendants were not tracked. Parent CPU0/low RSS are not whole installation costs.",
                            "global_pip_cache_increment_bytes": None},
              "public_data_script_entry_intervals": public_runs["events"],
              "public_data_bytes": public_bytes, "historical_training_pool": "reused DATA001231cases without new collection; historical costs remain in DATA001/COSTS.json",
              "training": {"outer_process_record": outer["first_training"], "main_wall_s": training["main_wall_s"], "main_cpu_s": training["main_cpu_s"],
                           "steps": training["steps_completed"], "budget_elapsed_s_including_evaluations": training["budget_elapsed_s_including_evaluations"],
                           "application_process_peak_working_set_bytes": training["actual_python_process_metrics_at_end"]["peak_working_set_bytes"],
                           "torch_import_wall_s": training["torch_import_wall_s"], "train_array_load_wall_s": training["train_array_load_wall_s"],
                           "normalization_wall_s": training["normalization_wall_s"], "nested_stage_wall_s": training["timings"], "weight_bytes": training["final_weights"]["bytes"]},
              "baselines": {"outer_process_record": outer["baseline_full"], "main_wall_s": baseline["main_wall_s"], "main_cpu_s": baseline["main_cpu_s"],
                            "calibration": baseline["calibration"]["timing"], "development": baseline["development"]["timing_before_report_write"],
                            "validation": baseline["validation"]["timing_before_report_write"], "fit_cache_reuse": "33training control fits counted once in calibration, reused in development"},
              "online": {"fixed_cases": ["Stanford_Armadillo_patch_00/sample_00", "Stanford_Armadillo_patch_00/sample_06", "Stanford_Armadillo_patch_00/sample_12"],
                         "worker_processes": 6, "calls": 24, "cold_per_method": 3, "warm_per_method": 9,
                         "method_statistics": online["method_statistics"], "paired_differences": online["paired_differences"],
                         "full_candidates_saved_bytes": online["full_candidates_saved_bytes"], "includes_coupling": False,
                         "driver_wall_s_including_worker_intervals": online["driver_wall_s_before_report_write"],
                         "driver_CPU_s_excluding_workers": online["driver_cpu_s_before_report_write"],
                         "complete_task_extra_p95_gate": online["complete_task_extra_p95_gate"],
                         "scope": "fresh-process cold and reused source/topology/model warm, full dynamic geometry prep and full173k-point save/readback included; OS cache uncontrolled"},
              "coupling": {"outer_process_record": outer["coupling_native_domain"], "status": read(HERE / "COUPLING_STATUS.json")},
              "render": read(HERE / "RENDER_RESULT.json"),
              "all_outer_process_records": process_records,
              "private_bytes_at_cost_summary": private_bytes,
              "whole_research_task_CPU_s": None, "whole_research_task_peak_RSS_bytes": None, "monetary_cost": None,
              "unmeasured": ["framework installer descendant CPU/RSS and global pip-cache increment", "outer-monitor controller CPU/RSS outside the explicitly recorded online driver", "agent authoring/review/token fees and complete packaging/callback cost", "complete product capture/M5/host feedback latency", "supported whole-mesh coupling on native-unit validation source"],
              "interval_rule": "source preparation and framework setup overlapped; outer intervals include nested stages. Do not sum overlapping or nested rows as total elapsed task time.",
              "CPU_resolution_note": "short Windows process CPU stages have15.625ms ticks, so0 is below tick resolution",
              "memory_note": "Windows PeakWorkingSetSize is process-lifetime RSS analogue; tree concurrent peak sampled50ms. Brief undiscovered children may be missing; main train/eval workers tracked.",
              "candidate_training_runs": 1, "optimizer_steps": 1200, "optimization_training_runs": 0, "Bunny_model_MLS_scores": 0,
              "Blender_processes": 0, "paid_API_calls": 0, "M5_actions": 0, "product_performance_claim": False}
    (HERE / "COSTS.json").write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"training_outer_wall_s": outer["first_training"]["full_process_wall_s"],
                      "training_tree_CPU_s": outer["first_training"]["tree_cpu_s"], "private_bytes": private_bytes}))


if __name__ == "__main__":
    main()
