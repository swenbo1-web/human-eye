"""Bounded execution geometry, separate from display/contact tolerances.

The solid classifier reuses the engine's certified convex-component SAT. It is
not an independent ground-truth evaluator and does not certify swept paths.
Clearance uses all triangle-surface vertex/triangle and edge/edge features without display
rounding or witness-point attention heuristics. Unsupported solids and resource
limits remain unknown, never clear.
"""
from __future__ import annotations

import math
from types import SimpleNamespace
import numpy as np

from human_eye_module1_operators import MeshEntity3D
from human_eye_module1_operators.submodule_1_4_spatial_sniffer import (
    _certified_solid_collision, _convex_shells, _single_convex_collision_and_zero,
)


COLLISION_TOLERANCE_M = 1e-9
MAX_DENSE_ELEMENTS = 1_000_000
MAX_SAT_PROJECTION_ELEMENTS = 2_000_000
MAX_SCENE_WORK_ELEMENTS = 8_000_000
_CHUNK = 64
SURFACE_SCOPE = "certified_triangle_surface_only_loose_vertices_and_edges_excluded"


def _counts(mesh):
    if isinstance(mesh, dict):
        vertices, faces = mesh.get("vertices", ()), mesh.get("faces", ())
        edges = mesh.get("edges")
        return len(vertices), len(faces), max(len(edges) if edges is not None else 0, 3 * len(faces))
    return len(mesh.vertices), len(mesh.faces), max(len(mesh.edges), 3 * len(mesh.faces))


def work_budget_status(meshes, *, query_pairs=None, purpose="collision"):
    """Conservative preflight for legacy dense geometry kernels, without probing.

    Counts deliberately overestimate distinct normals/edge directions. One
    million float64 elements is 8 MB for one matrix; kernels keep several such
    arrays. Edge counts bound all certified directions, including objects with
    multiple convex shells. This is admission policy, not a memory guarantee.
    """
    if not isinstance(purpose, str) or purpose not in {"collision", "mesh_validation", "render", "attention"}:
        raise ValueError("Unknown geometry work budget purpose")
    meshes = list(meshes)
    counts = [_counts(mesh) for mesh in meshes]
    if query_pairs is not None:
        if not isinstance(query_pairs, (list, tuple)):
            raise ValueError("query_pairs must be an explicit list of object ID pairs")
        identities = [mesh.get("object_id") if isinstance(mesh, dict) else getattr(mesh, "object_id", None)
                      for mesh in meshes]
        if any(not isinstance(identity, str) or not identity for identity in identities) or len(set(identities)) != len(identities):
            raise ValueError("Explicit work pairs require unique stable object IDs")
        positions = {identity: i for i, identity in enumerate(identities)}
        pairs, seen = [], set()
        for pair in query_pairs:
            if (not isinstance(pair, (list, tuple)) or len(pair) != 2
                    or any(not isinstance(identity, str) or identity not in positions for identity in pair)
                    or pair[0] == pair[1]):
                raise ValueError("Invalid query pair")
            left, right = sorted((positions[pair[0]], positions[pair[1]]))
            if (left, right) in seen:
                raise ValueError("Repeated query pair")
            seen.add((left, right))
            pairs.append((left, right))
    else:
        pairs = ([(i, j) for i in range(len(counts)) for j in range(i + 1, len(counts))]
                 if purpose == "collision" else [])
    if purpose != "collision":
        if query_pairs:
            raise ValueError("Only collision budgets accept nonempty query pairs")
        pairs = []
    reasons = []
    # Rendering and attention use linear vertex/triangle arrays, not the
    # convex validation matrix or pairwise SAT. Raster row limits remain in
    # the rasterizers themselves and are not weakened by this admission plan.
    validation = purpose in {"collision", "mesh_validation"}
    own_work = [v * f if validation else v + 3 * f + e for v, f, e in counts]
    largest_dense = max(own_work, default=0)
    largest_sat = 0
    total = sum(own_work)
    for left, right in pairs:
        va, fa, ea = counts[left]
        vb, fb, eb = counts[right]
        dense = max(va * fb, vb * fa, ea * eb, fa * fb)
        sat = (va + vb) * (fa + fb + ea * eb)
        largest_dense = max(largest_dense, dense)
        largest_sat = max(largest_sat, sat)
        total += va * fb + vb * fa + ea * eb + fa * fb + sat
    if largest_dense > MAX_DENSE_ELEMENTS:
        reasons.append("dense_geometry_work_limit")
    if largest_sat > MAX_SAT_PROJECTION_ELEMENTS:
        reasons.append("sat_projection_work_limit")
    if total > MAX_SCENE_WORK_ELEMENTS:
        reasons.append("scene_geometry_work_limit")
    result = {"within_budget": not reasons, "reason_codes": reasons,
            "estimates": {"largest_dense_elements": largest_dense,
                          "largest_sat_projection_elements": largest_sat,
                          "scene_work_elements": total,
                          "largest_float64_matrix_bytes": 8 * max(largest_dense, largest_sat)},
            "limits": {"dense_elements": MAX_DENSE_ELEMENTS,
                       "sat_projection_elements": MAX_SAT_PROJECTION_ELEMENTS,
                       "scene_work_elements": MAX_SCENE_WORK_ELEMENTS},
            "policy": "conservative_full_geometry_no_decimation"}
    if query_pairs is not None or purpose != "collision":
        result.update(purpose=purpose, planned_pair_count=len(pairs),
                      mesh_validation_included=validation,
                      policy="purpose_scoped_conservative_geometry_no_decimation")
    return result


