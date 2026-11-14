"""Run the frozen six-process online cost probe sequentially with base Python."""

import time

BOOT_WALL = time.perf_counter()
BOOT_CPU = time.process_time()

import hashlib
import importlib.util
import json
from pathlib import Path
import os
import sys

for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import numpy as np


HERE = Path(__file__).resolve().parent
TRAIN = HERE.parent / "m6_shape_train_001"
sys.path.insert(0, str(HERE))
# Isolated module state redirects only this run's ledgers to the new batch.
_runner_spec = importlib.util.spec_from_file_location("frozen_online_runner", TRAIN / "process_runner.py")
_runner = importlib.util.module_from_spec(_runner_spec)
_runner_spec.loader.exec_module(_runner)
_runner.HERE = HERE
run = _runner.run


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as saved:
        for chunk in iter(lambda: saved.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_report(report):
    (HERE / "ONLINE_RESULTS.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


def distribution(values):
    values = np.asarray(values, dtype=np.float64)
    return {
        "count": len(values),
        "minimum": float(values.min()),
        "median": float(np.median(values)),
        "p95": float(np.quantile(values, 0.95, method="linear")),
        "maximum": float(values.max()),
    }


def public_worker(worker):
    result = {key: worker[key] for key in (
        "status", "method", "id", "units", "versions", "startup", "denominators",
        "weights_sha256_before", "weights_sha256_after", "weights_unchanged",
        "torch_loaded", "tau", "model_location_tau", "gate_semantics", "cold_start_to_first_complete",
        "location_calibration_sha256_before", "location_calibration_sha256_after",
        "MLS_calibration_sha256_before", "MLS_calibration_sha256_after",
        "normalization_sha256_before", "normalization_sha256_after",
        "calibrations_and_normalization_unchanged", "worker_code_sha256",
        "worker_before_final_report", "at_end_resources",
    )}
    result["rounds"] = []
    for measured in worker["rounds"]:
        row = {key: value for key, value in measured.items() if key != "MLS_diagnostics"}
        if "MLS_diagnostics" in measured:
            row["MLS_counts"] = measured["MLS_diagnostics"]["counts"]
        result["rounds"].append(row)
    return result


def finalize_statistics(report):
    groups = {}
    for method in ("model", "mls"):
        selected = [item for item in report["workers"] if item["method"] == method]
        cold = [item["worker"]["cold_start_to_first_complete"]["wall_s"] for item in selected]
        warm = [
            call["full_call"]["wall_s"]
            for item in selected for call in item["worker"]["rounds"] if call["mode"] == "warm"
        ]
        warm_calls = [
            call for item in selected for call in item["worker"]["rounds"] if call["mode"] == "warm"
        ]
        stage_names = sorted({name for call in warm_calls for name in call["timings"]})
        groups[method] = {
            "fresh_process_cold_start_to_first_complete_wall_s": distribution(cold),
            "warm_complete_call_wall_s": distribution(warm),
            "outer_process_wall_s": distribution([item["process"]["full_process_wall_s"] for item in selected]),
            "outer_tree_cpu_s": distribution([item["process"]["tree_cpu_s"] for item in selected]),
            "outer_tree_sampled_peak_working_set_bytes": distribution([
                item["process"]["tree_sampled_peak_working_set_bytes"] for item in selected
            ]),
            "worker_lifetime_peak_working_set_bytes": distribution([
                item["worker"]["at_end_resources"]["peak_working_set_bytes"] for item in selected
            ]),
            "warm_complete_call_cpu_s": distribution([call["full_call"]["cpu_s"] for call in warm_calls]),
            "warm_stages": {
                name: {
                    unit: distribution([call["timings"][name][unit] for call in warm_calls])
                    for unit in ("wall_s", "cpu_s")
                }
                for name in stage_names
            },
        }
    report["method_statistics"] = groups
    paired = []
    for sample in ("sample_00", "sample_06", "sample_12"):
        methods = {
            item["method"]: item["worker"]
            for item in report["workers"] if item["sample"] == sample
        }
        paired.append({
            "sample": sample,
            "cold_model_minus_MLS_wall_s": (
                methods["model"]["cold_start_to_first_complete"]["wall_s"]
                - methods["mls"]["cold_start_to_first_complete"]["wall_s"]
            ),
            "warm_model_minus_MLS_wall_s": [
                methods["model"]["rounds"][ordinal]["full_call"]["wall_s"]
                - methods["mls"]["rounds"][ordinal]["full_call"]["wall_s"]
                for ordinal in (1, 2, 3)
            ],
        })
    report["paired_differences"] = paired
    report["paired_cold_model_minus_MLS_wall_s"] = distribution([
        row["cold_model_minus_MLS_wall_s"] for row in paired
    ])
    report["paired_warm_model_minus_MLS_wall_s"] = distribution([
        value for row in paired for value in row["warm_model_minus_MLS_wall_s"]
    ])
    report["all_input_whitelists_exact"] = all(
        call["input_alignment"]["all_whitelist_values_exact"]
        for item in report["workers"] for call in item["worker"]["rounds"]
    )
    report["all_readback_preservation_checks_passed"] = all(
        call["preservation"][key]
        for item in report["workers"] for call in item["worker"]["rounds"]
        for key in ("full_readback_bitwise_equal", "boundary_bitwise_preserved",
                    "all_outside_free_bitwise_preserved")
    )
    report["all_worker_lifetime_peaks_within_RSS_budget"] = all(
        item["worker"]["at_end_resources"]["peak_working_set_bytes"] <= report["memory_budget_bytes"]
        for item in report["workers"]
    )
    report["worker_processes"] = len(report["workers"])
    report["completed_calls"] = sum(len(item["worker"]["rounds"]) for item in report["workers"])
    report["cold_calls"] = len(report["workers"])
    report["warm_calls"] = report["completed_calls"] - report["cold_calls"]
    report["full_candidates_saved_bytes"] = sum(
        call["artifact"]["file_bytes"]
        for item in report["workers"] for call in item["worker"]["rounds"]
    )


def main():
    started = BOOT_WALL, BOOT_CPU
    plan = json.loads((HERE / "TRAIN_PLAN.json").read_bytes())
    expected_probe = "first Armadillo patch normal00,center06,offcenter12; coldandthree warm permodel/MLS"
    if plan["cost_cases"] != expected_probe:
        raise ValueError("frozen_online_probe_plan_mismatch")
    train_log = json.loads((HERE / "TRAIN_LOG.json").read_bytes())
    if train_log["steps_completed"] != 1200 or train_log["final_weights"]["step"] != 1200:
        raise ValueError("online_probe_requires_completed_fixed_optimization_training_round")
    weights_path = HERE / "private/weights/step_1200.pt"
    expected_weights_sha = train_log["final_weights"]["sha256"]
    if sha256(weights_path) != expected_weights_sha:
        raise ValueError("frozen_final_weights_SHA256_mismatch")
    calibration_path = TRAIN / "MLS_CALIBRATION.json"
    calibration_sha = sha256(calibration_path)
    loc_calibration_path = HERE / "LOC_CALIBRATION.json"
    loc_calibration_sha = sha256(loc_calibration_path)
    loc_calibration = json.loads(loc_calibration_path.read_bytes())
    if loc_calibration["calibration_count"] != 1 or loc_calibration["weights_sha256"] != expected_weights_sha:
        raise ValueError("online_requires_once_calibrated_fixed_final_weights")
    model_tau = float(loc_calibration["tau"])
    if not np.isfinite(model_tau) or not 0.5 <= model_tau <= 1.0:
        raise ValueError("online_model_location_tau_out_of_contract")
    python = TRAIN / "private/venv/Scripts/python.exe"
    if not python.is_file():
        raise ValueError("isolated_online_runtime_missing")
    report = {
        "task": "M6-SHAPE-OPT-001",
        "status": "incomplete",
        "plan_sha256": sha256(HERE / "TRAIN_PLAN.json"),
        "weights_sha256": expected_weights_sha,
        "calibration_sha256": calibration_sha,
        "location_calibration_sha256": loc_calibration_sha,
        "model_location_tau": model_tau,
        "driver_measurement_scope": "script bootstrap through final statistics before final report write; CPU excludes child processes",
        "historical_first_round_paired_cold_extra_p95_s": 2.1931237899989355,
        "historical_cost_comparison_scope": "first-round record only; same-window current model versus frozen MLS is measured here",
        "methods": ["model", "mls"],
        "samples": ["sample_00", "sample_06", "sample_12"],
        "requested_worker_processes": 6,
        "requested_calls": 24,
        "warm_calls_per_process": 3,
        "execution": "sequential workers, alternating first method by case ordinal",
        "cold_definition": "new Python process; operating-system file caches uncontrolled",
        "warm_definition": "same source snapshot, topology, and method state; repeated full observed geometry preparation and full candidate save/readback",
        "native_units": "Stanford native coordinates; physical unit unspecified",
        "includes_coupling": False,
        "complete_task_extra_p95_gate": {
            "status": "unknown",
            "maximum_model_extra_wall_s": 2.0,
            "coupling_cost": None,
            "scope": "complete task requires the pending coupling phase",
        },
        "product_complete_task_benefit": "unmeasured",
        "memory_budget_bytes": 2147483648,
        "timeout_per_worker_s": 120,
        "workers": [],
    }
    try:
        for case_ordinal, sample in enumerate(report["samples"]):
            methods = ("model", "mls") if case_ordinal % 2 == 0 else ("mls", "model")
            for method in methods:
                label = f"online_{method}_{sample}"
                worker_output = HERE / "private" / "online" / label / "WORKER.json"
                worker_output.parent.mkdir(parents=True, exist_ok=True)
                weights_before = sha256(weights_path)
                if (weights_before != expected_weights_sha
                        or sha256(calibration_path) != calibration_sha
                        or sha256(loc_calibration_path) != loc_calibration_sha):
                    raise ValueError("frozen_online_artifact_changed_before_worker")
                command = [
                    str(python), "-I", "-B", "-X", "utf8", str(HERE / "online_worker.py"),
                    "--method", method, "--sample", sample,
                    "--weights-sha256", expected_weights_sha, "--output", str(worker_output),
                ]
                ledger = HERE / "private" / "processes" / (label + ".json")
                resumed = ledger.exists()
                if resumed:
                    process = json.loads(ledger.read_bytes())
                else:
                    process = run(command, label, timeout_s=120, rss_limit_bytes=2147483648)
                weights_after = sha256(weights_path)
                item = {
                    "method": method, "sample": sample, "label": label,
                    "weights_sha256_before_worker": weights_before,
                    "weights_sha256_after_worker": weights_after,
                    "resumed_existing_process_record": resumed,
                    "private_worker_report": str(worker_output),
                    "private_process_ledger": str(ledger),
                    "process": process,
                }
                if process["status"] != "completed" or process["returncode"] != 0:
                    report["failed_process"] = item
                    raise RuntimeError("online_worker_failed_" + label)
                worker = json.loads(worker_output.read_bytes())
                if worker["status"] != "complete" or len(worker["rounds"]) != 4:
                    raise RuntimeError("online_worker_round_denominator_mismatch_" + label)
                if worker["method"] != method or worker["id"].split("/")[-1] != sample:
                    raise RuntimeError("online_worker_identity_mismatch_" + label)
                if weights_after != expected_weights_sha or not worker["weights_unchanged"]:
                    raise ValueError("fixed_weights_changed_during_worker")
                if method == "mls" and worker["torch_loaded"]:
                    raise ValueError("MLS_worker_imported_torch")
                if (not worker["calibrations_and_normalization_unchanged"]
                        or worker["location_calibration_sha256_before"] != loc_calibration_sha
                        or worker["MLS_calibration_sha256_before"] != calibration_sha
                        or worker["worker_code_sha256"] != sha256(HERE / "online_worker.py")):
                    raise ValueError("worker_calibration_normalization_or_code_identity_changed")
                item["worker"] = public_worker(worker)
                report["workers"].append(item)
                write_report(report)
        if sha256(calibration_path) != calibration_sha or sha256(loc_calibration_path) != loc_calibration_sha:
            raise ValueError("frozen_MLS_calibration_changed_during_online_probe")
        finalize_statistics(report)
        report["status"] = "complete_frozen_online_probe"
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        report["driver_wall_s_before_report_write"] = time.perf_counter() - started[0]
        report["driver_cpu_s_before_report_write"] = time.process_time() - started[1]
        report["weights_sha256_at_end"] = sha256(weights_path)
        report["calibration_sha256_at_end"] = sha256(calibration_path)
        report["location_calibration_sha256_at_end"] = sha256(loc_calibration_path)
        report["code_sha256"] = {
            name: sha256(HERE / name) for name in ("online_worker.py", "run_online.py")
        }
        write_report(report)
    print(json.dumps({
        "status": report["status"], "workers": report["worker_processes"],
        "calls": report["completed_calls"], "output": str(HERE / "ONLINE_RESULTS.json"),
    }), flush=True)


if __name__ == "__main__":
    main()
