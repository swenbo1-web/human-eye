"""Independently verify the frozen ring residuals, calibration and evaluations."""

import os
for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[name] = "1"

import hashlib
import json
from pathlib import Path
import sys
import time
import traceback

BOOT_WALL, BOOT_CPU = time.perf_counter(), time.process_time()
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np
from qa_math import independent_auc_ap, independent_bfs, independent_clusters, independent_fit, independent_frame, independent_operating, resources

CONFIGURATIONS = ("solid_point", "ring_point", "solid_cluster", "ring_cluster")


def main():
    checks, largest = 0, 0.0
    identities, failures, timings = {}, [], {}
    coverage = {"sources": 0, "cached_BFS_queries": 0, "cases": 0, "free_point_observations": 0,
                "independent_fit_queries": 0, "case_configurations": 0, "normal_calibration_patches": 0}

    def check(name, condition):
        nonlocal checks
        checks += 1
        if not condition:
            raise ValueError(name)

    def close(name, actual, expected):
        nonlocal largest
        if actual is None or expected is None:
            check(name, actual is expected)
            return
        first, second = np.asarray(actual), np.asarray(expected)
        check(name + "_shape", first.shape == second.shape)
        finite = np.isfinite(first) & np.isfinite(second)
        if np.any(finite):
            largest = max(largest, float(np.max(np.abs(first[finite] - second[finite]))))
        check(name, bool(np.allclose(first, second, rtol=2e-8, atol=2e-10, equal_nan=True)))

    def remember(path, expected=None):
        path = Path(path).resolve()
        if str(path) not in identities:
            data = path.read_bytes()
            identities[str(path)] = {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        if expected is not None:
            check("hash_" + path.name, identities[str(path)]["sha256"] == expected)
        check("no_Bunny_input", "Stanford_Bunny" not in str(path))
        return path

    def load(path, expected=None):
        return np.load(remember(path, expected), allow_pickle=False)

    def read(name):
        return json.loads((HERE / name).read_bytes())

    def charge(stage, beginning):
        row = timings.setdefault(stage, {"wall_s": 0.0, "CPU_s": 0.0})
        row["wall_s"] += time.perf_counter() - beginning[0]
        row["CPU_s"] += time.process_time() - beginning[1]

    try:
        beginning = time.perf_counter(), time.process_time()
        residuals, calibration, evaluation = read("RESIDUALS.json"), read("CALIBRATION.json"), read("EVALUATION.json")
        whitelist = {row["id"]: row for row in read("INPUT_WHITELIST.json")["cases"]}
        check("fixed348", len(whitelist) == len(residuals["cases"]) == len(evaluation["cases"]) == 348)
        check("fit_no_label_reference_fields_read", residuals["input_label_reference_or_generation_fields_read"] == 0)
        for row in read("CALIBRATION_FREEZE.json")["files"]:
            remember(row["path"], row["sha256"])
        sources = {}
        for row in residuals["topology"]:
            source_name = row["source"]
            source_case = next(case for case in whitelist.values() if case["source"] == source_name)
            with load(source_case["snapshot"]["path"], source_case["snapshot"]["sha256"]) as package:
                vertices, triangles = package["vertices"].astype(np.float64), package["triangles"].astype(np.int64)
            adjacency = [set() for _ in vertices]
            for first, second, third in triangles:
                adjacency[first].update((int(second), int(third)))
                adjacency[second].update((int(first), int(third)))
                adjacency[third].update((int(first), int(second)))
            for vertex, neighbors in enumerate(adjacency):
                neighbors.discard(vertex)
            with load(row["path"], row["sha256"]) as package:
                cache = {key: package[key].copy() for key in package.files}
            for index, query in enumerate(cache["query_source_ids"]):
                actual_ids, actual_hops = independent_bfs(adjacency, query)
                start, end = cache["neighbor_offsets"][index:index + 2]
                check("BFS_ids_" + source_name + str(query), np.array_equal(actual_ids, cache["neighbor_source_ids"][start:end]))
                check("BFS_hops_" + source_name + str(query), np.array_equal(actual_hops, cache["neighbor_hops"][start:end]))
                coverage["cached_BFS_queries"] += 1
            expected_edges = np.asarray([(first, second) for first, neighbors in enumerate(adjacency)
                                         for second in sorted(neighbors) if first < second], dtype=np.int64)
            check("complete_source_edges_" + source_name, np.array_equal(expected_edges, cache["edges"]))
            sources[source_name] = {"vertices": vertices, "triangles": triangles, "cache": cache, "edges": expected_edges}
            coverage["sources"] += 1
        charge("complete_source_and_independent_BFS", beginning)

        saved_cases, expected_scores, expected_labels, expected_areas, expected_depth = {}, {}, {}, {}, {}
        cases_by_id = {row["id"]: row for row in residuals["cases"]}
        calibration_cases = [row for row in residuals["cases"] if row["purpose"] == "development_train_pool" and row["normal_control"]]
        seed_values = {branch: [] for branch in ("solid", "ring")}
        beginning = time.perf_counter(), time.process_time()
        for row in residuals["cases"]:
            original = whitelist[row["id"]]
            source = sources[row["source"]]
            with load(row["path"], row["sha256"]) as package:
                saved = {key: package[key].copy() for key in package.files}
            with load(original["mapping_path"]) as package:
                context = package["context_source_ids"].astype(np.int64)
            with load(original["graph_path"]) as package:
                free_mask = package["free_mask"].astype(bool)
            free_context = np.flatnonzero(free_mask)
            free_context = free_context[np.argsort(context[free_context])]
            free_ids = context[free_context]
            check("original_F_" + row["id"], np.array_equal(free_ids, saved["free_source_ids"]))
            check("original_context_" + row["id"], np.array_equal(context, saved["context_source_ids"]))
            local = np.full(len(source["vertices"]), -1, dtype=np.int64)
            local[free_ids] = np.arange(len(free_ids))
            local_edges = local[source["edges"]]
            local_edges = local_edges[np.all(local_edges >= 0, axis=1)].T
            check("original_F_induced_edges_" + row["id"], np.array_equal(local_edges, saved["free_edge_index"]))
            observed = load(original["observed"]["path"], original["observed"]["sha256"])
            with load(original["input"]["path"], original["input"]["sha256"]) as package:
                normals = package["normals"][free_context].astype(np.float64)
                ell = float(package["scale_m"])
            close("original_ell_" + row["id"], ell, row["ell"])
            current = source["vertices"].copy()
            current[context] = observed
            close("current_F_positions_" + row["id"], current[free_ids], saved["query_positions"])
            mask = np.zeros(len(current), dtype=bool)
            mask[free_ids] = True
            incident_ids = np.flatnonzero(np.any(mask[source["triangles"]], axis=1))
            incident = source["triangles"][incident_ids]
            positions = current[incident]
            triangle_areas = .5 * np.sqrt(np.sum(np.cross(positions[:, 1] - positions[:, 0], positions[:, 2] - positions[:, 0]) ** 2, axis=1))
            all_area = np.zeros(len(current))
            np.add.at(all_area, incident.ravel(), np.repeat(triangle_areas / 3., 3))
            area = all_area[free_ids]
            close("full_source_F_area_" + row["id"], area, saved["area"])
            with load(row["patch_topology_cache"]["path"], row["patch_topology_cache"]["sha256"]) as package:
                check("all_incident_face_ids_" + row["id"], np.array_equal(incident_ids, package["incident_source_triangle_ids"]))
            cache = source["cache"]
            sample_rows = sorted(set((0, len(free_ids)//2, len(free_ids)-1)))
            for index, query in enumerate(free_ids):
                basis, valid = independent_frame(normals[index])
                close("observed_frame_" + row["id"] + str(index), saved["frame_basis"][index], basis)
                close("observed_unitnormal_" + row["id"] + str(index), saved["normal_unit"][index], basis[:, 2])
                check("normal_valid_" + row["id"] + str(index), bool(saved["normal_valid"][index]) == valid)
                cache_index = int(np.searchsorted(cache["query_source_ids"], query))
                start, end = cache["neighbor_offsets"][cache_index:cache_index+2]
                neighbors, hops = cache["neighbor_source_ids"][start:end], cache["neighbor_hops"][start:end]
                relative = current[neighbors] - current[query]
                radius = float(np.max(np.sqrt(np.sum(relative * relative, axis=1)))) if len(relative) else 0.
                close("common_R_" + row["id"] + str(index), saved["R"][index], radius)
                for branch, chosen in (("solid", np.ones(len(neighbors), dtype=bool)), ("ring", hops >= 6)):
                    check("branch_point_count", saved[branch+"_point_count"][index] == np.count_nonzero(chosen))
                    if index in sample_rows:
                        fitted = independent_fit((relative @ basis / radius)[chosen]) if valid and radius > 0 else {"valid": False, "height": 0.}
                        check("independent_fit_valid_" + row["id"] + branch + str(index), bool(saved[branch+"_valid"][index]) == fitted["valid"])
                        close("independent_fit_r_" + row["id"] + branch + str(index), saved[branch+"_r"][index], fitted["height"] * radius)
                        coverage["independent_fit_queries"] += 1
            for branch in ("solid", "ring"):
                check("failed_fit_zero_scores_" + row["id"] + branch,
                      bool(np.all(saved[branch+"_r"][~saved[branch+"_valid"]] == 0)))
                if row["normal_control"] and row["purpose"] == "development_train_pool":
                    seed_values[branch].append(np.abs(saved[branch+"_r"])/ell)
            folder = Path(original["observed"]["path"]).parents[1]
            reference = load(folder / "reference_local.npy")
            with load(folder / "labels" / (Path(original["observed"]["path"]).stem + ".npz")) as package:
                damaged = package["damaged_mask"][free_context].astype(bool)
            target_vector = reference[free_context] - observed[free_context]
            strong = np.linalg.norm(target_vector, axis=1) > .10 * ell
            target_depth = np.sum(target_vector * saved["normal_unit"], axis=1)
            target_depth[~saved["normal_valid"]] = np.nan
            expected_labels[row["id"]] = {"support": damaged, "strong": strong}
            expected_areas[row["id"]] = area
            expected_depth[row["id"]] = target_depth
            saved_cases[row["id"]] = saved
            coverage["cases"] += 1
            coverage["free_point_observations"] += len(free_ids)
        charge("all_current_geometry_areas_frames_R_and_sampled_fits", beginning)

        beginning = time.perf_counter(), time.process_time()
        for branch in ("solid", "ring"):
            close("33normal_q90_" + branch, calibration["seed_thresholds"][branch], np.quantile(np.concatenate(seed_values[branch]), .9, method="linear"))
        maxima = {name: [] for name in CONFIGURATIONS}
        for row in residuals["cases"]:
            saved = saved_cases[row["id"]]
            score = {}
            for branch in ("solid", "ring"):
                score[branch+"_point"] = np.abs(saved[branch+"_r"])/row["ell"]
                score[branch+"_cluster"], components = independent_clusters(saved[branch+"_r"], saved["area"], row["ell"], saved["free_edge_index"], calibration["seed_thresholds"][branch])
            expected_scores[row["id"]] = score
            if row["normal_control"] and row["purpose"] == "development_train_pool":
                for name in CONFIGURATIONS:
                    maxima[name].append(float(np.max(score[name])))
        for name in CONFIGURATIONS:
            close("33normal_patchmax_q95_" + name, calibration["operating_thresholds"][name], np.quantile(maxima[name], .95, method="linear"))
        for record in calibration["cases"]:
            with load(record["path"], record["sha256"]) as package:
                for name in CONFIGURATIONS:
                    close("calibration_saved_score_" + record["id"]+name, package[name], expected_scores[record["id"]][name])
            coverage["normal_calibration_patches"] += 1
        charge("independent_four_scores_and_normal_only_calibration", beginning)

        # Evaluation schema and every reported aggregate are checked below.
        verify_evaluation(evaluation, residuals, saved_cases, expected_scores, expected_labels, expected_areas,
                          expected_depth, calibration, check, close, coverage, load)
    except Exception as error:
        failures.append({"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()})

    report = {"cycle_id": "M6-SHAPE-RING-001", "status": "failed_independent_ring_verification" if failures else "passed_independent_ring_verification",
              "check_count": checks, "failures": failures, "coverage": coverage,
              "largest_compared_absolute_difference": largest, "timings": timings,
              "input_file_identities": list(identities.values()),
              "source_sha256": {name: hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in ("verify.py", "qa_math.py")},
              "wall_s_before_final_report": time.perf_counter()-BOOT_WALL,
              "CPU_s_before_final_report": time.process_time()-BOOT_CPU,
              "own_process_before_final_report": resources(), "new_model_forwards": 0, "training": 0,
              "repair_candidates": 0, "new_observation_cases": 0, "Bunny_arrays": 0,
              "interpretation": "Independent saved-result and repeated fixed-query verification, no repair or model selection rerun",
              "measurement_scope": "imports and complete verification before final write, enclosing monitor supplies process startup/exit"}
    (HERE / "INDEPENDENT_VERIFY.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf8", newline="\n")
    print(json.dumps({"status": report["status"], "checks": checks, "coverage": coverage}))
    if failures:
        raise SystemExit(1)


def verify_evaluation(evaluation, residuals, saved_cases, expected_scores, expected_labels, expected_areas,
                      expected_depth, calibration, check, close, coverage, load):
    rows = evaluation["cases"]
    by_id = {row["id"]: row for row in rows}
    old_report = json.loads((HERE.parent / "m6_shape_opt_001/EVAL_FINAL_HARD.json").read_bytes())
    old_index = {row["id"]: row for group in ("development", "validation") for row in old_report[group]["cases"]}
    own_case_metrics, own_case_operations, own_case_depth = {}, {}, {}

    def compare_distribution(name, actual, values):
        values = list(values)
        finite = np.asarray([value for value in values if value is not None], dtype=np.float64)
        check(name+"_requested", actual["requested_values"] == len(values))
        check(name+"_eligible", actual["count"] == len(finite))
        check(name+"_not_applicable", actual["not_applicable_values"] == len(values)-len(finite))
        expected = {"min": np.min(finite), "max": np.max(finite), "median": np.median(finite),
                    "mean": np.mean(finite), "p95": np.quantile(finite, .95, method="linear")} if len(finite) else dict.fromkeys(("min", "max", "median", "mean", "p95"))
        for key, value in expected.items():
            close(name+"_"+key, actual[key], value)

    def check_rank(name, actual, labels, scores):
        expected = independent_auc_ap(labels, scores)
        check(name+"_F", actual["points"] == len(labels))
        check(name+"_positive", actual["positive"] == expected["positive_points"])
        check(name+"_negative", actual["negative"] == expected["negative_points"])
        close(name+"_AUC", actual["ROC_AUC"], expected["ROC_AUC"])
        close(name+"_AP", actual["AP"], expected["AP"])
        return expected

    for row in rows:
        case_id = row["id"]
        saved, labels, area = saved_cases[case_id], expected_labels[case_id], expected_areas[case_id]
        with load(row["score_path"], row["score_sha256"]) as package:
            payload = {key: package[key].copy() for key in package.files}
        check("same_F_score_ids_"+case_id, np.array_equal(payload["free_source_ids"], saved["free_source_ids"]))
        for task in ("support", "strong"):
            check("same_F_labels_"+case_id+task, np.array_equal(payload[task], labels[task]))
        close("target_depth_"+case_id, payload["target_depth"], expected_depth[case_id])
        check("weak_damage_as_strong_negative_"+case_id, row["weak_damaged_as_strong_task_negative_points"] == int(np.count_nonzero(labels["support"] & ~labels["strong"])))
        own_case_metrics[case_id], own_case_operations[case_id], own_case_depth[case_id] = {}, {}, {}
        historical = old_index.get(case_id)
        if historical and Path(historical["component_path"]).exists():
            with load(historical["component_path"], historical["component_sha256"]) as package:
                expected_scores[case_id]["old_p"] = package["p"].reshape(-1)[saved["free_context_ids"]].astype(np.float64)
        for configuration in (*CONFIGURATIONS, "old_p"):
            actual = row["configurations"][configuration]
            if configuration == "old_p" and configuration not in expected_scores[case_id]:
                check("old_p_unavailable_status_"+case_id, actual["status"] != "available")
                own_case_metrics[case_id][configuration] = {task: {"ROC_AUC": None, "AP": None} for task in ("support", "strong")}
                continue
            score = expected_scores[case_id][configuration]
            close("saved_score_"+case_id+configuration, payload[configuration], score)
            own_case_metrics[case_id][configuration] = {}
            own_case_operations[case_id][configuration] = {}
            for task in ("support", "strong"):
                rank = check_rank("case_rank_"+case_id+configuration+task, actual["rank"][task], labels[task], score)
                own_case_metrics[case_id][configuration][task] = rank
                if configuration != "old_p":
                    threshold = calibration["operating_thresholds"][configuration]
                    close("frozen_threshold_"+case_id+configuration, actual["threshold"], threshold)
                    op = independent_operating(labels[task], score, area, threshold)
                    own_case_operations[case_id][configuration][task] = op
                    authored = actual["operation"][task]
                    for key in ("TP", "FP", "FN", "point_recall", "point_precision", "area_recall", "area_precision"):
                        close("case_operating_"+case_id+configuration+task+key, authored[key], op[key])
                    close("case_missed_area_"+case_id+configuration+task, authored["missed_positive_area_native"], op["missed_support_area"])
                    close("case_normal_area_"+case_id+configuration+task, authored["selected_normal_area_native"], op["selected_normal_area"])
                    check("strict_selected_mask_"+case_id+configuration, np.array_equal(payload[configuration+"_selected"], op["selected"]))
                    if configuration.endswith("cluster"):
                        branch = configuration.split("_")[0]
                        _, clusters = independent_clusters(saved[branch+"_r"], area, row["ell"], saved["free_edge_index"], calibration["seed_thresholds"][branch])
                        check("unsigned_component_count_"+case_id+branch, len(actual["components"]) == len(clusters))
                        for authored_component, cluster in zip(actual["components"], clusters):
                            check("component_vertex_count", authored_component["vertices"] == len(cluster["indices"]))
                            check("component_minimum5", authored_component["retained_at_least5"] == cluster["kept"])
                            for key, expected in (("energy_E", cluster["E"]), ("coherence_C", cluster["C"]), ("score_T", cluster["T"]), ("area_native", cluster["area"])):
                                close("component_"+key, authored_component[key], expected)
            coverage["case_configurations"] += 1
        for branch in ("solid", "ring"):
            actual = row["depth"][branch]
            support = labels["support"]
            valid = support & saved["normal_valid"] & np.isfinite(expected_depth[case_id])
            target = expected_depth[case_id][valid]
            prediction = saved[branch+"_r"][valid]
            error = prediction-target
            baseline = float(np.sqrt(np.mean(target*target))) if len(target) else None
            rmse = float(np.sqrt(np.mean(error*error))) if len(target) else None
            floor = 64*np.finfo(np.float64).eps*row["ell"]
            expected = {"support_RMSE_native": rmse, "zero_prediction_RMSE_native": baseline,
                        "RMSE_ratio_to_zero": rmse/baseline if baseline is not None and baseline>floor else None,
                        "bias_over_ell": float(error.mean())/row["ell"] if len(error) else None,
                        "support_RMSE_over_ell": rmse/row["ell"] if rmse is not None else None,
                        "prediction_RMS_over_target_RMS": float(np.sqrt(np.mean(prediction*prediction)))/baseline if baseline is not None and baseline>floor else None}
            eligible_sign = np.abs(target)>floor
            expected["sign_agreement_fraction"] = float(np.mean(np.sign(prediction[eligible_sign])==np.sign(target[eligible_sign]))) if np.any(eligible_sign) else None
            own_case_depth[case_id][branch] = expected
            for key, value in expected.items():
                close("case_depth_"+case_id+branch+key, actual[key], value)
            check("support_depth_valid_count", actual["support_depth_valid_points"] == len(target))
            check("support_depth_invalid_count", actual["support_depth_invalid_points"] == np.count_nonzero(support & ~valid))
            check("support_fit_unavailable_count", actual["support_fit_unavailable_points"] == np.count_nonzero(support & ~saved[branch+"_valid"]))
            compare_distribution("normal_depth_"+case_id+branch, actual["normal_F_abs_residual_over_ell"], np.abs(saved[branch+"_r"][~support])/row["ell"])
        baseline = own_case_depth[case_id]["solid"]["support_RMSE_native"]
        error = own_case_depth[case_id]["ring"]["support_RMSE_native"]
        close("ring_vs_solid_gain_"+case_id, row["ring_depth_improvement_to_solid"], 1-error/baseline if baseline is not None and baseline>64*np.finfo(float).eps*row["ell"] else None)

    def groups_for_rows():
        groups = {"all": rows,
            "development_center": [row for row in rows if row["purpose"]=="development_train_pool"],
            "validation_center": [row for row in rows if row["purpose"]=="validation" and row["position_group"]=="center"],
            "validation_offcenter": [row for row in rows if row["purpose"]=="validation" and row["position_group"]=="offcenter"],
            "development_normal_controls": [row for row in rows if row["purpose"]=="development_train_pool" and row["normal_control"]],
            "validation_normal_controls": [row for row in rows if row["purpose"]=="validation" and row["normal_control"]]}
        for field in ("source", "patch_id", "amplitude_ratio"):
            for value in {row[field] for row in rows}:
                groups[field+"_"+str(value)] = [row for row in rows if row[field]==value]
        for name in ("development_center", "validation_center", "validation_offcenter"):
            for amplitude in (.05, .15, .3):
                groups[name+"_amplitude_"+str(amplitude)] = [row for row in groups[name] if row["amplitude_ratio"]==amplitude]
        return groups

    own_group_values = {}
    for group_name, group_rows in groups_for_rows().items():
        actual_group = evaluation["groups"][group_name]
        check("group_case_denominator_"+group_name, actual_group["requested_cases"]==len(group_rows))
        check("group_F_denominator_"+group_name, actual_group["F_points"]==sum(len(expected_areas[row["id"]]) for row in group_rows))
        own_group_values[group_name] = {}
        for configuration in (*CONFIGURATIONS, "old_p"):
            entry = actual_group["configurations"][configuration]
            available = [row for row in group_rows if configuration in expected_scores[row["id"]]]
            check("group_available_"+group_name+configuration, entry["available_cases"]==len(available))
            own_group_values[group_name][configuration] = {}
            for task in ("support", "strong"):
                labels = np.concatenate([expected_labels[row["id"]][task] for row in available]) if available else np.empty(0, dtype=bool)
                scores = np.concatenate([expected_scores[row["id"]][configuration] for row in available]) if available else np.empty(0)
                check_rank("pool_"+group_name+configuration+task, entry["rank"][task]["point_pool"], labels, scores)
                for metric in ("ROC_AUC", "AP"):
                    compare_distribution("case_distribution_"+group_name+configuration+task+metric,
                        entry["rank"][task]["per_case_"+metric], [own_case_metrics[row["id"]][configuration][task][metric] for row in group_rows])
                    patches = {}
                    for row in group_rows:
                        patches.setdefault(row["patch_id"], []).append(own_case_metrics[row["id"]][configuration][task][metric])
                    patch_values=[]
                    authored=entry["rank"][task]["patch_macro_"+metric]
                    for patch, values in patches.items():
                        eligible=[value for value in values if value is not None]
                        expected=float(np.mean(eligible)) if eligible else None
                        close("patch_macro_cell_"+group_name+configuration+task+metric+patch, authored["patches"][patch]["value"], expected)
                        check("patch_eligible_cases", authored["patches"][patch]["eligible_cases"]==len(eligible))
                        if expected is not None:
                            patch_values.append(expected)
                    expected=float(np.mean(patch_values)) if patch_values else None
                    close("patch_equal_macro_"+group_name+configuration+task+metric, authored["value"], expected)
                    check("patch_eligible_count", authored["eligible_patches"]==len(patch_values))
                    own_group_values[group_name][configuration][task+"_"+metric]=expected
                if configuration != "old_p":
                    operations=[own_case_operations[row["id"]][configuration][task] for row in available]
                    op=entry["operation"][task]
                    for key in ("TP", "FP", "FN"):
                        close("group_operating_count_"+group_name+configuration+task+key,op[key],sum(value[key] for value in operations))
                    positive_area=sum(value["support_area"] for value in operations)
                    selected_positive=sum(value["area_recall"]*value["support_area"] if value["area_recall"] is not None else 0 for value in operations)
                    expected=selected_positive/positive_area if positive_area else None
                    close("group_native_area_recall_"+group_name+configuration+task, op["area_recall"], expected)
                    own_group_values[group_name][configuration][task+"_area_recall"]=expected
                    close("group_missed_area", op["missed_positive_area_native"],sum(value["missed_support_area"] for value in operations))
                    close("group_selected_normal_area",op["selected_normal_area_native"],sum(value["selected_normal_area"] for value in operations))
                    check("group_zero_detection_cases",op["zero_true_detection_cases"]==sum(value["zero_detected_dent"] for value in operations))
            if configuration != "old_p":
                false_patches=sorted({row["patch_id"] for row in available if row["normal_control"] and np.any(expected_scores[row["id"]][configuration]>calibration["operating_thresholds"][configuration])})
                check("normal_false_patch_ids_"+group_name+configuration,entry["normal_control_false_patch_ids"]==false_patches)
                own_group_values[group_name][configuration]["normal_false_patches"]=len(false_patches)
        for branch in ("solid", "ring"):
            damaged=[row for row in group_rows if not row["normal_control"]]
            for field in ("RMSE_ratio_to_zero", "support_RMSE_over_ell", "bias_over_ell", "prediction_RMS_over_target_RMS", "sign_agreement_fraction"):
                compare_distribution("group_depth_"+group_name+branch+field,actual_group["depth"][branch][field],
                    [own_case_depth[row["id"]][branch][field] for row in damaged])
        compare_distribution("group_ring_improvement_"+group_name,actual_group["depth"]["ring_improvement_to_solid"],
                             [row["ring_depth_improvement_to_solid"] for row in group_rows if not row["normal_control"]])

    gates=evaluation["decision_gates"]
    depth_flags=[]
    for name in ("validation_center", "validation_offcenter"):
        actual=evaluation["groups"][name]["depth"]
        ratio=actual["ring"]["RMSE_ratio_to_zero"]
        gain=actual["ring_improvement_to_solid"]
        expected={"all_requested_ratios_eligible":ratio["count"]==actual["ring"]["requested_dented_cases"] and gain["count"]==actual["ring"]["requested_dented_cases"],
                  "ring_zero_ratio_median_le085":ratio["median"] is not None and ratio["median"]<=.85,
                  "ring_vs_solid_gain_median_ge010":gain["median"] is not None and gain["median"]>=.10}
        check("depth_goal_"+name,gates["depth_goals"][name]==expected)
        depth_flags.extend(expected.values())
    check("all_depth_goals",gates["depth_signal_goals_passed"]==all(depth_flags))
    configuration_flags={}
    for configuration in ("solid_cluster", "ring_point", "ring_cluster"):
        actual=gates["localization_goals"][configuration]
        flags=[]
        for name in ("validation_center", "validation_offcenter"):
            values=own_group_values[name][configuration]
            baseline=own_group_values[name]["solid_point"]
            auc,ap,recall=(values["support_"+key] for key in ("ROC_AUC","AP","area_recall"))
            auc0,ap0,recall0=(baseline["support_"+key] for key in ("ROC_AUC","AP","area_recall"))
            expected={"patch_macro_AUC_ge080":auc is not None and auc>=.8,
                      "AUC_gain_ge005":auc is not None and auc0 is not None and auc-auc0>=.05,
                      "AP_not_lower":ap is not None and ap0 is not None and ap>=ap0,
                      "area_recall_gain_ge010":recall is not None and recall0 is not None and recall-recall0>=.10}
            for key,value in expected.items():
                check("localization_goal_"+name+configuration+key,actual["positions"][name][key]==value)
            flags.extend(expected.values())
        false=own_group_values["validation_normal_controls"][configuration]["normal_false_patches"]
        baseline=own_group_values["validation_normal_controls"]["solid_point"]["normal_false_patches"]
        normal_pass=false<=baseline and false<=1
        check("normal_patch_goal_"+configuration,actual["normal_false_patch_gate"]==normal_pass)
        configuration_flags[configuration]=all(flags) and normal_pass
        check("all_localization_goals_"+configuration,actual["all_localization_goals_passed"]==configuration_flags[configuration])
    check("ring_cluster_goal",gates["ring_cluster_localization_goals_passed"]==configuration_flags["ring_cluster"])
    check("any_configuration_goal",gates["any_new_configuration_localization_goals_passed"]==any(configuration_flags.values()))


if __name__ == "__main__":
    main()
