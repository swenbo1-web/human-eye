"""Closed-form geometry and rigid/permutation checks for the surface meter."""

import os
for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import ctypes
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from surface_distance import nearest_points, context_boundary_edges, classify_boundary_points


def own_resources():
    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("faults", ctypes.c_ulong)] + [
            (name, ctypes.c_size_t) for name in ("peak", "working", "qpp", "pp", "qpnp", "pnp", "page", "peakpage", "private")]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(Counters), ctypes.c_ulong]
    valid = psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
    return {"process_CPU_s": time.process_time(), "peak_working_set_bytes": int(counters.peak) if valid else None}


def main():
    started, cpu_started = time.perf_counter(), time.process_time()
    output = HERE / "METER_QA.json"
    prior_attempts = []
    if output.exists():
        prior_attempts = json.loads(output.read_bytes()).get("attempts", [])
    records = []
    report = {"cycle_id": "M6-SHAPE-OBJECTIVE-001", "status": "running",
              "qa_scope": "synthetic metric-tool checks only", "real_observations_read": 0,
              "new_repairs": 0, "model_forwards": 0, "training": 0, "Bunny_arrays": 0,
              "failures": [], "checks": records}

    def check(name, actual, expected, tolerance=1e-12):
        actual, expected = np.asarray(actual), np.asarray(expected)
        passed = actual.shape == expected.shape and bool(np.allclose(actual, expected, rtol=tolerance, atol=tolerance))
        records.append({"name": name, "passed": passed, "actual": actual.tolist(), "expected": expected.tolist(),
                        "absolute_relative_tolerance": tolerance})
        if not passed:
            raise AssertionError(name)

    try:
        vertices = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]])
        triangles = np.array([[0, 1, 2]], dtype=np.int64)
        queries = np.array([[.25, .25, 2.], [.5, -.25, .5], [-1., -1., .5], [.4, .2, 0.], [.4, .2, .3]])
        nearest = nearest_points(queries, vertices, triangles)
        check("closed_form_face_edge_vertex_slide_off_surface_distance2", nearest["distance2"], [4., .3125, 2.25, 0., .09])
        check("closed_form_closest_locations", nearest["closest"], [[.25, .25, 0.], [.5, 0., 0.], [0., 0., 0.], [.4, .2, 0.], [.4, .2, 0.]])
        check("closed_form_face_barycentric", nearest["barycentric"][0], [.5, .25, .25])
        check("closed_form_barycentric_reconstruction", np.einsum("qi,qij->qj", nearest["barycentric"], vertices[triangles[nearest["triangle_id"]]]), nearest["closest"])
        check("all_closed_form_rows_available", nearest["valid"], np.ones(5, dtype=bool))
        vertex_distance2 = np.min(np.sum((queries[3, None, :] - vertices) ** 2, axis=1))
        check("in_surface_query_has_positive_nearest_vertex_distance", vertex_distance2 > 0, True)
        check("tangential_slide_keeps_surface_distance_zero", nearest["distance2"][3], 0.)
        check("tangential_slide_corresponding_coordinate_error_nonzero", np.linalg.norm(queries[3] - [.2, .2, 0.]), .2)

        collinear = np.array([[0., 0., 0.], [1., 0., 0.], [2., 0., 0.]])
        degenerate = nearest_points(np.array([[.5, 1., 0.]]), collinear, triangles)
        check("collinear_triangle_retains_segment_distance", degenerate["distance2"], [1.])
        check("collinear_triangle_degeneracy_count", degenerate["degenerate_triangle_count"], 1)
        check("collinear_triangle_closest_location", degenerate["closest"], [[.5, 0., 0.]])
        collapsed = nearest_points(np.array([[2., 3., 5.]]), np.array([[2., 3., 4.]] * 3), triangles)
        check("collapsed_triangle_retains_point_distance", collapsed["distance2"], [1.])
        check("collapsed_triangle_zero_edge_count", collapsed["zero_length_triangle_edge_count"], 3)
        duplicated = nearest_points(queries[:1], vertices, np.tile(triangles, (257, 1)))
        check("equal_distance_triangle_tie_uses_smallest_row_across_blocks", duplicated["triangle_id"], [0])
        blocked = nearest_points(np.tile(queries, (8, 1)), vertices, triangles, query_block=7, triangle_block=1)
        check("query_block_partition_preserves_distances", blocked["distance2"], np.tile(nearest["distance2"], 8))

        invalid_query = nearest_points(np.array([[0., 0., 0.], [np.nan, 0., 0.]]), vertices, triangles)
        check("nonfinite_query_retained_invalid", invalid_query["valid"], [True, False])
        check("nonfinite_query_denominator", invalid_query["invalid_query_count"], 1)
        check("nonfinite_query_nan_distance_retained", np.isnan(invalid_query["distance2"][1]), True)
        empty = nearest_points(queries, vertices, np.empty((0, 3), dtype=np.int64))
        check("empty_triangle_domain_explicit_unavailable", empty["status"] == "unavailable_empty_triangle_domain", True)
        check("empty_triangle_domain_retains_query_denominator", empty["query_count"], len(queries))
        broken_vertices = vertices.copy()
        broken_vertices[0, 0] = np.inf
        nonfinite = nearest_points(queries, broken_vertices, triangles)
        check("nonfinite_surface_explicit_unavailable", nonfinite["status"] == "unavailable_nonfinite_surface_vertices", True)
        check("nonfinite_surface_valid_rows_zero", np.count_nonzero(nonfinite["valid"]), 0)

        square = np.array([[0., 0., 0.], [1., 0., 0.], [1., 1., 0.], [0., 1., 0.]])
        square_faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
        square_edges = context_boundary_edges(square_faces)
        check("context_incidence_boundary_excludes_internal_diagonal", square_edges, [[0, 1], [0, 3], [1, 2], [2, 3]])
        boundary_points = np.array([[0., .25, 0.], [0., 0., 0.], [.5, .5, 0.], [.25, 0., 0.]])
        boundary = classify_boundary_points(boundary_points, square, square_edges)
        check("boundary_segments_and_vertex_classification", boundary["on_boundary"], [True, True, False, True])
        subset = classify_boundary_points(boundary_points, square, np.array([[0, 1]], dtype=np.int64))
        check("cutting_or_natural_subset_is_respected", subset["on_boundary"], [False, True, False, True])
        empty_boundary = classify_boundary_points(boundary_points, square, np.empty((0, 2), dtype=np.int64))
        check("empty_boundary_explicit_status", empty_boundary["status"] == "empty_boundary", True)
        check("empty_boundary_zero_flags", empty_boundary["on_boundary"], np.zeros(4, dtype=bool))
        check("empty_boundary_infinite_distance", np.isinf(empty_boundary["distance2"]), np.ones(4, dtype=bool))
        tolerance = boundary["length_tolerance"]
        near_edge = classify_boundary_points(np.array([[.5, tolerance * .5, 0.], [.5, tolerance * 2., 0.]]), square, np.array([[0, 1]], dtype=np.int64))
        check("length_roundoff_boundary_tolerance_not_sqrt_epsilon", near_edge["on_boundary"], [True, False])

        test_queries = np.array([[.2, .3, .7], [.7, .1, -.2], [1.3, .4, .1], [-.2, -.3, .1]])
        original = nearest_points(test_queries, square, square_faces)
        reordered_faces = nearest_points(test_queries, square, square_faces[::-1])
        check("triangle_permutation_preserves_metric", reordered_faces["distance2"], original["distance2"])
        vertex_order = np.array([2, 0, 3, 1])
        inverse = np.argsort(vertex_order)
        reordered_vertices = nearest_points(test_queries, square[vertex_order], inverse[square_faces[:, [2, 0, 1]]])
        check("vertex_and_corner_permutation_preserves_metric", reordered_vertices["distance2"], original["distance2"])
        axis = np.array([1.3, -2.1, .7])
        axis /= np.linalg.norm(axis)
        angle = .713
        x, y, z = axis
        cross_matrix = np.array([[0., -z, y], [z, 0., -x], [-y, x, 0.]])
        rotation = np.eye(3) * np.cos(angle) + (1.0 - np.cos(angle)) * np.outer(axis, axis) + np.sin(angle) * cross_matrix
        translation = np.array([12., -7., 3.5])
        transformed = nearest_points(test_queries @ rotation.T + translation, square @ rotation.T + translation, square_faces)
        check("common_rigid_transform_preserves_metric", transformed["distance2"], original["distance2"])
        check("common_rigid_transform_preserves_nearest_locations", transformed["closest"], original["closest"] @ rotation.T + translation)
        check("rotation_determinant_one", np.linalg.det(rotation), 1.)
        report["permutation_tie_note"] = "Equal-distance face rows use the smallest current triangle row ID. Reordering rows may change that ID and tie-location/barycentric metadata while the distance metric remains invariant."
        report["status"] = "passed_synthetic_metric_QA"
    except Exception as error:
        report["status"] = "failed_synthetic_metric_QA"
        report["failures"].append({"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        report["wall_s_before_final_report"] = time.perf_counter() - started
        report["CPU_s_before_final_report"] = time.process_time() - cpu_started
        report["own_process_before_final_report"] = own_resources()
        report["source_sha256"] = {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
                                    for name in ("surface_distance.py", "meter_qa.py")}
        report["check_count"] = len(records)
        report["attempts"] = prior_attempts + [{"status": report["status"], "wall_s": report["wall_s_before_final_report"],
                                                "CPU_s": report["CPU_s_before_final_report"], "failures": report["failures"]}]
        output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": report["status"], "checks": len(records), "wall_s": report["wall_s_before_final_report"]}), flush=True)


if __name__ == "__main__":
    main()
