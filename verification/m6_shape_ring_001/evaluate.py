"""Evaluate four frozen geometric scores and scalar depth on all original F."""

import time
BOOT_WALL, BOOT_CPU = time.perf_counter(), time.process_time()

import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from ring_metrics import (CONFIGURATIONS, component_scores, distribution, measure,
                          operating_metrics, process_resources, rank_metrics)
import numpy as np


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf8", newline="\n")


def scalar_depth(residual, target, support, normal_valid, fit_valid, ell):
    valid_support = support & normal_valid & np.isfinite(target)
    count = int(np.count_nonzero(valid_support))
    prediction, truth = residual[valid_support], target[valid_support]
    error = prediction - truth
    baseline = float(np.sqrt(np.mean(truth * truth))) if count else None
    rmse = float(np.sqrt(np.mean(error * error))) if count else None
    numerical_floor = 64 * np.finfo(np.float64).eps * ell
    eligible = baseline is not None and baseline > numerical_floor
    sign_eligible = np.abs(truth) > numerical_floor
    return {"support_points_requested": int(support.sum()), "support_depth_valid_points": count,
            "support_depth_invalid_points": int(np.count_nonzero(support & ~valid_support)),
            "support_fit_unavailable_points": int(np.count_nonzero(support & ~fit_valid)),
            "support_RMSE_native": rmse, "zero_prediction_RMSE_native": baseline,
            "support_RMSE_over_ell": rmse / ell if rmse is not None else None,
            "zero_prediction_RMSE_over_ell": baseline / ell if baseline is not None else None,
            "RMSE_ratio_to_zero": rmse / baseline if eligible else None,
            "ratio_not_applicable": not eligible, "baseline_numerical_roundoff_floor_native": numerical_floor,
            "bias_native": float(error.mean()) if count else None,
            "bias_over_ell": float(error.mean()) / ell if count else None,
            "prediction_RMS_native": float(np.sqrt(np.mean(prediction * prediction))) if count else None,
            "prediction_RMS_over_target_RMS": float(np.sqrt(np.mean(prediction * prediction))) / baseline if eligible else None,
            "target_sign_eligible_points": int(sign_eligible.sum()),
            "target_sign_roundoff_or_zero_points": count - int(sign_eligible.sum()),
            "sign_agreement_fraction": float(np.mean(np.sign(prediction[sign_eligible]) == np.sign(truth[sign_eligible]))) if np.any(sign_eligible) else None,
            "normal_F_abs_residual_over_ell": distribution(np.abs(residual[~support]) / ell),
            "all_F_fit_unavailable_points": int(np.count_nonzero(~fit_valid))}


def patch_macro(rows, value):
    by_patch = {}
    for row in rows:
        by_patch.setdefault(row["patch_id"], []).append(value(row))
    patches = {}
    for patch_id, values in sorted(by_patch.items()):
        valid = [item for item in values if item is not None]
        patches[patch_id] = {"requested_cases": len(values), "eligible_cases": len(valid),
                             "value": float(np.mean(valid)) if valid else None}
    valid = [row["value"] for row in patches.values() if row["value"] is not None]
    return {"requested_patches": len(patches), "eligible_patches": len(valid),
            "value": float(np.mean(valid)) if valid else None, "patches": patches}


