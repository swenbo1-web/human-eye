"""Replay fresh native/evaluated source correspondence and region-to-Cube distance.

This module runs in ordinary CPython with NumPy.  It never imports bpy or product
geometry code.  Inputs are the owned process's real-asset-source-v1 JSON and the
fixed historical ARM_REGION.json.  Full ordered arrays remain in those inputs.
The report includes every selected vertex/triangle and every reference triangle.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import time

import numpy as np


SCHEMA = "real-asset-source-v1"
EXPECTED_COUNTS = {"vertices": 27304, "polygons": 29073, "triangles": 53264}
WORLD_TOLERANCE_M = 1e-7
DISTANCE_TOLERANCE_M = 1e-7


class OracleFailure(ValueError):
    """An input failed a specific independently checked source condition."""


def read_json(path):
    return json.loads(Path(path).read_bytes())


def file_identity(path):
    path = Path(path).resolve()
    payload = path.read_bytes()
    return {"path": str(path), "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest()}


def array_identity(values, dtype):
    array = np.ascontiguousarray(values, dtype=np.dtype(dtype))
    return {"shape": list(array.shape), "dtype": array.dtype.str,
            "encoding": "C-order little-endian raw bytes",
            "sha256": hashlib.sha256(array.tobytes()).hexdigest()}


def require(condition, message):
    if not condition:
        raise OracleFailure(message)


def points(values, label):
    array = np.asarray(values, dtype=np.float64)
    require(array.ndim == 2 and array.shape[1] == 3, f"{label} must have shape N by 3")
    require(np.isfinite(array).all(), f"{label} contains nonfinite coordinates")
    return array


def triangles(values, vertex_count, label):
    array = np.asarray(values, dtype=np.int64)
    require(array.ndim == 2 and array.shape[1] == 3, f"{label} must have shape N by 3")
    require((array >= 0).all() and (array < vertex_count).all(),
            f"{label} has out-of-range vertex indices")
    require(np.equal(np.asarray(values), array).all(), f"{label} has noninteger indices")
    return array


def maximum_error(left, right):
    if left.shape != right.shape:
        return None
    return float(np.max(np.abs(left - right), initial=0.0))


def world_coordinates(vertices, matrix, scale):
    # Blender matrices act on column vectors.  Arrays here store one point per row.
    return (vertices @ matrix[:3, :3].T + matrix[:3, 3]) * scale


def topology_keys(triangle_rows, polygon_rows):
    return [(int(polygon), *sorted(int(value) for value in row))
            for row, polygon in zip(triangle_rows, polygon_rows)]


def make_unique_index(keys, label):
    result = defaultdict(list)
    for row, key in enumerate(keys):
        result[key].append(row)
    ambiguous = [(key, rows) for key, rows in result.items() if len(rows) != 1]
    require(not ambiguous, f"{label} has ambiguous polygon/vertex triples, first {ambiguous[:1]}")
    return {key: rows[0] for key, rows in result.items()}


def mesh_arrays(obj, scale):
    matrix = np.asarray(obj["matrix_world"], dtype=np.float64)
    require(matrix.shape == (4, 4) and np.isfinite(matrix).all(),
            f"{obj['name']} matrix_world must be finite 4 by 4")
    require(np.array_equal(matrix[3], [0, 0, 0, 1]),
            f"{obj['name']} matrix_world has a nonaffine last row")
    result = {}
    for domain in ("native", "evaluated"):
        data = obj[domain]
        vertex_rows = points(data["vertices"], f"{obj['name']} {domain} vertices")
        triangle_rows = triangles(data["triangles"], len(vertex_rows),
                                  f"{obj['name']} {domain} triangles")
        polygon_rows = np.asarray(data["triangle_polygons"], dtype=np.int64)
        require(polygon_rows.shape == (len(triangle_rows),),
                f"{obj['name']} {domain} triangle_polygons length mismatch")
        require(np.equal(np.asarray(data["triangle_polygons"]), polygon_rows).all(),
                f"{obj['name']} {domain} has noninteger polygon indices")
        require((polygon_rows >= 0).all(), f"{obj['name']} {domain} has negative polygon indices")
        ideal_world = world_coordinates(vertex_rows, matrix, scale)
        world = points(data["vertices_world_m"], f"{obj['name']} {domain} world readback")
        require(world.shape == ideal_world.shape, f"{obj['name']} {domain} world readback count mismatch")
        world_error = maximum_error(world, ideal_world)
        require(world_error <= WORLD_TOLERANCE_M,
                f"{obj['name']} {domain} world readback/matrix disagreement {world_error}m")
        result[domain] = {"vertices": vertex_rows, "triangles": triangle_rows,
                          "triangle_polygons": polygon_rows, "world": world,
                          "ideal_world": ideal_world, "readback_matrix_max_error_m": world_error,
                          "keys": topology_keys(triangle_rows, polygon_rows)}
    polygons = obj["native"]["polygons"]
    polygon_sets = [set(row) for row in polygons]
    require(all(len(row) >= 3 for row in polygon_sets), f"{obj['name']} has a degenerate native polygon")
    for row, (triangle, polygon) in enumerate(zip(result["native"]["triangles"],
                                                result["native"]["triangle_polygons"])):
        require(polygon < len(polygon_sets) and set(triangle).issubset(polygon_sets[polygon]),
                f"{obj['name']} native triangle {row} disagrees with polygon {polygon}")
    result["matrix"] = matrix
    return result


def mesh_summary(obj, arrays):
    result = {"name": obj["name"], "instance_id": obj.get("instance_id"),
              "mesh_name": obj.get("mesh_name"), "matrix_world": obj["matrix_world"],
              "display": obj.get("display"), "modifiers": obj.get("modifiers"),
              "animation": obj.get("animation"), "arrays": {}}
    for domain in ("native", "evaluated"):
        data = arrays[domain]
        result["arrays"][domain] = {
            "vertices_local": array_identity(data["vertices"], "<f8"),
            "vertices_world_m": array_identity(data["world"], "<f8"),
            "vertices_float64_matrix_world_m": array_identity(data["ideal_world"], "<f8"),
            "readback_vs_float64_matrix_max_error_m": data["readback_matrix_max_error_m"],
            "triangles": array_identity(data["triangles"], "<i8"),
            "triangle_polygons": array_identity(data["triangle_polygons"], "<i8"),
            "world_bounds_m": [data["world"].min(axis=0).tolist(),
                               data["world"].max(axis=0).tolist()]}
    # Polygon rows have variable lengths.  Hash their canonical JSON, preserving order.
    payload = json.dumps(obj["native"]["polygons"], separators=(",", ":")).encode("utf8")
    result["native_polygons"] = {"count": len(obj["native"]["polygons"]),
                                  "encoding": "UTF-8 compact JSON, original row and vertex order",
                                  "sha256": hashlib.sha256(payload).hexdigest()}
    return result


def closest_on_segment(query, start, end):
    direction = end - start
    squared_length = np.einsum("ij,ij->i", direction, direction)
    numerator = np.einsum("ij,ij->i", query - start, direction)
    parameter = np.divide(numerator, squared_length, out=np.zeros_like(numerator),
                          where=squared_length > 0)
    parameter = np.clip(parameter, 0, 1)
    return start + parameter[:, None] * direction


def closest_on_triangle(query, triangle_rows):
    """Independent point/triangle candidates, including degenerate triangles."""
    a, b, c = triangle_rows[:, 0], triangle_rows[:, 1], triangle_rows[:, 2]
    ab, ac, aq = b - a, c - a, query - a
    aa = np.einsum("ij,ij->i", ab, ab)
    bb = np.einsum("ij,ij->i", ab, ac)
    cc = np.einsum("ij,ij->i", ac, ac)
    dd = np.einsum("ij,ij->i", aq, ab)
    ee = np.einsum("ij,ij->i", aq, ac)
    denominator = aa * cc - bb * bb
    u = np.divide(cc * dd - bb * ee, denominator, out=np.zeros_like(dd), where=denominator > 0)
    v = np.divide(aa * ee - bb * dd, denominator, out=np.zeros_like(ee), where=denominator > 0)
    inside = (denominator > 0) & (u >= 0) & (v >= 0) & (u + v <= 1)
    projection = a + u[:, None] * ab + v[:, None] * ac
    candidates = np.stack([closest_on_segment(query, a, b),
                           closest_on_segment(query, b, c),
                           closest_on_segment(query, c, a), projection], axis=1)
    squared = np.sum((candidates - query[:, None]) ** 2, axis=2)
    squared[~inside, 3] = np.inf
    chosen = np.argmin(squared, axis=1)
    return candidates[np.arange(len(query)), chosen]


def barycentric(point, tri):
    ab, ac, ap = tri[1] - tri[0], tri[2] - tri[0], point - tri[0]
    gram = np.array([[ab @ ab, ab @ ac], [ab @ ac, ac @ ac]])
    if float(np.linalg.det(gram)) == 0:
        return None
    u, v = np.linalg.solve(gram, [ap @ ab, ap @ ac])
    return [float(1 - u - v), float(u), float(v)]


def containing_triangles(point, vertices, triangle_rows, tolerance=DISTANCE_TOLERANCE_M):
    positions = vertices[triangle_rows]
    queries = np.repeat(np.asarray(point)[None], len(positions), axis=0)
    nearest = closest_on_triangle(queries, positions)
    errors = np.linalg.norm(nearest - queries, axis=1)
    return [{"triangle_row": int(row), "barycentric": barycentric(point, positions[row]),
             "point_residual_m": float(errors[row])}
            for row in np.flatnonzero(errors <= tolerance)]


def axis_aligned_box_proof(region_vertices, cube_vertices, cube_triangles):
    """Prove the supplied 12 triangles cover the six faces of one exact box."""
    lower, upper = cube_vertices.min(axis=0), cube_vertices.max(axis=0)
    if len(cube_vertices) != 8 or len(cube_triangles) != 12 or np.any(upper <= lower):
        return None
    # Exact equality avoids replacing a slightly rotated surface with its AABB.
    corner_bits = []
    for point in cube_vertices:
        if not np.all((point == lower) | (point == upper)):
            return None
        corner_bits.append(tuple(int(value) for value in (point == upper)))
    if len(set(corner_bits)) != 8:
        return None
    face_rows = []
    for axis in range(3):
        for side, bound in (("min", lower[axis]), ("max", upper[axis])):
            rows = [row for row, triangle in enumerate(cube_triangles)
                    if np.all(cube_vertices[triangle, axis] == bound)]
            if len(rows) != 2:
                return None
            edges = Counter()
            for row in rows:
                a, b, c = (int(value) for value in cube_triangles[row])
                edges.update(tuple(sorted(pair)) for pair in ((a, b), (b, c), (c, a)))
            boundary = [edge for edge, count in edges.items() if count == 1]
            diagonal = [edge for edge, count in edges.items() if count == 2]
            if len(boundary) != 4 or len(diagonal) != 1:
                return None
            if any(sum(a != b for a, b in zip(corner_bits[i], corner_bits[j])) != 1
                   for i, j in boundary):
                return None
            if sum(a != b for a, b in zip(corner_bits[diagonal[0][0]],
                                          corner_bits[diagonal[0][1]])) != 2:
                return None
            face_rows.append({"axis": axis, "side": side, "bound_m": float(bound),
                              "triangle_rows": rows, "boundary_edges": boundary,
                              "shared_diagonal": diagonal[0]})
    if sorted(row for face in face_rows for row in face["triangle_rows"]) != list(range(12)):
        return None
    region_lower, region_upper = region_vertices.min(axis=0), region_vertices.max(axis=0)
    if np.any(region_lower < lower) or np.any(region_upper > upper):
        return None
    clearances = []
    for face in face_rows:
        axis, side = face["axis"], face["side"]
        local = int(np.argmin(region_vertices[:, axis]) if side == "min"
                    else np.argmax(region_vertices[:, axis]))
        source_point = region_vertices[local].copy()
        reference_point = source_point.copy()
        reference_point[axis] = face["bound_m"]
        clearances.append({"axis": axis, "side": side,
                           "clearance_m": float(abs(reference_point[axis] - source_point[axis])),
                           "region_vertex_ordinal": local,
                           "source_point_m": source_point.tolist(),
                           "reference_point_m": reference_point.tolist()})
    witness = min(clearances, key=lambda row: row["clearance_m"])
    return {"method": "axis_aligned_closed_box_convex_combination_bound",
            "distance_m": witness["clearance_m"],
            "source_point_m": witness["source_point_m"],
            "reference_point_m": witness["reference_point_m"],
            "source_region_vertex_ordinal": witness["region_vertex_ordinal"],
            "certificate": {
                "exact_axis_aligned_corner_coordinates": True,
                "cube_bounds_m": [lower.tolist(), upper.tolist()],
                "region_bounds_m": [region_lower.tolist(), region_upper.tolist()],
                "all_region_vertices_inside_closed_box": True,
                "reference_face_coverage": face_rows,
                "six_face_lower_bounds_with_attaining_vertices": clearances,
                "lower_bound_m": witness["clearance_m"],
                "attained_upper_bound_m": witness["clearance_m"],
                "reason": "Every source-triangle point is a convex combination of its three selected vertices. "
                          "Each of its six signed face clearances is at least the corresponding vertex minimum. "
                          "Distance to every boundary point is at least the least of those six clearances. "
                          "The recorded source vertex and its orthogonal projection onto a covered box face "
                          "attain that bound."}}


def exhaustive_triangle_distance(source_vertices, source_triangles, reference_vertices, reference_triangles):
    """Independent all-pairs vertex/face, edge/edge and segment/face candidates."""
    source_ids = np.repeat(np.arange(len(source_triangles)), len(reference_triangles))
    reference_ids = np.tile(np.arange(len(reference_triangles)), len(source_triangles))
    a = source_vertices[source_triangles[source_ids]]
    b = reference_vertices[reference_triangles[reference_ids]]
    best = {"squared": np.inf}

    def consider(left, right, method, valid=None):
        squared = np.sum((left - right) ** 2, axis=1)
        if valid is not None:
            squared = np.where(valid, squared, np.inf)
        index = int(np.argmin(squared))
        if squared[index] < best["squared"]:
            best.update(squared=float(squared[index]), source_point=left[index].tolist(),
                        reference_point=right[index].tolist(), source_row=int(source_ids[index]),
                        reference_row=int(reference_ids[index]), feature=method)

    for vertex in range(3):
        consider(a[:, vertex], closest_on_triangle(a[:, vertex], b), "source_vertex_reference_face")
        consider(closest_on_triangle(b[:, vertex], a), b[:, vertex], "reference_vertex_source_face")
    for source_edge in range(3):
        p, q = a[:, source_edge], a[:, (source_edge + 1) % 3]
        u = q - p
        for reference_edge in range(3):
            r, s = b[:, reference_edge], b[:, (reference_edge + 1) % 3]
            v, w = s - r, p - r
            consider(p, closest_on_segment(p, r, s), "edge_endpoint_projection")
            consider(q, closest_on_segment(q, r, s), "edge_endpoint_projection")
            consider(closest_on_segment(r, p, q), r, "edge_endpoint_projection")
            consider(closest_on_segment(s, p, q), s, "edge_endpoint_projection")
            aa = np.einsum("ij,ij->i", u, u)
            bb = np.einsum("ij,ij->i", u, v)
            cc = np.einsum("ij,ij->i", v, v)
            dd = np.einsum("ij,ij->i", u, w)
            ee = np.einsum("ij,ij->i", v, w)
            denominator = aa * cc - bb * bb
            st = np.divide(bb * ee - cc * dd, denominator,
                           out=np.zeros_like(dd), where=denominator > 0)
            tt = np.divide(aa * ee - bb * dd, denominator,
                           out=np.zeros_like(ee), where=denominator > 0)
            valid = (denominator > 0) & (st >= 0) & (st <= 1) & (tt >= 0) & (tt <= 1)
            consider(p + st[:, None] * u, r + tt[:, None] * v, "interior_edge_edge", valid)
    for reverse in (False, True):
        segments, faces = (b, a) if reverse else (a, b)
        edge1, edge2 = faces[:, 1] - faces[:, 0], faces[:, 2] - faces[:, 0]
        for edge in range(3):
            start = segments[:, edge]
            direction = segments[:, (edge + 1) % 3] - start
            h = np.cross(direction, edge2)
            determinant = np.einsum("ij,ij->i", edge1, h)
            valid_determinant = np.abs(determinant) > 0
            inverse = np.divide(1.0, determinant, out=np.zeros_like(determinant),
                                where=valid_determinant)
            relative = start - faces[:, 0]
            u = inverse * np.einsum("ij,ij->i", relative, h)
            cross = np.cross(relative, edge1)
            v = inverse * np.einsum("ij,ij->i", direction, cross)
            t = inverse * np.einsum("ij,ij->i", edge2, cross)
            valid = valid_determinant & (u >= 0) & (v >= 0) & (u + v <= 1) & (t >= 0) & (t <= 1)
            intersection = start + t[:, None] * direction
            consider(intersection, intersection, "segment_face_intersection", valid)
    return {"method": "independent_exhaustive_triangle_features",
            "distance_m": float(np.sqrt(best["squared"])),
            "source_point_m": best["source_point"], "reference_point_m": best["reference_point"],
            "candidate_source_region_triangle_ordinal": best["source_row"],
            "candidate_reference_triangle_row": best["reference_row"],
            "certificate": {"triangle_pair_count": len(source_ids), "winning_feature": best["feature"],
                            "vertex_face_candidates": 6 * len(source_ids),
                            "edge_edge_pairs": 9 * len(source_ids),
                            "segment_face_tests": 6 * len(source_ids),
                            "arithmetic": "IEEE-754 float64 exhaustive feature computation",
                            "comparison_tolerance_m": DISTANCE_TOLERANCE_M}}


def source_correspondence(snapshot, region, raw, saved_evaluated, target, target_arrays):
    native, evaluated = target_arrays["native"], target_arrays["evaluated"]
    source_vertex_ids = np.asarray(region["source_vertex_ids"], dtype=np.int64)
    source_triangle_ids = np.asarray(region["source_triangle_ids"], dtype=np.int64)
    require(len(source_vertex_ids) == len(set(source_vertex_ids)) == 410, "fixed region must contain 410 distinct vertices")
    require(len(source_triangle_ids) == len(set(source_triangle_ids)) == 748, "fixed region must contain 748 distinct triangles")
    require(target["name"] == raw["object_name"] == saved_evaluated["object_name"], "target name differs from saved source")
    require(target.get("mesh_name") == region["mesh_name"] == raw["mesh_name"], "target mesh name differs from fixed source")
    for field in ("vertices_object", "triangles", "polygon_ids_by_triangle"):
        require(raw[field] == saved_evaluated[field], f"saved native/evaluated {field} differs")
    saved_vertices = points(raw["vertices_object"], "saved native vertices")
    saved_triangles = triangles(raw["triangles"], len(saved_vertices), "saved native triangles")
    saved_polygons = np.asarray(raw["polygon_ids_by_triangle"], dtype=np.int64)
    require(native["vertices"].shape == saved_vertices.shape, "fresh native vertex count differs from saved source")
    native_error = maximum_error(native["vertices"], saved_vertices)
    differing = np.argwhere(native["vertices"] != saved_vertices)
    require(not len(differing), f"fresh native local coordinates differ, max {native_error}, first coordinate {differing[:1].tolist()}")
    require(np.array_equal(native["vertices"], evaluated["vertices"]),
            f"fresh evaluated vertex array differs from native, max error {maximum_error(native['vertices'], evaluated['vertices'])}")
    historical_keys = topology_keys(saved_triangles, saved_polygons)
    require(Counter(native["keys"]) == Counter(historical_keys), "fresh native triangle/polygon topology differs from saved source")
    require(Counter(evaluated["keys"]) == Counter(historical_keys), "fresh evaluated triangle/polygon topology differs from saved source")
    native_index = make_unique_index(native["keys"], "fresh native")
    evaluated_index = make_unique_index(evaluated["keys"], "fresh evaluated")
    require(len(native["vertices"]) == EXPECTED_COUNTS["vertices"], "unexpected target vertex count")
    require(len(target["native"]["polygons"]) == EXPECTED_COUNTS["polygons"], "unexpected target polygon count")
    require(len(native["triangles"]) == EXPECTED_COUNTS["triangles"], "unexpected target triangle count")
    require(np.array_equal(region["vertices_object"], saved_vertices[source_vertex_ids]), "ARM_REGION local point correspondence differs")
    require(np.array_equal(region["vertices_world"], np.asarray(raw["vertices_world"])[source_vertex_ids]),
            "ARM_REGION saved world point correspondence differs")
    historical_region_triangles = source_vertex_ids[np.asarray(region["triangles_local"], dtype=np.int64)]
    require(np.array_equal(historical_region_triangles, saved_triangles[source_triangle_ids]),
            "ARM_REGION historical source triangle rows differ")
    require(np.array_equal(region["source_polygon_ids"], saved_polygons[source_triangle_ids]),
            "ARM_REGION historical source polygon rows differ")
    require(set(historical_region_triangles.ravel()) == set(source_vertex_ids),
            "fixed region point membership differs from its full triangle membership")
    mapping = []
    for ordinal, historical_row in enumerate(source_triangle_ids):
        key = historical_keys[int(historical_row)]
        native_row, evaluated_row = native_index[key], evaluated_index[key]
        historical_vertices = historical_region_triangles[ordinal].tolist()
        native_vertices = native["triangles"][native_row].tolist()
        evaluated_vertices = evaluated["triangles"][evaluated_row].tolist()
        mapping.append({"region_triangle_ordinal": ordinal,
                        "historical_source_triangle_row": int(historical_row),
                        "native_triangle_row": native_row, "evaluated_triangle_row": evaluated_row,
                        "native_polygon_index": int(native["triangle_polygons"][native_row]),
                        "evaluated_polygon_index": int(evaluated["triangle_polygons"][evaluated_row]),
                        "historical_vertex_ids": historical_vertices,
                        "native_vertex_ids": native_vertices, "evaluated_vertex_ids": evaluated_vertices,
                        "native_positions_in_historical_triple": [historical_vertices.index(v) for v in native_vertices],
                        "evaluated_positions_in_historical_triple": [historical_vertices.index(v) for v in evaluated_vertices]})
    vertex_mapping = []
    for ordinal, vertex_id in enumerate(source_vertex_ids):
        vertex_id = int(vertex_id)
        vertex_mapping.append({"region_vertex_ordinal": ordinal,
                               "historical_native_vertex_id": vertex_id,
                               "fresh_native_vertex_id": vertex_id, "fresh_evaluated_vertex_id": vertex_id,
                               "historical_local": region["vertices_object"][ordinal],
                               "historical_world_m": region["vertices_world"][ordinal],
                               "native_local": native["vertices"][vertex_id].tolist(),
                               "evaluated_local": evaluated["vertices"][vertex_id].tolist(),
                               "native_world_m": native["world"][vertex_id].tolist(),
                               "evaluated_world_m": evaluated["world"][vertex_id].tolist()})
    old_matrix = np.asarray(region["matrix_world"], dtype=np.float64)
    old_calculated_world = world_coordinates(saved_vertices[source_vertex_ids], old_matrix, 1.0)
    old_saved_world = np.asarray(region["vertices_world"], dtype=np.float64)
    saved_world_roundoff = maximum_error(old_calculated_world, old_saved_world)
    require(saved_world_roundoff <= WORLD_TOLERANCE_M, "historical saved world points disagree with matrix beyond tolerance")
    matrix_delta = target_arrays["matrix"] - old_matrix
    expected_delta = np.zeros((4, 4))
    if snapshot["state"] == "moved":
        expected_delta[0, 3] = 0.25 / float(snapshot["unit_scale"])
    recognized_state = snapshot["state"] in ("initial", "moved", "restored")
    if recognized_state:
        require(np.max(np.abs(matrix_delta - expected_delta)) <= 1e-12,
                f"{snapshot['state']} matrix differs from prescribed historical/+0.25m-X state")
    return {"status": "passed", "full_native_vertices_equal_saved_local": True,
            "full_native_evaluated_vertices_equal_local": True,
            "full_native_and_evaluated_triangle_polygon_multisets_equal_saved": True,
            "full_native_triangle_rows_equal_saved": np.array_equal(native["triangles"], saved_triangles),
            "full_evaluated_triangle_rows_equal_saved": np.array_equal(evaluated["triangles"], saved_triangles),
            "full_native_vertex_max_coordinate_error_local": native_error,
            "historical_float32_world_vs_float64_matrix_max_error_m": saved_world_roundoff,
            "world_coordinate_tolerance_m": WORLD_TOLERANCE_M,
            "historical_matrix_world": region["matrix_world"],
            "fresh_minus_historical_matrix_world": matrix_delta.tolist(),
            "prescribed_state_matrix_checked": recognized_state,
            "region_semantics": region.get("selection"),
            "region_triangle_count": len(mapping), "region_vertex_count": len(vertex_mapping),
            "triangle_mapping": mapping, "vertex_mapping": vertex_mapping}


def analyze(snapshot_path, arm_region_path, output_path, *, raw_path=None, evaluated_path=None):
    """Write and return a replayable report, including a failed report on invalid input.

    Optional baseline paths support relocating the saved M6 evidence.  By default
    capture_02/raw_selected.json and evaluated_selected.json are resolved beside
    the fixed ARM_REGION.json.  Only output_path is written.
    """
    started = time.perf_counter()
    output_path = Path(output_path)
    region_path = Path(arm_region_path)
    raw_path = Path(raw_path) if raw_path else region_path.parent / "capture_02/raw_selected.json"
    evaluated_path = Path(evaluated_path) if evaluated_path else region_path.parent / "capture_02/evaluated_selected.json"
    if not raw_path.exists():
        raw_path = region_path.parent / "raw_selected.json"
    if not evaluated_path.exists():
        evaluated_path = region_path.parent / "evaluated_selected.json"
    report = {"schema": "real-asset-source-distance-oracle-v1", "status": "failed",
              "implementation": file_identity(__file__), "numpy_version": np.__version__,
              "production_geometry_imports": 0, "blender_processes_started": 0,
              "arithmetic": "NumPy IEEE-754 float64 over host vertices_world_m readback; "
                            "independent ideal world = (matrix_world @ local_homogeneous)[:3] * unit_scale",
              "comparison_tolerance_m": DISTANCE_TOLERANCE_M}
    try:
        report["inputs"] = {"snapshot": file_identity(snapshot_path),
                            "arm_region": file_identity(region_path), "historical_raw": file_identity(raw_path),
                            "historical_evaluated": file_identity(evaluated_path)}
        snapshot, region = read_json(snapshot_path), read_json(region_path)
        raw, saved_evaluated = read_json(raw_path), read_json(evaluated_path)
        report.update(state=snapshot.get("state"), process_id=snapshot.get("process_id"),
                      frame=snapshot.get("frame"), subframe=snapshot.get("subframe"),
                      source_sha256=snapshot.get("source_sha256"))
        require(snapshot.get("schema") == SCHEMA, f"snapshot schema must be {SCHEMA}")
        require(snapshot["source_sha256"] == region["source_sha256"], "fresh input and fixed region asset SHA differ")
        scale = float(snapshot["unit_scale"])
        require(np.isfinite(scale) and scale > 0, "unit_scale must be finite and positive")
        require(scale == float(snapshot["unit_settings"]["scale_length"]), "unit_scale differs from scale_length")
        require(region["unit"] == "m", "historical region unit must be m")
        report["units"] = {"unit_scale": scale, "unit_settings": snapshot["unit_settings"],
                           "output_unit": "m", "source_local_coordinates": "Blender units"}
        targets = [obj for obj in snapshot["objects"] if obj["name"] == region["object_name"]]
        references = [obj for obj in snapshot["objects"] if obj["name"] == "Cube"]
        require(len(targets) == len(references) == 1, "snapshot must contain exactly one target and one Cube")
        target, reference = targets[0], references[0]
        target_arrays, reference_arrays = mesh_arrays(target, scale), mesh_arrays(reference, scale)
        report["target"] = mesh_summary(target, target_arrays)
        report["reference"] = mesh_summary(reference, reference_arrays)
        report["source_correspondence"] = source_correspondence(
            snapshot, region, raw, saved_evaluated, target, target_arrays)
        require(target.get("modifiers") == [], "fixed source target has fresh modifiers")
        native_ref, evaluated_ref = reference_arrays["native"], reference_arrays["evaluated"]
        require(len(native_ref["vertices"]) == 8 and len(reference["native"]["polygons"]) == 6,
                "fresh Cube must contain 8 native vertices and 6 polygons")
        require(len(native_ref["triangles"]) == len(evaluated_ref["triangles"]) == 12,
                "fresh Cube must contain 12 native/evaluated triangles")
        require(np.array_equal(native_ref["vertices"], evaluated_ref["vertices"]),
                "fresh Cube native/evaluated local vertices differ")
        require(Counter(native_ref["keys"]) == Counter(evaluated_ref["keys"]),
                "fresh Cube native/evaluated topology differs")
        reference_native_index = make_unique_index(native_ref["keys"], "Cube native")
        report["reference"]["triangle_mapping"] = [
            {"evaluated_triangle_row": row, "native_triangle_row": reference_native_index[key],
             "native_polygon_index": int(evaluated_ref["triangle_polygons"][row]),
             "evaluated_vertex_ids": evaluated_ref["triangles"][row].tolist(),
             "evaluated_vertices_world_m": evaluated_ref["world"][evaluated_ref["triangles"][row]].tolist()}
            for row, key in enumerate(evaluated_ref["keys"])]
        vertex_ids = np.asarray(region["source_vertex_ids"], dtype=np.int64)
        region_vertices = target_arrays["evaluated"]["world"][vertex_ids]
        region_triangles = np.asarray(region["triangles_local"], dtype=np.int64)
        distance = axis_aligned_box_proof(region_vertices, evaluated_ref["world"], evaluated_ref["triangles"])
        if distance is None:
            distance = exhaustive_triangle_distance(region_vertices, region_triangles,
                                                     evaluated_ref["world"], evaluated_ref["triangles"])
        source_point = np.asarray(distance["source_point_m"])
        reference_point = np.asarray(distance["reference_point_m"])
        vector = reference_point - source_point
        norm = float(np.linalg.norm(vector))
        distance["source_to_reference_vector_m"] = vector.tolist()
        distance["source_to_reference_unit_direction"] = (vector / norm).tolist() if norm else None
        source_members = containing_triangles(source_point, region_vertices, region_triangles)
        source_mapping = report["source_correspondence"]["triangle_mapping"]
        for member in source_members:
            ordinal = member.pop("triangle_row")
            member.update(source_mapping[ordinal])
        reference_members = containing_triangles(reference_point, evaluated_ref["world"], evaluated_ref["triangles"])
        for member in reference_members:
            member["native_polygon_index"] = int(evaluated_ref["triangle_polygons"][member["triangle_row"]])
        require(source_members and reference_members, "oracle nearest-point witness failed triangle membership")
        require(abs(norm - distance["distance_m"]) <= DISTANCE_TOLERANCE_M, "oracle witness distance mismatch")
        distance["source_memberships"] = source_members
        distance["reference_memberships"] = reference_members
        report["distance_oracle"] = distance
        ideal_distance = axis_aligned_box_proof(target_arrays["evaluated"]["ideal_world"][vertex_ids],
                                                evaluated_ref["ideal_world"], evaluated_ref["triangles"])
        if ideal_distance is None:
            ideal_distance = exhaustive_triangle_distance(
                target_arrays["evaluated"]["ideal_world"][vertex_ids], region_triangles,
                evaluated_ref["ideal_world"], evaluated_ref["triangles"])
        report["float64_matrix_distance_comparison"] = {
            "method": ideal_distance["method"], "distance_m": ideal_distance["distance_m"],
            "readback_minus_float64_matrix_distance_m": distance["distance_m"] - ideal_distance["distance_m"],
            "source_point_m": ideal_distance["source_point_m"],
            "reference_point_m": ideal_distance["reference_point_m"]}
        current_rows = [row["evaluated_triangle_row"] for row in source_mapping]
        report["request_region_selection"] = {"object": target["name"], "source_triangle_ids": current_rows}
        report["ordered_region_arrays"] = {
            "historical_row_order_current_evaluated_rows": array_identity(current_rows, "<i8"),
            "source_vertex_ids": array_identity(vertex_ids, "<i8"),
            "world_vertices_m": array_identity(region_vertices, "<f8"),
            "triangles_in_region_vertex_ordinals": array_identity(region_triangles, "<i8")}
        report["status"] = "passed"
    except (OracleFailure, KeyError, IndexError, TypeError, ValueError, OSError) as error:
        report["failure"] = {"type": type(error).__name__, "reason": str(error)}
    report["elapsed_seconds"] = time.perf_counter() - started
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot_path")
    parser.add_argument("arm_region_path")
    parser.add_argument("output_path")
    parser.add_argument("--raw-path")
    parser.add_argument("--evaluated-path")
    args = parser.parse_args()
    result = analyze(args.snapshot_path, args.arm_region_path, args.output_path,
                     raw_path=args.raw_path, evaluated_path=args.evaluated_path)
    print(json.dumps({"status": result["status"], "state": result.get("state"),
                      "distance_m": result.get("distance_oracle", {}).get("distance_m"),
                      "failure": result.get("failure"), "elapsed_seconds": result["elapsed_seconds"]}))
    raise SystemExit(0 if result["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
