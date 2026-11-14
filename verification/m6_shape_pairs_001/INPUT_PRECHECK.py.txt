"""Cheap pristine-input inspection used to choose a curved-surface baseline."""
import hashlib
import heapq
import json
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA = ROOT / "verification/m6_real_data_001_review/snapshot/verification/m6_real_data_001/private"
raw_bytes = (DATA / "capture_02/raw_selected.json").read_bytes()
assert hashlib.sha256(raw_bytes).hexdigest() == "e1700a3869ff48d9159be8f5d97212329629920eed6581370465ced9d986f18b"
raw = json.loads(raw_bytes)
patch_bytes = (DATA / "ARM_REGION.json").read_bytes()
assert hashlib.sha256(patch_bytes).hexdigest() == "a203e27a45387170d6682cbf93de73f98d7c2042024c513f888c55f336c2cef1"
patch = json.loads(patch_bytes)
v = np.asarray(raw["vertices_world"]); faces = np.asarray(raw["triangles"])
ids = patch["source_vertex_ids"]; selected = set(ids)
inside = [t for t in faces.tolist() if all(i in selected for i in t)]
edges = {}
for tri in inside:
    for a, b in zip(tri, tri[1:] + tri[:1]):
        edge = tuple(sorted((a, b))); edges[edge] = edges.get(edge, 0) + 1
boundary = sorted({i for edge, count in edges.items() if count == 1 for i in edge})
adj = {i: [] for i in ids}
for a, b in edges:
    weight = float(np.linalg.norm(v[a] - v[b])); adj[a].append((b, weight)); adj[b].append((a, weight))
dist = {i: 0. if i in boundary else float("inf") for i in ids}
heap = [(0., i) for i in boundary]; heapq.heapify(heap)
while heap:
    d, i = heapq.heappop(heap)
    if d != dist[i]:
        continue
    for j, w in adj[i]:
        if d + w < dist[j]:
            dist[j] = d + w; heapq.heappush(heap, (d + w, j))
center = max(ids, key=lambda i: (dist[i], -i))
points = v[ids]; _, singular, basis = np.linalg.svd(points - points.mean(0), full_matrices=False)
incident = faces[np.any(np.isin(faces, ids), axis=1)]
cross = np.cross(v[incident[:, 1]] - v[incident[:, 0]], v[incident[:, 2]] - v[incident[:, 0]])
length = np.linalg.norm(cross, axis=1); nz = length > 0
normals = cross[nz] / length[nz, None]
result = {"source_sha256": hashlib.sha256(raw_bytes).hexdigest(), "patch_sha256": hashlib.sha256(patch_bytes).hexdigest(),
          "selected_vertices": len(ids), "boundary_vertices": len(boundary), "deepest_vertex_id": int(center),
          "center_distance_to_boundary_m": dist[center], "pca_singular_values": singular.tolist(),
          "pca_axis_extents_m": np.ptp((points - points.mean(0)) @ basis.T, axis=0).tolist(),
          "incident_nondegenerate_faces": int(nz.sum()),
          "abs_normal_alignment_to_smallest_pca_axis_percentiles": np.percentile(abs(normals @ basis[-1]), [0, 25, 50, 75, 100]).tolist(),
          "interpretation": "Do not assume a globally nearly planar patch; prefer a baseline defined on original mesh topology. This does not prove every local chart invalid.",
          "scope": "Read-only input screening. No corruptions, repair, learning or performance comparison executed."}
(HERE / "RESULTS.json").write_bytes((json.dumps(result, indent=2) + "\n").encode("utf-8"))
print(json.dumps({"center": int(center), "boundary_distance_m": dist[center], "selected": len(ids)}))