def solid_support_status(mesh):
    """Validate one current closed convex/component solid before any pruning.

    This wraps the existing numerical support classifier without expanding its
    tolerance, supported topology or physical precision claims. It is not a
    collision measurement and does not authorize a host action.
    """
    budget = work_budget_status([mesh], purpose="mesh_validation")
    result = {"supported": False, "component_count": None, "work_budget": budget,
              "support_method": "existing_closed_convex_components_validation",
              "evaluator_source": "engine_geometry", "independent_ground_truth": False,
              "geometry_scope": SURFACE_SCOPE}
    if not budget["within_budget"]:
        return {**result, "reason": "geometry_resource_limit"}
    try:
        # Validate detached current contents. Do not let a mutable caller's
        # in-process CRC-token cache become an authoritative support proof for
        # this new spatial index, and do not persist certified shell objects.
        value = mesh.to_dict() if callable(getattr(mesh, "to_dict", None)) else mesh
        faces = np.asarray(value["faces"])
        vertices = np.asarray(value["vertices"])
        if (faces.ndim != 2 or faces.shape[1:] != (3,) or faces.dtype.kind not in "iu"
                or not len(faces) or vertices.ndim != 2 or vertices.shape[1:] != (3,)
                or vertices.dtype.kind not in "ifu" or not np.isfinite(vertices).all()
                or np.min(faces) < 0 or np.max(faces) >= len(vertices)):
            raise ValueError("invalid_current_solid_input")
        current = MeshEntity3D.from_dict(value)
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            shells = _convex_shells(current)
        if shells is None or not shells:
            from .orthogonal_solid import decompose_orthogonal_solid
            proof = decompose_orthogonal_solid(current)
            if proof['supported'] is not True:
                return {**result, "reason": "unsupported_solid_geometry",
                        "orthogonal_support": proof}
            if proof['convex_part_count'] <= 1:
                # This new branch adds genuinely nonconvex solids. It must
                # not revive a convex box rejected by legacy numeric guards.
                return {**result, "reason": "unsupported_solid_geometry",
                        "orthogonal_support": {"supported": False,
                            "reason": "legacy_convex_rejection_not_overridden"}}
            return {**result, "supported": True, "component_count": 1,
                    "support_method": proof['support_method'],
                    "convex_part_count": proof['convex_part_count'],
                    "orthogonal_boundary_proof": proof['proof']}
        return {**result, "supported": True, "component_count": len(shells)}
    except (ValueError, IndexError, TypeError, FloatingPointError, OverflowError, AttributeError, KeyError) as exc:
        return {**result, "reason": "solid_support_evaluation_failed", "error_type": type(exc).__name__}


