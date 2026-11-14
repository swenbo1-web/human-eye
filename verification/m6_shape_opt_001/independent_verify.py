"""Read-only NumPy verification of the saved optimization outputs and records.

This script performs no model forward, training, calibration pass or Bunny
scoring. Torch is used only to deserialize existing checkpoint tensors.
"""

import os
for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import ctypes
from ctypes import wintypes
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time

import numpy as np


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PRIOR = HERE.parent / "m6_shape_train_001"
DATA = HERE.parent / "m6_shape_data_001"
FREEZE_COMMIT = "2a8b9811"
CHECKS = 0
MAX_FLOAT_ERROR = 0.0


def require(condition, detail):
    global CHECKS
    CHECKS += 1
    if not condition:
        raise AssertionError(detail)


def compare(actual, expected, detail, rtol=1e-12, atol=1e-14):
    global MAX_FLOAT_ERROR
    if isinstance(expected, dict):
        require(set(actual) == set(expected), (detail, "keys", set(actual), set(expected)))
        for key in expected:
            compare(actual[key], expected[key], f"{detail}.{key}", rtol, atol)
    elif isinstance(expected, list):
        require(len(actual) == len(expected), (detail, "length"))
        for index, (first, second) in enumerate(zip(actual, expected)):
            compare(first, second, f"{detail}[{index}]", rtol, atol)
    elif isinstance(expected, float):
        require(actual is not None and np.isfinite(actual), (detail, "nonfinite", actual))
        MAX_FLOAT_ERROR = max(MAX_FLOAT_ERROR, abs(float(actual) - expected))
        require(math.isclose(float(actual), expected, rel_tol=rtol, abs_tol=atol),
                (detail, actual, expected, rtol, atol))
    else:
        require(actual == expected, (detail, actual, expected))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_bytes())


def same_bits(first, second):
    return bool(np.array_equal(np.ascontiguousarray(first).view(np.uint8),
                               np.ascontiguousarray(second).view(np.uint8)))


def distribution(values):
    values = list(values)
    if not values:
        return {"count": 0, "median": None, "p95": None, "max": None}
    return {"count": len(values), "median": float(np.median(values)),
            "p95": float(np.quantile(values, .95, method="linear")), "max": float(np.max(values))}


def errors(points, reference, mask, scale):
    count = int(mask.sum())
    names = ("rmse_native", "p95_native", "max_native", "rmse_over_scale", "p95_over_scale", "max_over_scale")
    if not count:
        return {"count": 0, **dict.fromkeys(names)}
    distance = np.linalg.norm(points - reference, axis=1)[mask]
    rmse = float(np.sqrt(np.mean(distance ** 2)))
    p95 = float(np.quantile(distance, .95, method="linear"))
    maximum = float(np.max(distance))
    return {"count": count, "rmse_native": rmse, "p95_native": p95, "max_native": maximum,
            "rmse_over_scale": rmse / scale, "p95_over_scale": p95 / scale,
            "max_over_scale": maximum / scale}


def classification(selected, support, free, tau):
    tp = int(np.sum(selected & support))
    fp = int(np.sum(selected & ~support))
    fn = int(np.sum(free & ~selected & support))
    tn = int(np.sum(free & ~selected & ~support))
    den = {"free": int(free.sum()), "true_support": tp + fn,
           "normal_free": fp + tn, "selected": tp + fp}
    return {"TP": tp, "FP": fp, "FN": fn, "TN": tn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "FPR": fp / (fp + tn) if fp + tn else None,
            "denominators": den,
            "empty_denominators": [key for key, value in den.items() if not value],
            "selection_threshold": tau, "comparison": "strict p > tau",
            "scope": "all free vertices, labels used only for evaluation",
            "diagnostic_threshold_only": False}


