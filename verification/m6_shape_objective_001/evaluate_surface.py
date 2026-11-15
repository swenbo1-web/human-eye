"""Compare four saved outputs on the six fixed witnesses using triangle distance."""

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
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "m6_shape_data_001"
TRAIN = HERE.parent / "m6_shape_train_001"
OPT = HERE.parent / "m6_shape_opt_001"
OBSERVE = HERE.parent / "m6_shape_observe_001"
sys.path.insert(0, str(HERE))
METHODS = ("no_op", "mls", "train_final", "opt_final_hard")


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


def own_resources():
    spec = importlib.util.spec_from_file_location("_objective_surface_monitor", TRAIN / "process_runner.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    return module.process_metrics(ctypes.windll.kernel32.GetCurrentProcess())


def distance_statistics(distance2, valid, selection=None):
    selected = np.ones(len(distance2), dtype=bool) if selection is None else np.asarray(selection, dtype=bool)
    requested = int(selected.sum())
    usable = selected & np.asarray(valid, dtype=bool) & np.isfinite(distance2) & (distance2 >= 0)
    count = int(usable.sum())
    result = {"requested_points": requested, "valid_points": count, "invalid_points": requested - count,
              "complete": count == requested, "mean_squared_distance": None,
              "RMSE": None, "p95": None, "max": None}
    if requested and count == requested:
        values = np.sqrt(distance2[usable])
        result.update(mean_squared_distance=float(distance2[usable].mean()),
                      RMSE=float(np.sqrt(distance2[usable].mean())),
                      p95=float(np.quantile(values, .95, method="linear")), max=float(values.max()))
    return result


def legacy_result(record):
    normal_pass = all(not record["errors"][domain]["count"] or (
        record["errors"][domain]["p95_over_scale"] <= .02
        and record["errors"][domain]["max_over_scale"] <= .10) for domain in ("N", "N_F"))
    control_pass = None
    if record["normal_control"]:
        value = record["errors"]["A"]
        control_pass = value["rmse_over_scale"] <= .01 and value["p95_over_scale"] <= .02 and value["max_over_scale"] <= .05
    incident = record["incident_quality"]
    return {
        "original_method": record["method"], "normal_control": record["normal_control"],
        "errors": record["errors"], "support_rmse_ratio_to_noop": record["support_rmse_ratio_to_noop"],
        "allowed_improvement_to_noop": record["allowed_improvement_to_noop"],
        "actual_changed_vertices": record["actual_changed_vertices"],
        "actual_changed_free_vertices": record["actual_changed_free_vertices"],
        "actual_changed_fixed_vertices": record["actual_changed_fixed_vertices"],
        "fixed_bitwise_preserved": record["fixed_bitwise_preserved"],
        "boundary_bitwise_preserved": record["boundary_bitwise_preserved"],
        "outside_allowed_bitwise_preserved": record["outside_allowed_bitwise_preserved"],
        "incident_quality": incident, "fallback_noop": record["fallback_noop"],
        "fallback_reason": record["fallback_reason"],
        "original_normal_point_preservation_passed": normal_pass,
        "original_normal_control_passed": control_pass,
        "original_incident_quality_passed": incident["complete"] and not incident["new_degenerate_faces"]
        and not incident["normal_reversals_from_input"],
        "source": "unchanged saved records; original coordinate and protection gates retained",
    }


def source_edge_incidence(path):
    with np.load(path, allow_pickle=False) as saved:
        triangles = saved["triangles"].copy()
    if triangles.ndim != 2 or triangles.shape[1] != 3 or not np.issubdtype(triangles.dtype, np.integer):
        raise ValueError("invalid_full_source_triangle_array")
    if not len(triangles) or triangles.min() < 0:
        raise ValueError("empty_or_negative_full_source_triangles")
    key_base = int(triangles.max()) + 1
    if key_base > 3037000499:
        raise ValueError("full_source_edge_key_range_exceeded")
    edges = np.concatenate((triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]))
    edges.sort(axis=1)
    keys, counts = np.unique(edges[:, 0] * key_base + edges[:, 1], return_counts=True)
    return {"keys": keys, "counts": counts, "key_base": key_base, "source_triangles": len(triangles)}