def _point_segment_sq(points, starts, ends):
    delta = ends - starts
    offset = points[:, None, :] - starts[None, :, :]
    length_sq = np.einsum("ij,ij->i", delta, delta)
    parameter = np.divide(np.einsum("ijk,jk->ij", offset, delta), length_sq[None, :],
                          out=np.zeros(offset.shape[:2]), where=length_sq[None, :] > 0)
    np.clip(parameter, 0, 1, out=parameter)
    residual = offset - parameter[:, :, None] * delta[None, :, :]
    return np.einsum("ijk,ijk->ij", residual, residual)


def _point_triangle_min_sq(points, triangles):
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    ab, ac = b - a, c - a
    normal = np.cross(ab, ac)
    normal_sq = np.einsum("ij,ij->i", normal, normal)
    offset = points[:, None, :] - a[None, :, :]
    normal_dot = np.einsum("ijk,jk->ij", offset, normal)
    projection = offset - (normal_dot / normal_sq[None, :])[:, :, None] * normal[None, :, :]
    ab_sq = np.einsum("ij,ij->i", ab, ab)
    ac_sq = np.einsum("ij,ij->i", ac, ac)
    abac = np.einsum("ij,ij->i", ab, ac)
    dot_ab = np.einsum("ijk,jk->ij", projection, ab)
    dot_ac = np.einsum("ijk,jk->ij", projection, ac)
    # |ab x ac|^2 avoids subtracting nearly equal squared dot products.
    u = (dot_ab * ac_sq[None, :] - dot_ac * abac[None, :]) / normal_sq[None, :]
    v = (dot_ac * ab_sq[None, :] - dot_ab * abac[None, :]) / normal_sq[None, :]
    inside = (u >= 0) & (v >= 0) & (u + v <= 1)
    best = np.where(inside, normal_dot * normal_dot / normal_sq[None, :], np.inf)
    for left, right in ((a, b), (b, c), (c, a)):
        best = np.minimum(best, _point_segment_sq(points, left, right))
    return float(best.min())


def _segment_min_sq(a0, a1, b0, b1):
    # Endpoints cover boundary minima. The unconstrained line-line minimum
    # covers interior minima; parallel segments attain a boundary minimum.
    best = min(float(_point_segment_sq(a0, b0, b1).min()),
               float(_point_segment_sq(a1, b0, b1).min()),
               float(_point_segment_sq(b0, a0, a1).min()),
               float(_point_segment_sq(b1, a0, a1).min()))
    u, v = a1 - a0, b1 - b0
    w = a0[:, None, :] - b0[None, :, :]
    aa = np.einsum("ij,ij->i", u, u)[:, None]
    bb = u @ v.T
    cc = np.einsum("ij,ij->i", v, v)[None, :]
    dd = np.einsum("ijk,ik->ij", w, u)
    ee = np.einsum("ijk,jk->ij", w, v)
    cross = np.cross(u[:, None, :], v[None, :, :])
    determinant = np.einsum("ijk,ijk->ij", cross, cross)
    nonparallel = determinant > 0
    s = np.divide(bb * ee - cc * dd, determinant,
                  out=np.zeros_like(determinant), where=nonparallel)
    t = np.divide(aa * ee - bb * dd, determinant,
                  out=np.zeros_like(determinant), where=nonparallel)
    inside = nonparallel & (s >= 0) & (s <= 1) & (t >= 0) & (t <= 1)
    residual = w + s[:, :, None] * u[:, None, :] - t[:, :, None] * v[None, :, :]
    values = np.where(inside, np.einsum("ijk,ijk->ij", residual, residual), np.inf)
    return min(best, float(values.min()))


