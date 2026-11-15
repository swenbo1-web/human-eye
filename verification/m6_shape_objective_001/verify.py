"""Independent saved-array arithmetic and bounded scalar triangle verification."""

import time
BOOT_WALL, BOOT_CPU = time.perf_counter(), time.process_time()

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
DATA = HERE.parent / "m6_shape_data_001"
TRAIN = HERE.parent / "m6_shape_train_001"
OPT = HERE.parent / "m6_shape_opt_001"
METHODS = ("no_op", "mls", "train_final", "opt_final_hard")
KINDS = ("all_context_boundary", "cut", "natural_open", "unknown")
CORE_SHA = "a0ff4107d0767b731bf374cfb346e809ae6f39ac17637b0f843e29242a631799"


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def arrays(path, names=None):
    with np.load(path, allow_pickle=False) as saved:
        return {name: saved[name].copy() for name in (saved.files if names is None else names)}


def own_resources():
    spec = importlib.util.spec_from_file_location("_objective_verify_monitor", TRAIN / "process_runner.py")
    monitor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitor)
    ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    return monitor.process_metrics(ctypes.windll.kernel32.GetCurrentProcess())


def describe(values):
    values = [value for value in values if value is not None]
    if not values:
        return {"count": 0, "minimum": None, "median": None, "p95": None, "maximum": None}
    values = np.asarray(values, dtype=np.float64)
    return {"count": len(values), "minimum": float(values.min()), "median": float(np.median(values)),
            "p95": float(np.quantile(values, .95)), "maximum": float(values.max())}


def scalar_segment(point, first, second):
    edge = second - first
    denominator = float(edge @ edge)
    parameter = min(1.0, max(0.0, float((point - first) @ edge) / denominator)) if denominator else 0.0
    return first + parameter * edge


def scalar_ericson(point, first, second, third):
    """Independent vertex/edge/face Voronoi-region triangle projection."""
    ab, ac = second - first, third - first
    normal = np.cross(ab, ac)
    if float(normal @ normal) == 0.0:
        candidates = [scalar_segment(point, first, second), scalar_segment(point, second, third),
                      scalar_segment(point, third, first)]
        return min(candidates, key=lambda value: float((point - value) @ (point - value)))
    ap = point - first
    d1, d2 = float(ab @ ap), float(ac @ ap)
    if d1 <= 0 and d2 <= 0:
        return first
    bp = point - second
    d3, d4 = float(ab @ bp), float(ac @ bp)
    if d3 >= 0 and d4 <= d3:
        return second
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        return first + d1 / (d1 - d3) * ab
    cp = point - third
    d5, d6 = float(ab @ cp), float(ac @ cp)
    if d6 >= 0 and d5 <= d6:
        return third
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        return first + d2 / (d2 - d6) * ac
    va = d3 * d6 - d5 * d4
    if va <= 0 and d4 - d3 >= 0 and d5 - d6 >= 0:
        return second + (d4 - d3) / ((d4 - d3) + (d5 - d6)) * (third - second)
    denominator = va + vb + vc
    return first + (vb * ab + vc * ac) / denominator


def boundary_distances(points, vertices, edges):
    result = np.full(len(points), np.inf)
    for first, second in edges:
        a, b = vertices[first], vertices[second]
        edge = b - a
        denominator = float(edge @ edge)
        parameter = np.zeros(len(points)) if denominator == 0 else np.clip((points - a) @ edge / denominator, 0.0, 1.0)
        nearest = a + parameter[:, None] * edge
        distance2 = np.sum((points - nearest) ** 2, axis=1)
        result = np.minimum(result, distance2)
    return result


def statistic(distance2, valid, selected=None):
    selected = np.ones(len(distance2), dtype=bool) if selected is None else selected
    requested = int(selected.sum())
    use = selected & valid & np.isfinite(distance2) & (distance2 >= 0)
    count = int(use.sum())
    value = {"requested_points": requested, "valid_points": count, "invalid_points": requested - count,
             "complete": requested == count, "mean_squared_distance": None, "RMSE": None, "p95": None, "max": None}
    if count and count == requested:
        distances = np.sqrt(distance2[use])
        value.update(mean_squared_distance=float(np.mean(distance2[use])), RMSE=float(np.sqrt(np.mean(distance2[use]))),
                     p95=float(np.quantile(distances, .95)), max=float(np.max(distances)))
    return value


