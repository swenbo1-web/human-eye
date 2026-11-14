"""Per-case quality on restored binary64 candidates, with explicit denominators."""

import re
import time
from pathlib import Path

import numpy as np

from data_io import candidate_from_prediction, forward_tensors, load_sample


def _errors(distances, mask, scale):
    count = int(np.count_nonzero(mask))
    if not count:
        return {"count": 0, "rmse_native": None, "p95_native": None, "max_native": None,
                "rmse_over_scale": None, "p95_over_scale": None, "max_over_scale": None}
    selected = distances[mask]
    rmse = float(np.sqrt(np.mean(selected * selected)))
    p95 = float(np.quantile(selected, 0.95))
    maximum = float(selected.max())
    return {"count": count, "rmse_native": rmse, "p95_native": p95, "max_native": maximum,
            "rmse_over_scale": rmse / scale, "p95_over_scale": p95 / scale,
            "max_over_scale": maximum / scale}


def _bitwise_equal(first, second):
    return bool(np.array_equal(np.ascontiguousarray(first).view(np.uint64),
                               np.ascontiguousarray(second).view(np.uint64)))


def _incident_quality(sample, candidate):
    mapping = sample["mapping"]
    source_faces = mapping["context_source_face_ids"]
    incident_ids = mapping["incident_source_face_ids"]
    selected = np.isin(source_faces, incident_ids)
    triangles = mapping["context_triangles"][selected]
    present = source_faces[selected]
    missing = np.setdiff1d(incident_ids, present)
    before = sample["observed"]
    first = np.cross(before[triangles[:, 1]] - before[triangles[:, 0]],
                     before[triangles[:, 2]] - before[triangles[:, 0]])
    second = np.cross(candidate[triangles[:, 1]] - candidate[triangles[:, 0]],
                      candidate[triangles[:, 2]] - candidate[triangles[:, 0]])
    before_size = np.linalg.norm(first, axis=1)
    after_size = np.linalg.norm(second, axis=1)
    before_valid = before_size > 0
    after_valid = after_size > 0
    new_degenerate = before_valid & ~after_valid
    reversed_normal = before_valid & after_valid & (np.einsum("ij,ij->i", first, second) < 0)
    return {
        "scope": "all saved source faces incident to the allowed region",
        "complete": len(missing) == 0,
        "incident_faces_required": len(incident_ids),
        "incident_faces_evaluated": len(triangles),
        "missing_source_face_ids": missing.tolist(),
        "degenerate_input": int(np.count_nonzero(~before_valid)),
        "degenerate_candidate": int(np.count_nonzero(~after_valid)),
        "new_degenerate_faces": int(np.count_nonzero(new_degenerate)),
        "new_degenerate_source_face_ids": present[new_degenerate].tolist(),
        "normal_reversals_from_input": int(np.count_nonzero(reversed_normal)),
        "reversed_source_face_ids": present[reversed_normal].tolist(),
        "degeneracy_definition": "exact zero cross-product norm, matching frozen geometry quality",
        "intersection_check": "not_evaluated_by_this_shape_metric",
    }


def _path_component(value):
    result = re.sub(r"[^A-Za-z0-9_.-]", "_", str(value))
    if result in ("", ".", ".."):
        raise ValueError("invalid_result_path_component")
    return result


