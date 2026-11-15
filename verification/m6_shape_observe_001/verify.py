"""Independent saved-result arithmetic and scope verification for OBSERVE001."""

import time
BOOT_WALL = time.perf_counter()
BOOT_CPU = time.process_time()

import os
for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import ctypes
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import cases, load_case

METHODS = ("R0", "R1", "frozen_p")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def own_resources():
    spec = importlib.util.spec_from_file_location("_observe_verify_metrics", HERE.parent / "m6_shape_opt_001/process_runner.py")
    monitor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitor)
    ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    return monitor.process_metrics(ctypes.windll.kernel32.GetCurrentProcess())


def independent_metrics(labels, scores):
    """AUC from positive/negative pair comparisons, AP from unique-score sets."""
    labels = np.asarray(labels, dtype=bool)
    scores = np.asarray(scores, dtype=np.float64)
    positive = scores[labels]
    negative = scores[~labels]
    result = {"points": len(scores), "positive": len(positive), "negative": len(negative),
              "ROC_AUC": None, "AP": None, "score_groups": len(np.unique(scores))}
    if not len(positive) or not len(negative):
        return result
    comparisons = positive[:, None] - negative[None, :]
    result["ROC_AUC"] = float((np.count_nonzero(comparisons > 0)
                               + .5 * np.count_nonzero(comparisons == 0)) / comparisons.size)
    ap = 0.0
    for value in np.unique(scores):
        group_positive = np.count_nonzero(labels & (scores == value))
        above_or_equal = scores >= value
        precision = np.count_nonzero(labels & above_or_equal) / np.count_nonzero(above_or_equal)
        ap += group_positive * precision / len(positive)
    result["AP"] = float(ap)
    return result


def group_rows(name, rows):
    if name.startswith("source_"):
        return [row for row in rows if row["source"] == name[len("source_"):]]
    base = name
    radius = amplitude = None
    match = re.fullmatch(r"(.+)_r([0-9.]+)_a([0-9.]+)", name)
    if match:
        base, radius, amplitude = match[1], float(match[2]), float(match[3])
    elif "_amplitude_" in name:
        base, value = name.rsplit("_amplitude_", 1)
        amplitude = float(value)
    if base == "development":
        selected = [row for row in rows if row["purpose"] == "development_train_pool"]
    elif base in ("validation_center", "validation_offcenter"):
        position = base[len("validation_"):]
        selected = [row for row in rows if row["purpose"] == "validation" and row["position_group"] == position]
    else:
        raise ValueError("unrecognized_fixed_summary_group_" + name)
    if radius is not None:
        selected = [row for row in selected if row["radius_ratio"] == radius]
    if amplitude is not None:
        selected = [row for row in selected if row["amplitude_ratio"] == amplitude]
    return selected


