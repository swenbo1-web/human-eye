"""Independently verify fixed local-support membership using public current inputs."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write
import numpy as np

BASELINE_FIELDS = (
    "attention", "per_view_score", "incident_face_visible", "incident_face_pixel_area",
    "incident_face_signal", "candidate_rank", "ranked_source_ids", "active_core_source_ids",
    "positive_attention_source_ids", "fit_support_source_ids", "transition_source_ids",
    "unobserved_source_ids", "fit_exclusion_source_ids", "pixel_center_face_ids",
    "pixel_center_depth", "pixel_center_boundary", "pixel_center_RGBmax_difference",
    "pixel_center_energy", "pixel_center_coverage_count", "pixel_center_depth_tie_event",
    "vertex_projection_inside_image", "triangle_polygon_ids", "triangle_source_ids",
)
LOCAL_FIELDS = (
    "fit_target_source_ids", "fit_target_support_mask", "fit_target_support_count",
    "fit_target_design_rank", "fit_target_condition_number", "fit_target_angular_bins",
    "fit_target_normals", "fit_target_nearest_distance_m", "fit_target_farthest_distance_m",
    "fit_target_normal_dot_minimum", "fit_target_max_angular_gap_rad",
)


def load_fields(path, fields):
    with np.load(path, allow_pickle=False) as archive:
        if set(archive.files).intersection({"clean_vertices_world", "damage_mask", "support_ids", "noise"}):
            raise ValueError("audit_requires_public_current_or_derived_correspondence_packets")
        return {key: archive[key] for key in fields}


def array_identity(array):
    return dict(dtype=str(array.dtype), shape=list(array.shape),
        sha256=hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest())


def current_normals(vertices, faces):
    triangles = vertices[faces]
    cross = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    summed = np.zeros_like(vertices)
    for corner in range(3):
        np.add.at(summed, faces[:, corner], cross)
    lengths = np.linalg.norm(summed, axis=1)
    return np.divide(summed, lengths[:, None], out=np.zeros_like(summed), where=lengths[:, None] > 0)


def coverage(vertices, normals, target_id, selected):
    normal = normals[target_id]
    axis = np.eye(3)[np.argmin(np.abs(normal))]
    tangent0 = np.cross(normal, axis)
    length = np.linalg.norm(tangent0)
    if length > 0:
        tangent0 /= length
    tangent1 = np.cross(normal, tangent0)
    delta = vertices[selected] - vertices[target_id]
    x, y = delta @ tangent0 / .032, delta @ tangent1 / .032
    design = np.column_stack((np.ones(len(selected)), x, y, x * x, x * y, y * y))
    singular = np.linalg.svd(design, compute_uv=False)
    tolerance = singular[0] * max(design.shape) * np.finfo(np.float64).eps if len(singular) else 0.
    rank = int(np.count_nonzero(singular > tolerance))
    condition = float(singular[0] / singular[-1]) if rank == 6 else -1.
    angles = np.mod(np.arctan2(y, x), 2 * np.pi)
    angular_bins = len(np.unique(np.floor(angles * 8 / (2 * np.pi)).astype(int)))
    ordered_angles = np.sort(angles)
    maximum_gap = float(np.diff(np.r_[ordered_angles, ordered_angles[0] + 2 * np.pi]).max())
    return dict(rank=rank, condition_number=condition, angular_bins=angular_bins,
        maximum_angular_gap_rad=maximum_gap, singular_values=singular.tolist())


def audit(packet_path, current_path, baseline_path, correspondence_path, output_path):
    started, cpu = time.perf_counter(), time.process_time()
    if not Path(output_path).resolve().is_relative_to(HERE):
        raise ValueError("optimized_support_audit_output_outside_current_batch")
    packet = load_fields(packet_path, ("source_ids", "current_positions_world", "current_vertex_normals") + LOCAL_FIELDS)
    current = load_fields(current_path, ("source_ids", "vertices_world", "faces", "I_ids"))
    baseline = load_fields(baseline_path, BASELINE_FIELDS)
    corresponding = load_fields(correspondence_path, BASELINE_FIELDS)
    vertices, faces = current["vertices_world"], current["faces"]
    normals = current_normals(vertices, faces)
    outer, targets = packet["source_ids"], packet["fit_target_source_ids"]
    checks = dict(source_IDs_index_current_rows=bool(np.array_equal(current["source_ids"], np.arange(len(vertices)))),
        core_targets_69=bool(len(targets) == 69 and np.array_equal(targets, np.sort(baseline["active_core_source_ids"]))),
        outer_pool_unchanged=bool(np.array_equal(outer, baseline["fit_support_source_ids"])),
        outer_current_positions_exact=bool(np.array_equal(packet["current_positions_world"], vertices[outer])),
        outer_reference_normals_match_current_triangles=bool(np.allclose(packet["current_vertex_normals"], normals[outer], rtol=0, atol=1e-12)),
        target_reference_normals_match_current_triangles=bool(np.allclose(packet["fit_target_normals"], normals[targets], rtol=0, atol=1e-12)),
        membership_shape=packet["fit_target_support_mask"].shape == (len(outer), len(targets)),
        membership_dtype=packet["fit_target_support_mask"].dtype == np.dtype(bool))
    immutable_fields = {}
    for key in BASELINE_FIELDS:
        first, second = baseline[key], corresponding[key]
        equal = first.dtype == second.dtype and first.shape == second.shape and first.tobytes() == second.tobytes()
        checks["unchanged_" + key] = bool(equal)
        immutable_fields[key] = dict(baseline=array_identity(first), optimized=array_identity(second), bytes_equal=bool(equal))
    plan = read("OPTIMIZATION_PLAN.json")["fixed_rule"]
    checks["fixed_rule_parameters"] = (plan["maximum_distance_m"] == .032 and plan["normal_dot_minimum"] == .55
        and plan["normal_dot_comparison"] == "strictly_greater" and plan["maximum_neighbors"] == 32)
    rows = []
    for column, target_id in enumerate(targets):
        delta = vertices[outer] - vertices[target_id]
        distance = np.sqrt(np.einsum("ij,ij->i", delta, delta))
        normal_dot = np.einsum("ij,j->i", normals[outer], normals[target_id])
        eligible = np.flatnonzero((distance <= .032) & (normal_dot > .55))
        ordered = sorted(eligible.tolist(), key=lambda index: (distance[index], int(outer[index])))
        selected_rows = np.asarray(ordered[:32], dtype=np.int64)
        expected_mask = np.zeros(len(outer), dtype=bool)
        expected_mask[selected_rows] = True
        actual_mask = packet["fit_target_support_mask"][:, column]
        selected = outer[selected_rows]
        metrics = dict(rank=0, condition_number=-1., angular_bins=0, maximum_angular_gap_rad=float(2 * np.pi), singular_values=[])
        nearest = farthest = normal_minimum = -1.
        if len(selected):
            metrics = coverage(vertices, normals, target_id, selected)
            nearest, farthest = float(distance[selected_rows[0]]), float(distance[selected_rows[-1]])
            normal_minimum = float(normal_dot[selected_rows].min())
        row_checks = dict(stable_nearest_membership=bool(np.array_equal(actual_mask, expected_mask)),
            recorded_count_matches=int(packet["fit_target_support_count"][column]) == len(selected),
            recorded_rank_matches=int(packet["fit_target_design_rank"][column]) == metrics["rank"],
            recorded_angular_bins_match=int(packet["fit_target_angular_bins"][column]) == metrics["angular_bins"])
        for field, expected in (("condition_number", metrics["condition_number"]), ("nearest_distance_m", nearest),
                                ("farthest_distance_m", farthest), ("normal_dot_minimum", normal_minimum),
                                ("max_angular_gap_rad", metrics["maximum_angular_gap_rad"])):
            row_checks["recorded_" + field + "_matches"] = bool(np.isclose(packet["fit_target_" + field][column], expected, rtol=1e-10, atol=1e-12))
        checks["target_" + str(int(target_id))] = all(row_checks.values())
        rows.append(dict(target_source_id=int(target_id), eligible_pool_points=len(eligible), selected_source_ids_nearest_order=selected.tolist(),
            recorded_source_ids=outer[actual_mask].tolist(), checks=row_checks, support_count=len(selected),
            nearest_distance_m=nearest, farthest_distance_m=farthest, minimum_normal_dot=normal_minimum, **metrics))
    result = dict(cycle_id="M6-IMAGE-CORRESPONDENCE-005", status="pass" if all(checks.values()) else "fail",
        checks=checks, passed=sum(bool(value) for value in checks.values()), total=len(checks), target_rows=rows,
        summary=dict(targets=len(targets), outer_pool_points=len(outer),
            support_count_minimum=min(row["support_count"] for row in rows), support_count_maximum=max(row["support_count"] for row in rows),
            rank_distribution={str(rank): sum(row["rank"] == rank for row in rows) for rank in sorted({row["rank"] for row in rows})},
            angular_bins_minimum=min(row["angular_bins"] for row in rows), angular_bins_maximum=max(row["angular_bins"] for row in rows),
            maximum_selected_distance_m=max(row["farthest_distance_m"] for row in rows),
            minimum_selected_normal_dot=min(row["minimum_normal_dot"] for row in rows),
            maximum_full_rank_condition_number=max(row["condition_number"] for row in rows)),
        immutable_array_fields=immutable_fields,
        inputs=dict(outer_packet=identity(packet_path), public_current_packet=identity(current_path), baseline_arrays=identity(baseline_path),
            optimized_correspondence_arrays=identity(correspondence_path), fixed_optimization_plan=identity(HERE / "OPTIMIZATION_PLAN.json")),
        source=identity(Path(__file__)), hidden_labels_read=False, target_geometry_read=False,
        normal_definition="Normalized incident current triangle cross sums, independently recomputed from full current mesh.",
        coverage_role="Rank, condition and angular coverage are algebraic/geometric observations; membership rule validation is separate from restoration quality.",
        wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu, actual_Blender_calls=0, actual_Pro_calls=0)
    write(output_path, result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet-path", type=Path, required=True)
    parser.add_argument("--current-packet", type=Path, default=HERE / "private/cases/repair/initial.npz")
    parser.add_argument("--baseline-arrays", type=Path, default=HERE / "private/correspondence_preflight/baseline/ARRAYS.npz")
    parser.add_argument("--correspondence-arrays", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=HERE / "OPTIMIZED_SUPPORT_AUDIT.json")
    args = parser.parse_args()
    result = audit(args.packet_path.resolve(), args.current_packet.resolve(), args.baseline_arrays.resolve(),
        args.correspondence_arrays.resolve(), args.output.resolve())
    print(json.dumps({key: result[key] for key in ("status", "passed", "total", "summary", "wall_s", "CPU_s")}))
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
