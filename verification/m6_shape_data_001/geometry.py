"""Deterministic mesh graph operations shared by preparation and verification."""
import heapq

import numpy as np


def graph(vertices, triangles):
    edges = np.sort(np.concatenate((triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]])), axis=1)
    edges, counts = np.unique(edges, axis=0, return_counts=True)
    lengths = np.linalg.norm(vertices[edges[:, 0]] - vertices[edges[:, 1]], axis=1)
    adjacency = [[] for _ in vertices]
    for (a, b), length in zip(edges, lengths):
        adjacency[a].append((int(b), float(length)))
        adjacency[b].append((int(a), float(length)))
    for neighbors in adjacency:
        neighbors.sort()
    return edges, counts, lengths, adjacency


def shortest(adjacency, starts, allowed=None, limit=None):
    distances = {int(index): 0. for index in starts}
    queue = [(0., int(index)) for index in starts]
    heapq.heapify(queue)
    settled = {}
    while queue:
        distance, index = heapq.heappop(queue)
        if index in settled:
            continue
        settled[index] = distance
        if limit is not None and len(settled) >= limit:
            break
        for neighbor, length in adjacency[index]:
            candidate = distance + length
            if allowed is not None and neighbor not in allowed:
                continue
            if candidate < distances.get(neighbor, float("inf")):
                distances[neighbor] = candidate
                heapq.heappush(queue, (candidate, neighbor))
    return settled


def normals(vertices, triangles):
    cross = np.cross(vertices[triangles[:, 1]] - vertices[triangles[:, 0]],
                     vertices[triangles[:, 2]] - vertices[triangles[:, 0]])
    magnitude = np.linalg.norm(cross, axis=1)
    total = np.zeros_like(vertices)
    mass = np.zeros(len(vertices))
    for corner in range(3):
        np.add.at(total, triangles[:, corner], cross)
        np.add.at(mass, triangles[:, corner], magnitude)
    lengths = np.linalg.norm(total, axis=1)
    unit = total / np.maximum(lengths[:, None], np.finfo(float).tiny)
    coherence = lengths / np.maximum(mass, np.finfo(float).tiny)
    return unit, cross, magnitude, coherence


def components(adjacency):
    labels = np.full(len(adjacency), -1, dtype=np.int64)
    sizes = []
    for seed in range(len(adjacency)):
        if labels[seed] >= 0:
            continue
        label = len(sizes)
        labels[seed] = label
        stack = [seed]
        size = 0
        while stack:
            index = stack.pop()
            size += 1
            for neighbor, _ in adjacency[index]:
                if labels[neighbor] < 0:
                    labels[neighbor] = label
                    stack.append(neighbor)
        sizes.append(size)
    return labels, np.asarray(sizes, dtype=np.int64)


def boundary_ids(triangles, allowed_ids):
    inside = triangles[np.all(np.isin(triangles, allowed_ids), axis=1)]
    edges = np.sort(np.concatenate((inside[:, [0, 1]], inside[:, [1, 2]], inside[:, [2, 0]])), axis=1)
    edges, counts = np.unique(edges, axis=0, return_counts=True)
    return np.unique(edges[counts == 1]), inside, counts


def halo_ids(adjacency, allowed_ids, rings=2):
    context = set(int(index) for index in allowed_ids)
    frontier = context.copy()
    for _ in range(rings):
        frontier = {neighbor for index in frontier for neighbor, _ in adjacency[index]} - context
        context.update(frontier)
    return np.asarray(sorted(context), dtype=np.int64)


def quality(reference, observed, triangles):
    before = np.cross(reference[triangles[:, 1]] - reference[triangles[:, 0]], reference[triangles[:, 2]] - reference[triangles[:, 0]])
    after = np.cross(observed[triangles[:, 1]] - observed[triangles[:, 0]], observed[triangles[:, 2]] - observed[triangles[:, 0]])
    size_before = np.linalg.norm(before, axis=1)
    size_after = np.linalg.norm(after, axis=1)
    valid = size_before > 0
    cosine = np.einsum("ij,ij->i", before[valid], after[valid]) / np.maximum(size_before[valid] * size_after[valid], np.finfo(float).tiny)
    ratios = size_after[valid] / size_before[valid]
    edges = np.unique(np.sort(np.concatenate((triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]])), axis=1), axis=0)
    edge_before = np.linalg.norm(reference[edges[:, 1]] - reference[edges[:, 0]], axis=1)
    edge_after = np.linalg.norm(observed[edges[:, 1]] - observed[edges[:, 0]], axis=1)
    edge_change = np.abs(edge_after[edge_before > 0] / edge_before[edge_before > 0] - 1)
    return {"triangles": len(triangles), "degenerate_before": int(np.count_nonzero(size_before == 0)),
            "degenerate_after": int(np.count_nonzero(size_after == 0)), "normal_reversals": int(np.count_nonzero(cosine < 0)),
            "area_ratio_min_median_max": np.quantile(ratios, [0, .5, 1]).tolist(),
            "edge_absolute_relative_change_p95_max": np.quantile(edge_change, [.95, 1]).tolist(),
            "normal_angle_p95_max_deg": np.quantile(np.degrees(np.arccos(np.clip(cosine, -1, 1))), [.95, 1]).tolist()}