def group_keys(row):
    primary = "development_center" if row["purpose"] == "development_train_pool" else "validation_" + row["position_group"]
    source = "source_" + row["source"]
    return ("all", primary, source, f"{primary}_amplitude_{row['amplitude_ratio']}",
            f"{primary}_r{row['radius_ratio']}_a{row['amplitude_ratio']}", f"{source}_amplitude_{row['amplitude_ratio']}",
            f"amplitude_{row['amplitude_ratio']}")


def main():
    started, cpu_started = time.perf_counter(), time.process_time()
    checks, maximum_difference = 0, 0.0
    stage_times = {}
    report = {"cycle_id": "M6-SHAPE-OBJECTIVE-001", "status": "running", "failures": [],
              "model_forwards": 0, "training": 0, "new_repair_outputs": 0, "new_unique_surface_query_points": 0,
              "Bunny_arrays": 0, "threshold_searches": 0}

    def check(name, condition):
        nonlocal checks
        checks += 1
        if not condition:
            raise AssertionError(name)

    def close(name, actual, expected, tolerance=5e-12):
        nonlocal maximum_difference
        if actual is None or expected is None:
            check(name, actual is None and expected is None)
            return
        actual, expected = np.asarray(actual), np.asarray(expected)
        if actual.shape == expected.shape and np.issubdtype(actual.dtype, np.number) and actual.size:
            finite = np.isfinite(actual) & np.isfinite(expected)
            if np.any(finite):
                maximum_difference = max(maximum_difference, float(np.max(np.abs(actual[finite] - expected[finite]))))
        check(name, actual.shape == expected.shape and bool(np.allclose(actual, expected, atol=tolerance, rtol=tolerance, equal_nan=True)))

    def same_statistics(name, actual, expected):
        check(name + "_keys", set(actual) == set(expected))
        for key, value in expected.items():
            if value is None or isinstance(value, bool):
                check(name + "_" + key, actual[key] is value)
            else:
                close(name + "_" + key, actual[key], value)

    try:
        qa = read(HERE / "METER_QA.json")
        check("meter34syntheticpass", qa["status"] == "passed_synthetic_metric_QA" and qa["check_count"] == 34 and not qa["failures"])
        check("frozen_core_sha", sha(HERE / "surface_distance.py") == CORE_SHA == qa["source_sha256"]["surface_distance.py"])
        decomp = read(HERE / "DECOMPOSITION.json")
        surface = read(HERE / "SURFACE_RESULTS.json")
        check("surface_repaired_metadata_present", all(value[direction]["metric_domain_diagnostics"]
              for case in surface["cases"] for value in case["methods"].values()
              for direction in ("candidate_to_reference", "reference_to_candidate")))
        before, cpu = time.perf_counter(), time.process_time()
        reference_cache = {}
        recomputed_rows = []
        for row in decomp["cases"]:
            name, patch = row["id"], row["patch_id"]
            root = DATA / "private/patches" if row["purpose"] == "development_train_pool" else TRAIN / "private/public_data/patches"
            folder = root / patch
            check("decomp_case_scope_" + name, row["purpose"] != "reserved_test" and row["source"] != "Stanford_Bunny")
            if patch not in reference_cache:
                reference = np.load(folder / "reference_local.npy", allow_pickle=False)
                normal = arrays(folder / "inputs/sample_00.npz", ("normals",))["normals"].astype(np.float64)
                source_ids = arrays(folder / "mapping.npz", ("context_source_ids",))["context_source_ids"]
                length = np.sqrt(np.sum(normal * normal, axis=1))
                finite_components, finite_length = np.all(np.isfinite(normal), axis=1), np.isfinite(length)
                valid = finite_components & finite_length & (length > 0)
                unit = np.full_like(normal, np.nan)
                unit[valid] = normal[valid] / length[valid, None]
                reference_cache[patch] = (reference, unit, valid, source_ids, finite_components, finite_length, length)
            reference, unit, valid_normal, source_ids, finite_components, finite_length, length = reference_cache[patch]
            sample = name.split("/")[-1]
            observed = np.load(folder / "observed" / (sample + ".npy"), allow_pickle=False)
            support = arrays(folder / "labels" / (sample + ".npz"), ("damaged_mask",))["damaged_mask"]
            scale = float(arrays(folder / "inputs" / (sample + ".npz"), ("scale_m",))["scale_m"])
            check("component_file_hash_" + name, sha(row["private_point_components"]["path"]) == row["private_point_components"]["sha256"])
            saved = arrays(row["private_point_components"]["path"])
            d, n = (reference - observed)[support] / scale, unit[support]
            energy = np.sum(d * d, axis=1)
            finite_target = np.all(np.isfinite(d), axis=1) & np.isfinite(energy)
            usable = valid_normal[support] & finite_target
            dn, dt = np.full_like(d, np.nan), np.full_like(d, np.nan)
            dn[usable] = np.sum(d[usable] * n[usable], axis=1)[:, None] * n[usable]
            dt[usable] = d[usable] - dn[usable]
            for field, expected in (("source_vertex_ids", source_ids[support]), ("target_normalized_float64", d),
                                    ("reference_unit_normal", n), ("valid_normal", valid_normal[support]),
                                    ("finite_target", finite_target), ("decomposable", usable),
                                    ("normal_component", dn), ("tangent_component", dt), ("target_energy", energy)):
                close(name + "_" + field, saved[field], expected)
            close(name + "_unit_norm", np.sum(n[valid_normal[support]] ** 2, axis=1), np.ones(np.count_nonzero(valid_normal[support])))
            e_normal, e_tangent = np.sum(dn[usable] ** 2, axis=1), np.sum(dt[usable] ** 2, axis=1)
            close(name + "_energy_closure", e_normal + e_tangent, energy[usable])
            closure = e_normal + e_tangent - energy[usable]
            orthogonality = np.sum(dn[usable] * dt[usable], axis=1)
            close(name + "_orthogonality", orthogonality, np.zeros(usable.sum()))
            expected_counts = {"support_points": int(support.sum()), "valid_normal_points": int(valid_normal[support].sum()),
                               "invalid_normal_points": int((~valid_normal[support]).sum()),
                               "nonfinite_normal_component_points": int((~finite_components[support]).sum()),
                               "nonfinite_normal_length_points": int((~finite_length[support]).sum()),
                               "zero_normal_points": int((finite_components[support] & finite_length[support] & (length[support] == 0)).sum()),
                               "finite_target_points": int(finite_target.sum()), "nonfinite_target_points": int((~finite_target).sum()),
                               "decomposable_points": int(usable.sum())}
            check(name + "_denominators", row["denominators"] == expected_counts)
            expected_energies = {"total_target_energy": float(energy.sum()) if finite_target.all() else None,
                                 "finite_target_energy": float(energy[finite_target].sum()),
                                 "decomposable_target_energy": float(energy[usable].sum()),
                                 "normal_energy": float(e_normal.sum()), "tangent_energy": float(e_tangent.sum()),
                                 "invalid_normal_finite_target_energy": float(energy[finite_target & ~valid_normal[support]].sum())}
            for field, value in expected_energies.items():
                close(name + "_" + field, row[field], value)
            denominator = expected_energies["decomposable_target_energy"]
            tangent_fraction = expected_energies["tangent_energy"] / denominator if denominator > 0 else None
            normal_fraction = expected_energies["normal_energy"] / denominator if denominator > 0 else None
            close(name + "_tangent_fraction", row["tangent_fraction_of_decomposable_target"], tangent_fraction)
            close(name + "_normal_fraction", row["normal_fraction_of_decomposable_target"], normal_fraction)
            closure_max = float(np.max(np.abs(closure))) if len(closure) else 0.0
            orthogonality_max = float(np.max(np.abs(orthogonality))) if len(orthogonality) else 0.0
            close(name + "_reported_closure_max", row["maximum_energy_closure_abs_error"], closure_max)
            close(name + "_reported_orthogonality_max", row["maximum_normal_tangent_abs_dot"], orthogonality_max)
            recomputed_rows.append(dict(row, denominators=expected_counts,
                                        tangent_fraction_of_decomposable_target=tangent_fraction,
                                        normal_fraction_of_decomposable_target=normal_fraction,
                                        maximum_energy_closure_abs_error=closure_max,
                                        maximum_normal_tangent_abs_dot=orthogonality_max, **expected_energies))
        for group, value in decomp["summaries"].items():
            selected = [row for row in recomputed_rows if group in group_keys(row)]
            check(group + "_case_ids", value["case_ids"] == [row["id"] for row in selected])
            check(group + "_case_patch_source_counts", (value["case_count"], value["patch_count"], value["source_count"]) ==
                  (len(selected), len({row["patch_id"] for row in selected}), len({row["source"] for row in selected})))
            check(group + "_denominators", value["denominators"] == {key: sum(row["denominators"][key] for row in selected)
                                                                   for key in selected[0]["denominators"]})
            for field in ("total_target_energy", "finite_target_energy", "decomposable_target_energy", "normal_energy", "tangent_energy",
                          "invalid_normal_finite_target_energy"):
                close(group + "_" + field, value[field], sum(row[field] for row in selected))
            normal = sum(row["normal_energy"] for row in selected)
            tangent = sum(row["tangent_energy"] for row in selected)
            total = sum(row["decomposable_target_energy"] for row in selected)
            close(group + "_normal_fraction", value["normal_fraction_of_decomposable_target"], normal / total if total > 0 else None)
            close(group + "_tangent_fraction", value["tangent_fraction_of_decomposable_target"], tangent / total if total > 0 else None)
            same_statistics(group + "_case_tangent_fraction", value["per_case_tangent_fraction"], describe([row["tangent_fraction_of_decomposable_target"] for row in selected]))
            same_statistics(group + "_case_target_energy", value["per_case_target_energy"], describe([row["total_target_energy"] for row in selected]))
            close(group + "_reported_closure_max", value["maximum_energy_closure_abs_error"], max(row["maximum_energy_closure_abs_error"] for row in selected))
            close(group + "_reported_orthogonality_max", value["maximum_normal_tangent_abs_dot"], max(row["maximum_normal_tangent_abs_dot"] for row in selected))
        check("306cases10767support", len(recomputed_rows) == 306 and sum(row["denominators"]["support_points"] for row in recomputed_rows) == 10767)
        stage_times["decomposition_saved_arithmetic_and_old_input_read"] = {"wall_s": time.perf_counter() - before, "CPU_s": time.process_time() - cpu}

        before, cpu = time.perf_counter(), time.process_time()
        train, opt = read(TRAIN / "RESULTS.json"), read(OPT / "RESULTS.json")
        old_train = {row["id"]: row for row in train["model_cases"]}
        old_opt = {row["id"]: row for row in opt["model_cases"]}
        old_baseline = {row["id"]: row for row in train["baseline_cases"]}
        initial_surface = read(HERE / "private/recovery/SURFACE_RESULTS_initial.json")
        initial_cases = {row["case_id"]: row for row in initial_surface["cases"]}
        topology_cache = {}
        scalar_QA_wall = scalar_QA_cpu = 0.0
        scalar_QA_queries = 0
        direction_count, candidate_count = 0, 0
        rankings = []
        for case in surface["cases"]:
            name = case["case_id"]
            old_records = {"no_op": old_baseline[name]["no_op"], "mls": old_baseline[name]["mls"],
                           "train_final": old_train[name], "opt_final_hard": old_opt[name]}
            original = old_train[name]
            graph = arrays(original["graph_path"])
            mapping = arrays(original["mapping_path"])
            allowed, triangles, source_ids = graph["allowed_mask"], mapping["context_triangles"], mapping["context_source_ids"]
            input_path = Path(original["graph_path"]).parent / "inputs" / (name.split("/")[-1] + ".npz")
            inputs = arrays(input_path, ("scale_m", "origin_world_m"))
            scale, origin = float(inputs["scale_m"]), inputs["origin_world_m"]
            reference = (np.load(original["reference_path"], allow_pickle=False) - origin) / scale
            all_edges = np.sort(np.concatenate((triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]])), axis=1)
            edge_counts = {}
            for first, second in all_edges:
                key = (int(first), int(second))
                edge_counts[key] = edge_counts.get(key, 0) + 1
            boundary = np.asarray(sorted(key for key, count in edge_counts.items() if count == 1), dtype=np.int64).reshape(-1, 2)
            source_path = case["source_snapshot_used_only_for_boundary_topology"]
            if source_path not in topology_cache:
                topology_cache[source_path] = arrays(source_path, ("triangles",))["triangles"]
            full_triangles = topology_cache[source_path]
            incidences = []
            for first, second in source_ids[boundary]:
                count = 0
                for left, right in ((0, 1), (1, 2), (2, 0)):
                    forward = (full_triangles[:, left] == first) & (full_triangles[:, right] == second)
                    backward = (full_triangles[:, left] == second) & (full_triangles[:, right] == first)
                    count += int(np.count_nonzero(forward | backward))
                incidences.append(count)
            incidences = np.asarray(incidences)
            domain_edges = {"all_context_boundary": boundary, "cut": boundary[incidences > 1],
                            "natural_open": boundary[incidences == 1], "unknown": boundary[incidences == 0]}
            check(name + "_domain_edge_counts", case["boundary_edges"] == {kind: len(edges) for kind, edges in domain_edges.items()})
            for method in METHODS:
                candidate_count += 1
                value, old = case["methods"][method], old_records[method]
                check(name + method + "_candidate_old_path", value["candidate_path"] == old["candidate_path"])
                check(name + method + "_candidate_SHA", sha(value["candidate_path"]) == value["candidate_sha256"])
                check(name + method + "_candidate_initial_SHA", value["candidate_sha256"] == initial_cases[name]["methods"][method]["candidate_sha256"])
                check(name + method + "_legacy_method", value["legacy"]["original_method"] == old["method"])
                candidate = (np.load(value["candidate_path"], allow_pickle=False) - origin) / scale
                for field in ("normal_control", "errors", "support_rmse_ratio_to_noop", "allowed_improvement_to_noop", "actual_changed_vertices",
                              "actual_changed_free_vertices", "actual_changed_fixed_vertices", "fixed_bitwise_preserved", "boundary_bitwise_preserved",
                              "outside_allowed_bitwise_preserved", "incident_quality", "fallback_noop", "fallback_reason"):
                    check(name + method + "_legacy_" + field, value["legacy"][field] == old[field])
                incident = old["incident_quality"]
                normal_pass = all(old["errors"][domain]["count"] == 0 or (old["errors"][domain]["p95_over_scale"] <= .02 and old["errors"][domain]["max_over_scale"] <= .10)
                                  for domain in ("N", "N_F"))
                check(name + method + "_legacy_normal_gate", value["legacy"]["original_normal_point_preservation_passed"] == normal_pass)
                control_pass = None
                if old["normal_control"]:
                    error = old["errors"]["A"]
                    control_pass = error["rmse_over_scale"] <= .01 and error["p95_over_scale"] <= .02 and error["max_over_scale"] <= .05
                check(name + method + "_legacy_control_gate", value["legacy"]["original_normal_control_passed"] == control_pass)
                check(name + method + "_legacy_incident_gate", value["legacy"]["original_incident_quality_passed"] ==
                      (incident["complete"] and not incident["new_degenerate_faces"] and not incident["normal_reversals_from_input"]))
                for direction, queries, target in (("candidate_to_reference", candidate[allowed], reference),
                                                   ("reference_to_candidate", reference[allowed], candidate)):
                    direction_count += 1
                    measured = value[direction]
                    check(name + method + direction + "_detail_SHA", sha(measured["detail_path"]) == measured["detail_sha256"])
                    detail = arrays(measured["detail_path"])
                    close(name + method + direction + "_query_source_ids", detail["query_source_ids"], source_ids[allowed])
                    close(name + method + direction + "_query_positions", detail["query_normalized"], queries)
                    distance2, valid = detail["distance2"], detail["valid"]
                    close(name + method + direction + "_residual_distance", distance2[valid], np.sum((queries[valid] - detail["closest_normalized"][valid]) ** 2, axis=1))
                    selected_triangles = triangles[detail["triangle_id"][valid]]
                    reconstructed = np.sum(target[selected_triangles] * detail["barycentric"][valid, :, None], axis=1)
                    close(name + method + direction + "_barycentric_location", detail["closest_normalized"][valid], reconstructed)
                    close(name + method + direction + "_barycentric_sum", detail["barycentric"][valid].sum(axis=1), np.ones(valid.sum()))
                    check(name + method + direction + "_closed_triangle_barycentric", bool(np.all(detail["barycentric"][valid] >= -5e-12)))
                    same_statistics(name + method + direction + "_distance_stats", measured["distance"], statistic(distance2, valid))
                    faces = target[triangles]
                    normal = np.cross(faces[:, 1] - faces[:, 0], faces[:, 2] - faces[:, 0])
                    counts = measured["metric_domain_diagnostics"]
                    expected_counts = {"query_count": len(queries), "triangle_count": len(triangles),
                                       "invalid_query_count": int(np.count_nonzero(~np.all(np.isfinite(queries), axis=1))),
                                       "finite_query_count": int(np.count_nonzero(np.all(np.isfinite(queries), axis=1))),
                                       "available_query_count": int(valid.sum()),
                                       "numeric_unavailable_query_count": int(np.count_nonzero(np.all(np.isfinite(queries), axis=1) & ~valid)),
                                       "nonfinite_surface_vertex_count": int(np.count_nonzero(~np.all(np.isfinite(target), axis=1))),
                                       "numeric_nonfinite_triangle_count": int(np.count_nonzero(~np.all(np.isfinite(normal), axis=1) | ~np.isfinite(np.sum(normal ** 2, axis=1)))),
                                       "degenerate_triangle_count": int(np.count_nonzero(np.sum(normal ** 2, axis=1) == 0)),
                                       "zero_length_triangle_edge_count": sum(int(np.count_nonzero(np.sum((faces[:, second] - faces[:, first]) ** 2, axis=1) == 0))
                                                                               for first, second in ((0, 1), (1, 2), (2, 0)))}
                    check(name + method + direction + "_surface_domain_counts", counts == expected_counts)
                    tolerance = 64 * np.finfo(np.float64).eps * max(1.0, float(np.max(np.abs(target))))
                    close(name + method + direction + "_boundary_tolerance", measured["boundary_length_tolerance"], tolerance)
                    for kind, edges in domain_edges.items():
                        independently_computed = boundary_distances(detail["closest_normalized"], target, edges)
                        flag = independently_computed <= tolerance ** 2
                        close(name + method + direction + kind + "_boundary_distance", detail[kind + "_distance2_from_nearest_point"], independently_computed)
                        check(name + method + direction + kind + "_boundary_flags", np.array_equal(detail[kind + "_nearest_point_flag"], flag))
                        boundary_record = measured["boundary_classification"][kind]
                        check(name + method + direction + kind + "_boundary_count", boundary_record["nearest_point_on_boundary_count"] == int((flag & valid).sum()))
                        check(name + method + direction + kind + "_segment_count", boundary_record["boundary_segment_count"] == len(edges))
                        same_statistics(name + method + direction + kind + "_boundary_stats", boundary_record["query_distance_for_boundary_hits"], statistic(distance2, valid, flag))
                    same_statistics(name + method + direction + "_off_boundary_stats", measured["nearest_point_off_all_context_boundary"],
                                    statistic(distance2, valid, ~detail["all_context_boundary_nearest_point_flag"]))
                    scalar_started, scalar_cpu = time.perf_counter(), time.process_time()
                    for index in (0, len(queries) - 1):
                        query = queries[index]
                        independent_minimum = float("inf")
                        for face in faces:
                            closest = scalar_ericson(query, *face)
                            residual = query - closest
                            independent_minimum = min(independent_minimum, float(residual @ residual))
                        close(name + method + direction + "_scalar_triangle_QA_" + str(index), distance2[index], independent_minimum)
                        scalar_QA_queries += 1
                    scalar_QA_wall += time.perf_counter() - scalar_started
                    scalar_QA_cpu += time.process_time() - scalar_cpu
                expected_mse = .5 * (value["candidate_to_reference"]["distance"]["mean_squared_distance"]
                                      + value["reference_to_candidate"]["distance"]["mean_squared_distance"])
                close(name + method + "_symmetric_MSE", value["symmetric_MSE"], expected_mse)
                close(name + method + "_symmetric_RMSE", value["symmetric_RMSE"], np.sqrt(expected_mse))
            coordinate_order = sorted(METHODS, key=lambda method: (case["methods"][method]["legacy"]["errors"]["A"]["rmse_over_scale"], METHODS.index(method)))
            surface_order = sorted(METHODS, key=lambda method: (case["methods"][method]["symmetric_RMSE"], METHODS.index(method)))
            check(name + "_coordinate_order", case["coordinate_A_RMSE_order"] == coordinate_order)
            check(name + "_surface_order", case["surface_symmetric_RMSE_order"] == surface_order)
            rankings.append({"case_id": name, "coordinate_order": coordinate_order, "surface_order": surface_order,
                             "rank_order_matches": coordinate_order == surface_order})
        stage_times["surface_saved_geometry_boundary_and_scalar_QA"] = {"wall_s": time.perf_counter() - before, "CPU_s": time.process_time() - cpu}
        stage_times["scalar_Ericson_repeated_existing_queries_nested"] = {"wall_s": scalar_QA_wall, "CPU_s": scalar_QA_cpu}
        check("24outputs48directions96repeatQA", candidate_count == 24 and direction_count == 48 and scalar_QA_queries == 96)
        report.update(status="passed_independent_saved_result_verification", decomposition_cases=306,
                      decomposition_support_points=10767, decomposition_summary_groups=len(decomp["summaries"]),
                      reference_normal_patches_read=len(reference_cache), surface_candidates=24, surface_directions=48,
                      repeated_scalar_nearest_triangle_QA_queries=scalar_QA_queries, new_unique_surface_query_points=0,
                      ordering=rankings, meter_QA_checks=qa["check_count"], core_meter_sha256=CORE_SHA,
                      interpretation="Distance magnitudes and one old failed-control method ordering can differ. Original coordinate/protection/face gate judgments remain retained, with no old candidate reacceptance.")
    except Exception as error:
        report["status"] = "failed_independent_saved_result_verification"
        report["failures"].append({"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        report["check_count"] = checks
        report["largest_compared_absolute_difference"] = maximum_difference
        report["stages"] = stage_times
        report["wall_s_before_final_report"] = time.perf_counter() - started
        report["CPU_s_before_final_report"] = time.process_time() - cpu_started
        report["bootstrap_to_report_wall_s"] = time.perf_counter() - BOOT_WALL
        report["bootstrap_to_report_CPU_s"] = time.process_time() - BOOT_CPU
        report["own_process_before_report"] = own_resources()
        report["measurement_scope"] = "self process timed blocks before report serialization; enclosing root process ledger covers startup/exit; no model or repair operations"
        (HERE / "INDEPENDENT_VERIFY.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": report["status"], "checks": checks, "decomposition_cases": 306,
                      "surface_directions": 48, "repeated_scalar_QA_queries": scalar_QA_queries,
                      "wall_s": report["wall_s_before_final_report"]}), flush=True)


if __name__ == "__main__":
    main()
