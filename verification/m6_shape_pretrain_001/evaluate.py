"""Evaluate fixed second-iteration candidates against the original task rules."""

import time
BOOT_WALL = time.perf_counter()
BOOT_CPU = time.process_time()

import os
for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
TRAIN = HERE.parent / "m6_shape_train_001"
DATA = HERE.parent / "m6_shape_data_001"
OPT = HERE.parent / "m6_shape_opt_001"
OBJECTIVE = HERE.parent / "m6_shape_objective_001"
METHODS = ("no_op", "pointfilter", "robust_mls")
sys.path.insert(0, str(TRAIN))
sys.path.insert(0, str(OBJECTIVE))


def module_at(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


QUALITY = module_at("_pretrain_original_quality", TRAIN / "evaluate.py")
SURFACE = module_at("_pretrain_original_surface", OBJECTIVE / "evaluate_surface.py")


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                          encoding="utf-8", newline="\n")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stamp():
    return time.perf_counter(), time.process_time()


def charge(stages, name, before):
    stages[name]["wall_s"] += time.perf_counter() - before[0]
    stages[name]["CPU_s"] += time.process_time() - before[1]


def quantiles(values):
    finite = [float(value) for value in values if value is not None and np.isfinite(value)]
    return {"requested_values": len(values), "count": len(finite), "not_applicable_values": len(values) - len(finite),
            "median": float(np.median(finite)) if finite else None,
            "p95": float(np.quantile(finite, .95)) if finite else None,
            "max": max(finite) if finite else None}


def incident_quality(before, after, triangles, incident_ids, saved_incident_ids, saved_context_face_ids):
    selected = triangles[incident_ids]
    first = np.cross(before[selected[:, 1]] - before[selected[:, 0]],
                     before[selected[:, 2]] - before[selected[:, 0]])
    second = np.cross(after[selected[:, 1]] - after[selected[:, 0]],
                      after[selected[:, 2]] - after[selected[:, 0]])
    valid_first = np.linalg.norm(first, axis=1) > 0
    valid_second = np.linalg.norm(second, axis=1) > 0
    new_degenerate = valid_first & ~valid_second
    reversed_normal = valid_first & valid_second & (np.einsum("ij,ij->i", first, second) < 0)
    missing = np.setdiff1d(incident_ids, saved_context_face_ids)
    return {"scope": "all full-source triangle rows incident to the original allowed region A",
            "complete": True, "incident_faces_required": len(incident_ids),
            "incident_faces_evaluated": len(selected), "missing_source_face_ids": [],
            "saved_incident_set_matches_full_source": bool(np.array_equal(incident_ids, np.sort(saved_incident_ids))),
            "saved_context_incident_coverage_complete": not len(missing),
            "saved_context_missing_source_face_ids": missing.tolist(),
            "degenerate_input": int((~valid_first).sum()), "degenerate_candidate": int((~valid_second).sum()),
            "new_degenerate_faces": int(new_degenerate.sum()),
            "new_degenerate_source_face_ids": incident_ids[new_degenerate].tolist(),
            "normal_reversals_from_input": int(reversed_normal.sum()),
            "reversed_source_face_ids": incident_ids[reversed_normal].tolist(),
            "degeneracy_definition": "exact zero cross-product norm, matching the original shape metric",
            "intersection_check": "unknown_not_evaluated_for_this_candidate"}


