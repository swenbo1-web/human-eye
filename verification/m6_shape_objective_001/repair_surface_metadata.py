"""Restore omitted surface-domain counters without recomputing any distance."""

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

import numpy as np

HERE = Path(__file__).resolve().parent
TRAIN = HERE.parent / "m6_shape_train_001"
DIRECTIONS = ("candidate_to_reference", "reference_to_candidate")
COUNTER_FIELDS = (
    "query_count", "triangle_count", "invalid_query_count", "finite_query_count", "available_query_count",
    "numeric_unavailable_query_count", "nonfinite_surface_vertex_count", "numeric_nonfinite_triangle_count",
    "degenerate_triangle_count", "zero_length_triangle_edge_count")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                          encoding="utf-8", newline="\n")


def stamp():
    return time.perf_counter(), time.process_time()


def charge(stages, name, before):
    stages[name]["wall_s"] += time.perf_counter() - before[0]
    stages[name]["CPU_s"] += time.process_time() - before[1]


def resources():
    spec = importlib.util.spec_from_file_location("_objective_metadata_monitor", TRAIN / "process_runner.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    return module.process_metrics(ctypes.windll.kernel32.GetCurrentProcess())


def scientific_payload(report):
    """Hash only already measured quantities and their saved-detail identities."""
    return [{"case_id": case["case_id"],
             "coordinate_order": case["coordinate_A_RMSE_order"],
             "surface_order": case["surface_symmetric_RMSE_order"],
             "methods": {name: {"legacy": method["legacy"], "symmetric_MSE": method["symmetric_MSE"],
                                "symmetric_RMSE": method["symmetric_RMSE"],
                                "directions": {direction: {
                                    key: method[direction][key] for key in (
                                        "status", "distance", "boundary_length_tolerance", "boundary_classification",
                                        "nearest_point_off_all_context_boundary", "query_points", "detail_path", "detail_sha256")}
                                    for direction in DIRECTIONS}}
                         for name, method in case["methods"].items()}}
            for case in report["cases"]]


def payload_sha(report):
    blob = json.dumps(scientific_payload(report), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(blob).hexdigest()


def triangle_counters(queries, valid, vertices, triangles):
    finite_queries = np.isfinite(queries).all(axis=1)
    nonfinite_vertices = int(np.count_nonzero(~np.isfinite(vertices).all(axis=1)))
    output = {
        "query_count": len(queries), "triangle_count": len(triangles),
        "invalid_query_count": int(np.count_nonzero(~finite_queries)),
        "finite_query_count": int(np.count_nonzero(finite_queries)),
        "available_query_count": int(np.count_nonzero(valid)),
        "numeric_unavailable_query_count": int(np.count_nonzero(finite_queries & ~valid)),
        "nonfinite_surface_vertex_count": nonfinite_vertices,
        "numeric_nonfinite_triangle_count": 0,
        "degenerate_triangle_count": None, "zero_length_triangle_edge_count": None,
    }
    if nonfinite_vertices or not len(triangles):
        return output
    faces = vertices[triangles]
    with np.errstate(over="ignore", invalid="ignore"):
        normals = np.cross(faces[:, 1] - faces[:, 0], faces[:, 2] - faces[:, 0])
        normal2 = np.einsum("ij,ij->i", normals, normals)
    output["numeric_nonfinite_triangle_count"] = int(np.count_nonzero(~np.isfinite(normal2)))
    if output["numeric_nonfinite_triangle_count"]:
        return output
    output["degenerate_triangle_count"] = int(np.count_nonzero(normal2 == 0))
    output["zero_length_triangle_edge_count"] = sum(
        int(np.count_nonzero(np.all(faces[:, start] == faces[:, end], axis=1)))
        for start, end in ((0, 1), (1, 2), (2, 0)))
    assert tuple(output) == COUNTER_FIELDS
    return output


def reconstruct_executed_source(current_path, expected_sha):
    current = current_path.read_text(encoding="utf-8")
    new = '''    domain_diagnostics = {name: nearest[name] for name in (
        "query_count", "triangle_count", "invalid_query_count", "finite_query_count",
        "available_query_count", "numeric_unavailable_query_count", "nonfinite_surface_vertex_count",
        "numeric_nonfinite_triangle_count", "degenerate_triangle_count", "zero_length_triangle_edge_count")}
    result = {"status": nearest["status"], "distance": statistics,
              "metric_domain_diagnostics": domain_diagnostics,'''
    old = '''    result = {"status": nearest["status"], "distance": statistics,
              "metric_domain_diagnostics": nearest.get("counts", {}),'''
    if current.count(new) != 1:
        raise ValueError("cannot_uniquely_reverse_counter_metadata_patch")
    original = current.replace(new, old).encode("utf-8")
    if hashlib.sha256(original).hexdigest() != expected_sha:
        raise ValueError("reconstructed_executed_source_hash_mismatch")
    return original


def main():
    marker = HERE / "SURFACE_METADATA_REPAIR.json"
    if marker.exists() and json.loads(marker.read_bytes()).get("status") == "completed_metadata_only_repair":
        raise RuntimeError("metadata_repair_already_completed")
    stages = {name: {"wall_s": 0.0, "CPU_s": 0.0} for name in (
        "preserve_initial_report_and_source", "old_metadata_read", "old_arrays_and_details_read",
        "counter_and_overlap_reconstruction", "final_integrity_checks")}
    before = stamp()
    output = HERE / "SURFACE_RESULTS.json"
    initial_bytes = output.read_bytes()
    initial = json.loads(initial_bytes)
    initial_sha = hashlib.sha256(initial_bytes).hexdigest()
    expected_source_sha = initial["code_sha256"]["evaluate_surface.py"]
    original_source = reconstruct_executed_source(HERE / "evaluate_surface.py", expected_source_sha)
    recovery = HERE / "private/recovery"
    recovery.mkdir(parents=True, exist_ok=True)
    initial_path = recovery / "SURFACE_RESULTS_initial.json"
    original_source_path = recovery / "evaluate_surface_initial_executed.py"
    for path, blob in ((initial_path, initial_bytes), (original_source_path, original_source)):
        if path.exists():
            if path.read_bytes() != blob:
                raise ValueError("existing_recovery_artifact_differs_" + path.name)
        else:
            path.write_bytes(blob)
    report = json.loads(initial_bytes)
    original_payload_sha = payload_sha(report)
    charge(stages, "preserve_initial_report_and_source", before)
    before = stamp()
    train_path = TRAIN / "RESULTS.json"
    records = {row["id"]: row for row in json.loads(train_path.read_bytes())["model_cases"]}
    old_identities = {row["path"]: row for row in report["input_identities"]}
    read_files = {}

    def verify_old_file(path):
        path = Path(path).resolve()
        key = str(path)
        if key not in read_files:
            actual = {"path": key, "bytes": path.stat().st_size, "sha256": sha256(path)}
            expected = old_identities.get(key)
            if expected is not None and actual != expected:
                raise ValueError("old_input_changed_since_distance_measurement_" + key)
            read_files[key] = actual

    charge(stages, "old_metadata_read", before)
    directions_repaired = 0
    original_detail_hashes = []
    for case in report["cases"]:
        before = stamp()
        old = records[case["case_id"]]
        reference_path = Path(old["reference_path"])
        mapping_path = Path(old["mapping_path"])
        input_path = mapping_path.parent / "inputs" / (case["case_id"].split("/")[-1] + ".npz")
        for path in (reference_path, mapping_path, input_path):
            verify_old_file(path)
        reference = np.load(reference_path, allow_pickle=False)
        with np.load(mapping_path, allow_pickle=False) as saved:
            triangles = saved["context_triangles"].copy()
        with np.load(input_path, allow_pickle=False) as saved:
            origin = saved["origin_world_m"].copy()
            scale = float(saved["scale_m"])
        reference_normalized = (reference - origin) / scale
        charge(stages, "old_arrays_and_details_read", before)
        for method in case["methods"].values():
            before = stamp()
            candidate_path = Path(method["candidate_path"])
            verify_old_file(candidate_path)
            candidate = np.load(candidate_path, allow_pickle=False)
            candidate_normalized = (candidate - origin) / scale
            charge(stages, "old_arrays_and_details_read", before)
            for direction in DIRECTIONS:
                measured = method[direction]
                before = stamp()
                path = Path(measured["detail_path"])
                actual_hash = sha256(path)
                if actual_hash != measured["detail_sha256"]:
                    raise ValueError("distance_detail_changed_" + str(path))
                original_detail_hashes.append((str(path), actual_hash))
                with np.load(path, allow_pickle=False) as saved:
                    queries = saved["query_normalized"].copy()
                    valid = saved["valid"].copy()
                    flags = {kind: saved[kind + "_nearest_point_flag"].copy() for kind in (
                        "all_context_boundary", "cut", "natural_open", "unknown")}
                charge(stages, "old_arrays_and_details_read", before)
                before = stamp()
                surface_vertices = reference_normalized if direction == "candidate_to_reference" else candidate_normalized
                counters = triangle_counters(queries, valid, surface_vertices, triangles)
                if measured["metric_domain_diagnostics"] and measured["metric_domain_diagnostics"] != counters:
                    raise ValueError("preexisting_counter_disagrees_with_saved_arrays")
                measured["metric_domain_diagnostics"] = counters
                union = flags["cut"] | flags["natural_open"] | flags["unknown"]
                measured["boundary_classification_overlap"] = {
                    "all_context_boundary_hits": int(np.count_nonzero(flags["all_context_boundary"] & valid)),
                    "cut_or_natural_or_unknown_hits": int(np.count_nonzero(union & valid)),
                    "cut_and_natural_open_hits": int(np.count_nonzero(flags["cut"] & flags["natural_open"] & valid)),
                    "cut_and_unknown_hits": int(np.count_nonzero(flags["cut"] & flags["unknown"] & valid)),
                    "natural_open_and_unknown_hits": int(np.count_nonzero(flags["natural_open"] & flags["unknown"] & valid)),
                    "union_vs_all_mismatch_points": int(np.count_nonzero((union != flags["all_context_boundary"]) & valid)),
                    "interpretation": "a shared boundary vertex may belong to several edge classes; hit counts can overlap",
                }
                directions_repaired += 1
                charge(stages, "counter_and_overlap_reconstruction", before)
    before = stamp()
    if directions_repaired != 48:
        raise ValueError("six_cases_four_methods_two_directions_required")
    if payload_sha(report) != original_payload_sha:
        raise ValueError("original_scientific_measurement_changed")
    if any(sha256(path) != expected for path, expected in original_detail_hashes):
        raise ValueError("saved_distance_arrays_changed_during_metadata_repair")
    charge(stages, "final_integrity_checks", before)
    repair = {
        "cycle_id": "M6-SHAPE-OBJECTIVE-001", "status": "completed_metadata_only_repair",
        "reason": "metric counters are top-level fields; initial caller read a missing nested counts key",
        "actual_sequence": "first surface phase completed before caller counter-copy patch; earlier pre-run description corrected",
        "directions_repaired": directions_repaired, "new_nearest_points_calls": 0,
        "new_boundary_queries": 0, "new_model_forwards": 0, "new_predictions": 0,
        "original_report_path": str(initial_path.resolve()), "original_report_sha256": initial_sha,
        "executed_source_snapshot_path": str(original_source_path.resolve()),
        "executed_source_sha256": expected_source_sha,
        "source_reconstruction": "reverse sole counter-copy patch and verify exact SHA against original report/controller",
        "current_corrected_caller_sha256": sha256(HERE / "evaluate_surface.py"),
        "repair_source_sha256": sha256(Path(__file__)),
        "original_scientific_payload_sha256": original_payload_sha,
        "postrepair_scientific_payload_sha256": payload_sha(report),
        "original_48_distance_details_unchanged": True,
        "old_files_read_and_hash_verified": list(read_files.values()), "timings": stages,
        "wall_s_before_final_writes": time.perf_counter() - BOOT_WALL,
        "CPU_s_before_final_writes": time.process_time() - BOOT_CPU,
        "own_process_before_final_writes": resources(),
        "measurement_scope": "metadata repair from original saved arrays; final report/marker writes and exit outside own window",
    }
    report["metadata_repair"] = repair
    write(output, report)
    write(marker, repair)
    print(json.dumps({"status": repair["status"], "directions_repaired": directions_repaired,
                      "new_distance_queries": 0, "original_distances_unchanged": True,
                      "wall_s": repair["wall_s_before_final_writes"]}), flush=True)


if __name__ == "__main__":
    main()
