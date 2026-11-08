"""Exact bounded cell certificates for a narrow closed-polyhedron subclass.

All original coordinates are binary rationals.  Triangle/rectangle clipping,
coverage, winding and reconstructed boundary equality use those rationals,
without snapping coordinates or sampling occupancy.  The accepted surface is
exactly the boundary of the occupied coordinate cells.  Arbitrarily inclined
faces, disconnected shells and resource limits remain unsupported.
"""
from __future__ import annotations

from fractions import Fraction
import itertools
import math

import numpy as np

from human_eye_module1_operators.submodule_1_4_spatial_sniffer import (
    _convex_shells, _convex_sat_parts,
)


PROOF_REVISION = "exact-orthogonal-cell-boundary-v1-20261024"
MAX_FACES = 256
MAX_PLANES_PER_AXIS = 16
MAX_GRID_CELLS = 512
MAX_CELL_BOXES = 64
MAX_FACE_CLIPS = 8192
MAX_OVERLAP_TESTS = 16384
MAX_RATIONAL_BITS = 256
MAX_PART_PAIRS = 4096
MAX_PAIR_PROJECTIONS = 2_000_000
MAX_ESCAPE_PAIR_TESTS = 6 * MAX_PART_PAIRS
MAX_ESCAPE_OUTWARD_STEPS = 8


def _fraction(value):
    value = Fraction(float(value))
    if max(abs(value.numerator).bit_length(), value.denominator.bit_length()) > MAX_RATIONAL_BITS:
        raise ValueError("orthogonal_coordinate_bit_limit")
    return value


def _area(poly):
    if len(poly) < 3:
        return Fraction(0)
    return abs(sum(a[0] * b[1] - a[1] * b[0]
                   for a, b in zip(poly, poly[1:] + poly[:1]))) / 2


def _clip_values(poly, evaluate):
    if not poly:
        return []
    result = []
    previous = poly[-1]
    before = evaluate(previous)
    for point in poly:
        after = evaluate(point)
        if (before >= 0) != (after >= 0):
            parameter = before / (before - after)
            crossing = tuple(previous[k] + parameter * (point[k] - previous[k]) for k in (0, 1))
            if not result or result[-1] != crossing:
                result.append(crossing)
        if after >= 0 and (not result or result[-1] != point):
            result.append(point)
        previous, before = point, after
    if len(result) > 1 and result[0] == result[-1]:
        result.pop()
    return result


def _clip_rectangle(poly, low_u, high_u, low_v, high_v):
    for evaluate in (lambda p: p[0] - low_u, lambda p: high_u - p[0],
                     lambda p: p[1] - low_v, lambda p: high_v - p[1]):
        poly = _clip_values(poly, evaluate)
    return poly


def _overlap_area(left, right):
    orientation = sum(a[0] * b[1] - a[1] * b[0]
                      for a, b in zip(right, right[1:] + right[:1]))
    if orientation == 0:
        return Fraction(0)
    sign = 1 if orientation > 0 else -1
    for start, end in zip(right, right[1:] + right[:1]):
        du, dv = end[0] - start[0], end[1] - start[1]
        left = _clip_values(left, lambda p: sign * (du * (p[1] - start[1]) - dv * (p[0] - start[0])))
        if not left:
            break
    return _area(left)


def _closed_manifold(faces, vertex_count):
    """Check directed edges and each vertex link, including pinched vertices."""
    edge_faces, links, used = {}, {}, set()
    for index, face in enumerate(faces):
        if len(set(face)) != 3:
            raise ValueError("orthogonal_degenerate_face")
        used.update(face)
        for a, b in zip(face, face[1:] + face[:1]):
            key = tuple(sorted((a, b)))
            edge_faces.setdefault(key, []).append((index, 1 if a < b else -1))
        for k, vertex in enumerate(face):
            a, b = face[(k + 1) % 3], face[(k + 2) % 3]
            links.setdefault(vertex, {}).setdefault(a, []).append(b)
            links[vertex].setdefault(b, []).append(a)
    if used != set(range(vertex_count)):
        raise ValueError("orthogonal_unused_or_missing_vertices")
    adjacency = [set() for _ in faces]
    for incident in edge_faces.values():
        if len(incident) != 2 or incident[0][1] + incident[1][1] != 0:
            raise ValueError("orthogonal_open_or_nonmanifold_or_winding")
        a, b = incident[0][0], incident[1][0]
        adjacency[a].add(b)
        adjacency[b].add(a)
    visited, pending = set(), [0]
    while pending:
        index = pending.pop()
        if index not in visited:
            visited.add(index)
            pending.extend(adjacency[index] - visited)
    if len(visited) != len(faces):
        raise ValueError("orthogonal_disconnected_shells_unsupported")
    for graph in links.values():
        if any(len(neighbors) != 2 for neighbors in graph.values()):
            raise ValueError("orthogonal_nonmanifold_vertex")
        reached, pending = set(), [next(iter(graph))]
        while pending:
            vertex = pending.pop()
            if vertex not in reached:
                reached.add(vertex)
                pending.extend(set(graph[vertex]) - reached)
        if len(reached) != len(graph):
            raise ValueError("orthogonal_pinched_vertex")


