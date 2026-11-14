"""Read back every sample and independently check labels and graph scope."""
import os
for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

from collections import Counter, deque
import hashlib
import inspect
import json
import math
from pathlib import Path
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from features import observe, prepare_topology, restore_prediction


def file_record(path):
    path = Path(path)
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def hops(adjacency, starts):
    result = [-1] * len(adjacency)
    queue = deque(starts)
    for index in queue:
        result[index] = 0
    while queue:
        index = queue.popleft()
        for neighbor in adjacency[index]:
            if result[neighbor] < 0:
                result[neighbor] = result[index] + 1
                queue.append(neighbor)
    return result


def main():
    started, cpu_started = time.perf_counter(), time.process_time()
    output = {"cycle_id": "M6-SHAPE-DATA-001", "status": "running", "checks": [], "graph_statistics": [],
              "feature_roundtrips": 0, "feature_rotation_scale_checks": 0, "label_replay_max_error_m": 0.,
              "zero_context_normals_over_observations": 0, "generation_calls": 0, "training_calls": 0, "contact_queries": 0}
    def check(name, condition):
        output["checks"].append({"name": name, "passed": bool(condition)})
        if not condition:
            raise AssertionError(name)
    frozen = json.loads((HERE / "FROZEN_INPUTS.json").read_bytes())
    for item in frozen["public_files"] + frozen["private_inputs"] + frozen["source_inputs"] + frozen["reused_code"]:
        check("frozen " + item["path"], file_record(item["path"]) == item)
    selection = json.loads((HERE / "PATCH_SELECTION.json").read_bytes())
    dataset = json.loads((HERE / "DATASET_INDEX.json").read_bytes())
    audit = json.loads((HERE / "SOURCE_AUDIT.json").read_bytes())
    group = json.loads((HERE / "SOURCE_GROUPS.json").read_bytes())
    sources = {item["name"]: dict(np.load(item["snapshot"]["path"], allow_pickle=False)) for item in audit["sources"]}
    check("one conservative group with no validation/test", group["conservative_groups"] == 1 and group["splits"]["validation"] == group["splits"]["reserved_test"] == [])
    check("observation-only function signature", list(inspect.signature(observe).parameters) == ["observed_vertices", "triangles", "shared_topology"])
    check("bounded patches and observations", len(selection["patches"]) <= 48 and len(dataset["cases"]) == 7 * len(selection["patches"]) <= 336)
    check("unique sample IDs", len({case["id"] for case in dataset["cases"]}) == len(dataset["cases"]))
    for patch in selection["patches"]:
        mesh = sources[patch["source"]]
        reference, triangles = mesh["vertices"], mesh["triangles"]
        folder = Path(patch["private_directory"])
        mapping = dict(np.load(folder / "mapping.npz", allow_pickle=False))
        saved_graph = dict(np.load(folder / "graph.npz", allow_pickle=False))
        context, allowed = mapping["context_source_ids"], mapping["allowed_source_ids"]
        reference_local = np.load(folder / "reference_local.npy", allow_pickle=False)
        check(patch["id"] + " reference exact", np.array_equal(reference_local, reference[context]))
        allowed_set = set(allowed.tolist())
        inside = [face for face in triangles.tolist() if set(face).issubset(allowed_set)]
        edge_counts = Counter(tuple(sorted((face[i], face[(i + 1) % 3]))) for face in inside for i in range(3))
        boundary = sorted({index for edge, count in edge_counts.items() if count == 1 for index in edge})
        check(patch["id"] + " independent boundary", np.array_equal(boundary, mapping["boundary_source_ids"]))
        independent_adj = {int(index): [] for index in allowed}
        for first, second in edge_counts:
            distance = math.dist(reference[first].tolist(), reference[second].tolist())
            independent_adj[first].append((second, distance))
            independent_adj[second].append((first, distance))
        # Dense unvisited-min Dijkstra provides a different traversal from the generator heap.
        distances = {int(index): math.inf for index in allowed}
        distances[patch["center_vertex_id"]] = 0.
        unvisited = set(distances)
        while unvisited:
            index = min(unvisited, key=lambda vertex: (distances[vertex], vertex))
            unvisited.remove(index)
            for neighbor, length in independent_adj[index]:
                distances[neighbor] = min(distances[neighbor], distances[index] + length)
        depth = min(distances[index] for index in boundary)
        check(patch["id"] + " independent boundary distance", abs(depth - patch["distance_to_boundary_m"]) < 1e-13)
        center_faces = [face for face in triangles.tolist() if patch["center_vertex_id"] in face]
        normal = sum((np.cross(reference[face[1]] - reference[face[0]], reference[face[2]] - reference[face[0]]) for face in center_faces), np.zeros(3))
        normal /= np.linalg.norm(normal)
        local = {int(source): index for index, source in enumerate(context)}
        check(patch["id"] + " source face mapping", np.array_equal(context[mapping["context_triangles"]], triangles[mapping["context_source_face_ids"]]) and np.array_equal(mapping["source_polygon_ids"], mesh["source_polygon_ids"][mapping["context_source_face_ids"]]))
        shared = prepare_topology(triangles, len(reference), allowed)
        check(patch["id"] + " graph exact", all(np.array_equal(saved_graph[key], shared[key]) for key in saved_graph))
        adjacency = [[] for _ in context]
        for first, second in saved_graph["edge_index"].T:
            adjacency[first].append(int(second))
        graph_diameter = max(max(hops(adjacency, [index])) for index in range(len(context)))
        fixed_hops = np.asarray(hops(adjacency, np.flatnonzero(~saved_graph["free_mask"]).tolist()))
        check(patch["id"] + " graph connected", min(hops(adjacency, [0])) >= 0)
        max_to_fixed = 0
        max_to_clean = 0
        max_support_diameter = 0
        patch_cases = [case for case in dataset["cases"] if case["patch_id"] == patch["id"]]
        check(patch["id"] + " seven cases and one control", len(patch_cases) == 7 and sum(case["normal_control"] for case in patch_cases) == 1)
        for case in patch_cases:
            name = case["id"]
            for field in ("observed", "input", "labels"):
                check(name + " file hash " + field, file_record(case[field]["path"]) == case[field])
            observed_local = np.load(case["observed"]["path"], allow_pickle=False)
            inputs = dict(np.load(case["input"]["path"], allow_pickle=False))
            labels = dict(np.load(case["labels"]["path"], allow_pickle=False))
            observed = reference.copy()
            observed[context] = observed_local
            delta = reference_local - observed_local
            check(name + " full-context inverse labels", np.array_equal(labels["target_world_m"], delta))
            support = [] if case["normal_control"] else sorted(index for index in allowed if index not in boundary and distances[int(index)] < case["radius_ratio"] * depth)
            damaged = np.isin(context, support)
            check(name + " independent support and denominators", np.array_equal(damaged, labels["damaged_mask"]) and int(damaged.sum()) == case["damaged_vertices"] and case["damaged_vertices"] + case["normal_allowed_vertices"] == 384)
            expected_delta = np.zeros_like(reference_local)
            for source_id in support:
                weight = (1 - (distances[int(source_id)] / (case["radius_ratio"] * depth)) ** 2) ** 2
                expected_delta[local[int(source_id)]] = case["amplitude_m"] * weight * normal
            check(name + " independent dent formula", np.allclose(delta, expected_delta, rtol=1e-10, atol=3e-15))
            check(name + " boundary/halo unchanged", np.array_equal(observed_local[~saved_graph["free_mask"]], reference_local[~saved_graph["free_mask"]]))
            check(name + " full labels and normal masks", labels["target_normalized"].shape == (len(context), 3) and np.array_equal(labels["normal_allowed_mask"], saved_graph["allowed_mask"] & ~damaged) and np.array_equal(labels["normal_free_mask"], saved_graph["free_mask"] & ~damaged))
            check(name + " normalized labels", np.array_equal(labels["target_normalized"], (delta / float(inputs["scale_m"])).astype(np.float32)))
            check(name + " strict input whitelist", set(inputs) == {"node_features", "edge_features", "positions", "normals", "origin_world_m", "scale_m", "feature_names"})
            check(name + " numeric feature shapes", inputs["node_features"].shape == (len(context), 7) and inputs["edge_features"].shape == (saved_graph["edge_index"].shape[1], 4) and np.isfinite(inputs["node_features"]).all() and np.isfinite(inputs["edge_features"]).all())
            check(name + " feature masks", np.array_equal(inputs["node_features"][:, 5], saved_graph["allowed_mask"]) and np.array_equal(inputs["node_features"][:, 6], ~saved_graph["free_mask"]))
            raw_error = np.linalg.norm(delta[saved_graph["allowed_mask"]], axis=1)
            scalar_rmse = math.sqrt(sum(float(value) ** 2 for value in raw_error) / len(raw_error))
            check(name + " scalar no-op RMSE", abs(scalar_rmse - case["no_op_allowed_error"]["rmse_m"]) < 1e-15)
            subset = triangles[mapping["incident_source_face_ids"]]
            before = np.cross(reference[subset[:, 1]] - reference[subset[:, 0]], reference[subset[:, 2]] - reference[subset[:, 0]])
            after = np.cross(observed[subset[:, 1]] - observed[subset[:, 0]], observed[subset[:, 2]] - observed[subset[:, 0]])
            bad = np.count_nonzero(np.linalg.norm(after, axis=1) == 0)
            flips = np.count_nonzero(np.einsum("ij,ij->i", before, after) < 0)
            check(name + " independent quality admission", bad == case["quality"]["degenerate_after"] and flips == case["quality"]["normal_reversals"] and case["accepted"] == (bad == flips == 0))
            restored = restore_prediction(observed, shared, labels["target_normalized"], inputs["scale_m"])
            replay_error = float(np.linalg.norm(restored[allowed] - reference[allowed], axis=1).max())
            output["label_replay_max_error_m"] = max(output["label_replay_max_error_m"], replay_error)
            check(name + " label precision roundtrip", replay_error < 1e-8)
            check(name + " zero residual preserves full observation", np.array_equal(restore_prediction(observed, shared, np.zeros((len(context), 3)), inputs["scale_m"]), observed))
            output["zero_context_normals_over_observations"] += int(np.count_nonzero(np.linalg.norm(inputs["normals"], axis=1) == 0))
            if support:
                max_to_fixed = max(max_to_fixed, int(fixed_hops[damaged].max()))
                max_to_clean = max(max_to_clean, case["hop_statistics"]["damaged_to_observed_clean_max_hops"])
                max_support_diameter = max(max_support_diameter, case["hop_statistics"]["support_diameter_hops"])
            if case["normal_control"] or name.endswith("sample_06"):
                recalculated = observe(observed, triangles, shared)
                check(name + " observe feature readback", all(np.array_equal(inputs[key], recalculated[key]) for key in inputs))
                output["feature_roundtrips"] += 1
        output["graph_statistics"].append({"patch_id": patch["id"], "input_vertices": len(context), "directed_edges": saved_graph["edge_index"].shape[1],
                                           "input_graph_diameter_hops": graph_diameter, "support_diameter_hops": max_support_diameter,
                                           "damaged_to_clean_max_hops": max_to_clean, "damaged_to_fixed_halo_max_hops": max_to_fixed})
        print(patch["id"] + " verified", flush=True)
    for source in audit["sources"]:
        patch = next(item for item in selection["patches"] if item["source"] == source["name"])
        case = next(item for item in dataset["cases"] if item["patch_id"] == patch["id"] and item["id"].endswith("sample_06"))
        mesh = sources[source["name"]]
        vertices, triangles = mesh["vertices"].copy(), mesh["triangles"]
        mapping = dict(np.load(Path(patch["private_directory"]) / "mapping.npz", allow_pickle=False))
        vertices[mapping["context_source_ids"]] = np.load(case["observed"]["path"], allow_pickle=False)
        shared = prepare_topology(triangles, len(vertices), mapping["allowed_source_ids"])
        baseline = dict(np.load(case["input"]["path"], allow_pickle=False))
        axis = np.asarray([1., 2., 3.]); axis /= np.linalg.norm(axis)
        skew = np.asarray([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
        rotation = np.eye(3) + math.sin(.7) * skew + (1 - math.cos(.7)) * (skew @ skew)
        rotated = observe(2.75 * vertices @ rotation.T + np.asarray([.2, -.1, .3]), triangles, shared)
        check(source["name"] + " scalar rotation-scale invariance", np.allclose(rotated["node_features"], baseline["node_features"], rtol=3e-5, atol=3e-5) and np.allclose(rotated["edge_features"], baseline["edge_features"], rtol=3e-5, atol=3e-5))
        check(source["name"] + " vector rotation covariance", np.allclose(rotated["positions"], baseline["positions"] @ rotation.T, rtol=3e-5, atol=3e-5) and np.allclose(rotated["normals"], baseline["normals"] @ rotation.T, rtol=3e-5, atol=3e-5))
        output["feature_rotation_scale_checks"] += 1
    h_fixed = max(item["damaged_to_fixed_halo_max_hops"] for item in output["graph_statistics"])
    k = max(12, h_fixed + 2)
    output.update(status="passed", assertion_count=len(output["checks"]), verified_observations=len(dataset["cases"]),
                  verified_patches=len(selection["patches"]), frozen_message_steps=k, h_fixed_max=h_fixed,
                  wall_s=time.perf_counter() - started, cpu_s=time.process_time() - cpu_started,
                  label_replay_scope="inverse-label serialization precision only; no candidate prediction or quality gain measured",
                  missing_measurements=["verification whole-process CPU including imports", "verification peak RSS"])
    (HERE / "VERIFICATION.json").write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({key: output[key] for key in ("status", "assertion_count", "verified_observations", "frozen_message_steps", "wall_s")}))


if __name__ == "__main__":
    main()
