"""One prescribed score quantile from the 33 training normal controls."""

import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np


HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / "m6_shape_train_001"
sys.path.insert(0, str(HERE))
sys.path.append(str(PRIOR))
from data_io import cases_at, forward_tensors, load_sample


def calibrate_model(model, cases, patch_root, stats, weights_record, normalization_path):
    """Read observation inputs and the graph free mask, with labels disabled."""
    import torch

    started, cpu_started = time.perf_counter(), time.process_time()
    marker = HERE / "CALIBRATION_STARTED.json"
    report_path = HERE / "LOC_CALIBRATION.json"
    if report_path.exists():
        raise RuntimeError("calibration_already_completed")
    controls = [case for case in cases if case["normal_control"]]
    if len(cases) != 231 or len(controls) != 33:
        raise ValueError("calibration_training_case_count_mismatch")
    if any(case["purpose"] != "development_train_pool" for case in cases):
        raise ValueError("calibration_requires_training_controls_only")
    if weights_record["step"] != 1200:
        raise ValueError("calibration_requires_final_step1200")
    with marker.open("x", encoding="utf-8") as saved:
        json.dump({"status": "started", "calibration_count": 1,
                   "weights_sha256": weights_record["sha256"], "controls": 33,
                   "quantile": .995, "method": "linear"}, saved, indent=2)
        saved.write("\n")
    was_training = model.training
    model.eval()
    all_scores, rows = [], []
    try:
        for case in controls:
            sample = load_sample(case, patch_root, with_labels=False)
            with torch.inference_mode():
                u, z, p = model.forward_components(*forward_tensors(sample, stats))
            scores = p.cpu().numpy()[sample["graph"]["free_mask"]]
            if not np.isfinite(scores).all() or np.any(scores < 0) or np.any(scores > 1):
                raise ValueError("invalid_calibration_location_scores")
            folder = HERE / "private/calibration" / case["patch_id"]
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / (sample["sample_name"] + ".npy")
            np.save(path, scores, allow_pickle=False)
            rows.append({"id": case["id"], "free_points": len(scores), "scores_path": str(path),
                         "scores_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
            all_scores.append(scores)
    except Exception as error:
        marker.write_text(json.dumps({"status": "failed", "calibration_count": 1,
                                     "type": type(error).__name__, "message": str(error),
                                     "completed_controls": len(rows), "wall_s": time.perf_counter() - started,
                                     "cpu_s": time.process_time() - cpu_started}, indent=2) + "\n", encoding="utf-8")
        raise
    finally:
        model.train(was_training)
    scores = np.concatenate(all_scores)
    if len(scores) != 10405:
        raise ValueError("calibration_free_point_denominator_mismatch")
    quantile = float(np.quantile(scores, .995, method="linear"))
    tau = max(.5, quantile)
    report = {"cycle_id": "M6-SHAPE-OPT-001", "status": "complete_frozen_calibration",
              "calibration_count": 1, "weights_sha256": weights_record["sha256"],
              "normalization_sha256": hashlib.sha256(Path(normalization_path).read_bytes()).hexdigest(),
              "control_case_count": 33, "free_point_count": len(scores),
              "quantile": .995, "quantile_method": "linear", "q995": quantile,
              "minimum_tau": .5, "tau": tau, "comparison": "strict p > tau",
              "pooled_selected_control_points": int(np.count_nonzero(scores.astype(np.float64) > tau)),
              "scores_min": float(scores.min()), "scores_max": float(scores.max()),
              "cases": rows, "data_scope": "33 training normal controls, with_labels=False",
              "validation_or_test_controls": 0, "threshold_candidates_tried": 1,
              "wall_s": time.perf_counter() - started, "cpu_s": time.process_time() - cpu_started}
    report_path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    marker.write_text(json.dumps({"status": "completed", "calibration_count": 1,
                                 "result_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest()}, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    started, cpu_started = time.perf_counter(), time.process_time()
    import torch
    from model import ResidualExpert
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    log = json.loads((HERE / "TRAIN_LOG.json").read_bytes())
    weights = HERE / "private/weights/step_1200.pt"
    if log["steps_completed"] != 1200 or hashlib.sha256(weights.read_bytes()).hexdigest() != log["final_weights"]["sha256"]:
        raise ValueError("calibration_requires_frozen_final_weights")
    model = ResidualExpert()
    state = torch.load(weights, map_location="cpu", weights_only=False)
    model.load_state_dict(state["model"])
    with np.load(HERE / "private/normalization.npz", allow_pickle=False) as saved:
        stats = {key: saved[key].copy() for key in saved.files}
    train_root = HERE.parent / "m6_shape_data_001"
    result = calibrate_model(model, cases_at(train_root / "DATASET_INDEX.json"),
                             train_root / "private/patches", stats, log["final_weights"],
                             HERE / "private/normalization.npz")
    print(json.dumps({"status": result["status"], "tau": result["tau"],
                      "q995": result["q995"], "free_points": result["free_point_count"],
                      "full_entry_wall_s": time.perf_counter() - started,
                      "full_entry_cpu_s": time.process_time() - cpu_started}), flush=True)


if __name__ == "__main__":
    main()