def _surface_vertices(mesh):
    # Solid certification is over face-referenced vertices. Do not introduce
    # isolated points into clearance, or mutate/reindex the original mesh.
    return mesh.vertices[np.unique(mesh.faces)]


def _aabb_candidates(left_low, left_high, right_low, right_high, best):
    """Keep original row/column order and all numerically uncertain pairs.

    The retained Cartesian product can include extra pairs. Its leaves still
    use the original kernels and witness phase order. Bounds live only for
    this call, in the same coordinates as those kernels.
    """
    bounds = (left_low, left_high, right_low, right_high)
    if not all(np.isfinite(value).all() for value in bounds):
        return np.arange(len(left_low)), np.arange(len(right_low))
    scale = max(float(np.max(np.abs(value))) for value in bounds)
    # Include world-coordinate subtraction and squared-distance rounding.
    # At extreme scales the margin becomes infinite, retaining every pair.
    with np.errstate(over='ignore', invalid='ignore'):
        gap = np.maximum(0.0, np.maximum(left_low[:, None, :] - right_high[None, :, :],
                                        right_low[None, :, :] - left_high[:, None, :]))
        lower = np.einsum('ijk,ijk->ij', gap, gap)
        margin = 128 * np.finfo(float).eps * np.float64(scale) ** 2
        keep = ~np.isfinite(lower) | (lower <= best + margin)
    return np.flatnonzero(keep.any(axis=1)), np.flatnonzero(keep.any(axis=0))


def _surface_candidates(left, right, best):
    if not math.isfinite(best):
        return left, right
    rows, columns = _aabb_candidates(left.min(axis=1), left.max(axis=1),
                                    right.min(axis=1), right.max(axis=1), best)
    return left[rows], right[columns]


def _surface_distance(a, b):
    minimum = math.inf
    for points_mesh, faces_mesh in ((a, b), (b, a)):
        surface_points = _surface_vertices(points_mesh)
        for p in range(0, len(surface_points), _CHUNK):
            points = surface_points[p:p + _CHUNK]
            for f in range(0, len(faces_mesh.faces), _CHUNK):
                triangles = faces_mesh.vertices[faces_mesh.faces[f:f + _CHUNK]]
                candidates, triangles = _surface_candidates(points[:, None, :], triangles, minimum)
                if len(candidates) and len(triangles):
                    minimum = min(minimum, _point_triangle_min_sq(candidates[:, 0], triangles))
    # Explicit scene edges may describe only visible outlines. Derive complete
    # surface edges from triangles so those hints cannot hide an EE minimum.
    def all_edges(mesh):
        pairs = np.concatenate([mesh.faces[:, [0, 1]], mesh.faces[:, [1, 2]],
                                mesh.faces[:, [2, 0]]])
        return np.unique(np.sort(pairs, axis=1), axis=0)
    edges_a, edges_b = all_edges(a), all_edges(b)
    for i in range(0, len(edges_a), _CHUNK):
        ae = a.vertices[edges_a[i:i + _CHUNK]]
        for j in range(0, len(edges_b), _CHUNK):
            be = b.vertices[edges_b[j:j + _CHUNK]]
            left, right = _surface_candidates(ae, be, minimum)
            if len(left) and len(right):
                minimum = min(minimum, _segment_min_sq(left[:, 0], left[:, 1], right[:, 0], right[:, 1]))
    return math.sqrt(max(0.0, minimum))


