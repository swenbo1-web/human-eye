"""Finite float64 point-to-closed-triangle distances and boundary attribution.

Inputs are already expressed in the caller's common normalized frame. Every
triangle participates. Exact zero-area triangles retain their three closed
segments, including zero-length segments. Nearest-vertex substitution is absent.
"""

import numpy as np


def _points(value, name):
    value = np.asarray(value, dtype=np.float64)
    if value.ndim != 2 or value.shape[1] != 3:
        raise ValueError(name + "_must_have_shape_N_by_3")
    return value


def _indices(value, width, vertex_count, name):
    value = np.asarray(value)
    if value.ndim != 2 or value.shape[1] != width or not np.issubdtype(value.dtype, np.integer):
        raise ValueError(name + "_must_be_integer_index_rows")
    if value.size and (np.min(value) < 0 or np.max(value) >= vertex_count):
        raise ValueError(name + "_index_out_of_bounds")
    return value.astype(np.int64, copy=False)


def _segment_block(points, first, second):
    """Return every point's nearest location on every closed segment."""
    edge = second - first
    length2 = np.einsum("ij,ij->i", edge, edge)
    offset = points[:, None, :] - first[None, :, :]
    numerator = np.einsum("qei,ei->qe", offset, edge)
    parameter = np.zeros_like(numerator)
    np.divide(numerator, length2[None, :], out=parameter, where=length2[None, :] > 0)
    np.clip(parameter, 0.0, 1.0, out=parameter)
    closest = first[None, :, :] + parameter[:, :, None] * edge[None, :, :]
    residual = points[:, None, :] - closest
    distance2 = np.einsum("qei,qei->qe", residual, residual)
    return distance2, closest, parameter


def _triangle_block(points, triangles):
    """Closest points on triangle interiors and all three closed edges."""
    first, second, third = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    distance2, closest, parameter = _segment_block(points, first, second)
    barycentric = np.zeros_like(closest)
    barycentric[:, :, 0] = 1.0 - parameter
    barycentric[:, :, 1] = parameter

    for start, end, first_weight, second_weight in (
        (second, third, 1, 2), (third, first, 2, 0)
    ):
        edge_distance2, edge_closest, edge_parameter = _segment_block(points, start, end)
        improved = edge_distance2 < distance2
        distance2[improved] = edge_distance2[improved]
        closest[improved] = edge_closest[improved]
        edge_barycentric = np.zeros_like(closest)
        edge_barycentric[:, :, first_weight] = 1.0 - edge_parameter
        edge_barycentric[:, :, second_weight] = edge_parameter
        barycentric[improved] = edge_barycentric[improved]

    normal = np.cross(second - first, third - first)
    normal2 = np.einsum("ij,ij->i", normal, normal)
    offset = points[:, None, :] - first[None, :, :]
    normal_offset = np.einsum("qti,ti->qt", offset, normal)
    projection_factor = np.zeros_like(normal_offset)
    np.divide(normal_offset, normal2[None, :], out=projection_factor, where=normal2[None, :] > 0)
    projected = points[:, None, :] - projection_factor[:, :, None] * normal[None, :, :]
    projected_offset = projected - first[None, :, :]
    second_numerator = np.einsum(
        "qti,ti->qt", np.cross(projected_offset, third[None, :, :] - first[None, :, :]), normal
    )
    third_numerator = np.einsum(
        "qti,ti->qt", np.cross(second[None, :, :] - first[None, :, :], projected_offset), normal
    )
    second_coordinate = np.zeros_like(normal_offset)
    third_coordinate = np.zeros_like(normal_offset)
    np.divide(second_numerator, normal2[None, :], out=second_coordinate, where=normal2[None, :] > 0)
    np.divide(third_numerator, normal2[None, :], out=third_coordinate, where=normal2[None, :] > 0)
    first_coordinate = 1.0 - second_coordinate - third_coordinate
    inside = ((normal2[None, :] > 0) & (first_coordinate >= 0.0)
              & (second_coordinate >= 0.0) & (third_coordinate >= 0.0))
    residual = points[:, None, :] - projected
    plane_distance2 = np.einsum("qti,qti->qt", residual, residual)
    improved = inside & (plane_distance2 < distance2)
    distance2[improved] = plane_distance2[improved]
    closest[improved] = projected[improved]
    plane_barycentric = np.stack((first_coordinate, second_coordinate, third_coordinate), axis=2)
    barycentric[improved] = plane_barycentric[improved]
    return distance2, closest, barycentric