def face_quality(observed, candidate, mapping):
    required = mapping["incident_source_face_ids"]
    saved_ids = mapping["context_source_face_ids"]
    covered = np.isin(saved_ids, required)
    ids = saved_ids[covered]
    triangles = mapping["context_triangles"][covered]
    before = np.cross(observed[triangles[:, 1]] - observed[triangles[:, 0]],
                      observed[triangles[:, 2]] - observed[triangles[:, 0]])
    after = np.cross(candidate[triangles[:, 1]] - candidate[triangles[:, 0]],
                     candidate[triangles[:, 2]] - candidate[triangles[:, 0]])
    first_valid = np.linalg.norm(before, axis=1) > 0
    last_valid = np.linalg.norm(after, axis=1) > 0
    new_zero = first_valid & ~last_valid
    reversed_faces = first_valid & last_valid & (np.sum(before * after, axis=1) < 0)
    missing = np.setdiff1d(required, ids)
    return {"scope": "all saved source faces incident to the allowed region",
            "complete": len(missing) == 0, "incident_faces_required": len(required),
            "incident_faces_evaluated": len(triangles), "missing_source_face_ids": missing.tolist(),
            "degenerate_input": int(np.sum(~first_valid)),
            "degenerate_candidate": int(np.sum(~last_valid)),
            "new_degenerate_faces": int(new_zero.sum()), "new_degenerate_source_face_ids": ids[new_zero].tolist(),
            "normal_reversals_from_input": int(reversed_faces.sum()),
            "reversed_source_face_ids": ids[reversed_faces].tolist(),
            "degeneracy_definition": "exact zero cross-product norm, matching frozen geometry quality",
            "intersection_check": "not_evaluated_by_this_shape_metric"}


def localization_summary(rows):
    items = [row["classification"] for row in rows]
    counts = {key: sum(item[key] for item in items) for key in ("TP", "FP", "FN", "TN")}
    tp, fp, fn, tn = (counts[key] for key in ("TP", "FP", "FN", "TN"))
    den = {"free": tp + fp + fn + tn, "selected": tp + fp, "true_support": tp + fn, "normal_free": fp + tn}
    return {"cases": len(rows), "available_cases": len(rows), "unavailable_case_ids": [], **counts,
            "denominators": den, "empty_denominators": [key for key, value in den.items() if not value],
            "pooled_precision": tp / (tp + fp) if tp + fp else None,
            "pooled_recall": tp / (tp + fn) if tp + fn else None,
            "pooled_FPR": fp / (fp + tn) if fp + tn else None,
            "per_case_precision": distribution(item["precision"] for item in items if item["precision"] is not None),
            "per_case_recall": distribution(item["recall"] for item in items if item["recall"] is not None),
            "per_case_FPR": distribution(item["FPR"] for item in items if item["FPR"] is not None),
            "scope": "pooled counts over free vertices; cases repeat source vertices across synthetic variants"}


