"""Observation-only, residual-gated robust quadratic MLS for TRAIN-001.

All lengths are in the normalized observation coordinates q=(p-origin)/scale.
Each free point uses the same frozen observation. The returned signed residual
is observed normal height minus fitted height at that point. Threshold fitting
belongs to the caller, using the frozen training normal controls exactly once.
"""

from __future__ import annotations

import heapq

import numpy as np


GRAPH_RADIUS = 8.0
DISTANCE_BANDWIDTH = 4.0
NORMAL_DOT_MIN = 0.5
MINIMUM_POINTS = 12
IRLS_PASSES = 3
TUKEY_CUTOFF = 4.685
MAD_FACTOR = 1.4826
RESIDUAL_SCALE_FLOOR = 1.0e-4

FAILURE_REASONS = (
    "invalid_normal",
    "too_few_points",
    "rank_deficient",
    "irls_rank_deficient",
    "invalid_numeric",
)


def _unit_normals(normals):
    """Keep valid observation directions, including roundoff in unit length."""
    with np.errstate(invalid="ignore", over="ignore"):
        lengths = np.linalg.norm(normals, axis=1)
    valid = np.isfinite(normals).all(axis=1) & np.isfinite(lengths) & (lengths > 0)
    unit = np.zeros_like(normals)
    unit[valid] = normals[valid] / lengths[valid, None]
    return unit, valid


def _validate_geometry(positions, normals, edge_index, free_mask):
    positions = np.asarray(positions, dtype=np.float64)
    normals = np.asarray(normals, dtype=np.float64)
    edge_index = np.asarray(edge_index)
    free_mask = np.asarray(free_mask, dtype=bool)
    if positions.ndim != 2 or positions.shape[1] != 3:
        raise ValueError("positions must have shape (N, 3)")
    if normals.shape != positions.shape:
        raise ValueError("normals must have the same shape as positions")
    if free_mask.shape != (len(positions),):
        raise ValueError("free_mask must have shape (N,)")
    if edge_index.ndim != 2 or edge_index.shape[0] != 2:
        raise ValueError("edge_index must have shape (2, directed_edge_count)")
    if edge_index.dtype.kind not in "iu":
        raise ValueError("edge_index must contain integer local indices")
    if edge_index.size and (
        edge_index.min() < 0 or edge_index.max() >= len(positions)
    ):
        raise ValueError("edge_index contains an out-of-range local index")
    return positions, normals, edge_index, free_mask


def _adjacency(positions, edge_index):
    adjacency = [[] for _ in positions]
    invalid_edges = 0
    for source, target in edge_index.T:
        with np.errstate(invalid="ignore", over="ignore"):
            length = float(np.linalg.norm(positions[target] - positions[source]))
        if np.isfinite(length):
            adjacency[source].append((int(target), length))
        else:
            invalid_edges += 1
    return adjacency, invalid_edges


def _geodesic_neighborhood(adjacency, center):
    """Bounded shortest paths in the supplied directed two-way context graph."""
    best = {center: 0.0}
    pending = [(0.0, center)]
    while pending:
        distance, point = heapq.heappop(pending)
        if distance != best[point]:
            continue
        for neighbor, edge_length in adjacency[point]:
            candidate = distance + edge_length
            if candidate <= GRAPH_RADIUS and candidate < best.get(neighbor, np.inf):
                best[neighbor] = candidate
                heapq.heappush(pending, (candidate, neighbor))
    indices = np.array(sorted(best), dtype=np.int64)
    distances = np.array([best[index] for index in indices], dtype=np.float64)
    return indices, distances


def _tangent_frame(normal):
    axis = np.zeros(3, dtype=np.float64)
    axis[int(np.argmin(np.abs(normal)))] = 1.0
    tangent_u = np.cross(normal, axis)
    tangent_u /= np.linalg.norm(tangent_u)
    tangent_v = np.cross(normal, tangent_u)
    return tangent_u, tangent_v


