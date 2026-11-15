"""Independently check saved inputs, updates and fixed-candidate measurements."""

import os
for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import hashlib
import json
from pathlib import Path
import sys
import time

BOOT_WALL, BOOT_CPU = time.perf_counter(), time.process_time()
HERE = Path(__file__).resolve().parent
TRAIN = HERE.parent / "m6_shape_train_001"
DATA = HERE.parent / "m6_shape_data_001"
sys.path.insert(0, str(HERE))
from adapter import process_resources
import numpy as np
from scipy.spatial import cKDTree


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bitwise(first, second):
    return first.dtype == second.dtype and first.shape == second.shape and first.tobytes() == second.tobytes()


def scalar_triangle_distance2(query, vertices, triangles):
    """Closed triangle distance from independent plane and three edge projections."""
    a, b, c = (vertices[triangles[:, index]] for index in (0, 1, 2))
    ab, ac, aq = b - a, c - a, query - a
    aa, bb = (np.sum(value * value, axis=1) for value in (ab, ac))
    cross_dot = np.sum(ab * ac, axis=1)
    u_dot, v_dot = np.sum(aq * ab, axis=1), np.sum(aq * ac, axis=1)
    denominator = aa * bb - cross_dot * cross_dot
    nonzero = denominator > 0
    u = np.full(len(a), np.nan)
    v = np.full(len(a), np.nan)
    u[nonzero] = (bb[nonzero] * u_dot[nonzero] - cross_dot[nonzero] * v_dot[nonzero]) / denominator[nonzero]
    v[nonzero] = (aa[nonzero] * v_dot[nonzero] - cross_dot[nonzero] * u_dot[nonzero]) / denominator[nonzero]
    interior = nonzero & (u >= 0) & (v >= 0) & (u + v <= 1)
    distances = np.full(len(a), np.inf)
    projected = a[interior] + u[interior, None] * ab[interior] + v[interior, None] * ac[interior]
    distances[interior] = np.sum((query - projected) ** 2, axis=1)
    for first, second in ((a, b), (b, c), (c, a)):
        edge = second - first
        length2 = np.sum(edge * edge, axis=1)
        t = np.zeros(len(a))
        valid = length2 > 0
        t[valid] = np.sum((query - first[valid]) * edge[valid], axis=1) / length2[valid]
        t = np.clip(t, 0, 1)
        candidate = first + t[:, None] * edge
        distances = np.minimum(distances, np.sum((query - candidate) ** 2, axis=1))
    return float(np.min(distances))