def operation_summary(rows):
    counts = {key: sum(row[key] for row in rows) for key in ("TP", "FP", "FN", "TN")}
    tp, fp, fn, tn = (counts[key] for key in ("TP", "FP", "FN", "TN"))
    area_keys = ("positive_area_native", "selected_positive_area_native", "missed_positive_area_native",
                 "selected_normal_area_native", "normal_area_native", "positive_area_over_ell2",
                 "selected_positive_area_over_ell2", "missed_positive_area_over_ell2", "selected_normal_area_over_ell2", "normal_area_over_ell2")
    totals = {key: sum(row[key] for row in rows) for key in area_keys}
    selected_area = totals["selected_positive_area_native"] + totals["selected_normal_area_native"]
    positive_area = totals["positive_area_native"]
    sizes = [size for row in rows for size in row["selected_component_sizes"]]
    return {**counts, **totals, "points": tp + fp + fn + tn,
            "point_recall": tp / (tp + fn) if tp + fn else None,
            "point_precision": tp / (tp + fp) if tp + fp else None,
            "point_FPR": fp / (fp + tn) if fp + tn else None,
            "area_recall": totals["selected_positive_area_native"] / positive_area if positive_area else None,
            "area_precision": totals["selected_positive_area_native"] / selected_area if selected_area else None,
            "area_recall_ell_normalized_pool": totals["selected_positive_area_over_ell2"] / totals["positive_area_over_ell2"] if totals["positive_area_over_ell2"] else None,
            "zero_true_detection_cases": sum(row["zero_true_detection"] is True for row in rows),
            "damage_cases_with_defined_zero_detection": sum(row["zero_true_detection"] is not None for row in rows),
            "selected_component_count": len(sizes), "selected_component_size_distribution": distribution(sizes),
            "per_case_point_recall": distribution(row["point_recall"] for row in rows),
            "per_case_area_recall": distribution(row["area_recall"] for row in rows),
            "per_case_point_precision": distribution(row["point_precision"] for row in rows)}


def summarize_group(rows, arrays, timings):
    result = {"requested_cases": len(rows), "normal_controls": sum(row["normal_control"] for row in rows),
              "dented_cases": sum(not row["normal_control"] for row in rows), "patches": len({row["patch_id"] for row in rows}),
              "sources": sorted({row["source"] for row in rows}),
              "F_points": sum(row["F_points"] for row in rows), "support_points": sum(row["support_points"] for row in rows),
              "strong_points": sum(row["strong_points"] for row in rows),
              "weak_damaged_as_strong_task_negative_points": sum(row["weak_damaged_as_strong_task_negative_points"] for row in rows),
              "configurations": {}, "depth": {}}
    for configuration in (*CONFIGURATIONS, "old_p"):
        available = [row for row in rows if row["configurations"][configuration]["status"] == "available"]
        available_ids = {row["id"] for row in available}
        with measure(timings, "group_ranking_" + configuration):
            entry = {"requested_cases": len(rows), "available_cases": len(available),
                     "unavailable_case_ids": [row["id"] for row in rows if row["id"] not in available_ids], "rank": {}}
            for task, label_key in (("support", "support"), ("strong", "strong")):
                labels = np.concatenate([arrays[row["id"]][label_key] for row in available]) if available else np.empty(0, dtype=bool)
                scores = np.concatenate([arrays[row["id"]][configuration] for row in available]) if available else np.empty(0)
                entry["rank"][task] = {"point_pool": rank_metrics(labels, scores),
                    "per_case_ROC_AUC": distribution(row["configurations"][configuration]["rank"][task]["ROC_AUC"] for row in rows),
                    "per_case_AP": distribution(row["configurations"][configuration]["rank"][task]["AP"] for row in rows),
                    "patch_macro_ROC_AUC": patch_macro(rows, lambda row: row["configurations"][configuration]["rank"][task]["ROC_AUC"]),
                    "patch_macro_AP": patch_macro(rows, lambda row: row["configurations"][configuration]["rank"][task]["AP"])}
        if configuration != "old_p":
            with measure(timings, "group_operations_" + configuration):
                entry["operation"] = {}
                for task in ("support", "strong"):
                    operations = [row["configurations"][configuration]["operation"][task] for row in available]
                    entry["operation"][task] = operation_summary(operations)
                    entry["operation"][task]["patch_macro_area_recall"] = patch_macro(rows, lambda row: row["configurations"][configuration]["operation"][task]["area_recall"])
                normals = [row for row in available if row["normal_control"]]
                entry["normal_control_false_patch_ids"] = sorted({row["patch_id"] for row in normals if row["configurations"][configuration]["operation"]["support"]["normal_case_any_selection"]})
                entry["normal_control_cases_selected"] = sum(row["configurations"][configuration]["operation"]["support"]["normal_case_any_selection"] for row in normals)
                entry["component_counts"] = {"seed_components": sum(len(row["configurations"][configuration].get("components", [])) for row in rows),
                                              "retained_components": sum(sum(record["retained_at_least5"] for record in row["configurations"][configuration].get("components", [])) for row in rows)}
        result["configurations"][configuration] = entry
    damaged = [row for row in rows if not row["normal_control"]]
    for branch in ("solid", "ring"):
        result["depth"][branch] = {"requested_dented_cases": len(damaged),
            "support_points_requested": sum(row["depth"][branch]["support_points_requested"] for row in rows),
            "support_depth_valid_points": sum(row["depth"][branch]["support_depth_valid_points"] for row in rows),
            "support_depth_invalid_points": sum(row["depth"][branch]["support_depth_invalid_points"] for row in rows),
            "support_fit_unavailable_points": sum(row["depth"][branch]["support_fit_unavailable_points"] for row in rows),
            "RMSE_ratio_to_zero": distribution(row["depth"][branch]["RMSE_ratio_to_zero"] for row in damaged),
            "support_RMSE_over_ell": distribution(row["depth"][branch]["support_RMSE_over_ell"] for row in damaged),
            "bias_over_ell": distribution(row["depth"][branch]["bias_over_ell"] for row in damaged),
            "prediction_RMS_over_target_RMS": distribution(row["depth"][branch]["prediction_RMS_over_target_RMS"] for row in damaged),
            "sign_agreement_fraction": distribution(row["depth"][branch]["sign_agreement_fraction"] for row in damaged),
            "normal_F_abs_residual_over_ell": distribution(np.concatenate([np.abs(arrays[row["id"]][branch + "_r"][~arrays[row["id"]]["support"]]) / row["ell"] for row in rows]) if rows else []),
            "all_F_fit_unavailable_points": sum(row["depth"][branch]["all_F_fit_unavailable_points"] for row in rows)}
    result["depth"]["ring_improvement_to_solid"] = distribution(row["ring_depth_improvement_to_solid"] for row in damaged)
    return result