def coordinate_record(sample, full_before, full_candidate, method, base, source_triangles, incident_ids):
    mapping = sample["mapping"]
    context_ids = mapping["context_source_ids"]
    candidate = full_candidate[context_ids]
    observed, reference = sample["observed"], sample["reference"]
    allowed, free, boundary = (sample["graph"][name] for name in ("allowed_mask", "free_mask", "boundary_mask"))
    support = sample["labels"]["damaged_mask"]
    masks = {"A": allowed, "S": support, "N": allowed & ~support, "N_F": allowed & ~support & free}
    residual = np.linalg.norm(candidate - reference, axis=1)
    errors = {name: QUALITY._errors(residual, mask, sample["scale"]) for name, mask in masks.items()}
    result = copy.deepcopy(base)
    result.update(method=method, errors=errors)
    noop_s, noop_a = (base["no_op_errors"][name]["rmse_native"] for name in ("S", "A"))
    result["support_rmse_ratio_to_noop"] = errors["S"]["rmse_native"] / noop_s if noop_s is not None and noop_s > 0 else None
    result["support_ratio_applicability"] = "applicable" if noop_s is not None and noop_s > 0 else "empty_or_zero_noop_support_error"
    result["allowed_improvement_to_noop"] = 1 - errors["A"]["rmse_native"] / noop_a if noop_a is not None and noop_a > 0 else None
    changed = np.any(candidate.view(np.uint64) != observed.view(np.uint64), axis=1)
    full_free = np.zeros(len(full_before), dtype=bool)
    full_free[context_ids[free]] = True
    result.update(actual_changed_vertices=int(changed.sum()), actual_changed_free_vertices=int((changed & free).sum()),
                  actual_changed_fixed_vertices=int((changed & ~free).sum()),
                  fixed_bitwise_preserved=QUALITY._bitwise_equal(candidate[~free], observed[~free]),
                  boundary_bitwise_preserved=QUALITY._bitwise_equal(candidate[boundary], observed[boundary]),
                  outside_allowed_bitwise_preserved=QUALITY._bitwise_equal(candidate[~allowed], observed[~allowed]),
                  entire_context_bitwise_noop=QUALITY._bitwise_equal(candidate, observed),
                  full_source_outside_free_bitwise_preserved=QUALITY._bitwise_equal(full_candidate[~full_free], full_before[~full_free]),
                  full_source_changed_vertices=int(np.any(full_candidate.view(np.uint64) != full_before.view(np.uint64), axis=1).sum()))
    result["incident_quality"] = incident_quality(full_before, full_candidate, source_triangles, incident_ids,
                                                  mapping["incident_source_face_ids"], mapping["context_source_face_ids"])
    result["normal_point_preservation_passed"] = all(not errors[name]["count"] or (
        errors[name]["p95_over_scale"] <= .02 and errors[name]["max_over_scale"] <= .10) for name in ("N", "N_F"))
    a = errors["A"]
    result["normal_control_passed"] = (a["rmse_over_scale"] <= .01 and a["p95_over_scale"] <= .02
                                        and a["max_over_scale"] <= .05) if result["normal_control"] else None
    result["incident_quality_passed"] = not result["incident_quality"]["new_degenerate_faces"] and not result["incident_quality"]["normal_reversals_from_input"]
    result["coupling"] = {"contact": "unknown_not_evaluated_for_this_candidate",
                          "complete_intersections": "unknown_not_evaluated_for_this_candidate",
                          "artistic_acceptance": "unknown_not_evaluated_for_this_candidate"}
    result["status"] = "evaluated"
    return result


