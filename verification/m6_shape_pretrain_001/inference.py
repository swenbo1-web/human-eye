"""Run the frozen Pointfilter and matched-neighborhood MLS transfer screen."""

import os
for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import traceback

BOOT_WALL, BOOT_CPU = time.perf_counter(), time.process_time()
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
IMPORT_WALL, IMPORT_CPU = time.perf_counter(), time.process_time()
from adapter import configure_dependencies, load_official_pca, measure, process_resources, run_iteration
import numpy as np
import torch
IMPORT_COST = {"wall_s": time.perf_counter() - IMPORT_WALL, "CPU_s": time.process_time() - IMPORT_CPU}


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def resolve(path):
    path = Path(path)
    return path if path.is_absolute() else HERE / path


def load_model(timings=None):
    if timings is None:
        timings = {}
    with measure(timings, "official_architecture_import"):
        path = HERE / "private/pointfilter/Pointfilter_Network_Architecture.py"
        spec = importlib.util.spec_from_file_location("_m6_pointfilter_architecture", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    with measure(timings, "checkpoint_hash_and_read"):
        weights = HERE / "private/pointfilter/model_full_ae.pth"
        if file_sha(weights) != "86600e6d57fab7887fbda0cf54292578a52d956c36766a130d1e32a475d18cee":
            raise ValueError("checkpoint SHA mismatch")
        checkpoint = torch.load(weights, map_location="cpu", weights_only=True)
    with measure(timings, "model_creation_and_strict_weight_load"):
        model = module.pointfilternet().cpu().eval()
        result = model.load_state_dict(checkpoint["state_dict"], strict=True)
        if result.missing_keys or result.unexpected_keys:
            raise ValueError("checkpoint state mismatch")
        if not all(torch.isfinite(tensor).all() for tensor in model.state_dict().values()):
            raise ValueError("nonfinite checkpoint")
    return model


def write_report(report):
    report["bootstrap_to_report_wall_s"] = time.perf_counter() - BOOT_WALL
    report["bootstrap_to_report_CPU_s"] = time.process_time() - BOOT_CPU
    report["own_process_before_report"] = process_resources()
    (HERE / "MODEL_OUTPUTS.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                                            encoding="utf-8", newline="\n")


def main():
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.manual_seed(1729)
    timings = {}
    with measure(timings, "frozen_plan_and_input_index_read"):
        frozen = json.loads((HERE / "PLAN_FREEZE.json").read_bytes())
        for row in frozen["files"]:
            if file_sha(HERE / row["path"]) != row["sha256"]:
                raise ValueError("frozen plan file changed " + row["path"])
        index = json.loads((HERE / "INPUT_INDEX.json").read_bytes())
        cases = sorted(index["cases"], key=lambda case: case["id"])
        selection = json.loads((HERE / "CASE_SELECTION.json").read_bytes())
        if [case["id"] for case in cases] != sorted(case["id"] for case in selection["cases"]):
            raise ValueError("input case IDs differ from frozen selection")
    with measure(timings, "official_PCA_import"):
        pca_alignment = load_official_pca()
    model = load_model(timings)
    report = {"cycle_id": "M6-SHAPE-PRETRAIN-001", "status": "running", "cases": [], "failures": [],
              "requested_cases": len(cases), "methods": ["pointfilter", "robust_mls"],
              "seed": 1729, "RNG_scope": "each case/method resets RandomState1729; iteration2 continues the same case RNG",
              "sampling_order": "case ID, iteration, ascending query source ID; scalar cKDTree upstream neighbor-list order",
              "iterations": 2, "selected_iteration": 2, "batch_size": 64, "threads": 1,
              "parameter_count": sum(parameter.numel() for parameter in model.parameters()),
              "imports": IMPORT_COST, "shared_timings": timings,
              "training": 0, "Bunny_arrays": 0, "model_alternatives_run": 0,
              "local_task_adaptation": "only F updated synchronously; full current source sets radius and neighborhoods",
              "precision_adaptation": "float32 normalized network input and inverse rotation; float64 displacement added to original float64 center; fullcloud float32 disk quantization omitted",
              "source_sha256": {name: file_sha(HERE / name) for name in ("adapter.py", "inference.py")}}
    for case in cases:
        case_row = {"id": case["id"], "input_path": str(resolve(case["path"])),
                    "input_sha256": case["sha256"], "methods": {}}
        report["cases"].append(case_row)
        for method in report["methods"]:
            method_row = {"status": "running", "iterations": [], "timings": {}}
            case_row["methods"][method] = method_row
            method_started, method_cpu = time.perf_counter(), time.process_time()
            try:
                with measure(method_row["timings"], "inference_input_hash_and_read"):
                    if file_sha(case_row["input_path"]) != case["sha256"]:
                        raise ValueError("input SHA mismatch")
                    with np.load(case_row["input_path"], allow_pickle=False) as package:
                        if set(package.files) != {"vertices", "free_source_ids", "context_source_ids"}:
                            raise ValueError("unexpected inference package fields")
                        current = package["vertices"].astype(np.float64)
                        free_ids = package["free_source_ids"].astype(np.int64)
                rng = np.random.RandomState(1729)
                for iteration in (1, 2):
                    candidate, detail, statistics = run_iteration(current, free_ids, method, rng, pca_alignment,
                                                                  model=model, timings=method_row["timings"])
                    with measure(method_row["timings"], "candidate_and_sampling_save_hash"):
                        destination = HERE / "private/predictions" / method / case["id"]
                        destination.mkdir(parents=True, exist_ok=True)
                        candidate_path = destination / ("iter_" + str(iteration) + ".npy")
                        detail_path = destination / ("sampling_" + str(iteration) + ".npz")
                        np.save(candidate_path, candidate, allow_pickle=False)
                        np.savez_compressed(detail_path, **detail)
                        row = {"iteration": iteration, "candidate_path": str(candidate_path),
                               "candidate_sha256": file_sha(candidate_path), "sampling_path": str(detail_path),
                               "sampling_sha256": file_sha(detail_path),
                               "sampled_source_ids_sha256": hashlib.sha256(detail["sampled_source_ids"].tobytes()).hexdigest(),
                               "statistics": statistics}
                    method_row["iterations"].append(row)
                    current = candidate
                method_row.update(status="completed", final_candidate_path=row["candidate_path"],
                                  final_candidate_sha256=row["candidate_sha256"])
            except Exception as error:
                method_row.update(status="failed", error_type=type(error).__name__, error=str(error), traceback=traceback.format_exc())
                report["failures"].append({"id": case["id"], "method": method, "error": str(error)})
            method_row["main_wall_s"] = time.perf_counter() - method_started
            method_row["main_CPU_s"] = time.process_time() - method_cpu
            method_row["resources_at_end"] = process_resources()
        first_step_hashes = [row["iterations"][0]["sampled_source_ids_sha256"]
                             for row in case_row["methods"].values() if row["iterations"]]
        case_row["first_iteration_sampled_ids_equal"] = (len(first_step_hashes) == 2
                                                        and first_step_hashes[0] == first_step_hashes[1])
        write_report(report)
        print(json.dumps({"case_id": case["id"], "methods": {name: row["status"] for name, row in case_row["methods"].items()}}, ensure_ascii=False), flush=True)
    report["status"] = "completed_with_failures" if report["failures"] else "completed_all_frozen_cases"
    report["completed_case_methods"] = sum(method["status"] == "completed" for case in report["cases"] for method in case["methods"].values())
    report["network_forward_batches"] = sum(step["statistics"]["network_forward_batches"] for case in report["cases"] for method in case["methods"].values() for step in method["iterations"])
    report["network_forward_query_count"] = sum(step["statistics"]["network_forward_query_count"] for case in report["cases"] for method in case["methods"].values() for step in method["iterations"])
    report["measurement_scope"] = "imports and nested shared/case/method stages recorded; case rereads included per method; JSON serialization/write/exit outside own final window, outer phase ledger separate"
    write_report(report)


if __name__ == "__main__":
    main()