def _weighted_fit(design, height, weights):
    root_weights = np.sqrt(weights)
    weighted_design = design * root_weights[:, None]
    weighted_height = height * root_weights
    coefficients, _, rank, _ = np.linalg.lstsq(
        weighted_design, weighted_height, rcond=None
    )
    return coefficients, int(rank)


def _fit_point(positions, unit_normals, center, indices, distances):
    normal = unit_normals[center]
    tangent_u, tangent_v = _tangent_frame(normal)
    with np.errstate(invalid="ignore", over="ignore"):
        offsets = positions[indices] - positions[center]
        u = offsets @ tangent_u
        v = offsets @ tangent_v
        height = offsets @ normal
        design = np.column_stack((u * u, u * v, v * v, u, v, np.ones(len(u))))
    if not np.isfinite(design).all() or not np.isfinite(height).all():
        return 0.0, "invalid_numeric", 0

    spatial_weight = np.exp(-np.square(distances / DISTANCE_BANDWIDTH))
    completed = 0
    try:
        coefficients, rank = _weighted_fit(design, height, spatial_weight)
        if rank != 6:
            return 0.0, "rank_deficient", completed
        if not np.isfinite(coefficients).all():
            return 0.0, "invalid_numeric", completed
        for _ in range(IRLS_PASSES):
            residual = height - design @ coefficients
            if not np.isfinite(residual).all():
                return 0.0, "invalid_numeric", completed
            median = np.median(residual)
            mad = np.median(np.abs(residual - median))
            scale = max(MAD_FACTOR * float(mad), RESIDUAL_SCALE_FLOOR)
            standardized = residual / (TUKEY_CUTOFF * scale)
            tukey_weight = np.zeros_like(residual)
            inside = np.abs(standardized) < 1.0
            tukey_weight[inside] = np.square(1.0 - np.square(standardized[inside]))
            coefficients, rank = _weighted_fit(
                design, height, spatial_weight * tukey_weight
            )
            if rank != 6:
                return 0.0, "irls_rank_deficient", completed
            if not np.isfinite(coefficients).all():
                return 0.0, "invalid_numeric", completed
            completed += 1
    except (np.linalg.LinAlgError, FloatingPointError):
        return 0.0, "invalid_numeric", completed

    # The observation is the coordinate origin, so z0=0 and fitted z=f.
    signed_residual = -float(coefficients[5])
    if not np.isfinite(signed_residual):
        return 0.0, "invalid_numeric", completed
    return signed_residual, "applicable", completed