def main():
    checks, failures, identities = 0, [], {}
    coverage = {"inference_inputs": 0, "saved_iterations": 0, "case_methods": 0,
                "surface_directions": 0, "repeated_scalar_triangle_queries": 0}
    largest_difference = 0.0
    stages = {}

    def check(name, passed):
        nonlocal checks
        checks += 1
        if not passed:
            raise ValueError(name)

    def close(name, actual, expected):
        nonlocal largest_difference
        if actual is None or expected is None:
            check(name, actual is expected)
            return
        difference = abs(float(actual) - float(expected))
        largest_difference = max(largest_difference, difference)
        check(name, bool(np.isclose(actual, expected, atol=2e-12, rtol=2e-10)))

    def remember(path, expected=None):
        path = Path(path)
        key = str(path.resolve())
        if key not in identities:
            identities[key] = {"path": key, "bytes": path.stat().st_size, "sha256": sha(path)}
        if expected is not None:
            check("SHA_" + key, identities[key]["sha256"] == expected)

    def load(path, expected=None):
        remember(path, expected)
        return np.load(path, allow_pickle=False)

    def charge(name, before):
        row = stages.setdefault(name, {"wall_s": 0.0, "CPU_s": 0.0})
        row["wall_s"] += time.perf_counter() - before[0]
        row["CPU_s"] += time.process_time() - before[1]

    def statistics(distances):
        if len(distances) == 0:
            return {"count": 0, "rmse_native": None, "p95_native": None, "max_native": None}
        return {"count": len(distances), "rmse_native": float(np.sqrt(np.average(distances ** 2))),
                "p95_native": float(np.percentile(distances, 95)), "max_native": float(np.max(distances))}

    try:
        before = time.perf_counter(), time.process_time()
        selection = read(HERE / "CASE_SELECTION.json")["cases"]
        inputs = read(HERE / "INPUT_INDEX.json")
        outputs = read(HERE / "MODEL_OUTPUTS.json")
        evaluation = read(HERE / "EVALUATION.json")
        qa = read(HERE / "TETRAHEDRON_CHECK.json")
        expected_ids = sorted(row["id"] for row in selection)
        for name, rows in (("input", inputs["cases"]), ("output", outputs["cases"]), ("evaluation", evaluation["cases"])):
            check(name + "_37_case_denominator", sorted(row["id"] for row in rows) == expected_ids and len(rows) == 37)
        check("no_Bunny_selection", all(row["source"] != "Stanford_Bunny" for row in selection))
        check("fixed_7_12_9_9_denominators", evaluation["actual_denominators"]
              == {"normal_controls": 7, "development_dents": 12,
                  "validation_center_dents": 9, "validation_offcenter_dents": 9})
        check("official_QA_passed", qa["status"] == "passed_official_adapter_workflow_QA"
              and all(row["passed"] for row in qa["checks"]))
        for name, expected in outputs["source_sha256"].items():
            remember(HERE / name, expected)
        for path, expected in evaluation["code_sha256"].items():
            remember(path, expected)
        for row in read(HERE / "INPUT_PROVENANCE.json")["files"]:
            check("input_provenance_excludes_Bunny_arrays", "Bunny" not in row["path"])
            remember(row["path"], row["sha256"])
        old = {row["id"]: row for row in read(TRAIN / "RESULTS.json")["model_cases"]}
        source_records = read(DATA / "SOURCE_AUDIT.json")["sources"] + read(TRAIN / "PUBLIC_SOURCES.json")["sources"]
        source_paths = {row["name"]: row["snapshot"]["path"] for row in source_records if row["name"] != "Stanford_Bunny"}
        source_cache = {}
        input_lookup = {row["id"]: row for row in inputs["cases"]}
        output_lookup = {row["id"]: row for row in outputs["cases"]}
        charge("metadata_and_identity_checks", before)
        for case in evaluation["cases"]:
            case_id = case["id"]
            before = time.perf_counter(), time.process_time()
            input_row = input_lookup[case_id]
            with load(input_row["path"], input_row["sha256"]) as saved:
                check(case_id + "_inference_fields_have_no_answers", set(saved.files)
                      == {"vertices", "free_source_ids", "context_source_ids"})
                observed_full = saved["vertices"]
                free_ids, context_ids = saved["free_source_ids"], saved["context_source_ids"]
            check(case_id + "_binary64_complete_current_source", observed_full.dtype == np.float64
                  and len(observed_full) == input_row["full_source_vertices"] and bool(np.isfinite(observed_full).all()))
            original = old[case_id]
            observed = load(original["observed_path"])
            reference = load(original["reference_path"])
            folder = Path(original["observed_path"]).parents[1]
            sample = case_id.split("/")[1]
            with load(original["mapping_path"]) as saved:
                mapping = {name: saved[name].copy() for name in saved.files}
            with load(original["graph_path"]) as saved:
                graph = {name: saved[name].astype(bool) for name in ("allowed_mask", "free_mask", "boundary_mask")}
            with load(folder / "labels" / (sample + ".npz")) as saved:
                support = saved["damaged_mask"].astype(bool)
            with load(folder / "inputs" / (sample + ".npz")) as saved:
                scale, origin = float(saved["scale_m"]), saved["origin_world_m"].copy()
            if case["source"] not in source_cache:
                with load(source_paths[case["source"]]) as saved:
                    source_cache[case["source"]] = saved["vertices"].astype(np.float64), saved["triangles"].copy()
            clean_full, triangles = source_cache[case["source"]]
            check(case_id + "_context_source_mapping", np.array_equal(context_ids, mapping["context_source_ids"]))
            check(case_id + "_free_domain_uses_task_F", np.array_equal(free_ids, np.sort(context_ids[graph["free_mask"]])))
            reconstructed = clean_full.copy()
            reconstructed[context_ids] = observed
            check(case_id + "_all_current_values_reconstructed", bitwise(observed_full, reconstructed))
            check(case_id + "_observed_context_bitwise", bitwise(observed_full[context_ids], observed))
            coverage["inference_inputs"] += 1
            full_fixed = np.ones(len(observed_full), dtype=bool)
            full_fixed[free_ids] = False
            charge("old_arrays_and_complete_input_reconstruction", before)

            first_samples = []
            for method in ("pointfilter", "robust_mls"):
                method_row = output_lookup[case_id]["methods"][method]
                if method_row["status"] != "completed":
                    check(case_id + "_failed_method_keeps_denominator_" + method,
                          case["methods"][method]["status"] != "evaluated")
                    continue
                check(case_id + "_two_fixed_iterations_" + method,
                      [row["iteration"] for row in method_row["iterations"]] == [1, 2])
                previous = observed_full
                rng = np.random.RandomState(1729)
                for step in method_row["iterations"]:
                    before = time.perf_counter(), time.process_time()
                    candidate = load(step["candidate_path"], step["candidate_sha256"])
                    with load(step["sampling_path"], step["sampling_sha256"]) as saved:
                        detail = {name: saved[name].copy() for name in saved.files}
                    check(case_id + "_step_query_ids_" + method, np.array_equal(detail["query_source_ids"], free_ids))
                    check(case_id + "_step_binary64_finite_" + method,
                          candidate.dtype == np.float64 and candidate.shape == previous.shape and bool(np.isfinite(candidate).all()))
                    check(case_id + "_step_fixed_bitwise_" + method, bitwise(candidate[full_fixed], previous[full_fixed]))
                    check(case_id + "_synchronous_center_restore_" + method,
                          bitwise(candidate[free_ids], previous[free_ids] + detail["restored_displacement"]))
                    radius = float(np.linalg.norm(previous.max(0) - previous.min(0))) * .05
                    close(case_id + "_whole_current_bbox_" + method, float(detail["radius"]), radius)
                    check(case_id + "_single_shared_radius_" + method, np.all(detail["radius_per_query"] == radius))
                    offsets, neighbor_ids = detail["neighbor_offsets"], detail["neighbor_source_ids"]
                    check(case_id + "_neighbor_offset_partition_" + method,
                          offsets[0] == 0 and offsets[-1] == len(neighbor_ids)
                          and np.array_equal(np.diff(offsets), detail["neighbor_count"]))
                    check(case_id + "_full_source_neighbor_ids_" + method,
                          bool(np.all((neighbor_ids >= 0) & (neighbor_ids < len(previous)))))
                    tree = cKDTree(previous)
                    for row, source_id in enumerate(free_ids):
                        neighbors = neighbor_ids[offsets[row]:offsets[row + 1]]
                        if len(neighbors) < 3:
                            check(case_id + "_unavailable_query_unchanged_" + method,
                                  detail["query_status_codes"][row] == 1
                                  and np.all(detail["restored_displacement"][row] == 0))
                            continue
                        chosen = rng.choice(range(len(neighbors)), 500, replace=len(neighbors) <= 500)
                        check(case_id + "_seeded_official_sample_" + method,
                              np.array_equal(detail["sampled_source_ids"][row], neighbors[chosen]))
                        check(case_id + "_sample_duplicate_count_" + method,
                              int(detail["sampling_duplicate_count"][row]) == 500 - len(np.unique(chosen)))
                        if row in (0, len(free_ids) - 1):
                            independent_neighbors = tree.query_ball_point(previous[source_id], radius)
                            check(case_id + "_repeated_full_radius_neighbors_" + method,
                                  np.array_equal(neighbors, independent_neighbors))
                    if step["iteration"] == 1:
                        first_samples.append(detail["sampled_source_ids"])
                    previous = candidate
                    coverage["saved_iterations"] += 1
                    charge("saved_iterations_sampling_and_F_updates", before)
                check(case_id + "_second_iteration_selected_" + method,
                      method_row["final_candidate_path"] == method_row["iterations"][1]["candidate_path"])
            if len(first_samples) == 2:
                check(case_id + "_same_first_iteration_samples", np.array_equal(first_samples[0], first_samples[1]))
                check(case_id + "_first_iteration_sample_report", output_lookup[case_id]["first_iteration_sampled_ids_equal"])

            for method, record in case["methods"].items():
                if record["status"] != "evaluated":
                    continue
                before = time.perf_counter(), time.process_time()
                if method == "no_op":
                    full_candidate = observed_full
                else:
                    model_row = output_lookup[case_id]["methods"][method]
                    full_candidate = load(model_row["final_candidate_path"], model_row["final_candidate_sha256"])
                candidate = full_candidate[context_ids]
                masks = {"A": graph["allowed_mask"], "S": support,
                         "N": graph["allowed_mask"] & ~support,
                         "N_F": graph["allowed_mask"] & ~support & graph["free_mask"]}
                residual = np.sqrt(np.sum((candidate - reference) ** 2, axis=1))
                noop_residual = np.sqrt(np.sum((observed - reference) ** 2, axis=1))
                for name, mask in masks.items():
                    actual = statistics(residual[mask])
                    check(case_id + "_coordinate_count_" + method + name, actual["count"] == record["errors"][name]["count"])
                    for key in ("rmse_native", "p95_native", "max_native"):
                        close(case_id + "_coordinate_" + method + name + key, actual[key], record["errors"][name][key])
                        normalized = actual[key] / scale if actual[key] is not None else None
                        close(case_id + "_coordinate_normalization_" + method + name + key, normalized,
                              record["errors"][name][key.replace("native", "over_scale")])
                noop_support = statistics(noop_residual[masks["S"]])["rmse_native"]
                support_ratio = record["errors"]["S"]["rmse_native"] / noop_support if noop_support else None
                close(case_id + "_support_ratio_denominator_" + method, support_ratio, record["support_rmse_ratio_to_noop"])
                noop_allowed = statistics(noop_residual[masks["A"]])["rmse_native"]
                allowed_improvement = 1 - record["errors"]["A"]["rmse_native"] / noop_allowed if noop_allowed else None
                close(case_id + "_allowed_improvement_denominator_" + method, allowed_improvement,
                      record["allowed_improvement_to_noop"])
                normal_passed = all(not record["errors"][name]["count"] or (
                    record["errors"][name]["p95_over_scale"] <= .02
                    and record["errors"][name]["max_over_scale"] <= .10) for name in ("N", "N_F"))
                check(case_id + "_original_normal_gate_" + method, normal_passed == record["normal_point_preservation_passed"])
                if case["normal_control"]:
                    error = record["errors"]["A"]
                    normal_control_passed = (error["rmse_over_scale"] <= .01
                        and error["p95_over_scale"] <= .02 and error["max_over_scale"] <= .05)
                    check(case_id + "_original_control_gate_" + method, normal_control_passed == record["normal_control_passed"])
                check(case_id + "_fixed_record_" + method,
                      record["full_source_outside_free_bitwise_preserved"] == bitwise(full_candidate[full_fixed], observed_full[full_fixed]))
                incident_vertex = np.zeros(len(observed_full), dtype=bool)
                incident_vertex[context_ids[masks["A"]]] = True
                face_ids = np.flatnonzero(np.any(incident_vertex[triangles], axis=1))
                faces = triangles[face_ids]
                normal_vectors = []
                for coordinates in (observed_full, full_candidate):
                    first, second = coordinates[faces[:, 1]] - coordinates[faces[:, 0]], coordinates[faces[:, 2]] - coordinates[faces[:, 0]]
                    normal_vectors.append(np.column_stack((first[:, 1] * second[:, 2] - first[:, 2] * second[:, 1],
                        first[:, 2] * second[:, 0] - first[:, 0] * second[:, 2],
                        first[:, 0] * second[:, 1] - first[:, 1] * second[:, 0])))
                valid_before, valid_after = (np.sum(normal * normal, axis=1) > 0 for normal in normal_vectors)
                reversed_faces = valid_before & valid_after & (np.sum(normal_vectors[0] * normal_vectors[1], axis=1) < 0)
                degenerate_faces = valid_before & ~valid_after
                quality = record["incident_quality"]
                check(case_id + "_all_source_incident_coverage_" + method,
                      len(face_ids) == quality["incident_faces_required"] == quality["incident_faces_evaluated"]
                      and np.array_equal(face_ids, np.sort(mapping["incident_source_face_ids"])))
                check(case_id + "_source_face_reversals_" + method,
                      quality["normal_reversals_from_input"] == int(reversed_faces.sum())
                      and quality["reversed_source_face_ids"] == face_ids[reversed_faces].tolist())
                check(case_id + "_source_face_degeneracy_" + method,
                      quality["new_degenerate_faces"] == int(degenerate_faces.sum())
                      and quality["new_degenerate_source_face_ids"] == face_ids[degenerate_faces].tolist())
                check(case_id + "_unknown_coupling_retained_" + method,
                      all(value == "unknown_not_evaluated_for_this_candidate" for value in record["coupling"].values()))
                coverage["case_methods"] += 1
                charge("independent_coordinates_and_incident_faces", before)

                before = time.perf_counter(), time.process_time()
                normalized_candidate, normalized_reference = (candidate - origin) / scale, (reference - origin) / scale
                for direction, surface_vertices, query in (
                    ("candidate_to_reference", normalized_reference, normalized_candidate[masks["A"]]),
                    ("reference_to_candidate", normalized_candidate, normalized_reference[masks["A"]])):
                    surface = record["surface"][direction]
                    with load(surface["detail_path"], surface["detail_sha256"]) as saved:
                        detail = {name: saved[name].copy() for name in saved.files}
                    check(case_id + "_surface_query_identity_" + method + direction,
                          np.array_equal(detail["query_source_ids"], context_ids[masks["A"]])
                          and bitwise(detail["query_normalized"], query))
                    valid, distance2 = detail["valid"].astype(bool), detail["distance2"]
                    check(case_id + "_surface_valid_count_" + method + direction,
                          int(valid.sum()) == surface["distance"]["valid_points"])
                    for key, actual in (("RMSE", np.sqrt(np.mean(distance2[valid]))),
                                       ("p95", np.percentile(np.sqrt(distance2[valid]), 95)),
                                       ("max", np.sqrt(np.max(distance2[valid])))):
                        close(case_id + "_surface_stat_" + method + direction + key, actual, surface["distance"][key])
                    squared_from_closest = np.sum((query - detail["closest_normalized"]) ** 2, axis=1)
                    check(case_id + "_closest_distance_consistency_" + method + direction,
                          bool(np.allclose(distance2[valid], squared_from_closest[valid], atol=2e-12, rtol=2e-10)))
                    chosen_triangles = mapping["context_triangles"][detail["triangle_id"][valid]]
                    closest_from_barycentric = np.sum(surface_vertices[chosen_triangles]
                        * detail["barycentric"][valid, :, None], axis=1)
                    check(case_id + "_closed_triangle_closest_geometry_" + method + direction,
                          bool(np.all(detail["barycentric"][valid] >= -1e-12))
                          and bool(np.allclose(np.sum(detail["barycentric"][valid], axis=1), 1, atol=1e-12))
                          and bool(np.allclose(closest_from_barycentric, detail["closest_normalized"][valid],
                                              atol=2e-12, rtol=2e-10)))
                    check(case_id + "_ten_domain_counters_" + method + direction, len(surface["metric_domain_diagnostics"]) == 10)
                    for boundary in ("all_context_boundary", "cut", "natural_open", "unknown"):
                        hits = int((detail[boundary + "_nearest_point_flag"] & valid).sum())
                        check(case_id + "_boundary_hit_count_" + method + direction + boundary,
                              hits == surface["boundary_classification"][boundary]["nearest_point_on_boundary_count"])
                    for row in (0, len(query) - 1):
                        independent = scalar_triangle_distance2(query[row], surface_vertices, mapping["context_triangles"])
                        close(case_id + "_repeated_independent_triangle_distance_" + method + direction,
                              independent, distance2[row])
                        coverage["repeated_scalar_triangle_queries"] += 1
                    coverage["surface_directions"] += 1
                expected_mse = .5 * sum(record["surface"][direction]["distance"]["mean_squared_distance"]
                                       for direction in ("candidate_to_reference", "reference_to_candidate"))
                close(case_id + "_symmetric_MSE_" + method, expected_mse, record["surface"]["symmetric_MSE"])
                close(case_id + "_symmetric_RMSE_" + method, np.sqrt(expected_mse), record["surface"]["symmetric_RMSE"])
                charge("saved_surface_and_repeated_scalar_queries", before)
        check("all_37_inputs_independently_verified", coverage["inference_inputs"] == 37)
        status = "passed_independent_saved_result_verification"
    except Exception as error:
        failures.append({"type": type(error).__name__, "message": str(error)})
        status = "failed_independent_saved_result_verification"
        raise
    finally:
        report = {"cycle_id": "M6-SHAPE-PRETRAIN-001", "status": status, "check_count": checks,
                  "failures": failures, "coverage": coverage, "timings": stages,
                  "largest_compared_absolute_difference": largest_difference,
                  "model_forwards": 0, "training": 0, "new_unique_surface_query_points": 0,
                  "Bunny_arrays": 0, "input_file_identities": list(identities.values()),
                  "source_sha256": sha(Path(__file__)),
                  "wall_s_before_final_report": time.perf_counter() - BOOT_WALL,
                  "CPU_s_before_final_report": time.process_time() - BOOT_CPU,
                  "own_process_before_final_report": process_resources(),
                  "measurement_scope": "saved-array reads/hashes, independent reconstructions and repeated already-used queries; imports and final write/exit covered by outer process ledger"}
        (HERE / "INDEPENDENT_VERIFY.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                                                       encoding="utf-8", newline="\n")
    print(json.dumps({"status": status, "checks": checks, "coverage": coverage}))


if __name__ == "__main__":
    main()