def nearest_points(queries, vertices, triangles, query_block=32, triangle_block=256):
    """Find nearest closed-triangle locations with deterministic row-ID ties.

    Nonfinite surface vertices or an empty triangle domain produce an explicit
    unavailable status. Nonfinite query rows retain NaN outputs and a false
    valid mask. Numeric overflow also produces an unavailable row. Invalid
    indices and array shapes raise a caller-visible ValueError.
    """
    queries = _points(queries, "queries")
    vertices = _points(vertices, "vertices")
    triangles = _indices(triangles, 3, len(vertices), "triangles")
    if not 1 <= query_block <= 32 or not 1 <= triangle_block <= 256:
        raise ValueError("point_triangle_block_limit")
    count = len(queries)
    finite_queries = np.all(np.isfinite(queries), axis=1)
    nonfinite_vertices = int(np.count_nonzero(~np.all(np.isfinite(vertices), axis=1)))
    result = {
        "status": "available", "distance2": np.full(count, np.nan),
        "closest": np.full((count, 3), np.nan), "barycentric": np.full((count, 3), np.nan),
        "triangle_id": np.full(count, -1, dtype=np.int64), "valid": np.zeros(count, dtype=bool),
        "query_count": count, "triangle_count": len(triangles),
        "invalid_query_count": int(np.count_nonzero(~finite_queries)),
        "finite_query_count": int(np.count_nonzero(finite_queries)),
        "available_query_count": 0, "numeric_unavailable_query_count": 0,
        "nonfinite_surface_vertex_count": nonfinite_vertices,
        "numeric_nonfinite_triangle_count": 0,
        "degenerate_triangle_count": None, "zero_length_triangle_edge_count": None,
        "query_block": query_block, "triangle_block": triangle_block,
    }
    if nonfinite_vertices:
        result["status"] = "unavailable_nonfinite_surface_vertices"
        return result
    if not len(triangles):
        result["status"] = "unavailable_empty_triangle_domain"
        return result
    faces = vertices[triangles]
    with np.errstate(over="ignore", invalid="ignore"):
        first_edge = faces[:, 1] - faces[:, 0]
        second_edge = faces[:, 2] - faces[:, 0]
        normals = np.cross(first_edge, second_edge)
        normal2 = np.einsum("ij,ij->i", normals, normals)
    result["numeric_nonfinite_triangle_count"] = int(np.count_nonzero(~np.isfinite(normal2)))
    if result["numeric_nonfinite_triangle_count"]:
        result["status"] = "unavailable_nonfinite_surface_arithmetic"
        return result
    result["degenerate_triangle_count"] = int(np.count_nonzero(normal2 == 0.0))
    result["zero_length_triangle_edge_count"] = sum(
        int(np.count_nonzero(np.all(faces[:, end] == faces[:, start], axis=1)))
        for start, end in ((0, 1), (1, 2), (2, 0))
    )
    finite_ids = np.flatnonzero(finite_queries)
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        for query_start in range(0, len(finite_ids), query_block):
            ids = finite_ids[query_start:query_start + query_block]
            points = queries[ids]
            best_distance2 = np.full(len(ids), np.inf)
            best_closest = np.full((len(ids), 3), np.nan)
            best_barycentric = np.full((len(ids), 3), np.nan)
            best_triangle = np.full(len(ids), -1, dtype=np.int64)
            for triangle_start in range(0, len(faces), triangle_block):
                distance2, closest, barycentric = _triangle_block(
                    points, faces[triangle_start:triangle_start + triangle_block])
                distance2[~np.isfinite(distance2)] = np.inf
                local = np.argmin(distance2, axis=1)
                query_rows = np.arange(len(ids))
                selected_distance2 = distance2[query_rows, local]
                improved = selected_distance2 < best_distance2
                best_distance2[improved] = selected_distance2[improved]
                best_closest[improved] = closest[query_rows[improved], local[improved]]
                best_barycentric[improved] = barycentric[query_rows[improved], local[improved]]
                best_triangle[improved] = triangle_start + local[improved]
            valid = np.isfinite(best_distance2) & np.all(np.isfinite(best_closest), axis=1)
            selected_ids = ids[valid]
            result["distance2"][selected_ids] = best_distance2[valid]
            result["closest"][selected_ids] = best_closest[valid]
            result["barycentric"][selected_ids] = best_barycentric[valid]
            result["triangle_id"][selected_ids] = best_triangle[valid]
            result["valid"][selected_ids] = True
    result["available_query_count"] = int(np.count_nonzero(result["valid"]))
    result["numeric_unavailable_query_count"] = int(np.count_nonzero(finite_queries & ~result["valid"]))
    if not np.all(result["valid"]):
        result["status"] = "partial_unavailable_queries"
    return result