def decisions(groups):
    depth_gates = {}
    for name in ("validation_center", "validation_offcenter"):
        depth = groups[name]["depth"]
        ratio, gain = depth["ring"]["RMSE_ratio_to_zero"], depth["ring_improvement_to_solid"]
        requested = depth["ring"]["requested_dented_cases"]
        depth_gates[name] = {"all_requested_ratios_eligible": requested > 0 and ratio["count"] == requested and gain["count"] == requested,
                             "ring_zero_ratio_median_le085": ratio["median"] is not None and ratio["median"] <= .85,
                             "ring_vs_solid_gain_median_ge010": gain["median"] is not None and gain["median"] >= .10}
    depth_pass = all(all(row.values()) for row in depth_gates.values())
    normal = groups["validation_normal_controls"]["configurations"]
    localization = {}
    for candidate in ("solid_cluster", "ring_point", "ring_cluster"):
        per_position = {}
        for name in ("validation_center", "validation_offcenter"):
            configs = groups[name]["configurations"]
            base, proposed = configs["solid_point"], configs[candidate]
            auc0 = base["rank"]["support"]["patch_macro_ROC_AUC"]["value"]
            ap0 = base["rank"]["support"]["patch_macro_AP"]["value"]
            auc = proposed["rank"]["support"]["patch_macro_ROC_AUC"]["value"]
            ap = proposed["rank"]["support"]["patch_macro_AP"]["value"]
            recall0, recall = base["operation"]["support"]["area_recall"], proposed["operation"]["support"]["area_recall"]
            per_position[name] = {"patch_macro_AUC_ge080": auc is not None and auc >= .80,
                                  "AUC_gain_ge005": auc is not None and auc0 is not None and auc - auc0 >= .05,
                                  "AP_not_lower": ap is not None and ap0 is not None and ap >= ap0,
                                  "area_recall_gain_ge010": recall is not None and recall0 is not None and recall - recall0 >= .10,
                                  "values": {"AUC": auc, "baseline_AUC": auc0, "AP": ap, "baseline_AP": ap0,
                                             "area_recall": recall, "baseline_area_recall": recall0}}
        false_count = len(normal[candidate]["normal_control_false_patch_ids"])
        baseline_count = len(normal["solid_point"]["normal_control_false_patch_ids"])
        localization[candidate] = {"positions": per_position, "validation_normal_false_patches": false_count,
                                  "baseline_validation_normal_false_patches": baseline_count,
                                  "normal_false_patch_gate": false_count <= baseline_count and false_count <= 1}
        localization[candidate]["all_localization_goals_passed"] = localization[candidate]["normal_false_patch_gate"] and all(
            all(value for key, value in row.items() if key != "values") for row in per_position.values())
    return {"depth_goals": depth_gates, "depth_signal_goals_passed": depth_pass,
            "localization_goals": localization,
            "ring_cluster_localization_goals_passed": localization["ring_cluster"]["all_localization_goals_passed"],
            "any_new_configuration_localization_goals_passed": any(row["all_localization_goals_passed"] for row in localization.values()),
            "scope": "entry goals for a future study, no repair acceptance or learned-model claim"}


