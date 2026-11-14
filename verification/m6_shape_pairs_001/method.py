"""One anomaly-weighted, fixed-boundary discrete biharmonic reconstruction."""
import time

import numpy as np


def reconstruct(abnormal_vertices, triangles, allowed_region_ids):
    """The method receives observed geometry, topology and the uniform region only."""
    started = time.perf_counter()
    vertices = np.asarray(abnormal_vertices, dtype=np.float64)
    faces = np.asarray(triangles, dtype=np.int64)
    region = set(allowed_region_ids)
    inside = faces[np.all(np.isin(faces, list(region)), axis=1)]
    region_edges = {}
    adjacency = [set() for _ in vertices]
    for face in faces:
        for a, b in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            adjacency[a].add(int(b))
            adjacency[b].add(int(a))
    for face in inside:
        for a, b in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            edge = tuple(sorted((int(a), int(b))))
            region_edges[edge] = region_edges.get(edge, 0) + 1
    if any(count > 2 for count in region_edges.values()):
        raise ValueError("nonmanifold_allowed_region")
    boundary = {index for edge, count in region_edges.items() if count == 1 for index in edge}
    free = sorted(region - boundary)
    rows = sorted(set(free) | {neighbor for index in free for neighbor in adjacency[index]})
    columns = sorted(set(rows) | {neighbor for index in rows for neighbor in adjacency[index]})
    row_map = {index: ordinal for ordinal, index in enumerate(rows)}
    column_map = {index: ordinal for ordinal, index in enumerate(columns)}
    incident = faces[np.any(np.isin(faces, rows), axis=1)]
    stiffness = np.zeros((len(rows), len(columns)))
    mass = np.zeros(len(rows))
    negative_cotangents = 0
    assembly_start = time.perf_counter()
    for face in incident:
        points = vertices[face]
        doubled_area = float(np.linalg.norm(np.cross(points[1] - points[0], points[2] - points[0])))
        if doubled_area == 0 or not np.isfinite(doubled_area):
            raise ValueError("degenerate_incident_triangle")
        for local, index in enumerate(face):
            if int(index) in row_map:
                mass[row_map[int(index)]] += doubled_area / 6
            first, second = (local + 1) % 3, (local + 2) % 3
            cotangent = float(np.dot(points[first] - points[local], points[second] - points[local]) / doubled_area)
            negative_cotangents += cotangent < 0
            weight = cotangent / 2
            a, b = int(face[first]), int(face[second])
            for row_id, other_id in ((a, b), (b, a)):
                if row_id in row_map:
                    row = row_map[row_id]
                    stiffness[row, column_map[row_id]] += weight
                    stiffness[row, column_map[other_id]] -= weight
    if np.any(mass <= 0) or not np.isfinite(stiffness).all():
        raise ValueError("invalid_mass_or_stiffness")
    weighted = stiffness / np.sqrt(mass[:, None])
    free_columns = [column_map[index] for index in free]
    fixed = [index for index in columns if index not in set(free)]
    fixed_columns = [column_map[index] for index in fixed]
    left = weighted[:, free_columns]
    right = -weighted[:, fixed_columns] @ vertices[fixed]
    assembly_wall = time.perf_counter() - assembly_start
    solve_start = time.perf_counter()
    solution, _, rank, singular = np.linalg.lstsq(left, right, rcond=None)
    solve_wall = time.perf_counter() - solve_start
    if rank != len(free) or not np.isfinite(solution).all():
        raise ValueError("biharmonic_free_system_rank_or_numeric_failure")
    output = vertices.copy()
    output[free] = solution
    residual = left @ solution - right
    normal_residual = left.T @ residual
    denominator = max(float(np.linalg.norm(left.T @ right)), np.finfo(float).tiny)
    diagnostics = {"method": "cotangent_stiffness_lumped_mass_squared_laplacian_positions",
                   "free_vertices": len(free), "boundary_vertices": len(boundary), "energy_rows": len(rows),
                   "context_columns": len(columns), "fixed_columns": len(fixed), "incident_assembly_faces": len(incident),
                   "matrix_shape": list(left.shape), "matrix_bytes": left.nbytes + weighted.nbytes + stiffness.nbytes,
                   "rank": int(rank), "singular_min": float(singular[-1]), "singular_max": float(singular[0]),
                   "condition_number": float(singular[0] / singular[-1]),
                   "energy_residual_frobenius": float(np.linalg.norm(residual)),
                   "normal_equation_relative_residual": float(np.linalg.norm(normal_residual)) / denominator,
                   "negative_face_cotangents_retained": int(negative_cotangents),
                   "mass_min_m2": float(mass.min()), "mass_max_m2": float(mass.max()),
                   "row_sum_max_abs": float(np.abs(stiffness.sum(axis=1)).max()),
                   "assembly_wall_s": assembly_wall, "solve_wall_s": solve_wall,
                   "total_method_wall_s": time.perf_counter() - started,
                   "input_fields": ["abnormal_vertices", "triangles", "allowed_region_ids"]}
    return output, diagnostics