def summary(rows):
    dents = [row for row in rows if not row["normal_control"]]
    controls = [row for row in rows if row["normal_control"]]
    normal_fail = [row["id"] for row in rows if any(
        row["errors"][domain]["count"] and (row["errors"][domain]["p95_over_scale"] > .02
        or row["errors"][domain]["max_over_scale"] > .10) for domain in ("N", "N_F"))]
    control_fail = [row["id"] for row in controls if row["errors"]["A"]["rmse_over_scale"] > .01
                    or row["errors"]["A"]["p95_over_scale"] > .02 or row["errors"]["A"]["max_over_scale"] > .05]
    fractions = []
    for row in dents:
        allowed = row["errors"]["A"]
        normal = row["errors"]["N"]
        total = allowed["rmse_native"] ** 2 * allowed["count"]
        if total > 0:
            fractions.append(normal["rmse_native"] ** 2 * normal["count"] / total)
    ratios = [row["support_rmse_ratio_to_noop"] for row in dents]
    return {"cases": len(rows), "dented": len(dents), "controls": len(controls),
            "support_RMSE_ratio_to_noop": distribution(ratios),
            "dented_support_improved_cases": sum(value < 1 for value in ratios),
            "allowed_improvement_to_noop": distribution(row["allowed_improvement_to_noop"] for row in dents),
            "normal_point_gate_failures": len(normal_fail), "normal_point_gate_failed_case_ids": normal_fail,
            "normal_control_gate_failures": len(control_fail), "normal_control_gate_failed_case_ids": control_fail,
            "normal_control_RMSE_over_scale": distribution(row["errors"]["A"]["rmse_over_scale"] for row in controls),
            "normal_free_p95_over_scale_worst": max((row["errors"]["N_F"]["p95_over_scale"] for row in rows), default=None),
            "normal_free_max_over_scale_worst": max((row["errors"]["N_F"]["max_over_scale"] for row in rows), default=None),
            "normal_point_fraction_of_final_squared_error": distribution(fractions),
            "new_degenerate_faces_sum_over_cases": sum(row["incident_quality"]["new_degenerate_faces"] for row in rows),
            "normal_reversals_from_input_sum_over_cases": sum(row["incident_quality"]["normal_reversals_from_input"] for row in rows),
            "face_quality_failed_cases": sum(row["incident_quality"]["new_degenerate_faces"] > 0
                                               or row["incident_quality"]["normal_reversals_from_input"] > 0 for row in rows),
            "incident_coverage_complete": all(row["incident_quality"]["complete"] for row in rows),
            "all_fixed_and_boundary_bitwise_preserved": all(row["fixed_bitwise_preserved"]
                 and row["boundary_bitwise_preserved"] and row["outside_allowed_bitwise_preserved"] for row in rows),
            "whole_case_noop_fallbacks": sum(row["fallback_noop"] for row in rows),
            "entire_context_bitwise_noop_cases": sum(row["entire_context_bitwise_noop"] for row in rows),
            "actual_changed_free_vertices_sum_over_cases": sum(row["actual_changed_free_vertices"] for row in rows),
            "region_error_quantiles": {domain: {metric: distribution(
                row["errors"][domain][metric] for row in rows if row["errors"][domain][metric] is not None)
                for metric in ("rmse_over_scale", "p95_over_scale", "max_over_scale")} for domain in ("A", "S", "N", "N_F")},
            "classification": localization_summary(rows),
            "support_improvement_to_MLS": distribution(row["support_improvement_to_MLS"] for row in dents)}


def gates(value, rows):
    ratios = value["support_RMSE_ratio_to_noop"]
    sources = {row["source"] for row in rows if not row["normal_control"]}
    medians = {source: float(np.median([row["support_rmse_ratio_to_noop"] for row in rows
                                      if not row["normal_control"] and row["source"] == source])) for source in sorted(sources)}
    return {"support_median_070": ratios["median"] <= .70,
            "source_file_median_085": all(median <= .85 for median in medians.values()),
            "support_p95_105": ratios["p95"] <= 1.05, "support_worst_125": ratios["max"] <= 1.25,
            "allowed_median_improvement_020": value["allowed_improvement_to_noop"]["median"] >= .20,
            "MLS_median_improvement_010": value["support_improvement_to_MLS"]["median"] >= .10,
            "normal_point_preservation": value["normal_point_gate_failures"] == 0,
            "normal_controls": value["normal_control_gate_failures"] == 0 if value["controls"] else None,
            "no_new_degenerate_or_reversed_faces": value["face_quality_failed_cases"] == 0,
            "incident_coverage_complete": value["incident_coverage_complete"],
            "bitwise_fixed": value["all_fixed_and_boundary_bitwise_preserved"],
            "no_inference_fallback": value["whole_case_noop_fallbacks"] == 0}, medians


def own_resources():
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (key, ctypes.c_size_t) for key in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
            "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage",
            "PeakPagefileUsage", "PrivateUsage")]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    memory = Counters()
    memory.cb = ctypes.sizeof(memory)
    require(bool(psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(memory), memory.cb)), "resource_measurement")
    return {"peak_working_set_bytes": int(memory.PeakWorkingSetSize), "working_set_bytes": int(memory.WorkingSetSize)}


