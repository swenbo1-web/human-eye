"""Observation-only graph inputs. Labels and source identities are absent."""
import numpy as np

from geometry import boundary_ids, graph, halo_ids, normals


def prepare_topology(triangles, vertex_count, allowed_region_ids):
    allowed = np.asarray(sorted(allowed_region_ids), dtype=np.int64)
    dummy = np.zeros((vertex_count, 3))
    edges, _, _, adjacency = graph(dummy, triangles)
    boundary, _, _ = boundary_ids(triangles, allowed)
    context = halo_ids(adjacency, allowed, rings=2)
    local_ids = np.full(vertex_count, -1, dtype=np.int64)
    local_ids[context] = np.arange(len(context))
    selected_edges = edges[np.all(np.isin(edges, context), axis=1)]
    local_edges = local_ids[selected_edges]
    directed = np.concatenate((local_edges, local_edges[:, ::-1])).T
    allowed_mask = np.isin(context, allowed)
    boundary_mask = np.isin(context, boundary)
    return {"context_ids": context, "edge_index": directed, "allowed_mask": allowed_mask,
            "boundary_mask": boundary_mask, "free_mask": allowed_mask & ~boundary_mask,
            "world_edges": selected_edges, "full_edges": edges}


def observe(observed_vertices, triangles, shared_topology):
    context = shared_topology["context_ids"]
    points = observed_vertices[context]
    fixed = ~shared_topology["free_mask"]
    origin = points[fixed].mean(axis=0)
    edges = shared_topology["world_edges"]
    scale = float(np.median(np.linalg.norm(observed_vertices[edges[:, 0]] - observed_vertices[edges[:, 1]], axis=1)))
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError("invalid_observed_scale")
    unit_normals, _, _, _ = normals(observed_vertices, triangles)
    full_edges = shared_topology["full_edges"]
    delta = (observed_vertices[full_edges[:, 1]] - observed_vertices[full_edges[:, 0]]) / scale
    length = np.linalg.norm(delta, axis=1)
    variation = 1 - np.clip(np.einsum("ij,ij->i", unit_normals[full_edges[:, 0]], unit_normals[full_edges[:, 1]]), -1, 1)
    degree = np.zeros(len(observed_vertices))
    laplacian = np.zeros_like(observed_vertices)
    mean_length = np.zeros(len(observed_vertices))
    normal_variation = np.zeros(len(observed_vertices))
    for corner, sign in ((0, 1), (1, -1)):
        ids = full_edges[:, corner]
        np.add.at(degree, ids, 1)
        np.add.at(laplacian, ids, sign * delta)
        np.add.at(mean_length, ids, length)
        np.add.at(normal_variation, ids, variation)
    divisor = np.maximum(degree, 1)
    signed_laplacian = np.einsum("ij,ij->i", laplacian / divisor[:, None], unit_normals)
    positions = (points - origin) / scale
    local_normals = unit_normals[context]
    features = np.column_stack((np.linalg.norm(positions, axis=1), signed_laplacian[context],
                                (normal_variation / divisor)[context], (mean_length / divisor)[context],
                                np.log1p(degree[context]), shared_topology["allowed_mask"],
                                ~shared_topology["free_mask"])).astype(np.float32)
    first, second = shared_topology["edge_index"]
    edge_delta = positions[second] - positions[first]
    edge_features = np.column_stack((np.einsum("ij,ij->i", edge_delta, edge_delta),
                                    np.einsum("ij,ij->i", local_normals[first], local_normals[second]),
                                    np.einsum("ij,ij->i", local_normals[first], edge_delta),
                                    np.einsum("ij,ij->i", local_normals[second], edge_delta))).astype(np.float32)
    if not np.isfinite(features).all():
        raise ValueError("nonfinite_observed_feature")
    return {"node_features": features, "edge_features": edge_features, "positions": positions.astype(np.float32),
            "normals": local_normals.astype(np.float32), "origin_world_m": origin, "scale_m": np.asarray(scale),
            "feature_names": np.asarray(["radius", "signed_laplacian", "normal_variation", "mean_edge", "log_degree", "allowed", "fixed"])}


def restore_prediction(observed_vertices, shared_topology, normalized_prediction, scale_m):
    context = shared_topology["context_ids"]
    prediction = np.asarray(normalized_prediction)
    if prediction.shape != (len(context), 3) or not np.isfinite(prediction).all():
        raise ValueError("prediction_shape_or_finite_error")
    result = observed_vertices.copy()
    free = shared_topology["free_mask"]
    result[context[free]] += prediction[free] * float(scale_m)
    return result
