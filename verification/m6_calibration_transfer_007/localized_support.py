"""Target-local fitting neighborhoods from current geometry and an outer pool."""

import time

import numpy as np


PARAMETERS = dict(maximum_distance_m=.032, minimum_normal_dot_exclusive=.55,
    maximum_support_points=32, angular_sector_count=8,
    ordering="ascending_Euclidean_distance_then_source_ID",
    normal_definition="normalized_sum_of_incident_current_triangle_cross_vectors",
    quadratic_coordinates="target_tangent_plane_coordinates_divided_by_0.032_source_native",
    deficient_condition_number=-1., unavailable_distance_or_normal_dot=-1.)


def tangent_basis(normal):
    anchor = np.eye(3)[int(np.argmin(np.abs(normal)))]
    first = np.cross(normal, anchor)
    length = np.linalg.norm(first)
    first = first / length if length > 0 else np.zeros(3)
    return first, np.cross(normal, first)


def build_local_support(vertices, normals, outer_source_ids, target_source_ids):
    started, cpu = time.perf_counter(), time.process_time()
    vertices = np.asarray(vertices, dtype=np.float64)
    normals = np.asarray(normals, dtype=np.float64)
    outer_ids = np.asarray(outer_source_ids)
    target_ids = np.asarray(target_source_ids)
    if vertices.ndim != 2 or vertices.shape[1] != 3 or normals.shape != vertices.shape:
        raise ValueError("local_support_requires_current_positions_and_normals_N_by3")
    if not np.isfinite(vertices).all() or not np.isfinite(normals).all():
        raise ValueError("local_support_current_geometry_must_be_finite")
    for ids in (outer_ids, target_ids):
        if ids.ndim != 1 or not np.issubdtype(ids.dtype, np.integer) or len(np.unique(ids)) != len(ids):
            raise ValueError("local_support_source_IDs_must_be_unique_integer_vectors")
        if len(ids) and (ids.min() < 0 or ids.max() >= len(vertices)):
            raise ValueError("local_support_source_ID_outside_current_mesh")
    outer_ids = outer_ids.astype(np.int64)
    target_ids = np.sort(target_ids.astype(np.int64))
    targets = len(target_ids)
    membership = np.zeros((len(outer_ids), targets), dtype=bool)
    counts = np.zeros(targets, dtype=np.int64)
    ranks = np.zeros(targets, dtype=np.int64)
    conditions = np.full(targets, -1., dtype=np.float64)
    angular_bins = np.zeros(targets, dtype=np.int64)
    nearest = np.full(targets, -1., dtype=np.float64)
    farthest = np.full(targets, -1., dtype=np.float64)
    normal_minimum = np.full(targets, -1., dtype=np.float64)
    angular_gap = np.full(targets, 2 * np.pi, dtype=np.float64)
    for column, target_id in enumerate(target_ids):
        offsets = vertices[outer_ids] - vertices[target_id]
        distance = np.linalg.norm(offsets, axis=1)
        normal_dot = normals[outer_ids] @ normals[target_id]
        eligible = np.flatnonzero((distance <= PARAMETERS["maximum_distance_m"])
                                  & (normal_dot > PARAMETERS["minimum_normal_dot_exclusive"]))
        order = np.lexsort((outer_ids[eligible], distance[eligible]))
        selected = eligible[order[:PARAMETERS["maximum_support_points"]]]
        membership[selected, column] = True
        counts[column] = len(selected)
        if not len(selected):
            continue
        nearest[column], farthest[column] = distance[selected[0]], distance[selected[-1]]
        normal_minimum[column] = normal_dot[selected].min()
        first, second = tangent_basis(normals[target_id])
        x = offsets[selected] @ first / PARAMETERS["maximum_distance_m"]
        y = offsets[selected] @ second / PARAMETERS["maximum_distance_m"]
        design = np.column_stack((np.ones(len(selected)), x, y, x * x, x * y, y * y))
        ranks[column] = np.linalg.matrix_rank(design)
        if ranks[column] == 6:
            conditions[column] = np.linalg.cond(design)
        angles = np.mod(np.arctan2(y, x), 2 * np.pi)
        sectors = np.floor(angles * PARAMETERS["angular_sector_count"] / (2 * np.pi)).astype(int)
        angular_bins[column] = len(np.unique(sectors))
        sorted_angles = np.sort(angles)
        angular_gap[column] = np.max(np.diff(np.r_[sorted_angles, sorted_angles[0] + 2 * np.pi]))
    arrays = dict(fit_target_source_ids=target_ids, fit_target_support_mask=membership,
        fit_target_support_count=counts, fit_target_design_rank=ranks,
        fit_target_condition_number=conditions, fit_target_angular_bins=angular_bins,
        fit_target_normals=normals[target_ids], fit_target_nearest_distance_m=nearest,
        fit_target_farthest_distance_m=farthest, fit_target_normal_dot_minimum=normal_minimum,
        fit_target_max_angular_gap_rad=angular_gap)
    summary = dict(parameters=PARAMETERS, targets=targets, outer_pool_points=len(outer_ids),
        support_count_minimum=int(counts.min()) if targets else 0,
        support_count_maximum=int(counts.max()) if targets else 0,
        support_count_median=float(np.median(counts)) if targets else 0.,
        full_rank_targets=int(np.sum(ranks == 6)), angular_bins_minimum=int(angular_bins.min()) if targets else 0,
        angular_bins_maximum=int(angular_bins.max()) if targets else 0,
        maximum_selected_distance_m=float(farthest.max()) if targets else -1.,
        maximum_full_rank_condition_number=float(conditions.max()) if targets else -1.,
        qualification="Full design rank is an algebraic measurement. Spatial coverage and extrapolation reliability require inspection.",
        wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu)
    return arrays, summary