def context_boundary_edges(triangles):
    """Return index-sorted edges incident to one saved-context triangle."""
    triangles = np.asarray(triangles)
    if triangles.ndim != 2 or triangles.shape[1] != 3 or not np.issubdtype(triangles.dtype, np.integer):
        raise ValueError("triangles_must_be_integer_index_rows")
    if not len(triangles):
        return np.empty((0, 2), dtype=np.int64)
    edges = np.concatenate((triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]))
    edges.sort(axis=1)
    unique, counts = np.unique(edges, axis=0, return_counts=True)
    return unique[counts == 1].astype(np.int64, copy=False)


def classify_boundary_points(points, vertices, edges, length_tolerance=None, query_block=32, edge_block=256):
    """Attribute nearest locations to specified boundary segments.

    The default tolerance is a float64 length-roundoff classification only.
    Caller-supplied edges may be all domain-boundary edges or a documented
    cutting/natural-boundary subset. Triangle distances remain unmodified.
    """
    points = _points(points, "points")
    vertices = _points(vertices, "vertices")
    edges = _indices(edges, 2, len(vertices), "edges")
    if not 1 <= query_block <= 32 or not 1 <= edge_block <= 256:
        raise ValueError("point_edge_block_limit")
    finite_queries = np.all(np.isfinite(points), axis=1)
    finite_vertices = bool(np.isfinite(vertices).all())
    maximum_coordinate = float(np.max(np.abs(vertices))) if vertices.size and finite_vertices else 0.0
    if length_tolerance is None:
        length_tolerance = float(64 * np.finfo(np.float64).eps * max(1.0, maximum_coordinate))
    if not np.isfinite(length_tolerance) or length_tolerance < 0:
        raise ValueError("invalid_boundary_length_tolerance")
    result = {"status": "available", "on_boundary": np.zeros(len(points), dtype=bool),
              "distance2": np.full(len(points), np.nan), "edge_id": np.full(len(points), -1, dtype=np.int64),
              "closest": np.full((len(points), 3), np.nan), "valid": np.zeros(len(points), dtype=bool),
              "length_tolerance": length_tolerance, "edge_count": len(edges),
              "invalid_query_count": int(np.count_nonzero(~finite_queries))}
    if not finite_vertices:
        result["status"] = "unavailable_nonfinite_surface_vertices"
        return result
    if not len(edges):
        result["status"] = "empty_boundary"
        result["distance2"][finite_queries] = np.inf
        result["valid"][finite_queries] = True
        return result
    finite_ids = np.flatnonzero(finite_queries)
    for query_start in range(0, len(finite_ids), query_block):
        ids = finite_ids[query_start:query_start + query_block]
        best_distance2 = np.full(len(ids), np.inf)
        best_closest = np.full((len(ids), 3), np.nan)
        best_edge = np.full(len(ids), -1, dtype=np.int64)
        for edge_start in range(0, len(edges), edge_block):
            selected_edges = edges[edge_start:edge_start + edge_block]
            distance2, closest, _ = _segment_block(points[ids], vertices[selected_edges[:, 0]], vertices[selected_edges[:, 1]])
            local = np.argmin(distance2, axis=1)
            rows = np.arange(len(ids))
            selected_distance2 = distance2[rows, local]
            improved = selected_distance2 < best_distance2
            best_distance2[improved] = selected_distance2[improved]
            best_closest[improved] = closest[rows[improved], local[improved]]
            best_edge[improved] = edge_start + local[improved]
        valid = np.isfinite(best_distance2)
        result["distance2"][ids[valid]] = best_distance2[valid]
        result["closest"][ids[valid]] = best_closest[valid]
        result["edge_id"][ids[valid]] = best_edge[valid]
        result["valid"][ids[valid]] = True
        result["on_boundary"][ids[valid]] = best_distance2[valid] <= length_tolerance ** 2
    if not np.all(result["valid"]):
        result["status"] = "partial_unavailable_queries"
    return result