def _grid_boundary_manifold(boundary):
    vertices, faces = {}, []
    for (axis, plane, u, v), sign in boundary.items():
        axes = ((axis + 1) % 3, (axis + 2) % 3)
        corners = []
        for a, b in ((u, v), (u + 1, v), (u + 1, v + 1), (u, v + 1)):
            point = [0, 0, 0]
            point[axis], point[axes[0]], point[axes[1]] = plane, a, b
            point = tuple(point)
            if point not in vertices:
                vertices[point] = len(vertices)
            corners.append(vertices[point])
        if sign < 0:
            corners.reverse()
        a, b, c, d = corners
        faces.extend(((a, b, c), (a, c, d)))
    _closed_manifold([list(face) for face in faces], len(vertices))


def _merge_cells(occupied, coordinates):
    remaining = set(occupied)
    boxes = []
    while remaining:
        start = min(remaining)
        stop = list(start)
        for axis in range(3):
            while True:
                proposed = stop.copy()
                proposed[axis] += 1
                if proposed[axis] >= len(coordinates[axis]) - 1:
                    break
                layer = [range(start[k], proposed[k] + 1) if k != axis else (proposed[k],)
                         for k in range(3)]
                if not all(cell in remaining for cell in itertools.product(*layer)):
                    break
                stop = proposed
        cells = set(itertools.product(*(range(start[k], stop[k] + 1) for k in range(3))))
        if not cells <= remaining:
            raise ValueError("orthogonal_cell_merge_inconsistent")
        remaining.difference_update(cells)
        boxes.append((tuple(float(coordinates[k][start[k]]) for k in range(3)),
                      tuple(float(coordinates[k][stop[k] + 1]) for k in range(3))))
        if len(boxes) > MAX_CELL_BOXES:
            raise ValueError("orthogonal_cell_box_limit")
    return boxes