def verify_frozen_identity():
    freeze = read_json(HERE / "TRAIN_FREEZE.json")
    rows = []
    for record in freeze["files"]:
        path = HERE / record["path"]
        current = path.read_bytes()
        frozen = subprocess.check_output(["git", "show", f"{FREEZE_COMMIT}:verification/m6_shape_opt_001/{record['path']}"], cwd=ROOT)
        require(hashlib.sha256(frozen).hexdigest() == record["sha256"], ("frozen_commit", record["path"]))
        changed = current != frozen
        require(not changed or record["path"] == "run_phase.py", ("unexpected_postfreeze_change", record["path"]))
        rows.append({"path": record["path"], "frozen_sha256": record["sha256"],
                     "current_sha256": hashlib.sha256(current).hexdigest(), "changed_after_freeze": changed})
    for record in freeze["reused_readonly_inputs"]:
        require(sha256(record["path"]) == record["sha256"], ("readonly_dependency", record["path"]))
    old_launcher = subprocess.check_output(["git", "show", f"{FREEZE_COMMIT}:verification/m6_shape_opt_001/run_phase.py"], cwd=ROOT).decode()
    expected_launcher = old_launcher.replace(
        '"render": ("render_results.py", [], 120), "online": ("run_online.py", [], 180)}',
        '"render": ("render_results.py", [str(HERE / "RESULTS.json")], 120),\n                "online": ("run_online.py", [], 180)}')
    expected_launcher = expected_launcher.replace(
        '    command = [str(python), "-I",',
        '    if phase == "render":\n        python = Path(sys.base_prefix) / "python.exe"\n    command = [str(python), "-I",')
    require((HERE / "run_phase.py").read_text(encoding="utf-8") == expected_launcher, "render_only_launcher_change")
    require(sha256(HERE / "private/normalization.npz") == freeze["normalization_sha256"], "frozen_normalization")
    return {"freeze_commit": subprocess.check_output(["git", "rev-parse", FREEZE_COMMIT], cwd=ROOT).decode().strip(),
            "files": rows, "readonly_dependencies": len(freeze["reused_readonly_inputs"]),
            "postfreeze_change": "run_phase.py render argument and render interpreter only; train/calibration/evaluation/model/plan unchanged"}


def verify_checkpoints(log):
    import torch
    torch.set_num_threads(1)
    old_initial = torch.load(PRIOR / "private/weights/step_0000.pt", map_location="cpu", weights_only=False)
    initial = torch.load(HERE / "private/weights/step_0000.pt", map_location="cpu", weights_only=False)
    final = torch.load(HERE / "private/weights/step_1200.pt", map_location="cpu", weights_only=False)
    require(initial["step"] == 0 and final["step"] == 1200, "checkpoint_steps")
    require(initial["parameters"] == final["parameters"] == 6339, "checkpoint_parameter_metadata")
    require(initial["seed"] == final["seed"] == 1729, "checkpoint_seeds")
    require(sum(value.numel() for value in final["model"].values()) == 6339, "actual_tensor_parameter_count")
    require(set(initial["model"]) - set(old_initial["model"]) == {"localization_head.weight", "localization_head.bias"}, "additional_parameters")
    for name, value in old_initial["model"].items():
        require(torch.equal(initial["model"][name], value), ("old_initial_tensor", name))
    for name in ("localization_head.weight", "localization_head.bias"):
        require(bool(torch.count_nonzero(initial["model"][name]) == 0), ("new_head_initial_zero", name))
    for name in ("initial_checkpoint", "final_weights"):
        require(sha256(log[name]["path"]) == log[name]["sha256"], ("checkpoint_SHA", name))
    require(log["old_module_initial_states_bitwise_equal"] and log["old_module_initial_tensor_count"] == 20, "initial_assertion_record")
    require(all(bool(torch.isfinite(value).all()) for value in final["model"].values()), "final_parameters_finite")
    steps = [int(state["step"]) for state in final["optimizer"]["state"].values()]
    require(len(steps) == len(final["model"]) and set(steps) == {1200}, "optimizer_parameter_update_steps")
    require(final["scheduler"]["last_epoch"] == 1200, "scheduler_steps")
    qa = read_json(HERE / "MODEL_QA.json")
    require(qa["initialization"]["old_state_tensors_equal"] == 20 and qa["parameter_count"] == 6339, "QA_initialization_record")
    return {"old_initial_tensor_count": len(old_initial["model"]), "old_parameter_values_equal": 6290,
            "new_parameter_values": 49, "actual_final_parameters": 6339,
            "initial_weights_sha256": sha256(HERE / "private/weights/step_0000.pt"),
            "final_weights_sha256": sha256(HERE / "private/weights/step_1200.pt"),
            "optimizer_parameter_steps": sorted(set(steps)), "model_objects_instantiated": 0}


