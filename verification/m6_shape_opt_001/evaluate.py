"""Soft checkpoint and fixed-threshold hard evaluation on frozen observations."""

import argparse
import hashlib
import importlib.util
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

_spec = importlib.util.spec_from_file_location("m6_train001_quality", PRIOR / "evaluate.py")
_quality = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_quality)
measure_case = _quality.measure_case


def classification_diagnostics(sample, scores, tau):
    """Count predicted/true support only over free vertices on the evaluator side."""
    free = sample["graph"]["free_mask"]
    truth = sample["labels"]["damaged_mask"]
    selected = free & (scores.astype(np.float64) > tau)
    tp = int(np.count_nonzero(selected & truth))
    fp = int(np.count_nonzero(selected & ~truth))
    fn = int(np.count_nonzero(free & ~selected & truth))
    tn = int(np.count_nonzero(free & ~selected & ~truth))
    denominators = {"free": int(free.sum()), "true_support": tp + fn,
                    "normal_free": fp + tn, "selected": tp + fp}
    return {"TP": tp, "FP": fp, "FN": fn, "TN": tn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "FPR": fp / (fp + tn) if fp + tn else None,
            "denominators": denominators,
            "empty_denominators": [key for key, value in denominators.items() if not value],
            "selection_threshold": float(tau), "comparison": "strict p > tau",
            "scope": "all free vertices, labels used only for evaluation"}