def decompose_orthogonal_solid(mesh):
    """Return detached exact cell proof and convex parts, or a typed unknown.

    ``parts`` is an internal value, never an observation/execution authority.
    New execution calls revalidate the complete current mesh.  A cavity with
    separate inner/outer shells is outside this first subclass; a connected
    through-hole is accepted when the exact boundary proof succeeds.
    """
    result = {"supported": False, "support_method": PROOF_REVISION}
    try:
        source = mesh.to_dict() if callable(getattr(mesh, "to_dict", None)) else mesh
        raw_vertices, raw_faces = np.asarray(source["vertices"]), np.asarray(source["faces"])
        if (raw_vertices.ndim != 2 or raw_vertices.shape[1:] != (3,)
                or raw_vertices.dtype.kind not in "ifu" or not np.isfinite(raw_vertices).all()
                or raw_faces.ndim != 2 or raw_faces.shape[1:] != (3,)
                or raw_faces.dtype.kind not in "iu" or len(raw_faces) < 4
                or np.min(raw_faces) < 0 or np.max(raw_faces) >= len(raw_vertices)):
            raise ValueError("orthogonal_invalid_input")
        if len(raw_faces) > MAX_FACES:
            raise ValueError("orthogonal_face_limit")
        # Every accepted vertex must occur in a face. Check this necessary
        # bound before creating any arbitrary-precision rational coordinates.
        if len(raw_vertices) > 3 * len(raw_faces):
            raise ValueError("orthogonal_unreferenced_vertex_work_limit")
        vertices = [tuple(_fraction(value) for value in point) for point in raw_vertices]
        if len(set(vertices)) != len(vertices):
            raise ValueError("orthogonal_coincident_vertices")
        faces = raw_faces.astype(np.int64).tolist()
        _closed_manifold(faces, len(vertices))
        coordinates = [sorted(set(point[axis] for point in vertices)) for axis in range(3)]
        dimensions = [len(values) - 1 for values in coordinates]
        if any(value < 1 or value + 1 > MAX_PLANES_PER_AXIS for value in dimensions):
            raise ValueError("orthogonal_coordinate_plane_limit")
        grid_cells = math.prod(dimensions)
        if grid_cells > MAX_GRID_CELLS:
            raise ValueError("orthogonal_grid_cell_limit")
        positions = [{value: index for index, value in enumerate(values)} for values in coordinates]
        face_data, volume6 = [], Fraction(0)
        origin = tuple(values[0] for values in coordinates)
        clip_count = 0
        for face in faces:
            points = [vertices[index] for index in face]
            constant = [axis for axis in range(3) if points[0][axis] == points[1][axis] == points[2][axis]]
            if len(constant) != 1:
                raise ValueError("orthogonal_inclined_or_degenerate_face")
            axis = constant[0]
            u, v = (axis + 1) % 3, (axis + 2) % 3
            triangle = [(point[u], point[v]) for point in points]
            determinant = ((triangle[1][0] - triangle[0][0]) * (triangle[2][1] - triangle[0][1])
                           - (triangle[1][1] - triangle[0][1]) * (triangle[2][0] - triangle[0][0]))
            if not determinant:
                raise ValueError("orthogonal_degenerate_face")
            volume6 += (points[0][axis] - origin[axis]) * determinant
            lower = [positions[k][min(point[k] for point in points)] for k in (u, v)]
            upper = [positions[k][max(point[k] for point in points)] for k in (u, v)]
            clip_count += (upper[0] - lower[0]) * (upper[1] - lower[1])
            if clip_count > MAX_FACE_CLIPS:
                raise ValueError("orthogonal_face_clip_limit")
            face_data.append((axis, positions[axis][points[0][axis]], triangle,
                              1 if determinant > 0 else -1, lower, upper))
        if not volume6:
            raise ValueError("orthogonal_zero_signed_volume")
        winding = 1 if volume6 > 0 else -1
        patches, overlap_tests = {}, 0
        for axis, plane, triangle, sign, lower, upper in face_data:
            u_axis, v_axis = (axis + 1) % 3, (axis + 2) % 3
            sign *= winding
            for u in range(lower[0], upper[0]):
                for v in range(lower[1], upper[1]):
                    clipped = _clip_rectangle(triangle, coordinates[u_axis][u], coordinates[u_axis][u + 1],
                                              coordinates[v_axis][v], coordinates[v_axis][v + 1])
                    area = _area(clipped)
                    if not area:
                        continue
                    key = (axis, plane, u, v)
                    prior = patches.setdefault(key, [])
                    for earlier_sign, earlier, _ in prior:
                        overlap_tests += 1
                        if overlap_tests > MAX_OVERLAP_TESTS:
                            raise ValueError("orthogonal_overlap_work_limit")
                        if earlier_sign != sign or _overlap_area(clipped, earlier):
                            raise ValueError("orthogonal_overlapping_or_opposed_facets")
                    prior.append((sign, clipped, area))
        boundary = {}
        for key, values in patches.items():
            axis, _, u, v = key
            u_axis, v_axis = (axis + 1) % 3, (axis + 2) % 3
            whole = ((coordinates[u_axis][u + 1] - coordinates[u_axis][u])
                     * (coordinates[v_axis][v + 1] - coordinates[v_axis][v]))
            if sum(value[2] for value in values) != whole:
                raise ValueError("orthogonal_partial_coordinate_cell_boundary")
            boundary[key] = values[0][0]
        occupied = set()
        for y in range(dimensions[1]):
            for z in range(dimensions[2]):
                inside = 0
                for x in range(dimensions[0] + 1):
                    inside -= boundary.get((0, x, y, z), 0)
                    if inside not in (0, 1):
                        raise ValueError("orthogonal_overlapping_or_inverted_occupancy")
                    if x < dimensions[0] and inside:
                        occupied.add((x, y, z))
                if inside:
                    raise ValueError("orthogonal_unclosed_occupancy")
        if not occupied:
            raise ValueError("orthogonal_empty_occupancy")
        reconstructed = {}
        for axis in range(3):
            u_axis, v_axis = (axis + 1) % 3, (axis + 2) % 3
            for plane in range(dimensions[axis] + 1):
                for u in range(dimensions[u_axis]):
                    for v in range(dimensions[v_axis]):
                        before, after = [0, 0, 0], [0, 0, 0]
                        before[axis], after[axis] = plane - 1, plane
                        before[u_axis] = after[u_axis] = u
                        before[v_axis] = after[v_axis] = v
                        sign = int(tuple(before) in occupied) - int(tuple(after) in occupied)
                        if sign:
                            reconstructed[(axis, plane, u, v)] = sign
        if reconstructed != boundary:
            raise ValueError("orthogonal_original_reconstructed_boundary_mismatch")
        _grid_boundary_manifold(reconstructed)
        boxes = _merge_cells(occupied, coordinates)
        parts = []
        for low, high in boxes:
            points = np.array(list(itertools.product(*zip(low, high))), dtype=np.float64)
            parts.append((points, np.eye(3), np.eye(3)))
        return {"supported": True, "support_method": PROOF_REVISION, "parts": tuple(parts),
                "component_count": 1, "convex_part_count": len(parts),
                "proof": {"scope": "exact_original_binary_coordinate_surface_boundary_equality",
                          "original_face_count": len(faces), "grid_cells": grid_cells,
                          "occupied_cells": len(occupied), "merged_boxes": len(parts),
                          "boundary_rectangles": len(boundary), "face_clips": clip_count,
                          "overlap_tests": overlap_tests, "coordinate_snapping": False,
                          "ray_sampling": False, "execution_authority": False}}
    except (ValueError, KeyError, AttributeError, TypeError, IndexError, OverflowError,
            FloatingPointError, ZeroDivisionError) as exc:
        return {**result, "reason": str(exc) if isinstance(exc, ValueError) else "orthogonal_evaluation_failed",
                "error_type": type(exc).__name__}