def _surface_distance_with_witness(a, b):
    """Nearest original-surface feature pair, never a decomposition seam."""
    original_a, original_b = a, b
    origin = np.asarray(a.vertices[a.faces[0, 0]], dtype=float).copy()
    a = SimpleNamespace(vertices=np.asarray(a.vertices) - origin, faces=a.faces)
    b = SimpleNamespace(vertices=np.asarray(b.vertices) - origin, faces=b.faces)
    best = math.inf
    witnesses = None

    def remember(left, right, distance_sq):
        nonlocal best, witnesses
        index = np.unravel_index(int(np.argmin(distance_sq)), distance_sq.shape)
        value = float(distance_sq[index])
        if value < best:
            best = value
            witnesses = (np.asarray(left[index], dtype=float).copy(),
                         np.asarray(right[index], dtype=float).copy())

    def point_segments(points, starts, ends, *, reverse=False):
        delta = ends - starts
        offsets = points[:, None, :] - starts[None, :, :]
        lengths = np.einsum('ij,ij->i', delta, delta)
        parameter = np.divide(np.einsum('ijk,jk->ij', offsets, delta), lengths[None, :],
                              out=np.zeros(offsets.shape[:2]), where=lengths[None, :] > 0)
        np.clip(parameter, 0, 1, out=parameter)
        on_segment = starts[None, :, :] + parameter[:, :, None] * delta[None, :, :]
        on_points = np.broadcast_to(points[:, None, :], on_segment.shape)
        residual = offsets - parameter[:, :, None] * delta[None, :, :]
        squared = np.einsum('ijk,ijk->ij', residual, residual)
        remember(on_segment if reverse else on_points, on_points if reverse else on_segment, squared)

    for left, right, reverse in ((a, b, False), (b, a, True)):
        surface_points = _surface_vertices(left)
        for start in range(0, len(surface_points), _CHUNK):
            block_points = surface_points[start:start + _CHUNK]
            for face in range(0, len(right.faces), _CHUNK):
                triangles = right.vertices[right.faces[face:face + _CHUNK]]
                candidates, triangles = _surface_candidates(block_points[:, None, :], triangles, best)
                if not len(candidates) or not len(triangles):
                    continue
                points = candidates[:, 0]
                p, q, r = triangles[:, 0], triangles[:, 1], triangles[:, 2]
                ab, ac = q - p, r - p
                normal = np.cross(ab, ac)
                norm_sq = np.einsum('ij,ij->i', normal, normal)
                if (norm_sq <= 0).any():
                    raise ValueError('Degenerate original surface for witness')
                offsets = points[:, None, :] - p[None, :, :]
                signed = np.einsum('ijk,jk->ij', offsets, normal)
                projected = offsets - (signed / norm_sq[None, :])[:, :, None] * normal[None, :, :]
                ab_sq, ac_sq = np.einsum('ij,ij->i', ab, ab), np.einsum('ij,ij->i', ac, ac)
                abac = np.einsum('ij,ij->i', ab, ac)
                dab, dac = np.einsum('ijk,jk->ij', projected, ab), np.einsum('ijk,jk->ij', projected, ac)
                u = (dab * ac_sq[None, :] - dac * abac[None, :]) / norm_sq[None, :]
                v = (dac * ab_sq[None, :] - dab * abac[None, :]) / norm_sq[None, :]
                inside = (u >= 0) & (v >= 0) & (u + v <= 1)
                squared = np.where(inside, signed * signed / norm_sq[None, :], np.inf)
                on_face = p[None, :, :] + projected
                on_points = np.broadcast_to(points[:, None, :], on_face.shape)
                remember(on_face if reverse else on_points, on_points if reverse else on_face, squared)
                for x, y in ((p, q), (q, r), (r, p)):
                    point_segments(points, x, y, reverse=reverse)

    def edges(mesh):
        pairs = np.concatenate([mesh.faces[:, [0, 1]], mesh.faces[:, [1, 2]], mesh.faces[:, [2, 0]]])
        return mesh.vertices[np.unique(np.sort(pairs, axis=1), axis=0)]

    left_edges, right_edges = edges(a), edges(b)
    for start in range(0, len(left_edges), _CHUNK):
        aa = left_edges[start:start + _CHUNK]
        a0, a1 = aa[:, 0], aa[:, 1]
        for stop in range(0, len(right_edges), _CHUNK):
            bb = right_edges[stop:stop + _CHUNK]
            selected_a, bb = _surface_candidates(aa, bb, best)
            if not len(selected_a) or not len(bb):
                continue
            a0, a1 = selected_a[:, 0], selected_a[:, 1]
            b0, b1 = bb[:, 0], bb[:, 1]
            u, v = a1 - a0, b1 - b0
            w = a0[:, None, :] - b0[None, :, :]
            ua = np.einsum('ij,ij->i', u, u)[:, None]
            uv = u @ v.T
            vb = np.einsum('ij,ij->i', v, v)[None, :]
            wu = np.einsum('ijk,ik->ij', w, u)
            wv = np.einsum('ijk,jk->ij', w, v)
            cross = np.cross(u[:, None, :], v[None, :, :])
            determinant = np.einsum('ijk,ijk->ij', cross, cross)
            valid = determinant > 0
            s = np.divide(uv * wv - vb * wu, determinant, out=np.zeros_like(determinant), where=valid)
            t = np.divide(ua * wv - uv * wu, determinant, out=np.zeros_like(determinant), where=valid)
            inside = valid & (s >= 0) & (s <= 1) & (t >= 0) & (t <= 1)
            on_left = a0[:, None, :] + s[:, :, None] * u[:, None, :]
            on_right = b0[None, :, :] + t[:, :, None] * v[None, :, :]
            residual = w + s[:, :, None] * u[:, None, :] - t[:, :, None] * v[None, :, :]
            squared = np.where(inside, np.einsum('ijk,ijk->ij', residual, residual), np.inf)
            remember(on_left, on_right, squared)
    if witnesses is None or not math.isfinite(best):
        raise ValueError('No finite original-surface witness')
    # The strict distance stays in the common local origin. Recomputing it
    # after adding a large global origin loses low bits even though the
    # represented input geometry still determines the surface feature.
    distance = math.sqrt(max(0.0, best))
    if not math.isfinite(distance):
        raise ValueError('Nonfinite original-surface witness')
    world = [point + origin for point in witnesses]
    reported_distance = float(np.linalg.norm(world[0] - world[1]))
    if (not math.isfinite(reported_distance)
            or abs(reported_distance - distance) > COLLISION_TOLERANCE_M):
        raise ValueError('original_surface_witness_precision_exceeded')
    # The exported world coordinates must also remain on each original
    # surface within the unchanged 1e-9m bound. Never silently snap them.
    for point, original in zip(world, (original_a, original_b)):
        minimum = math.inf
        for face in range(0, len(original.faces), _CHUNK):
            triangles = original.vertices[original.faces[face:face + _CHUNK]]
            minimum = min(minimum, _point_triangle_min_sq(point[None, :], triangles))
        if not math.isfinite(minimum) or minimum > COLLISION_TOLERANCE_M ** 2:
            raise ValueError('original_surface_witness_precision_exceeded')
    return distance, world[0].tolist(), world[1].tolist()