def evaluate_model(model, cases, patch_root, stats, output_dir=None, tau=None):
    """Use soft p*u for checkpoints and strict fixed-threshold u for final results."""
    import torch

    started, cpu_started = time.perf_counter(), time.process_time()
    load_wall = input_wall = forward_wall = forward_cpu = metrics_wall = 0.0
    records = []
    was_training = model.training
    model.eval()
    mode = "soft" if tau is None else "hard"
    threshold = .5 if tau is None else float(tau)
    if not np.isfinite(threshold) or threshold < 0 or threshold > 1:
        raise ValueError("invalid_evaluation_threshold")
    try:
        for case in cases:
            before = time.perf_counter()
            sample = load_sample(case, patch_root, with_labels=True)
            load_wall += time.perf_counter() - before
            before = time.perf_counter()
            values = forward_tensors(sample, stats)
            input_wall += time.perf_counter() - before
            before, before_cpu = time.perf_counter(), time.process_time()
            reason = None
            try:
                with torch.inference_mode():
                    u, z, p = model.forward_components(*values)
                    if tau is None:
                        predicted = p[:, None] * u
                    else:
                        from model import gate_prediction
                        predicted = gate_prediction(u, p, values[5], threshold)
                    u, z, p, prediction = (item.cpu().numpy() for item in (u, z, p, predicted))
                n = len(sample["observed"])
                if u.shape != (n, 3) or z.shape != (n,) or p.shape != (n,):
                    raise ValueError("invalid_component_shapes")
                if not all(np.isfinite(value).all() for value in (u, z, p, prediction)):
                    raise ValueError("nonfinite_model_component")
                if np.any(p < 0) or np.any(p > 1):
                    raise ValueError("invalid_location_scores")
                if np.any(prediction[~sample["graph"]["free_mask"]] != 0):
                    raise ValueError("nonzero_fixed_model_output")
            except (FloatingPointError, ValueError, RuntimeError) as error:
                prediction = np.zeros_like(sample["observed"])
                u = z = p = None
                reason = type(error).__name__ + " " + str(error)
            case_wall = time.perf_counter() - before
            case_cpu = time.process_time() - before_cpu
            forward_wall += case_wall
            forward_cpu += case_cpu
            before = time.perf_counter()
            row = measure_case(sample, prediction, "model", output_dir)
            row.update(output_mode=mode, tau=None if tau is None else threshold,
                       fallback_noop=reason is not None, fallback_reason=reason,
                       forward_wall_s=case_wall, forward_cpu_s=case_cpu,
                       classification=None, component_path=None, component_sha256=None)
            if reason is None:
                row["classification"] = classification_diagnostics(sample, p, threshold)
                row["classification"]["diagnostic_threshold_only"] = tau is None
                if output_dir is not None:
                    component_path = Path(output_dir) / "components" / case["patch_id"] / (sample["sample_name"] + ".npz")
                    component_path.parent.mkdir(parents=True, exist_ok=True)
                    np.savez(component_path, u=u, z=z, p=p, prediction_normalized=prediction,
                             selected=sample["graph"]["free_mask"] & (p.astype(np.float64) > threshold))
                    row["component_path"] = str(component_path.resolve())
                    row["component_sha256"] = hashlib.sha256(component_path.read_bytes()).hexdigest()
            metrics_wall += time.perf_counter() - before
            records.append(row)
    finally:
        model.train(was_training)
    return {"cases": records, "case_count": len(records), "output_mode": mode,
            "tau": None if tau is None else threshold,
            "checkpoint_classification_threshold": .5 if tau is None else None,
            "fallback_case_count": sum(row["fallback_noop"] for row in records),
            "wall_s": time.perf_counter() - started, "cpu_s": time.process_time() - cpu_started,
            "load_arrays_wall_s": load_wall, "forward_tensor_preparation_wall_s": input_wall,
            "forward_wall_s": forward_wall, "forward_cpu_s": forward_cpu,
            "metrics_components_and_candidate_save_wall_s": metrics_wall,
            "dynamic_geometry_preparation_included": False,
            "input_scope": "frozen prepared observation arrays, same six model arguments"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--final", action="store_true", required=True)
    args = parser.parse_args()
    started, cpu_started = time.perf_counter(), time.process_time()
    import torch
    from model import ResidualExpert
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    log = json.loads((HERE / "TRAIN_LOG.json").read_bytes())
    calibration_bytes = (HERE / "LOC_CALIBRATION.json").read_bytes()
    calibration = json.loads(calibration_bytes)
    weights = HERE / "private/weights/step_1200.pt"
    identity = hashlib.sha256(weights.read_bytes()).hexdigest()
    if log["steps_completed"] != 1200 or identity != log["final_weights"]["sha256"]:
        raise ValueError("hard_evaluation_requires_fixed_final_weights")
    if identity != calibration["weights_sha256"] or calibration["calibration_count"] != 1:
        raise ValueError("hard_evaluation_calibration_identity_mismatch")
    model = ResidualExpert()
    checkpoint = torch.load(weights, map_location="cpu", weights_only=False)
    model.load_state_dict(checkpoint["model"])
    with np.load(HERE / "private/normalization.npz", allow_pickle=False) as saved:
        stats = {key: saved[key].copy() for key in saved.files}
    train_root = HERE.parent / "m6_shape_data_001"
    development = evaluate_model(model, cases_at(train_root / "DATASET_INDEX.json"),
                                 train_root / "private/patches", stats,
                                 HERE / "private/predictions/final_hard_development", calibration["tau"])
    validation = evaluate_model(model, cases_at(PRIOR / "PUBLIC_DATASET_INDEX.json", "validation"),
                                PRIOR / "private/public_data/patches", stats,
                                HERE / "private/predictions/final_hard_validation", calibration["tau"])
    if development["case_count"] != 231 or validation["case_count"] != 117:
        raise ValueError("final_case_denominator_mismatch")
    report = {"cycle_id": "M6-SHAPE-OPT-001", "step": 1200, "output_mode": "hard",
              "tau": calibration["tau"], "weights_sha256": identity,
              "calibration_sha256": hashlib.sha256(calibration_bytes).hexdigest(),
              "development": development, "validation": validation,
              "Bunny_model_scores": 0, "wall_s": time.perf_counter() - started,
              "cpu_s": time.process_time() - cpu_started}
    (HERE / "EVAL_FINAL_HARD.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "cases": 348, "tau": calibration["tau"],
                      "wall_s": report["wall_s"], "cpu_s": report["cpu_s"]}), flush=True)


if __name__ == "__main__":
    main()