def _world_aabb_escape_candidate(focal, reference, axis, positive):
    """Certify a sufficient axis escape in exact and actual world arithmetic.

    A rounded subtraction can undershoot the exact represented endpoints.
    Check the original binary rational bounds as well as the actual exported
    float64 vertex addition; step outward only, with a fixed retry bound.
    """
    values = np.asarray(focal.vertices[:, axis], dtype=np.float64)
    endpoint = float(values.min() if positive else values.max())
    target = float(reference.vertices[:, axis].max() if positive else reference.vertices[:, axis].min())
    distance = target - endpoint
    direction = math.inf if positive else -math.inf
    for adjustment in range(MAX_ESCAPE_OUTWARD_STEPS + 1):
        if not math.isfinite(distance):
            return None
        delta = Fraction(distance)
        margin = ((Fraction(endpoint) + delta - Fraction(target)) if positive
                  else (Fraction(target) - Fraction(endpoint) - delta))
        # Nonfinite world additions are an uncertified candidate, never a
        # reason to trust the local projection or widen a collision tolerance.
        with np.errstate(over='ignore', invalid='ignore'):
            moved = values + distance
        if not np.isfinite(moved).all():
            return None
        actual_endpoint = float(moved.min() if positive else moved.max())
        actual_separated = actual_endpoint >= target if positive else actual_endpoint <= target
        if margin >= 0 and actual_separated:
            vector = np.zeros(3)
            vector[axis] = distance
            proof = {"scope": "original_binary_world_AABB_and_actual_world_vertex_addition",
                     "axis": axis, "direction": 1 if positive else -1,
                     "focal_endpoint_before_m": endpoint, "reference_endpoint_m": target,
                     "actual_world_endpoint_m": actual_endpoint,
                     "exact_binary_margin_numerator": str(margin.numerator),
                     "exact_binary_margin_denominator": str(margin.denominator),
                     "outward_nextafter_steps": adjustment,
                     "comparison_tolerance_m": 0.0}
            return vector, proof
        if adjustment == MAX_ESCAPE_OUTWARD_STEPS:
            return None
        distance = math.nextafter(distance, direction)
    return None