def summarize_group(selected, method):
    rows = [case["methods"][method] for case in selected if case["methods"][method]["status"] == "evaluated"]
    dents = [row for row in rows if not row["normal_control"]]
    controls = [row for row in rows if row["normal_control"]]
    expected_dents = sum(not case["normal_control"] for case in selected)
    expected_controls = len(selected) - expected_dents
    ratio = quantiles([row["support_rmse_ratio_to_noop"] for row in dents])
    improvement = quantiles([row["allowed_improvement_to_noop"] for row in dents])
    against_mls = quantiles([row.get("support_improvement_to_same_input_MLS") for row in dents])
    files = {source: quantiles([row["support_rmse_ratio_to_noop"] for row in dents if row["source"] == source])
             for source in sorted({case["source"] for case in selected if not case["normal_control"]})}
    expected_validation = sum(not case["normal_control"] and case["purpose"] == "validation" for case in selected)
    validation_files = {
        source: quantiles([row["support_rmse_ratio_to_noop"] for row in dents
                           if row["purpose"] == "validation" and row["source"] == source])
        for source in sorted({case["source"] for case in selected
                              if not case["normal_control"] and case["purpose"] == "validation"})}
    normal_failures = [row["id"] for row in rows if not row["normal_point_preservation_passed"]]
    control_failures = [row["id"] for row in controls if not row["normal_control_passed"]]
    face_failures = [row["id"] for row in rows if not row["incident_quality_passed"]]
    complete = len(rows) == len(selected)
    gate = {
        "all_requested_cases_evaluated": complete,
        "support_median_070": ratio["count"] == expected_dents and ratio["median"] <= .70 if expected_dents else None,
        "source_file_median_085": (sum(value["count"] for value in validation_files.values()) == expected_validation
            and all(value["count"] and value["median"] <= .85 for value in validation_files.values())) if expected_validation else None,
        "support_p95_105": ratio["count"] == expected_dents and ratio["p95"] <= 1.05 if expected_dents else None,
        "support_max_125": ratio["count"] == expected_dents and ratio["max"] <= 1.25 if expected_dents else None,
        "allowed_median_improvement_020": improvement["count"] == expected_dents and improvement["median"] >= .20 if expected_dents else None,
        "same_input_MLS_support_median_improvement_010": (against_mls["count"] == expected_dents
            and against_mls["median"] >= .10) if expected_dents and method == "pointfilter" else None,
        "normal_point_preservation": complete and not normal_failures,
        "normal_controls": len(controls) == expected_controls and not control_failures if expected_controls else None,
        "no_new_degenerate_or_reversed_faces": complete and not face_failures,
        "bitwise_fixed": complete and all(row["fixed_bitwise_preserved"] and row["boundary_bitwise_preserved"]
            and row["outside_allowed_bitwise_preserved"] and row["full_source_outside_free_bitwise_preserved"] for row in rows),
    }
    return {"requested_cases": len(selected), "evaluated_cases": len(rows),
            "unavailable_case_ids": [case["id"] for case in selected if case["methods"][method]["status"] != "evaluated"],
            "dented_requested": expected_dents, "dented_evaluated": len(dents),
            "normal_controls_requested": expected_controls, "normal_controls_evaluated": len(controls),
            "support_RMSE_ratio_to_noop": ratio, "allowed_improvement_to_noop": improvement,
            "support_improvement_to_same_input_MLS": against_mls,
            "source_file_support_RMSE_ratio": files,
            "validation_source_file_support_RMSE_ratio": validation_files,
            "source_file_grouping": "case.source; median085 gate applies only to purpose validation under this batch contract",
            "same_input_MLS_010_gate_applicability": "learning_candidate" if method == "pointfilter" else "not_applicable_geometry_baseline",
            "normal_point_gate_failed_case_ids": normal_failures,
            "normal_control_gate_failed_case_ids": control_failures,
            "normal_control_RMSE_over_scale": quantiles([row["errors"]["A"]["rmse_over_scale"] for row in controls]),
            "normal_free_p95_over_scale": quantiles([row["errors"]["N_F"]["p95_over_scale"] for row in rows]),
            "normal_free_max_over_scale": quantiles([row["errors"]["N_F"]["max_over_scale"] for row in rows]),
            "face_quality_failed_case_ids": face_failures,
            "new_degenerate_faces_sum_over_cases": sum(row["incident_quality"]["new_degenerate_faces"] for row in rows),
            "normal_reversals_sum_over_cases": sum(row["incident_quality"]["normal_reversals_from_input"] for row in rows),
            "full_source_incident_coverage_complete": all(row["incident_quality"]["complete"] for row in rows),
            "all_fixed_and_boundary_bitwise_preserved": gate["bitwise_fixed"],
            "surface_symmetric_RMSE": quantiles([row["surface"]["symmetric_RMSE"] for row in rows]),
            "coupling_unknown_cases": len(selected), "contact_unknown_cases": len(selected),
            "artistic_acceptance_unknown_cases": len(selected),
            "quality_gates": gate,
            "all_evaluated_shape_quality_gates_passed": complete and all(value for value in gate.values() if value is not None),
            "complete_repair_or_product_acceptance": "unknown_coupling_and_artistic_acceptance"}