def fit_residuals(positions, normals, edge_index, free_mask):
    """Return raw signed residuals, applicability, and exhaustive diagnostics.

    Inputs are local normalized positions (N,3), observation unit normals
    (N,3), the local directed 2E graph (2,2E), and the writable mask (N,).
    Finite nonzero normals are normalized internally to preserve their observed
    directions. Fixed and halo vertices remain neighborhood samples, with their
    own fits skipped. The center itself is a sample at geodesic distance zero.

    Each free point has exactly one final reason. Failed and fixed residuals
    are zero. Diagnostics contain JSON-serializable counts and length-N lists.
    """
    positions, normals, edge_index, free_mask = _validate_geometry(
        positions, normals, edge_index, free_mask
    )
    unit_normals, valid_normal = _unit_normals(normals)
    valid_position = np.isfinite(positions).all(axis=1)
    adjacency, invalid_edges = _adjacency(positions, edge_index)
    count = len(positions)
    raw_residual = np.zeros(count, dtype=np.float64)
    applicable = np.zeros(count, dtype=bool)
    reasons = ["fixed"] * count
    neighbor_count = np.zeros(count, dtype=np.int64)
    geodesic_count = np.zeros(count, dtype=np.int64)
    passes_completed = np.zeros(count, dtype=np.int64)
    excluded_invalid_normals = 0
    excluded_invalid_positions = 0

    for center in np.flatnonzero(free_mask):
        if not valid_normal[center]:
            reasons[center] = "invalid_normal"
            continue
        if not valid_position[center]:
            reasons[center] = "invalid_numeric"
            continue
        indices, distances = _geodesic_neighborhood(adjacency, int(center))
        geodesic_count[center] = len(indices)
        excluded_invalid_normals += int(np.count_nonzero(~valid_normal[indices]))
        excluded_invalid_positions += int(np.count_nonzero(~valid_position[indices]))
        aligned = unit_normals[indices] @ unit_normals[center] >= NORMAL_DOT_MIN
        keep = valid_normal[indices] & valid_position[indices] & aligned
        indices = indices[keep]
        distances = distances[keep]
        neighbor_count[center] = len(indices)
        if len(indices) < MINIMUM_POINTS:
            reasons[center] = "too_few_points"
            continue
        residual, reason, completed = _fit_point(
            positions, unit_normals, int(center), indices, distances
        )
        reasons[center] = reason
        passes_completed[center] = completed
        if reason == "applicable":
            raw_residual[center] = residual
            applicable[center] = True

    reason_counts = {
        reason: reasons.count(reason) for reason in ("applicable", *FAILURE_REASONS)
    }
    diagnostics = {
        "counts": {
            "total": count,
            "free": int(np.count_nonzero(free_mask)),
            "fixed": int(np.count_nonzero(~free_mask)),
            **reason_counts,
        },
        "per_point_reason": reasons,
        "neighbor_count": neighbor_count.tolist(),
        "geodesic_count": geodesic_count.tolist(),
        "irls_passes_completed": passes_completed.tolist(),
        "invalid_directed_edges_excluded": invalid_edges,
        "invalid_normal_neighbor_occurrences_excluded": excluded_invalid_normals,
        "invalid_position_neighbor_occurrences_excluded": excluded_invalid_positions,
        "configuration": {
            "coordinate_units": "observation local edge-length normalized",
            "graph_radius": GRAPH_RADIUS,
            "distance_bandwidth": DISTANCE_BANDWIDTH,
            "normal_dot_min": NORMAL_DOT_MIN,
            "minimum_points_including_center": MINIMUM_POINTS,
            "initial_WLS": 1,
            "Tukey_IRLS_passes": IRLS_PASSES,
            "Tukey_cutoff": TUKEY_CUTOFF,
            "MAD_factor": MAD_FACTOR,
            "residual_scale_floor": RESIDUAL_SCALE_FLOOR,
            "MAD_definition": "unweighted median(abs(signed_residual-median))",
            "Tukey_argument": "signed_residual/(Tukey_cutoff*scale)",
        },
    }
    return raw_residual, applicable, diagnostics


def gate_displacement(normals, raw_residual, applicable, free_mask, tau):
    """Apply the caller's frozen normalized threshold to the observed normals.

    Output is a fresh float64 (N,3) correction in normalized length units.
    Fixed, inapplicable, and nonfinite inputs yield exact zero corrections.
    """
    normals = np.asarray(normals, dtype=np.float64)
    raw_residual = np.asarray(raw_residual, dtype=np.float64)
    applicable = np.asarray(applicable, dtype=bool)
    free_mask = np.asarray(free_mask, dtype=bool)
    if normals.ndim != 2 or normals.shape[1] != 3:
        raise ValueError("normals must have shape (N, 3)")
    expected = (len(normals),)
    if any(value.shape != expected for value in (raw_residual, applicable, free_mask)):
        raise ValueError("raw_residual, applicable, and free_mask must have shape (N,)")
    tau_array = np.asarray(tau, dtype=np.float64)
    if tau_array.ndim != 0 or not np.isfinite(tau_array) or tau_array < 0:
        raise ValueError("tau must be a finite nonnegative scalar")
    tau = float(tau_array)
    unit_normals, valid_normal = _unit_normals(normals)
    active = applicable & free_mask & valid_normal & np.isfinite(raw_residual)
    correction = np.zeros_like(normals)
    signed_step = -np.sign(raw_residual[active]) * np.maximum(
        np.abs(raw_residual[active]) - tau, 0.0
    )
    correction[active] = signed_step[:, None] * unit_normals[active]
    return correction