def main():
    started, cpu_started = time.perf_counter(), time.process_time()
    report = {"cycle_id": "M6-SHAPE-OBSERVE-001", "status": "running", "checks": 0,
              "model_forward_calls": 0, "training_updates": 0, "new_thresholds": 0,
              "Bunny_arrays_loaded": 0, "additional_query_points": 0,
              "repeated_QA_top5_queries": 0, "failures": []}
    largest = 0.0

    def check(condition, label):
        report["checks"] += 1
        if not bool(condition):
            raise AssertionError(label)

    def close(actual, expected, label, atol=2e-12):
        nonlocal largest
        if actual is None or expected is None:
            check(actual is expected, label)
            return
        difference = float(np.max(np.abs(np.asarray(actual, dtype=np.float64)
                                          - np.asarray(expected, dtype=np.float64))))
        largest = max(largest, difference)
        check(np.allclose(actual, expected, rtol=2e-13, atol=atol), label)

    try:
        result = json.loads((HERE / "RETRIEVAL_RESULTS.json").read_bytes())
        witness = json.loads((HERE / "WITNESS_RETRIEVAL.json").read_bytes())
        trace = json.loads((HERE / "FROZEN_TRACE.json").read_bytes())
        marker = json.loads((HERE / "TRACE_STARTED.json").read_bytes())
        geometry = json.loads((HERE / "GEOMETRY_EVIDENCE.json").read_bytes())
        evidence_plan = json.loads((HERE / "EVIDENCE_PLAN.json").read_bytes())
        with np.load(HERE / "RETRIEVAL_POINTS.npz", allow_pickle=False) as saved:
            points = {name: saved[name].copy() for name in saved.files}
        rows = result["cases"]
        case_list = cases()
        check(len(rows) == len(case_list) == len(points["case_ids"]) == 348, "348_case_scope")
        check(len(points["label"]) == 22272, "22272_sampled_points")
        check(result["k"] == 5 and result["query_block_limit"] == 128, "fixed_k_and_block")
        check([row["id"] for row in rows] == [case["id"] for case in case_list]
              == points["case_ids"].tolist(), "same_sorted_case_order")
        check(not result["invalid_descriptions"], "zero_invalid_descriptions")
        checked_case_metrics = {}
        source_by_case = np.asarray([case["source"] for case in case_list])
        development_case = np.asarray([case["purpose"] == "development_train_pool" for case in case_list])
        development = development_case[points["case_index"]]
        scopes = {}
        selection_read_started = time.perf_counter()
        for number, (case, row) in enumerate(zip(case_list, rows)):
            sample = load_case(case)
            free = np.flatnonzero(sample["graph"]["free_mask"])
            ordered = sorted(free.tolist(), key=lambda index: int(sample["mapping"]["context_source_ids"][index]))
            count = min(64, len(ordered))
            chosen = np.asarray([ordered[(j * (len(ordered) - 1)) // (count - 1)] for j in range(count)] if count > 1 else ordered[:count])
            use = np.flatnonzero(points["case_index"] == number)
            check(np.array_equal(points["local_index"][use], chosen), "sample_ranks_" + case["id"])
            check(np.array_equal(points["source_vertex_id"][use], sample["mapping"]["context_source_ids"][chosen]), "sample_source_ids_" + case["id"])
            check(np.array_equal(points["label"][use], sample["labels"]["damaged_mask"][chosen]), "sample_labels_" + case["id"])
            target_norm = np.linalg.norm((sample["reference"] - sample["observed"]) / sample["scale"], axis=1)
            close(points["target_norm"][use], target_norm[chosen], "sample_target_norm_" + case["id"])
            close(points["frozen_p"][use], sample["p"][chosen], "sample_old_p_" + case["id"], atol=0)
            close(row["sampled_target_energy"], float(np.sum(target_norm[chosen] ** 2)), "sample_energy_" + case["id"])
            close(row["full_free_target_energy"], float(np.sum(target_norm[free] ** 2)), "full_energy_" + case["id"])
            check(count == row["sampled_points"] == 64, "sample_denominator_" + case["id"])
            labels, magnitude = points["label"][use], points["target_norm"][use]
            strong = ~labels | (magnitude > .1)
            metrics = {}
            for strength, selected in (("all_support", np.ones(count, dtype=bool)), ("strong_support", strong)):
                metrics[strength] = {}
                for method in METHODS:
                    score = points["frozen_p"][use] if method == "frozen_p" else points[method + "_score"][use]
                    computed = independent_metrics(labels[selected], score[selected])
                    metrics[strength][method] = computed
                    for domain in ("common_valid", "method_valid"):
                        old = row["metrics"][domain][strength][method]
                        for key, value in computed.items():
                            close(old[key], value, "case_metric_" + case["id"] + "_" + method + "_" + key)
                        check(old["excluded_invalid"] == 0, "zero_invalid_case_metric")
                        check(old["excluded_weak_support"] == int(np.count_nonzero(~selected)), "weak_support_denominator")
            checked_case_metrics[case["id"]] = metrics
        report["sample_and_case_metric_verification_wall_s"] = time.perf_counter() - selection_read_started
        for method in ("R0", "R1"):
            check(np.all(points[method + "_valid"]), "all_valid_" + method)
            description = points[method + "_description"]
            check(description.shape == (22272, 13 if method == "R0" else 19), "description_shape_" + method)
            check(np.isfinite(description).all(), "description_finite_" + method)
            selected_neighbors = points[method + "_neighbor_rows"]
            check(selected_neighbors.shape == (22272, 5), "neighbor_shape_" + method)
            check(np.all(selected_neighbors >= 0) and np.all(selected_neighbors < len(description)), "neighbor_index_bounds_" + method)
            check(np.all(development[selected_neighbors]), "only_development_neighbors_" + method)
            dev_queries = development
            check(np.all(source_by_case[points["case_index"][selected_neighbors[dev_queries]]]
                         != source_by_case[points["case_index"][dev_queries]][:, None]), "exclude_entire_source_member_" + method)
            check(np.array_equal(points[method + "_neighbor_labels"], points["label"][selected_neighbors]), "neighbor_labels_" + method)
            close(points[method + "_score"], points["label"][selected_neighbors].mean(axis=1), "neighbor_mean_score_" + method, atol=0)
            for pool_name, pool in result["reference_pools"][method].items():
                allowed = development.copy()
                if pool["excluded_member"] is not None:
                    allowed &= source_by_case[points["case_index"]] != pool["excluded_member"]
                refs = np.flatnonzero(allowed)
                mean = description[refs].mean(axis=0)
                raw_std = description[refs].std(axis=0)
                std = np.maximum(raw_std, 1e-6)
                close(pool["mean"], mean, "reference_mean_" + method + pool_name)
                close(pool["population_std"], raw_std, "reference_std_" + method + pool_name)
                close(pool["std_used"], std, "reference_floor_" + method + pool_name)
                check(pool["allowed_reference_points"] == pool["valid_reference_points"] == len(refs), "pool_count_" + pool_name)
                check(pool["reference_case_ids"] == sorted({case_list[index]["id"] for index in points["case_index"][refs]}), "reference_case_scope")
                is_validation = ~development
                queries = np.flatnonzero(is_validation if pool_name == "all_development" else
                                         (development & (source_by_case[points["case_index"]] == pool["excluded_member"])))
                q = (description[queries] - mean) / std
                n = (description[selected_neighbors[queries]] - mean) / std
                distances = np.sqrt(np.sum((q[:, None, :] - n) ** 2, axis=2))
                close(points[method + "_neighbor_distances"][queries], distances, "saved_distances_" + method + pool_name)
                saved_distance = points[method + "_neighbor_distances"][queries]
                check(np.all(saved_distance[:, :-1] <= saved_distance[:, 1:]), "neighbor_distance_order_" + method + pool_name)
                for column in range(4):
                    tied = saved_distance[:, column] == saved_distance[:, column + 1]
                    left, right = selected_neighbors[queries[tied], column], selected_neighbors[queries[tied], column + 1]
                    ordered = (points["case_index"][left] < points["case_index"][right]) | (
                        (points["case_index"][left] == points["case_index"][right])
                        & (points["source_vertex_id"][left] < points["source_vertex_id"][right]))
                    check(np.all(ordered), "neighbor_tie_order_" + method + pool_name)
                scopes[(method, pool_name)] = (refs, mean, std)
        for name, summary in result["summaries"].items():
            selected = group_rows(name, rows)
            damaged_rows = [row for row in selected if not row["normal_control"]]
            check(summary["cases"] == len(selected), "summary_case_scope_" + name)
            check(summary["sampled_points"] == sum(row["sampled_points"] for row in selected), "summary_sample_scope_" + name)
            check(all(v == 0 for v in summary["invalid_queries"].values()), "summary_zero_invalid_" + name)
            for strength in ("all_support", "strong_support"):
                for method in METHODS:
                    by_patch = {}
                    for row in damaged_rows:
                        by_patch.setdefault(row["patch_id"], []).append(checked_case_metrics[row["id"]][strength][method])
                    patch_values = []
                    for patch_id, values in sorted(by_patch.items()):
                        item = {"patch_id": patch_id, "dented_cases": len(values)}
                        for key in ("ROC_AUC", "AP"):
                            valid = [value[key] for value in values if value[key] is not None]
                            item[key] = float(np.mean(valid)) if valid else None
                            item["valid_" + ("AUC" if key == "ROC_AUC" else "AP") + "_cases"] = len(valid)
                        patch_values.append(item)
                    for domain in ("common_valid", "method_valid"):
                        old = summary["macro"][domain][strength][method]
                        check(old["patches"] == len(patch_values), "summary_patch_count_" + name)
                        check(old["damaged_cases"] == len(damaged_rows), "summary_damaged_count_" + name)
                        for key in ("ROC_AUC", "AP"):
                            valid = [value[key] for value in patch_values if value[key] is not None]
                            close(old[key], float(np.mean(valid)) if valid else None, "patch_macro_" + name + method + key)
                            check(old["valid_" + ("AUC" if key == "ROC_AUC" else "AP") + "_patches"] == len(valid), "valid_patch_count")
                        for expected, actual in zip(patch_values, old["per_patch"]):
                            check(expected["patch_id"] == actual["patch_id"], "patch_id_match")
                            for key in ("ROC_AUC", "AP", "valid_AUC_cases", "valid_AP_cases", "dented_cases"):
                                close(actual[key], expected[key], "per_patch_metric_" + name + key)
        qa_rows = []
        for name in ("development", "validation_center", "validation_offcenter"):
            pool_rows = np.concatenate([np.arange(row["sample_start"], row["sample_end"]) for row in group_rows(name, rows)])
            qa_rows.extend([int(pool_rows[index]) for index in (0, 1, len(pool_rows) - 2, len(pool_rows) - 1)])
        qa_started = time.perf_counter()
        qa = []
        for row_index in qa_rows:
            case = case_list[points["case_index"][row_index]]
            pool_name = "all_development" if case["purpose"] == "validation" else "exclude_" + case["source"]
            for method in ("R0", "R1"):
                description = points[method + "_description"]
                refs, mean, std = scopes[(method, pool_name)]
                query = (description[row_index] - mean) / std
                values = (description[refs] - mean) / std
                squared = np.zeros(len(refs))
                for column in range(description.shape[1]):
                    squared += (values[:, column] - query[column]) ** 2
                distance = np.sqrt(squared)
                order = np.lexsort((points["source_vertex_id"][refs], points["case_index"][refs], distance))[:5]
                selected = refs[order]
                check(np.array_equal(selected, points[method + "_neighbor_rows"][row_index]), "QA_complete_pool_top5")
                close(distance[order], points[method + "_neighbor_distances"][row_index], "QA_complete_pool_distances")
                qa.append({"method": method, "sampled_row": row_index, "case_id": case["id"], "source_vertex_id": int(points["source_vertex_id"][row_index]), "reference_pool": pool_name})
        report["repeated_QA_top5_queries"] = len(qa)
        report["repeated_QA_query_point_count"] = len(qa_rows)
        report["QA_selection_rule"] = "first two and last two already-sampled rows in each of development/validation_center/validation_offcenter, selected independently of scores"
        report["QA_top5_recomputation_wall_s"] = time.perf_counter() - qa_started
        report["QA_queries"] = qa
        check(len(witness["evidence"]) == 6 == len(evidence_plan["evidence"]) == len(geometry["rows"]), "six_evidence_rows")
        for row in witness["evidence"]:
            for method in ("R0", "R1"):
                values = row["methods"][method]
                check(values["valid"] and len(values["neighbors"]) == 5, "witness_five_neighbors")
                expected = next((neighbor for neighbor in values["neighbors"] if neighbor["label"] != row["label"]), None)
                check(expected == values["nearest_opposite"], "witness_opposite_in_same_five_only")
                for neighbor in values["neighbors"]:
                    index = neighbor["sampled_row"]
                    check(neighbor["case_id"] == points["case_ids"][points["case_index"][index]], "witness_neighbor_case")
                    check(neighbor["source_vertex_id"] == points["source_vertex_id"][index], "witness_neighbor_source_id")
                    check(neighbor["label"] == points["label"][index], "witness_neighbor_label")
        check(trace["status"] == "passed_frozen_replay_and_trace", "trace_passed")
        check(trace["actual_forward_calls"] == marker["attempted_calls"] == marker["completed_calls"] == 7, "seven_actual_frozen_calls")
        check(trace["weights_and_normalization_preserved"], "frozen_weights_preserved")
        for row in trace["cases"]:
            check(row["layer_norm_calls"] == 12 and set(row["captured_node_counts"]) == {"h0", "h4", "h8", "h12"}, "original_hook_sequence")
            check(all(value["bitwise_equal"] and value["max_abs_difference"] == 0 for value in row["replay"].values()), "frozen_replay_exact")
            check(sha256(row["trace_path"]) == row["trace_sha256"], "saved_trace_hash")
        image = Path(geometry["image_path"])
        check(sha256(image) == geometry["image_sha256"], "actual_image_hash")
        check(geometry["shared_scale_all_panels"] and geometry["identical_camera_within_each_observation_reference_pair"], "paired_geometry_camera_and_scale")
        report.update(status="passed", observations_verified=348, sampled_points_verified=22272,
                      neighbors_verified=22272 * 5 * 2, case_metric_tables_verified=348,
                      summary_groups_verified=len(result["summaries"]), frozen_calls_verified=7,
                      image_visual_review="six rows and six panels per row visually inspected; missing opposite labels displayed explicitly",
                      interpretation_limit="All checks refer to the fixed 348 observations and saved queries; no repair-quality acceptance follows from these diagnostic metrics.")
    except Exception as error:
        report["status"] = "failed"
        report["failures"].append({"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        report["largest_arithmetic_difference"] = largest
        report["wall_s"] = time.perf_counter() - started
        report["cpu_s"] = time.process_time() - cpu_started
        report["bootstrap_to_report_wall_s"] = time.perf_counter() - BOOT_WALL
        report["bootstrap_to_report_cpu_s"] = time.process_time() - BOOT_CPU
        report["own_process_at_end"] = own_resources()
        (HERE / "INDEPENDENT_VERIFY.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "checks", "observations_verified", "sampled_points_verified", "summary_groups_verified", "repeated_QA_top5_queries", "wall_s")}))


if __name__ == "__main__":
    main()