def measure_pair_geometry(focal, reference, *, collision_tolerance_m=COLLISION_TOLERANCE_M,
                          need_clearance=False):
    """Return unknown as a dictionary; invalid options raise ValueError.

    ``signed_clearance_m`` is populated only when requested. It is unrounded
    engine geometry, not independent physical truth. For component unions its
    negative value is a certified separating translation, not a globally
    minimal penetration depth. The collision classification always uses the
    declared tolerance; display flush tolerances are never consulted.
    """
    if (isinstance(collision_tolerance_m, bool) or not isinstance(collision_tolerance_m, (int, float))
            or not math.isfinite(collision_tolerance_m) or not 0 <= collision_tolerance_m <= 1e-8):
        raise ValueError("collision_tolerance_m must be finite and within 0..1e-8 metres")
    if type(need_clearance) is not bool:
        raise ValueError("need_clearance must be a boolean")
    budget = work_budget_status([focal, reference])
    result = {"measurement_valid": False, "is_penetrating": None,
              "penetration_depth_m": None, "signed_clearance_m": None,
              "collision_tolerance_m": float(collision_tolerance_m),
              "measurement_method": "certified_convex_components_sat",
              "geometry_scope": SURFACE_SCOPE,
              "evaluator_source": "engine_geometry", "independent_ground_truth": False,
              "work_budget": budget}
    if not budget["within_budget"]:
        result["reason"] = "geometry_resource_limit"
        return result
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            paired = (_single_convex_collision_and_zero(focal, reference, collision_tolerance_m)
                      if need_clearance and collision_tolerance_m != 0 else None)
            measured = (paired[0] if paired is not None else
                        _certified_solid_collision(focal, reference, collision_tolerance_m))
        if measured is None:
            from .orthogonal_solid import certified_orthogonal_collision
            with np.errstate(over="raise", invalid="raise", divide="raise"):
                orthogonal = certified_orthogonal_collision(focal, reference, collision_tolerance_m)
            if orthogonal['supported'] is not True:
                result.update(reason='unsupported_solid_geometry', orthogonal_geometry=orthogonal)
                return result
            result.update({key: value for key, value in orthogonal.items() if key != 'supported'})
            result['measurement_valid'] = True
            if need_clearance:
                if orthogonal['is_penetrating']:
                    result['signed_clearance_m'] = -float(orthogonal['penetration_depth_m'])
                    result['clearance_method'] = 'certified_separating_translation_not_minimum_depth'
                    result.update(point_a_world=None, point_b_world=None,
                                  witness_scope='no_surface_witness_for_escape_metric')
                else:
                    with np.errstate(over='raise', invalid='raise', divide='raise'):
                        clearance, point_a, point_b = _surface_distance_with_witness(focal, reference)
                    result.update(signed_clearance_m=clearance, point_a_world=point_a, point_b_world=point_b,
                                  clearance_method='unrounded_all_original_surface_features',
                                  witness_scope='nearest_original_surface_points_not_internal_cell_boundaries')
            return result
        penetrating, depth, _, method = measured
        if not math.isfinite(depth) or depth < 0:
            raise ValueError("Nonfinite penetration metric")
        result.update(measurement_valid=True, is_penetrating=bool(penetrating),
                      penetration_depth_m=float(depth), measurement_method=method)
        if need_clearance:
            with np.errstate(over="raise", invalid="raise", divide="raise"):
                zero = (measured if collision_tolerance_m == 0 else paired[1]
                        if paired is not None else _certified_solid_collision(focal, reference, 0.0))
                if zero is None:
                    raise ValueError("Cannot certify zero-tolerance solid")
                clearance = -float(zero[1]) if zero[0] else _surface_distance(focal, reference)
            if not math.isfinite(clearance):
                raise ValueError("Nonfinite clearance")
            result["signed_clearance_m"] = clearance
            result["clearance_method"] = "unrounded_all_surface_features_or_certified_escape"
        return result
    except (ValueError, IndexError, TypeError, FloatingPointError, OverflowError) as exc:
        result.update(measurement_valid=False, is_penetrating=None, penetration_depth_m=None,
                      signed_clearance_m=None,
                      reason=('original_surface_witness_precision_exceeded'
                              if str(exc) == 'original_surface_witness_precision_exceeded'
                              else 'sat_projection_precision_unresolved'
                              if str(exc) == 'sat_projection_precision_unresolved'
                              else 'geometry_evaluation_failed'),
                      error_type=type(exc).__name__)
        return result


__all__ = ["COLLISION_TOLERANCE_M", "work_budget_status", "measure_pair_geometry", "solid_support_status"]