def main():
    started, cpu = time.perf_counter(), time.process_time()
    timings, identities = {}, {}

    def record(path, expected=None):
        path = Path(path)
        data = path.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        if expected is not None and sha != expected:
            raise ValueError("input_identity_mismatch_" + str(path))
        identities[str(path)] = {"path": str(path), "bytes": len(data), "sha256": sha}
        return path

    with measure(timings, "frozen_calibration_binding_and_input_metadata_read"):
        binding = json.loads((HERE / "CALIBRATION_BINDING.json").read_bytes())
        freeze = json.loads((HERE / "CALIBRATION_FREEZE.json").read_bytes())
        for row in freeze["files"]:
            record(row["path"], row["sha256"])
        calibration = json.loads((HERE / "CALIBRATION.json").read_bytes())
        calibrated_cases = {row["id"]: row for row in calibration["cases"]}
        residuals = json.loads((HERE / "RESIDUALS.json").read_bytes())
        whitelist = json.loads((HERE / "INPUT_WHITELIST.json").read_bytes())
        if sorted(row["id"] for row in residuals["cases"]) != sorted(row["id"] for row in whitelist["cases"]):
            raise ValueError("residual_case_ids_differ_from_frozen348")
        old_cases = {}
        for path in (HERE.parent / "m6_shape_data_001/DATASET_INDEX.json", HERE.parent / "m6_shape_train_001/PUBLIC_DATASET_INDEX.json"):
            record(path)
            old_cases.update({row["id"]: row for row in json.loads(path.read_bytes())["cases"] if row["purpose"] != "reserved_test"})
        old_path = record(HERE.parent / "m6_shape_opt_001/EVAL_FINAL_HARD.json")
        old_outputs = json.loads(old_path.read_bytes())
        old_p_index = {row["id"]: row for group in ("development", "validation") for row in old_outputs[group]["cases"]}
    rows, arrays = [], {}
    for residual_case in residuals["cases"]:
        case_id = residual_case["id"]
        case = old_cases[case_id]
        with measure(timings, "residual_and_evaluation_label_read"):
            path = record(residual_case["path"], residual_case["sha256"])
            with np.load(path, allow_pickle=False) as saved:
                values = {key: saved[key].copy() for key in ("free_source_ids", "free_context_ids", "free_edge_index", "area", "normal_unit", "solid_r", "ring_r", "solid_valid", "ring_valid")}
            ell = residual_case["ell"]
            folder = Path(case["observed"]["path"]).parents[1]
            observed = np.load(record(case["observed"]["path"], case["observed"]["sha256"]), allow_pickle=False)
            reference = np.load(record(folder / "reference_local.npy"), allow_pickle=False)
            with np.load(record(folder / "mapping.npz"), allow_pickle=False) as saved:
                context = saved["context_source_ids"]
            with np.load(record(case["labels"]["path"], case["labels"]["sha256"]), allow_pickle=False) as saved:
                support = saved["damaged_mask"].astype(bool)[values["free_context_ids"]]
            if not np.array_equal(context[values["free_context_ids"]], values["free_source_ids"]):
                raise ValueError("residual_free_mapping_changed")
            target_vector = reference[values["free_context_ids"]] - observed[values["free_context_ids"]]
            strong = np.linalg.norm(target_vector, axis=1) > .10 * ell
            normal_valid = np.isfinite(values["normal_unit"]).all(axis=1) & (np.linalg.norm(values["normal_unit"], axis=1) > 0)
            target = np.einsum("ij,ij->i", target_vector, values["normal_unit"])
            target[~normal_valid] = np.nan
        scores, clusters, payload = {}, {}, {"free_source_ids": values["free_source_ids"], "support": support, "strong": strong,
                                           "normal_valid": normal_valid, "target_depth": target}
        if case_id in calibrated_cases:
            with measure(timings, "frozen33_normal_score_cache_read"):
                cached = calibrated_cases[case_id]
                with np.load(record(cached["path"], cached["sha256"]), allow_pickle=False) as saved:
                    scores = {key: saved[key].copy() for key in CONFIGURATIONS}
                    for branch in ("solid", "ring"):
                        payload[branch + "_component_ids"] = saved[branch + "_component_ids"].copy()
                clusters = cached["clusters"]
        else:
            for branch in ("solid", "ring"):
                with measure(timings, "score_" + branch + "_point"):
                    scores[branch + "_point"] = np.abs(values[branch + "_r"]) / ell
                with measure(timings, "score_" + branch + "_cluster"):
                    score, component_ids, details = component_scores(values[branch + "_r"], values["area"], ell,
                        values["free_edge_index"], calibration["seed_thresholds"][branch])
                    scores[branch + "_cluster"] = score
                    payload[branch + "_component_ids"] = component_ids
                    clusters[branch] = details
        historical_status = "unavailable_saved_p"
        with measure(timings, "historical_saved_p_read"):
            historical = old_p_index.get(case_id)
            scores["old_p"] = np.zeros(len(support), dtype=np.float64)
            if historical and Path(historical["component_path"]).exists():
                with np.load(record(historical["component_path"], historical["component_sha256"]), allow_pickle=False) as saved:
                    scores["old_p"] = saved["p"].reshape(-1)[values["free_context_ids"]].astype(np.float64)
                historical_status = "available"
        row = {key: case.get(key) for key in ("id", "patch_id", "source", "source_group", "purpose", "stratum", "normal_control", "radius_ratio", "amplitude_ratio")}
        row.update(position_group=residual_case["position_group"], ell=ell, F_points=len(support),
                   support_points=int(support.sum()), strong_points=int(strong.sum()),
                   weak_damaged_as_strong_task_negative_points=int(np.count_nonzero(support & ~strong)),
                   residual_path=str(path), configurations={}, depth={})
        for configuration in (*CONFIGURATIONS, "old_p"):
            with measure(timings, "case_evaluation_" + configuration):
                status = historical_status if configuration == "old_p" else "available"
                entry = {"status": status, "rank": {task: rank_metrics(label, scores[configuration]) if status == "available" else
                         {"points": len(label), "positive": int(label.sum()), "negative": len(label) - int(label.sum()), "ROC_AUC": None, "AP": None}
                         for task, label in (("support", support), ("strong", strong))}}
                if configuration != "old_p":
                    threshold = calibration["operating_thresholds"][configuration]
                    selected = scores[configuration] > threshold
                    entry.update(threshold=threshold, comparison="strictly_greater", operation={task: operating_metrics(label, selected, values["area"], ell, values["free_edge_index"])
                                 for task, label in (("support", support), ("strong", strong))})
                    if configuration.endswith("cluster"):
                        entry["components"] = clusters[configuration.split("_")[0]]
                    payload[configuration + "_selected"] = selected
                row["configurations"][configuration] = entry
                payload[configuration] = scores[configuration]
        with measure(timings, "label_assisted_scalar_depth_evaluation"):
            for branch in ("solid", "ring"):
                row["depth"][branch] = scalar_depth(values[branch + "_r"], target, support, normal_valid, values[branch + "_valid"], ell)
            solid_error, ring_error = (row["depth"][branch]["support_RMSE_native"] for branch in ("solid", "ring"))
            row["ring_depth_improvement_to_solid"] = 1 - ring_error / solid_error if solid_error is not None and solid_error > 64 * np.finfo(float).eps * ell else None
        with measure(timings, "evaluation_scores_save_and_hash"):
            patch, sample = case_id.split("/")
            destination = HERE / "private/scores" / patch / (sample + ".npz")
            destination.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(destination, **payload)
            data = destination.read_bytes()
            row.update(score_path=str(destination), score_sha256=hashlib.sha256(data).hexdigest())
        rows.append(row)
        arrays[case_id] = {"support": support, "strong": strong, "solid_r": values["solid_r"], "ring_r": values["ring_r"], **scores}
    groups = {"all": rows,
              "development_center": [row for row in rows if row["purpose"] == "development_train_pool"],
              "validation_center": [row for row in rows if row["purpose"] == "validation" and row["position_group"] == "center"],
              "validation_offcenter": [row for row in rows if row["purpose"] == "validation" and row["position_group"] == "offcenter"],
              "development_normal_controls": [row for row in rows if row["purpose"] == "development_train_pool" and row["normal_control"]],
              "validation_normal_controls": [row for row in rows if row["purpose"] == "validation" and row["normal_control"]]}
    for field in ("source", "patch_id", "stratum", "amplitude_ratio"):
        for value in sorted({row[field] for row in rows}, key=str):
            groups[field + "_" + str(value)] = [row for row in rows if row[field] == value]
    for group in ("development_center", "validation_center", "validation_offcenter"):
        for amplitude in (.05, .15, .3):
            groups[group + "_amplitude_" + str(amplitude)] = [row for row in groups[group] if row["amplitude_ratio"] == amplitude]
    summaries = {name: summarize_group(selected, arrays, timings) for name, selected in groups.items()}
    report = {"cycle_id": "M6-SHAPE-RING-001", "status": "completed_fixed348_signal_evaluation", "cases": rows,
              "case_count": len(rows), "normal_controls": sum(row["normal_control"] for row in rows),
              "configurations": list(CONFIGURATIONS), "historical_reference": "old_p saved final-hard output ranking only",
              "groups": summaries, "decision_gates": decisions(summaries), "calibration_binding": binding,
              "normal_calibration_score_cache_reused_cases": len(calibrated_cases),
              "new_case_score_generation_cases": len(rows) - len(calibrated_cases),
              "metric_conventions": {"strong": "norm(reference-observed)>.10ell on sameF, weaker support is negative in strong-only task",
                  "patch_macro": "mean eligible case metric within patch, then equal mean patches, absent classes retained in denominators",
                  "area_recall_gate": "pooled current-native-area selectedS/S for each validation position, ell-normalized pool also listed",
                  "all_source_native_area_caveat": "cross-source physical units unspecified, mixed-source native area pool is descriptive, normalized area pool also retained",
                  "selection": "frozen dev33 patch-max q95 strict>, actual validation FPR measured independently", "normal_AP": "None without positives"},
              "timings": timings, "input_file_identities": list(identities.values()),
              "source_sha256": {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest() for name in ("evaluate.py", "ring_metrics.py")},
              "wall_s_before_final_report": time.perf_counter() - started,
              "CPU_s_before_final_report": time.process_time() - cpu,
              "bootstrap_to_report_wall_s": time.perf_counter() - BOOT_WALL,
              "bootstrap_to_report_CPU_s": time.process_time() - BOOT_CPU,
              "own_process_before_report": process_resources(), "training": 0, "model_forwards": 0,
              "repair_candidates": 0, "Bunny_arrays": 0,
              "measurement_scope": "shared calibration scores reused, other315 scores generated once, per-config scoring/evaluation costs and shared label IO separated; final serialization/write outside self window"}
    write(HERE / "EVALUATION.json", report)
    print(json.dumps({"status": report["status"], "cases": len(rows), "depth_pass": report["decision_gates"]["depth_signal_goals_passed"],
                      "ring_cluster_localization_pass": report["decision_gates"]["ring_cluster_localization_goals_passed"]}))


if __name__ == "__main__":
    main()