def classify_domain_edges(boundary_edges, source_ids, source):
    global_edges = np.sort(source_ids[boundary_edges], axis=1)
    keys = global_edges[:, 0] * source["key_base"] + global_edges[:, 1]
    locations = np.searchsorted(source["keys"], keys)
    found = locations < len(source["keys"])
    found[found] &= source["keys"][locations[found]] == keys[found]
    counts = np.zeros(len(keys), dtype=np.int64)
    counts[found] = source["counts"][locations[found]]
    return {"all_context_boundary": boundary_edges, "cut": boundary_edges[counts > 1],
            "natural_open": boundary_edges[counts == 1], "unknown": boundary_edges[counts == 0],
            "source_incidence": counts, "global_edges": global_edges}


def measure_direction(queries, surface_vertices, triangles, domain_edges, detail_path, query_source_ids, stages):
    from surface_distance import nearest_points, classify_boundary_points

    before = stamp()
    nearest = nearest_points(queries, surface_vertices, triangles, query_block=32, triangle_block=256)
    charge(stages, "triangle_distance", before)
    before = stamp()
    boundaries = {}
    for kind in ("all_context_boundary", "cut", "natural_open", "unknown"):
        boundaries[kind] = classify_boundary_points(nearest["closest"], surface_vertices, domain_edges[kind],
                                                    query_block=32, edge_block=256)
    charge(stages, "nearest_point_boundary_classification", before)
    statistics = distance_statistics(nearest["distance2"], nearest["valid"])
    domain_diagnostics = {name: nearest[name] for name in (
        "query_count", "triangle_count", "invalid_query_count", "finite_query_count",
        "available_query_count", "numeric_unavailable_query_count", "nonfinite_surface_vertex_count",
        "numeric_nonfinite_triangle_count", "degenerate_triangle_count", "zero_length_triangle_edge_count")}
    result = {"status": nearest["status"], "distance": statistics,
              "metric_domain_diagnostics": domain_diagnostics,
              "boundary_length_tolerance": boundaries["all_context_boundary"]["length_tolerance"],
              "boundary_classification": {kind: {
                  "nearest_point_on_boundary_count": int((value["on_boundary"] & nearest["valid"]).sum()),
                  "query_distance_for_boundary_hits": distance_statistics(
                      nearest["distance2"], nearest["valid"], value["on_boundary"]),
                  "helper_status": value["status"],
                  "boundary_segment_count": len(domain_edges[kind]),
              } for kind, value in boundaries.items()},
              "nearest_point_off_all_context_boundary": distance_statistics(
                  nearest["distance2"], nearest["valid"], ~boundaries["all_context_boundary"]["on_boundary"]),
              "query_points": len(queries), "detail_path": str(detail_path.resolve())}
    before = stamp()
    detail_path.parent.mkdir(parents=True, exist_ok=True)
    arrays = {"query_source_ids": query_source_ids, "query_normalized": queries,
              "distance2": nearest["distance2"], "closest_normalized": nearest["closest"],
              "triangle_id": nearest["triangle_id"], "barycentric": nearest["barycentric"],
              "valid": nearest["valid"]}
    for kind, value in boundaries.items():
        arrays[kind + "_nearest_point_flag"] = value["on_boundary"]
        arrays[kind + "_distance2_from_nearest_point"] = value["distance2"]
        arrays[kind + "_edge_id"] = value["edge_id"]
    np.savez_compressed(detail_path, **arrays)
    result["detail_sha256"] = digest(detail_path)
    charge(stages, "private_details_save", before)
    return result