def group_cases(cases):
    groups = {"all": cases, "normal_controls": [case for case in cases if case["normal_control"]]}
    for purpose, position, name in (("development_train_pool", "center", "development_center"),
                                     ("validation", "center", "validation_center"),
                                     ("validation", "offcenter", "validation_offcenter")):
        groups[name] = [case for case in cases if case["purpose"] == purpose and case["position_group"] == position]
    for source in sorted({case["source"] for case in cases}):
        groups["source_" + source] = [case for case in cases if case["source"] == source]
    for patch in sorted({case["patch_id"] for case in cases}):
        groups["patch_" + patch] = [case for case in cases if case["patch_id"] == patch]
    for amplitude in sorted({case["amplitude_ratio"] for case in cases if not case["normal_control"]}):
        groups["amplitude_" + str(amplitude)] = [case for case in cases if not case["normal_control"] and case["amplitude_ratio"] == amplitude]
        for name in ("development_center", "validation_center", "validation_offcenter"):
            groups[name + "_amplitude_" + str(amplitude)] = [case for case in groups[name] if not case["normal_control"] and case["amplitude_ratio"] == amplitude]
    return groups


def main():
    from surface_distance import context_boundary_edges

    stages = {name: {"wall_s": 0.0, "CPU_s": 0.0} for name in (
        "metadata_read", "arrays_and_hashes_read", "source_topology_read_and_boundary_count", "coordinate_and_incident_quality",
        "triangle_distance", "nearest_point_boundary_classification", "private_details_save", "summary")}
    identities = {}

    def remember(path):
        path = Path(path).resolve()
        if str(path) not in identities:
            identities[str(path)] = {"path": str(path), "bytes": path.stat().st_size, "sha256": digest(path)}

    def load_array(path, expected_sha=None):
        remember(path)
        if expected_sha and identities[str(Path(path).resolve())]["sha256"] != expected_sha:
            raise ValueError("candidate_or_input_SHA_mismatch_" + str(path))
        return np.load(path, allow_pickle=False)

    report = {"cycle_id": "M6-SHAPE-PRETRAIN-001", "status": "running", "cases": [], "failures": [],
              "methods": list(METHODS), "timings": stages, "training": 0, "model_forwards_in_evaluation": 0,
              "Bunny_arrays_or_scores": 0, "metric_domain": "finite allowed vertices to the same saved context closed triangles",
              "pretrained_shape_overlap": "Armadillo and Bunny shapes visible in paper training figure; exact point overlap unknown",
              "validation_scope": "Armadillo is a transfer stress group, not an unseen-asset generalization claim"}
    try:
        before = stamp()
        paths = {"selection": HERE / "CASE_SELECTION.json", "inputs": HERE / "INPUT_INDEX.json",
                 "outputs": HERE / "MODEL_OUTPUTS.json", "train": TRAIN / "RESULTS.json", "opt": OPT / "RESULTS.json",
                 "audit": DATA / "SOURCE_AUDIT.json", "plan": HERE / "PLAN.json"}
        values = {name: read(path) for name, path in paths.items()}
        for path in paths.values():
            remember(path)
        selected = values["selection"]["cases"]
        if len(selected) != 37 or any(case["source"] == "Stanford_Bunny" for case in selected):
            raise ValueError("selection_contract_mismatch")
        input_lookup = {case["id"]: case for case in values["inputs"]["cases"]}
        output_lookup = {case["id"]: case for case in values["outputs"]["cases"]}
        train_lookup = {case["id"]: case for case in values["train"]["model_cases"]}
        baseline_lookup = {case["id"]: case for case in values["train"]["baseline_cases"]}
        opt_lookup = {case["id"]: case for case in values["opt"]["model_cases"]}
        snapshots = {row["name"]: Path(row["snapshot"]["path"]) for row in values["audit"]["sources"]}
        snapshots["Stanford_Armadillo"] = TRAIN / "private/public_data/sources/Stanford_Armadillo/snapshot.npz"
        report["plan_sha256"] = digest(paths["plan"])
        charge(stages, "metadata_read", before)
        sources = {}
        for choice in selected:
            case_id = choice["id"]
            old = train_lookup[case_id]
            case = {key: old[key] for key in ("id", "patch_id", "source", "source_group", "purpose", "position_group",
                                             "normal_control", "radius_ratio", "amplitude_ratio", "stratum", "unit")}
            case.update(choice)
            if case["purpose"] == "reserved_test":
                raise ValueError("reserved_test_outside_scope")
            before = stamp()
            original_paths = {name: Path(old[name + "_path"]) for name in ("observed", "reference", "mapping", "graph")}
            folder = original_paths["observed"].parent.parent
            sample_name = case_id.split("/")[-1]
            original_paths["labels"] = folder / "labels" / (sample_name + ".npz")
            original_paths["input"] = folder / "inputs" / (sample_name + ".npz")
            arrays = {name: load_array(path) for name, path in original_paths.items()}
            sample = {"case": case, "observed": arrays["observed"], "reference": arrays["reference"],
                      "graph": {name: arrays["graph"][name].copy() for name in arrays["graph"].files},
                      "mapping": {name: arrays["mapping"][name].copy() for name in arrays["mapping"].files},
                      "labels": {name: arrays["labels"][name].copy() for name in arrays["labels"].files},
                      "scale": float(arrays["input"]["scale_m"]), "origin": arrays["input"]["origin_world_m"].copy(),
                      "folder": folder, "sample_name": sample_name}
            for name in ("graph", "mapping", "labels", "input"):
                arrays[name].close()
            inp = input_lookup[case_id]
            input_path = Path(inp.get("path", inp.get("input_path")))
            with load_array(input_path, inp.get("sha256", inp.get("input_sha256"))) as saved:
                full_before = saved["vertices"].copy()
                context_ids = saved["context_source_ids"].copy()
                free_ids = saved["free_source_ids"].copy()
            if full_before.dtype != np.float64 or full_before.ndim != 2 or full_before.shape[1] != 3 or not np.isfinite(full_before).all():
                raise ValueError("invalid_full_observed")
            if not np.array_equal(context_ids, sample["mapping"]["context_source_ids"]):
                raise ValueError("inference_and_evaluation_context_id_mismatch")
            if not QUALITY._bitwise_equal(full_before[context_ids], sample["observed"]):
                raise ValueError("inference_context_does_not_match_original_observation")
            expected_free = np.sort(context_ids[sample["graph"]["free_mask"]])
            if not np.array_equal(free_ids, expected_free):
                raise ValueError("inference_free_region_changed")
            charge(stages, "arrays_and_hashes_read", before)
            before = stamp()
            source_name = case["source"]
            if source_name not in sources:
                remember(snapshots[source_name])
                with np.load(snapshots[source_name], allow_pickle=False) as saved:
                    source_triangles = saved["triangles"].copy()
                sources[source_name] = {"triangles": source_triangles,
                                        "edges": SURFACE.source_edge_incidence(snapshots[source_name])}
            source = sources[source_name]
            allowed = sample["graph"]["allowed_mask"]
            incident_ids = np.flatnonzero(np.isin(source["triangles"], context_ids[allowed]).any(axis=1))
            context_triangles = sample["mapping"]["context_triangles"]
            domain_edges = SURFACE.classify_domain_edges(context_boundary_edges(context_triangles), context_ids, source["edges"])
            charge(stages, "source_topology_read_and_boundary_count", before)
            before = stamp()
            case_result = dict(case)
            case_result.update(methods={}, historical={}, allowed_query_vertices_per_direction=int(allowed.sum()),
                               free_vertices=int(sample["graph"]["free_mask"].sum()),
                               boundary_edges={name: len(domain_edges[name]) for name in ("all_context_boundary", "cut", "natural_open", "unknown")})
            base = QUALITY.measure_case(sample, np.zeros_like(sample["observed"]), "no_op")
            normalized_reference = (sample["reference"] - sample["origin"]) / sample["scale"]
            charge(stages, "coordinate_and_incident_quality", before)
            for method in METHODS:
                try:
                    before = stamp()
                    candidate_path = None
                    if method == "no_op":
                        full_candidate = full_before
                    else:
                        output = output_lookup.get(case_id, {}).get("methods", {}).get(method, {})
                        if not output.get("final_candidate_path"):
                            case_result["methods"][method] = {"status": "unavailable", "reason": output.get("error", "no_completed_second_iteration_candidate"),
                                                              "inference_status": output.get("status"), "id": case_id}
                            continue
                        candidate_path = Path(output["final_candidate_path"])
                        full_candidate = load_array(candidate_path, output.get("final_candidate_sha256"))
                    if full_candidate.dtype != np.float64 or full_candidate.shape != full_before.shape or not np.isfinite(full_candidate).all():
                        raise ValueError("invalid_saved_candidate_binary64_full_source")
                    charge(stages, "arrays_and_hashes_read", before)
                    before = stamp()
                    record = coordinate_record(sample, full_before, full_candidate, method, base, source["triangles"], incident_ids)
                    record["candidate_path"] = str(candidate_path.resolve()) if candidate_path else str(input_path.resolve())
                    record["candidate_payload"] = "npy full-source vertices" if candidate_path else "npz vertices, exact no-op"
                    record["candidate_sha256"] = digest(candidate_path or input_path)
                    charge(stages, "coordinate_and_incident_quality", before)
                    candidate = full_candidate[context_ids]
                    normalized_candidate = (candidate - sample["origin"]) / sample["scale"]
                    details = HERE / "private/surface" / method / case_id
                    forward = SURFACE.measure_direction(normalized_candidate[allowed], normalized_reference, context_triangles,
                                                         domain_edges, details / "candidate_to_reference.npz", context_ids[allowed], stages)
                    reverse = SURFACE.measure_direction(normalized_reference[allowed], normalized_candidate, context_triangles,
                                                         domain_edges, details / "reference_to_candidate.npz", context_ids[allowed], stages)
                    means = [forward["distance"]["mean_squared_distance"], reverse["distance"]["mean_squared_distance"]]
                    symmetric_mse = .5 * sum(means) if all(value is not None for value in means) else None
                    record["surface"] = {"candidate_to_reference": forward, "reference_to_candidate": reverse,
                                           "symmetric_MSE": symmetric_mse, "symmetric_RMSE": float(np.sqrt(symmetric_mse)) if symmetric_mse is not None else None}
                    case_result["methods"][method] = record
                except (OSError, ValueError, KeyError, FloatingPointError) as error:
                    case_result["methods"][method] = {"status": "evaluation_failed", "id": case_id,
                                                       "error_type": type(error).__name__, "reason": str(error)}
                    report["failures"].append({"id": case_id, "method": method, "type": type(error).__name__, "message": str(error)})
            before = stamp()
            for method, historical in (("old_gated_mls", baseline_lookup.get(case_id, {}).get("mls")),
                                       ("old_train_final", train_lookup.get(case_id)), ("old_opt_final_hard", opt_lookup.get(case_id))):
                case_result["historical"][method] = {"status": "available_saved_history" if historical else "not_run_or_unavailable",
                                                       "record": historical,
                                                       "scope": "original saved metrics and candidate identity path; no new inference or historical matrix rerun"}
            mls = case_result["methods"]["robust_mls"]
            for record in case_result["methods"].values():
                if record["status"] != "evaluated":
                    continue
                denominator = mls.get("errors", {}).get("S", {}).get("rmse_native")
                applicable = not case["normal_control"] and denominator is not None and denominator > 0
                record["support_improvement_to_same_input_MLS"] = 1 - record["errors"]["S"]["rmse_native"] / denominator if applicable else None
                record["same_input_MLS_support_RMSE_native"] = denominator
                record["same_input_MLS_support_RMSE_over_scale"] = denominator / sample["scale"] if denominator is not None else None
                record["same_input_MLS_ratio_applicability"] = "applicable" if applicable else "normal_control_or_missing_or_zero_MLS_support_error"
            report["cases"].append(case_result)
            charge(stages, "summary", before)
            print(json.dumps({"evaluated_case": case_id, "cases_completed": len(report["cases"])}), flush=True)
        before = stamp()
        groups = group_cases(report["cases"])
        report["summaries"] = {name: {method: summarize_group(cases, method) for method in METHODS} for name, cases in groups.items()}
        report["requested_cases"] = len(selected)
        report["case_count"] = len(report["cases"])
        report["actual_denominators"] = {"normal_controls": sum(case["normal_control"] for case in report["cases"]),
            "development_dents": sum(not case["normal_control"] and case["purpose"] == "development_train_pool" for case in report["cases"]),
            "validation_center_dents": sum(not case["normal_control"] and case["purpose"] == "validation" and case["position_group"] == "center" for case in report["cases"]),
            "validation_offcenter_dents": sum(case["position_group"] == "offcenter" for case in report["cases"])}
        report["directed_vertex_surface_queries"] = sum(row["surface"][direction]["query_points"] for case in report["cases"]
            for row in case["methods"].values() if row["status"] == "evaluated" for direction in ("candidate_to_reference", "reference_to_candidate"))
        report["unknown_denominators_per_method"] = {"requested_candidates": 37, "contact": 37, "complete_intersections": 37,
                                                      "coupling_acceptance": 37, "artistic_acceptance": 37}
        report["quality_gates"] = {name: report["summaries"][name]["pointfilter"]["quality_gates"]
                                   for name in ("development_center", "validation_center", "validation_offcenter")}
        report["all_shape_quality_gates_passed"] = all(group["pointfilter"]["all_evaluated_shape_quality_gates_passed"]
            for name, group in report["summaries"].items() if name in ("development_center", "validation_center", "validation_offcenter"))
        report["complete_repair_acceptance"] = "unknown_complete_coupling_and_artistic_validation"
        report["status"] = "completed_fixed_candidate_evaluation" if not report["failures"] else "completed_with_explicit_evaluation_failures"
        charge(stages, "summary", before)
    except Exception as error:
        report["status"] = "failed_evaluation"
        report["failures"].append({"type": type(error).__name__, "message": str(error), "completed_cases": len(report["cases"])})
        raise
    finally:
        report["input_file_identities"] = list(identities.values())
        report["code_sha256"] = {str(path): digest(path) for path in (Path(__file__).resolve(), TRAIN / "evaluate.py",
                                      TRAIN / "data_io.py", OBJECTIVE / "evaluate_surface.py", OBJECTIVE / "surface_distance.py")}
        report["wall_s_before_final_report"] = time.perf_counter() - BOOT_WALL
        report["CPU_s_before_final_report"] = time.process_time() - BOOT_CPU
        report["own_process_before_final_report"] = SURFACE.own_resources()
        report["measurement_scope"] = "bootstrap/import through report serialization start; source-array reads, all coordinate/incident/surface geometry and hashes included; outer process ledger captures startup/exit"
        write(HERE / "EVALUATION.json", report)


if __name__ == "__main__":
    main()