def main():
    started, cpu_started = time.perf_counter(), time.process_time()
    identities = verify_frozen_identity()
    log = read_json(HERE / "TRAIN_LOG.json")
    final = read_json(HERE / "EVAL_FINAL_HARD.json")
    results = read_json(HERE / "RESULTS.json")
    calibration = read_json(HERE / "LOC_CALIBRATION.json")
    train_cases = read_json(DATA / "DATASET_INDEX.json")["cases"]
    public_cases = read_json(PRIOR / "PUBLIC_DATASET_INDEX.json")["cases"]
    val_cases = [case for case in public_cases if case["purpose"] == "validation"]
    require(len(train_cases) == 231 and len(val_cases) == 117, "data_counts")
    cases = {case["id"]: case for case in train_cases + val_cases}
    saved_rows = final["development"]["cases"] + final["validation"]["cases"]
    require(len(saved_rows) == 348 and set(cases) == {row["id"] for row in saved_rows}, "case_identity")
    require(results["tau"] == final["tau"] == calibration["tau"], "frozen_tau_identity")
    tau = calibration["tau"]
    baseline = {row["id"]: row for row in results["baseline_cases"]}
    recalculated = []
    training_denominators = {}
    max_sigmoid_difference = 0.0
    for row in saved_rows:
        case = cases[row["id"]]
        require(case["purpose"] != "reserved_test", "reserved_test_not_loaded")
        folder = (DATA / "private/patches" if case["purpose"] == "development_train_pool"
                  else PRIOR / "private/public_data/patches") / case["patch_id"]
        sample_name = case.get("sample_name", Path(case["input"]["path"]).stem)
        for field in ("source", "source_group", "normal_control", "purpose", "radius_ratio", "amplitude_ratio"):
            compare(row[field], case[field], f"{row['id']}.{field}")
        require(Path(row["observed_path"]) == folder / "observed" / (sample_name + ".npy"), "observation_path")
        observed = np.load(folder / "observed" / (sample_name + ".npy"), allow_pickle=False)
        reference = np.load(folder / "reference_local.npy", allow_pickle=False)
        candidate = np.load(row["candidate_path"], allow_pickle=False)
        require(observed.dtype == reference.dtype == candidate.dtype == np.float64, "binary64_geometry")
        with np.load(folder / "graph.npz", allow_pickle=False) as graph:
            free, allowed, boundary, edges = (graph[key].copy() for key in ("free_mask", "allowed_mask", "boundary_mask", "edge_index"))
        with np.load(folder / "labels" / (sample_name + ".npz"), allow_pickle=False) as labels:
            support, normal_free = labels["damaged_mask"].copy(), labels["normal_free_mask"].copy()
        with np.load(folder / "inputs" / (sample_name + ".npz"), allow_pickle=False) as inputs:
            scale = float(inputs["scale_m"])
        with np.load(folder / "mapping.npz", allow_pickle=False) as saved_mapping:
            mapping = {key: saved_mapping[key].copy() for key in saved_mapping.files}
        compare(row["scale_native"], scale, "observed_scale")
        require(np.array_equal(normal_free, allowed & ~support & free), "normal_free_mask")
        require(not np.any(support & ~free), "support_free")
        require(sha256(row["component_path"]) == row["component_sha256"], "component_SHA")
        with np.load(row["component_path"], allow_pickle=False) as components:
            u, z, p, hard, saved_selection = (components[key].copy() for key in ("u", "z", "p", "prediction_normalized", "selected"))
        require(u.shape == hard.shape == observed.shape and p.shape == z.shape == free.shape, "component_shapes")
        require(u.dtype == z.dtype == p.dtype == hard.dtype == np.float32, "component_float32")
        require(all(np.isfinite(value).all() for value in (u, z, p, hard)), "finite_components")
        require(np.all((p >= 0) & (p <= 1)) and not np.any(u[~free] != 0), "score_domain_and_fixed_u")
        sigmoid = 1 / (1 + np.exp(-z.astype(np.float64)))
        sigmoid_difference = float(np.max(np.abs(p.astype(np.float64) - sigmoid)))
        max_sigmoid_difference = max(max_sigmoid_difference, sigmoid_difference)
        require(sigmoid_difference <= 1.2e-7, "saved_p_sigmoid_z")
        selected = free & (p.astype(np.float64) > tau)
        expected_hard = np.zeros_like(u)
        expected_hard[selected] = u[selected]
        require(np.array_equal(selected, saved_selection), "saved_selection")
        require(same_bits(hard, expected_hard), "strict_hard_gate_values")
        expected_candidate = observed.copy()
        delta = hard.astype(np.float64) * scale
        active = free[:, None] & (delta != 0)
        expected_candidate[active] += delta[active]
        require(same_bits(candidate, expected_candidate), "binary64_nonzero_component_writeback")
        changed = np.any(candidate.view(np.uint64) != observed.view(np.uint64), axis=1)
        masks = {"A": allowed, "S": support, "N": allowed & ~support, "N_F": normal_free}
        calculated = {**{key: row[key] for key in ("id", "source", "normal_control", "purpose", "position_group")},
                      "errors": {key: errors(candidate, reference, mask, scale) for key, mask in masks.items()},
                      "no_op_errors": {key: errors(observed, reference, mask, scale) for key, mask in masks.items()},
                      "classification": classification(selected, support, free, tau),
                      "incident_quality": face_quality(observed, candidate, mapping),
                      "actual_changed_vertices": int(changed.sum()),
                      "actual_changed_free_vertices": int(np.sum(changed & free)),
                      "actual_changed_fixed_vertices": int(np.sum(changed & ~free)),
                      "fixed_bitwise_preserved": same_bits(candidate[~free], observed[~free]),
                      "boundary_bitwise_preserved": same_bits(candidate[boundary], observed[boundary]),
                      "outside_allowed_bitwise_preserved": same_bits(candidate[~allowed], observed[~allowed]),
                      "entire_context_bitwise_noop": same_bits(candidate, observed),
                      "fallback_noop": row["fallback_noop"]}
        s0 = calculated["no_op_errors"]["S"]["rmse_native"]
        a0 = calculated["no_op_errors"]["A"]["rmse_native"]
        calculated["support_rmse_ratio_to_noop"] = calculated["errors"]["S"]["rmse_native"] / s0 if s0 else None
        calculated["allowed_improvement_to_noop"] = 1 - calculated["errors"]["A"]["rmse_native"] / a0 if a0 else None
        for key in calculated:
            compare(row[key], calculated[key], f"{row['id']}.{key}")
        support_error = calculated["errors"]["S"]["rmse_native"]
        mls_error = baseline[row["id"]]["mls"]["errors"]["S"]["rmse_native"]
        floor = 1e-6 * scale
        calculated["support_improvement_to_MLS"] = None if row["normal_control"] else (
            (0. if support_error <= floor else -support_error / floor) if mls_error <= floor else 1 - support_error / mls_error)
        training_denominators[row["id"]] = {
            "A": int(allowed.sum()), "S": int(support.sum()), "normal_allowed": int(np.sum(allowed & ~support)),
            "normal_free": int(normal_free.sum()), "fixed": int(np.sum(~(support | normal_free))),
            "directed_edges": edges.shape[1]}
        recalculated.append(calculated)

    summaries, major_gates, source_medians = {}, {}, {}
    for name, ids in results["selections"].items():
        selected_ids = set(ids)
        rows = [row for row in recalculated if row["id"] in selected_ids]
        require(len(rows) == len(ids), (name, "selection_count"))
        summaries[name] = summary(rows)
        compare(results["summaries"][name]["model"], summaries[name], f"summary.{name}")
        if name in ("development_center", "validation_center", "validation_offcenter"):
            major_gates[name], source_medians[name] = gates(summaries[name], rows)
            compare(results["quality_gates"][name], major_gates[name], f"gates.{name}")
            compare(results["source_file_support_medians"][name], source_medians[name], f"source_medians.{name}")
    passed = all(value is not False for group in major_gates.values() for value in group.values())
    require(passed == results["all_quality_gates_passed"], "all_quality_gate_decision")

    scores = []
    controls = {case["id"] for case in train_cases if case["normal_control"]}
    require(len(calibration["cases"]) == len(controls) == 33, "calibration_control_count")
    require({row["id"] for row in calibration["cases"]} == controls, "calibration_train_controls_only")
    for row in calibration["cases"]:
        values = np.load(row["scores_path"], allow_pickle=False)
        require(sha256(row["scores_path"]) == row["scores_sha256"], "calibration_scores_SHA")
        require(len(values) == row["free_points"] == training_denominators[row["id"]]["normal_free"], "calibration_free_count")
        scores.append(values)
    all_scores = np.concatenate(scores)
    quantile = float(np.quantile(all_scores, .995, method="linear"))
    require(len(all_scores) == calibration["free_point_count"] == 10405, "pooled_calibration_denominator")
    require(quantile == calibration["q995"] and max(.5, quantile) == tau, "saved_score_quantile_recomputation")
    selected_controls = int(np.sum(all_scores.astype(np.float64) > tau))
    require(selected_controls == calibration["pooled_selected_control_points"], "calibration_selected_points")
    require(calibration["calibration_count"] == calibration["threshold_candidates_tried"] == 1, "one_calibration_record")

    historical_log = read_json(PRIOR / "TRAIN_LOG.json")
    require(log["steps_completed"] == len(log["steps"]) == 1200 and log["optimization_training_runs"] == 1, "training_count")
    max_log_arithmetic_error = 0.0
    for index, step in enumerate(log["steps"]):
        require(step["step"] == index + 1 and step["cases"] == historical_log["steps"][index]["cases"], "same_1200_batch_sequence")
        require(len(step["components"]) == len(step["cases"]) == 4, "four_graph_batch")
        require(sum(cases[key]["normal_control"] for key in step["cases"]) == 1, "one_control_per_batch")
        graph_totals = []
        for graph_id, (case_id, component) in enumerate(zip(step["cases"], step["components"])):
            require(component["graph_id"] == graph_id, "graph_id")
            compare(component["denominators"], training_denominators[case_id], "training_denominators")
            den = training_denominators[case_id]
            normal = cases[case_id]["normal_control"]
            require(component["normal_control"] == normal, "control_record")
            point = component["mse"]["A"] if normal else sum(component["mse"][key] * weight
                     for key, weight in (("A", .2), ("S", .4), ("normal_free", .4)))
            conditional_loss = .4 * component["conditional_support_mse"] if den["S"] else 0.
            loc_den = {"S": den["S"], "N_F": den["normal_free"], "F": den["S"] + den["normal_free"]}
            compare(component["localization_denominators"], loc_den, "localization_denominators")
            require(component["conditional_support_denominator"] == den["S"], "conditional_denominator")
            if normal:
                loc = component["localization_means"]["F_control_negative"]
                expected_weights = {"F": 1.0}
                require(component["conditional_support_mse"] is None, "control_conditional_empty")
            else:
                active = int(loc_den["S"] > 0) + int(loc_den["N_F"] > 0)
                loc = (component["localization_means"]["S_positive"]
                       + (component["localization_means"]["N_F_negative"] or 0.)) / active
                expected_weights = {"S": 1 / active, "N_F": 1 / active if loc_den["N_F"] else 0.}
            compare(component["localization_group_weights"], expected_weights, "location_group_weights")
            expected = {"point_loss": point,
                        "gradient_loss": .05 * component["directed_edge_gradient_mse"],
                        "base_total_loss": point + .05 * component["directed_edge_gradient_mse"],
                        "conditional_loss": conditional_loss, "localization_loss_unweighted": loc,
                        "localization_loss": .05 * loc}
            expected["total_loss"] = expected["base_total_loss"] + conditional_loss + .05 * loc
            for key, value in expected.items():
                max_log_arithmetic_error = max(max_log_arithmetic_error, abs(value - component[key]))
                compare(component[key], value, f"step{index + 1}.{key}", rtol=3e-6, atol=1e-8)
            graph_totals.append(expected["total_loss"])
        expected_step = float(np.mean(graph_totals))
        max_log_arithmetic_error = max(max_log_arithmetic_error, abs(expected_step - step["loss"]))
        compare(step["loss"], expected_step, "equal_graph_total", rtol=3e-6, atol=1e-8)
        require(np.isfinite(step["gradient_norm_before_clip"]), "finite_gradient")
        expected_lr = .0001 + .5 * (.001 - .0001) * (1 + math.cos(math.pi * (index + 1) / 1200))
        compare(step["lr_after_step"], expected_lr, "cosine_lr", rtol=1e-10, atol=1e-15)
    checkpoint_identity = verify_checkpoints(log)
    require(log["Bunny_model_scores"] == results["Bunny_model_or_MLS_scores"] == 0, "Bunny_scores_record_zero")
    report = {"cycle_id": "M6-SHAPE-OPT-001", "status": "passed", "quality_passed": passed,
              "scope": "independent saved-array NumPy arithmetic; checkpoint deserialization only",
              "model_forward_calls": 0, "training_runs": 0, "calibration_passes": 0,
              "reserved_test_geometry_loaded": 0, "Bunny_scores": 0,
              "saved_cases_recomputed": len(recalculated), "model_summary_groups_recomputed": len(summaries),
              "checks": CHECKS, "identities": identities, "checkpoints": checkpoint_identity,
              "maximum_saved_score_sigmoid_difference": max_sigmoid_difference,
              "calibration_saved_score_recomputation": {"control_cases": 33, "free_points": len(all_scores),
                  "q995": quantile, "tau": tau, "strict_selected_points": selected_controls,
                  "new_calibration_model_calls": 0},
              "training_log_arithmetic": {"steps": 1200, "graph_records": 4800,
                  "same_historical_batch_sequence": True, "all_graph_denominators_from_saved_masks": True,
                  "maximum_scalar_roundoff": max_log_arithmetic_error,
                  "primitive_values_scope": "arithmetic of recorded MSE/BCE means; per-step node predictions were not replayed"},
              "all_validation_hard_noop": all(row["entire_context_bitwise_noop"] for row in recalculated if row["purpose"] == "validation"),
              "quality_gates": major_gates, "source_file_support_medians": source_medians,
              "summaries": summaries, "cases": recalculated,
              "largest_comparison_absolute_difference": MAX_FLOAT_ERROR,
              "resources": own_resources(), "wall_s": time.perf_counter() - started,
              "cpu_s": time.process_time() - cpu_started}
    (HERE / "INDEPENDENT_VERIFY.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "quality_passed", "saved_cases_recomputed", "checks", "wall_s", "cpu_s", "resources")}))


if __name__ == "__main__":
    main()