def main():
    stages = {name: {"wall_s": 0.0, "CPU_s": 0.0} for name in (
        "metadata_read", "old_array_read", "full_source_topology_read_and_boundary_count",
        "domain_preparation", "triangle_distance", "nearest_point_boundary_classification",
        "private_details_save", "legacy_and_summary")}
    marker = HERE / "SURFACE_STARTED.json"
    if marker.exists() and read(marker).get("status") == "completed":
        raise RuntimeError("surface_diagnostic_already_completed")
    report = {"cycle_id": "M6-SHAPE-OBJECTIVE-001", "status": "running", "cases": [], "failures": [],
              "new_model_forwards": 0, "new_training": 0, "new_repair_outputs": 0,
              "threshold_searches": 0, "Bunny_arrays": 0, "methods": list(METHODS),
              "preflight_snapshot_schema_read": {
                  "snapshot": str(TRAIN / "private/public_data/sources/Stanford_Armadillo/snapshot.npz"),
                  "arrays_read": ["vertices", "triangles", "source_polygon_ids"],
                  "tool_process_wall_s": .3597553, "CPU_s": None, "peak_working_set_bytes": None,
                  "timing": "after PLAN was written, before final PLAN freeze; no distances computed"},
              "timings": stages, "input_identities": []}
    identities = {}

    def remember(path):
        path = Path(path).resolve()
        if str(path) not in identities:
            identities[str(path)] = {"path": str(path), "bytes": path.stat().st_size, "sha256": digest(path)}

    def load_coordinates(path):
        remember(path)
        values = np.load(path, allow_pickle=False)
        if values.ndim != 2 or values.shape[1] != 3 or values.dtype != np.float64:
            raise ValueError("stored_candidate_requires_binary64_N3")
        return values

    try:
        before = stamp()
        plan = read(HERE / "PLAN.json")
        report["plan_sha256"] = digest(HERE / "PLAN.json")
        evidence_path = OBSERVE / "EVIDENCE_PLAN.json"
        evidence = read(evidence_path)["evidence"]
        train_path, opt_path = TRAIN / "RESULTS.json", OPT / "RESULTS.json"
        training, optimized = read(train_path), read(opt_path)
        train_lookup = {row["id"]: row for row in training["model_cases"]}
        opt_lookup = {row["id"]: row for row in optimized["model_cases"]}
        baseline_lookup = {row["id"]: row for row in training["baseline_cases"]}
        source_audit_path = DATA / "SOURCE_AUDIT.json"
        source_paths = {row["name"]: Path(row["snapshot"]["path"]) for row in read(source_audit_path)["sources"]}
        source_paths["Stanford_Armadillo"] = TRAIN / "private/public_data/sources/Stanford_Armadillo/snapshot.npz"
        assert len(evidence) == 6 and {row["evidence_id"] for row in evidence} == {
            "development_Yanyite", "development_Richie", "development_Chipow", "development_Yunhex",
            "validation_center", "validation_offcenter"}
        for path in (HERE / "PLAN.json", evidence_path, train_path, opt_path, source_audit_path):
            remember(path)
        write(marker, {"status": "started", "case_ids": [row["case_id"] for row in evidence],
                       "methods": list(METHODS), "new_model_forwards": 0})
        charge(stages, "metadata_read", before)
        source_topologies = {}
        for witness in evidence:
            case_id = witness["case_id"]
            original = train_lookup[case_id]
            if original["purpose"] == "reserved_test" or original["source"] == "Stanford_Bunny":
                raise ValueError("reserved_test_outside_scope")
            records = {"no_op": baseline_lookup[case_id]["no_op"], "mls": baseline_lookup[case_id]["mls"],
                       "train_final": original, "opt_final_hard": opt_lookup[case_id]}
            before = stamp()
            observed = load_coordinates(original["observed_path"])
            reference = load_coordinates(original["reference_path"])
            graph_path, mapping_path = Path(original["graph_path"]), Path(original["mapping_path"])
            remember(graph_path)
            remember(mapping_path)
            with np.load(graph_path, allow_pickle=False) as saved:
                allowed = saved["allowed_mask"].copy()
            with np.load(mapping_path, allow_pickle=False) as saved:
                triangles = saved["context_triangles"].copy()
                source_ids = saved["context_source_ids"].copy()
                source_faces = saved["context_source_face_ids"].copy()
            input_path = graph_path.parent / "inputs" / (case_id.split("/")[-1] + ".npz")
            remember(input_path)
            with np.load(input_path, allow_pickle=False) as saved:
                scale = float(saved["scale_m"])
                origin = saved["origin_world_m"].copy()
            if not np.isfinite(scale) or scale <= 0 or origin.shape != (3,) or not np.isfinite(origin).all():
                raise ValueError("invalid_observation_frame")
            if reference.shape != observed.shape or len(source_ids) != len(reference):
                raise ValueError("stored_geometry_context_alignment_mismatch")
            charge(stages, "old_array_read", before)
            before = stamp()
            source = original["source"]
            if source not in source_topologies:
                remember(source_paths[source])
                source_topologies[source] = source_edge_incidence(source_paths[source])
            from surface_distance import context_boundary_edges
            boundary_edges = context_boundary_edges(triangles)
            domain_edges = classify_domain_edges(boundary_edges, source_ids, source_topologies[source])
            charge(stages, "full_source_topology_read_and_boundary_count", before)
            before = stamp()
            reference_normalized = (reference - origin) / scale
            case = {"case_id": case_id, "evidence_id": witness["evidence_id"], "source": source,
                    "purpose": original["purpose"], "position_group": original["position_group"],
                    "normal_control": original["normal_control"], "witness_source_vertex_id": witness["source_vertex_id"],
                    "scale_native": scale, "normalization": "one shared observed context median edge length",
                    "context_vertices": len(reference), "allowed_query_vertices_per_direction": int(allowed.sum()),
                    "context_triangles": len(triangles), "source_snapshot_used_only_for_boundary_topology": str(source_paths[source]),
                    "boundary_edges": {kind: len(domain_edges[kind]) for kind in (
                        "all_context_boundary", "cut", "natural_open", "unknown")},
                    "boundary_classification": "context edge incidence1; full-source incidence>1 is cut, =1 natural open, absent unknown",
                    "methods": {}}
            charge(stages, "domain_preparation", before)
            for method in METHODS:
                before = stamp()
                record = records[method]
                candidate_path = Path(record["candidate_path"])
                candidate = load_coordinates(candidate_path)
                if candidate.shape != reference.shape:
                    raise ValueError("candidate_context_alignment_mismatch")
                candidate_normalized = (candidate - origin) / scale
                charge(stages, "old_array_read", before)
                detail_folder = HERE / "private/surface" / method / case_id
                forward = measure_direction(candidate_normalized[allowed], reference_normalized, triangles,
                                            domain_edges, detail_folder / "candidate_to_reference.npz", source_ids[allowed], stages)
                backward = measure_direction(reference_normalized[allowed], candidate_normalized, triangles,
                                             domain_edges, detail_folder / "reference_to_candidate.npz", source_ids[allowed], stages)
                before = stamp()
                means = [forward["distance"]["mean_squared_distance"], backward["distance"]["mean_squared_distance"]]
                symmetric_mse = float(.5 * sum(means)) if all(value is not None for value in means) else None
                case["methods"][method] = {"candidate_path": str(candidate_path), "candidate_sha256": digest(candidate_path),
                                           "legacy": legacy_result(record), "candidate_to_reference": forward,
                                           "reference_to_candidate": backward, "symmetric_MSE": symmetric_mse,
                                           "symmetric_RMSE": float(np.sqrt(symmetric_mse)) if symmetric_mse is not None else None,
                                           "surface_status": "available" if symmetric_mse is not None else "unavailable",
                                           "new_candidate_or_prediction": False}
                charge(stages, "legacy_and_summary", before)
            coordinate_order = sorted(METHODS, key=lambda method: (case["methods"][method]["legacy"]["errors"]["A"]["rmse_over_scale"], METHODS.index(method)))
            surface_order = sorted(METHODS, key=lambda method: (
                case["methods"][method]["symmetric_RMSE"] if case["methods"][method]["symmetric_RMSE"] is not None else float("inf"), METHODS.index(method)))
            case["coordinate_A_RMSE_order"] = coordinate_order
            case["surface_symmetric_RMSE_order"] = surface_order
            case["exact_sorted_method_order_matches"] = coordinate_order == surface_order
            case["surface_metric_unit"] = "observed median-edge length; finite allowed-vertex samples to saved context triangle domain"
            report["cases"].append(case)
            print(json.dumps({"case": case_id, "comparisons_completed": len(report["cases"]) * 4}), flush=True)
        report.update(status="completed_saved_output_surface_diagnostic", case_count=len(report["cases"]),
                      saved_output_comparisons=sum(len(case["methods"]) for case in report["cases"]),
                      directed_vertex_surface_queries=sum(
                          value[direction]["query_points"] for case in report["cases"] for value in case["methods"].values()
                          for direction in ("candidate_to_reference", "reference_to_candidate")),
                      interpretation="finite vertices to finite context triangle surfaces; original protection and incident gates remain binding",
                      triangle_domain_expanded=False, full_source_geometry_used_for_distances=False)
    except Exception as error:
        report["status"] = "failed_surface_diagnostic"
        report["failures"].append({"type": type(error).__name__, "message": str(error), "completed_cases": len(report["cases"])})
        write(marker, {"status": "failed", "error": type(error).__name__ + " " + str(error),
                       "completed_cases": len(report["cases"]), "new_model_forwards": 0})
        raise
    finally:
        report["input_identities"] = list(identities.values())
        report["wall_s_before_report_write"] = time.perf_counter() - BOOT_WALL
        report["CPU_s_before_report_write"] = time.process_time() - BOOT_CPU
        report["own_process_before_report_write"] = own_resources()
        report["code_sha256"] = {name: digest(HERE / name) for name in ("evaluate_surface.py", "surface_distance.py") if (HERE / name).exists()}
        report["measurement_scope"] = "Python bootstrap through report serialization start; final write/exit and shell overhead excluded"
        write(HERE / "SURFACE_RESULTS.json", report)
    write(marker, {"status": "completed", "case_count": 6, "saved_output_comparisons": 24,
                   "new_model_forwards": 0, "new_training": 0})


if __name__ == "__main__":
    main()
