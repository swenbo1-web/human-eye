"""Reference-based evaluation helpers; never imported by the reconstruction."""
import numpy as np


def errors(reference, output, ids, scale):
    if not ids:
        return {"count": 0, "rmse_m": None, "p95_m": None, "max_m": None,
                "rmse_over_mean_edge": None, "p95_over_mean_edge": None, "max_over_mean_edge": None}
    values = np.linalg.norm(output[ids] - reference[ids], axis=1)
    rmse = float(np.sqrt(np.mean(values**2)))
    p95, maximum = float(np.percentile(values, 95)), float(values.max())
    return {"count": len(ids), "rmse_m": rmse, "p95_m": p95, "max_m": maximum,
            "rmse_over_mean_edge": rmse / scale, "p95_over_mean_edge": p95 / scale, "max_over_mean_edge": maximum / scale}


def triangle_quality(reference, output, faces):
    original = reference[faces]
    current = output[faces]
    normal0 = np.cross(original[:, 1] - original[:, 0], original[:, 2] - original[:, 0])
    normal1 = np.cross(current[:, 1] - current[:, 0], current[:, 2] - current[:, 0])
    length0, length1 = np.linalg.norm(normal0, axis=1), np.linalg.norm(normal1, axis=1)
    valid = (length0 > 0) & (length1 > 0)
    cosine = np.clip(np.sum(normal0[valid] * normal1[valid], axis=1) / (length0[valid] * length1[valid]), -1, 1)
    angles = np.rad2deg(np.arccos(cosine))
    edges = sorted({tuple(sorted((int(a), int(b)))) for face in faces for a, b in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0]))})
    pairs = np.asarray(edges)
    before_length = np.linalg.norm(reference[pairs[:, 0]] - reference[pairs[:, 1]], axis=1)
    after_length = np.linalg.norm(output[pairs[:, 0]] - output[pairs[:, 1]], axis=1)
    ratios = after_length[before_length > 0] / before_length[before_length > 0]
    area_ratios = length1[length0 > 0] / length0[length0 > 0]
    return {"triangles": len(faces), "degenerate_reference_triangles": int(np.sum(length0 == 0)),
            "degenerate_output_triangles": int(np.sum(length1 == 0)),
            "normal_reversal_dot_lt_zero": int(np.sum(np.sum(normal0 * normal1, axis=1) < 0)),
            "normal_angle_p50_p95_max_deg": np.percentile(angles, [50, 95, 100]).tolist() if len(angles) else None,
            "area_ratio_min_p05_median_max": np.percentile(area_ratios, [0, 5, 50, 100]).tolist(),
            "edges": len(edges), "edge_ratio_min_p05_median_p95_max": np.percentile(ratios, [0, 5, 50, 95, 100]).tolist(),
            "edge_absolute_relative_change_p95_max": np.percentile(np.abs(ratios - 1), [95, 100]).tolist()}


def support_normal_alignment(reference, triangles, support, direction):
    if not support:
        return None
    normals = {index: np.zeros(3) for index in support}
    selected = set(support)
    faces = triangles[np.any(np.isin(triangles, support), axis=1)]
    for face in faces:
        crossed = np.cross(reference[face[1]] - reference[face[0]], reference[face[2]] - reference[face[0]])
        for index in face:
            if int(index) in selected:
                normals[int(index)] += crossed
    alignment = [float(normal @ direction / np.linalg.norm(normal)) for normal in normals.values() if np.linalg.norm(normal) > 0]
    return {"evaluated_vertices": len(alignment), "min_median_max_cosine": np.percentile(alignment, [0, 50, 100]).tolist()}
