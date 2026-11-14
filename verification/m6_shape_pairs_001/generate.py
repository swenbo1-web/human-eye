"""Construct the single preregistered dent family; labels stay outside the method."""
import heapq
import json
from pathlib import Path

import numpy as np


def region_topology(triangles, region_ids):
    region = set(region_ids)
    inside = [face for face in triangles if region.issuperset(face)]
    counts = {}
    for face in inside:
        for a, b in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            edge = tuple(sorted((int(a), int(b))))
            counts[edge] = counts.get(edge, 0) + 1
    boundary = sorted({index for edge, count in counts.items() if count == 1 for index in edge})
    if any(count > 2 for count in counts.values()):
        raise ValueError("nonmanifold_region_edges")
    return sorted(counts), boundary


def shortest_paths(graph, start):
    distances = {index: float("inf") for index in graph}
    distances[start] = 0.
    queue = [(0., start)]
    while queue:
        distance, index = heapq.heappop(queue)
        if distance != distances[index]:
            continue
        for neighbor, weight in graph[index]:
            proposal = distance + weight
            if proposal < distances[neighbor]:
                distances[neighbor] = proposal
                heapq.heappush(queue, (proposal, neighbor))
    return distances


def generate(reference, triangles, region_ids, private_dir):
    """Reference is used here for synthetic labels and displacement generation."""
    private_dir = Path(private_dir)
    private_dir.mkdir(parents=True, exist_ok=True)
    edges, boundary = region_topology(triangles, region_ids)
    graph = {index: [] for index in region_ids}
    for a, b in edges:
        length = float(np.linalg.norm(reference[a] - reference[b]))
        graph[a].append((b, length))
        graph[b].append((a, length))
    center = 24205
    distances = shortest_paths(graph, center)
    depth = min(distances[index] for index in boundary)
    if abs(depth - .046924326994334485) > 1e-14:
        raise ValueError("registered_center_boundary_distance_changed")
    incident = np.flatnonzero(np.any(np.asarray(triangles) == center, axis=1))
    faces = np.asarray(triangles)[incident]
    crossed = np.cross(reference[faces[:, 1]] - reference[faces[:, 0]], reference[faces[:, 2]] - reference[faces[:, 0]])
    area_normal = crossed.sum(axis=0)
    normal_length = float(np.linalg.norm(area_normal))
    if normal_length == 0:
        raise ValueError("center_area_weighted_normal_undefined")
    normal = area_normal / normal_length
    reference_path = private_dir / "reference_vertices.npy"
    np.save(reference_path, reference, allow_pickle=False)
    cases = [{"id": "sample_00", "radius_ratio": None, "amplitude_ratio": 0., "radius_m": None, "amplitude_m": 0.}]
    for radius_ratio in (.35, .55):
        for amplitude_ratio in (.05, .15, .30):
            radius = radius_ratio * depth
            cases.append({"id": f"sample_{len(cases):02d}", "radius_ratio": radius_ratio, "amplitude_ratio": amplitude_ratio,
                          "radius_m": radius, "amplitude_m": amplitude_ratio * radius})
    region = set(region_ids)
    boundary_set = set(boundary)
    for case in cases:
        abnormal = reference.copy()
        support = []
        if case["radius_m"] is not None:
            for index in region_ids:
                distance = distances[index]
                if index not in boundary_set and distance < case["radius_m"]:
                    weight = (1 - (distance / case["radius_m"])**2)**2
                    abnormal[index] -= case["amplitude_m"] * weight * normal
                    support.append(index)
        path = private_dir / f"{case['id']}_abnormal.npy"
        np.save(path, abnormal, allow_pickle=False)
        actual = np.flatnonzero(np.any(abnormal != reference, axis=1)).tolist()
        assert actual == sorted(support)
        assert all(index in region and index not in boundary_set for index in actual)
        np.save(private_dir / f"{case['id']}_reference_displacement.npy", reference - abnormal, allow_pickle=False)
        closure = np.flatnonzero(np.any(np.isin(np.asarray(triangles), actual), axis=1)).tolist()
        case.update(abnormal_npy=str(path), true_support_ids=actual, actual_incident_face_ids=closure,
                    inverse_displacement_npy=str(private_dir / f"{case['id']}_reference_displacement.npy"),
                    max_actual_displacement_m=float(np.linalg.norm(abnormal - reference, axis=1).max()))
    labels = {"reference_npy": str(reference_path), "center_vertex_id": center, "center_normal": normal.tolist(),
              "center_normal_dot_region_radial_m": float(normal @ (reference[center] - reference[region_ids].mean(axis=0))),
              "distance_to_boundary_m": depth, "region_ids": list(region_ids), "boundary_ids": boundary,
              "reference_mean_region_edge_length_m": float(np.mean([np.linalg.norm(reference[a] - reference[b]) for a, b in edges])),
              "asset_group": "614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d",
              "label_scope": "Synthetic restoration to the undisturbed source; anatomical quality unlabelled",
              "cases": cases}
    (private_dir / "LABELS.json").write_text(json.dumps(labels, indent=2) + "\n", encoding="utf8")
    return labels