def measure_case(sample, prediction_normalized, method, output_dir=None):
    """Measure A/S/N/N_F after adding a residual to the original observation.

    Geometry, labels, and source metadata remain on this evaluation side. A
    nonfinite prediction raises an error, allowing the caller to record a no-op
    fallback while retaining the case. Empty domains have null error values.
    """
    case = sample["case"]
    if case.get("purpose") == "reserved_test":
        raise ValueError("reserved_test_scoring_is_locked_for_this_batch")
    candidate = candidate_from_prediction(sample, prediction_normalized)
    observed, reference = sample["observed"], sample["reference"]
    if observed.dtype != np.float64 or reference.dtype != np.float64:
        raise ValueError("quality_requires_original_binary64_observation_and_reference")
    scale = float(sample["scale"])
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError("invalid_observed_scale")
    allowed = sample["graph"]["allowed_mask"]
    free = sample["graph"]["free_mask"]
    boundary = sample["graph"]["boundary_mask"]
    support = sample["labels"]["damaged_mask"]
    masks = {"A": allowed, "S": support, "N": allowed & ~support,
             "N_F": allowed & ~support & free}
    residual = np.linalg.norm(candidate - reference, axis=1)
    no_op_residual = np.linalg.norm(observed - reference, axis=1)
    errors = {name: _errors(residual, mask, scale) for name, mask in masks.items()}
    no_op_errors = {name: _errors(no_op_residual, mask, scale) for name, mask in masks.items()}
    support_noop = no_op_errors["S"]["rmse_native"]
    allowed_noop = no_op_errors["A"]["rmse_native"]
    support_ratio = None
    if support_noop is not None and support_noop > 0:
        support_ratio = errors["S"]["rmse_native"] / support_noop
    allowed_improvement = None
    if allowed_noop is not None and allowed_noop > 0:
        allowed_improvement = 1 - errors["A"]["rmse_native"] / allowed_noop
    changed = np.any(candidate.view(np.uint64) != observed.view(np.uint64), axis=1)
    result = {
        "id": case["id"], "patch_id": case["patch_id"], "method": str(method),
        "source": case["source"], "source_group": case["source_group"],
        "purpose": case["purpose"], "position_group": case.get("position_group", "center"),
        "stratum": case.get("stratum"), "unit": case.get("unit", "m"),
        "normal_control": bool(case["normal_control"]),
        "radius_ratio": case.get("radius_ratio"), "amplitude_ratio": case.get("amplitude_ratio"),
        "radius_native": case.get("radius_native", case.get("radius_m")),
        "amplitude_native": case.get("amplitude_native", case.get("amplitude_m")),
        "scale_native": scale, "normalization": "observed context median edge length",
        "context_vertices": len(observed), "fixed_vertices": int(np.count_nonzero(~free)),
        "boundary_vertices": int(np.count_nonzero(boundary)),
        "outside_allowed_context_vertices": int(np.count_nonzero(~allowed)),
        "actual_changed_vertices": int(np.count_nonzero(changed)),
        "actual_changed_free_vertices": int(np.count_nonzero(changed & free)),
        "actual_changed_fixed_vertices": int(np.count_nonzero(changed & ~free)),
        "fixed_bitwise_preserved": _bitwise_equal(candidate[~free], observed[~free]),
        "boundary_bitwise_preserved": _bitwise_equal(candidate[boundary], observed[boundary]),
        "outside_allowed_bitwise_preserved": _bitwise_equal(candidate[~allowed], observed[~allowed]),
        "entire_context_bitwise_noop": _bitwise_equal(candidate, observed),
        "errors": errors, "no_op_errors": no_op_errors,
        "support_rmse_ratio_to_noop": support_ratio,
        "allowed_improvement_to_noop": allowed_improvement,
        "incident_quality": _incident_quality(sample, candidate),
        "fallback_noop": False, "fallback_reason": None,
        "candidate_path": None,
        "observed_path": str(Path(sample["folder"]) / "observed" / (sample["sample_name"] + ".npy")),
        "reference_path": str(Path(sample["folder"]) / "reference_local.npy"),
        "mapping_path": str(Path(sample["folder"]) / "mapping.npz"),
        "graph_path": str(Path(sample["folder"]) / "graph.npz"),
    }
    if output_dir is not None:
        path = (Path(output_dir) / _path_component(method) / _path_component(case["patch_id"])
                / (_path_component(sample["sample_name"]) + ".npy"))
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(path, candidate, allow_pickle=False)
        result["candidate_path"] = str(path.resolve())
    return result


def evaluate_model(model, cases, patch_root, stats, output_dir=None):
    """Forward every observation through the same six-input model entry point."""
    import torch

    started, cpu_started = time.perf_counter(), time.process_time()
    load_wall = forward_wall = forward_cpu = metrics_wall = input_wall = 0.0
    results = []
    was_training = model.training
    model.eval()
    try:
        for case in cases:
            before = time.perf_counter()
            sample = load_sample(case, patch_root, with_labels=True)
            load_wall += time.perf_counter() - before
            before = time.perf_counter()
            values = forward_tensors(sample, stats)
            input_wall += time.perf_counter() - before
            before, before_cpu = time.perf_counter(), time.process_time()
            fallback_reason = None
            try:
                with torch.inference_mode():
                    prediction = model(*values).cpu().numpy()
                if prediction.shape != sample["observed"].shape or not np.isfinite(prediction).all():
                    raise ValueError("invalid_model_prediction_shape_or_finiteness")
            except (FloatingPointError, ValueError, RuntimeError) as error:
                prediction = np.zeros_like(sample["observed"])
                fallback_reason = type(error).__name__ + " " + str(error)
            case_forward_wall = time.perf_counter() - before
            case_forward_cpu = time.process_time() - before_cpu
            forward_wall += case_forward_wall
            forward_cpu += case_forward_cpu
            before = time.perf_counter()
            record = measure_case(sample, prediction, "model", output_dir)
            record.update(fallback_noop=fallback_reason is not None, fallback_reason=fallback_reason,
                          forward_wall_s=case_forward_wall, forward_cpu_s=case_forward_cpu)
            metrics_wall += time.perf_counter() - before
            results.append(record)
    finally:
        model.train(was_training)
    return {"cases": results, "case_count": len(results),
            "fallback_case_count": sum(record["fallback_noop"] for record in results),
            "wall_s": time.perf_counter() - started, "cpu_s": time.process_time() - cpu_started,
            "load_arrays_wall_s": load_wall, "forward_tensor_preparation_wall_s": input_wall,
            "forward_wall_s": forward_wall, "forward_cpu_s": forward_cpu,
            "metrics_and_candidate_save_wall_s": metrics_wall,
            "dynamic_geometry_preparation_included": False,
            "input_scope": "frozen prepared observation arrays, six model arguments"}