def certified_orthogonal_collision(focal, reference, tolerance):
    """Fresh narrow-subclass fallback, including convex/orthogonal mixed pairs.

    Internal cell seams use zero overlap tolerance.  Applying a positive
    per-cell tolerance could split a thin embedded object into individually
    tolerated pieces and incorrectly call the union clear.  This deliberately
    stricter policy cannot expand the caller's allowed collision tolerance.
    """
    groups, proofs, expanded = [], [], False
    for mesh in (focal, reference):
        shells = _convex_shells(mesh)
        if shells:
            groups.append(shells)
            proofs.append(None)
            continue
        proof = decompose_orthogonal_solid(mesh)
        if not proof["supported"]:
            return {"supported": False, "reason": proof.get("reason", "orthogonal_support_unknown"),
                    "support": {key: value for key, value in proof.items() if key != "parts"}}
        if proof['convex_part_count'] <= 1:
            return {"supported": False, "reason": "legacy_convex_rejection_not_overridden"}
        expanded = True
        groups.append(proof["parts"])
        proofs.append({key: value for key, value in proof.items() if key != "parts"})
    if not expanded:
        return {"supported": False, "reason": "orthogonal_fallback_not_applicable"}
    # Preserve the original represented geometry, but project both parties
    # relative to one shared original vertex. Large global dot products can
    # otherwise cancel a real separating interval. Legacy convex validation
    # remains unchanged; this normalization applies only to the new fallback.
    origin = np.asarray(focal.vertices[0], dtype=np.float64)
    fa, rb = [[(part[0] - origin, part[1], part[2]) for part in group] for group in groups]
    pairs = len(fa) * len(rb)
    projections = sum((len(a[0]) + len(b[0])) * (len(a[1]) + len(b[1]) + len(a[2]) * len(b[2]))
                      for a in fa for b in rb)
    budget = {"within_budget": pairs <= MAX_PART_PAIRS and projections <= MAX_PAIR_PROJECTIONS,
              "convex_part_counts": [len(fa), len(rb)], "part_pairs": pairs,
              "projection_elements": projections, "max_part_pairs": MAX_PART_PAIRS,
              "max_projection_elements": MAX_PAIR_PROJECTIONS,
              "max_escape_pair_tests": MAX_ESCAPE_PAIR_TESTS}
    if not budget["within_budget"]:
        return {"supported": False, "reason": "orthogonal_pair_work_limit", "decomposition_work_budget": budget}
    hits = [_convex_sat_parts(a, b, 0.0)[0] for a in fa for b in rb]
    detail = {"supported": True, "support": proofs, "decomposition_work_budget": budget,
              "classification_tolerance_m": 0.0, "requested_collision_tolerance_m": float(tolerance),
              "tolerance_policy": "strict_zero_overlap_for_exact_union_internal_seams",
              "projection_coordinate_frame": "shared_first_focal_vertex_origin",
              "projection_origin_world_m": origin.tolist()}
    if not any(hits):
        return {**detail, "is_penetrating": False, "penetration_depth_m": 0.0,
                "measurement_method": "exact_orthogonal_cell_union_sat"}
    budget['max_escape_outward_steps'] = MAX_ESCAPE_OUTWARD_STEPS
    candidates = []
    for axis in range(3):
        for positive in (True, False):
            candidate = _world_aabb_escape_candidate(focal, reference, axis, positive)
            if candidate is not None:
                candidates.append(candidate)
    checked = 0
    for vector, endpoint_proof in sorted(candidates, key=lambda item: abs(float(item[0][item[1]['axis']]))):
        clear = True
        for a in groups[0]:
            # Rebase the actual world addition, rather than translating only
            # the already rebased coordinates. The endpoint certificate above
            # independently proves separation of the original whole mesh.
            moved = ((a[0] + vector) - origin, a[1], a[2])
            for b in rb:
                checked += 1
                if checked > MAX_ESCAPE_PAIR_TESTS:
                    return {"supported": False, "reason": "orthogonal_escape_work_limit",
                            "decomposition_work_budget": budget}
                if _convex_sat_parts(moved, b, 0.0)[0]:
                    clear = False
                    break
            if not clear:
                break
        if clear:
            return {**detail, "is_penetrating": True,
                    "penetration_depth_m": abs(float(vector[endpoint_proof['axis']])),
                    "escape_vector_world_m": vector.tolist(), "escape_pair_tests": checked,
                    "escape_endpoint_proof": endpoint_proof,
                    "penetration_metric_scope": "certified_separating_translation_not_minimum_depth",
                    "measurement_method": "exact_orthogonal_cell_union_escape"}
    return {"supported": False, "reason": "orthogonal_escape_not_certified",
            "decomposition_work_budget": budget}
