"""Generate the frozen finite dent set and observation-only training arrays."""
import os
for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

from collections import Counter, deque
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from features import observe, prepare_topology
from geometry import graph, quality


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def file_record(path):
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def old_rules():
    path = ROOT / "verification/m6_shape_pairs_001/generate.py"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == "3a0b551a32ab6148c96c0f76194d4d1274b61b695229f1d91a705e91afe1113e"
    spec = importlib.util.spec_from_file_location("frozen_pairs001_generation_rules", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def hop_statistics(edge_index, context, support, center):
    adjacency = [[] for _ in context]
    for first, second in edge_index.T:
        adjacency[first].append(int(second))
    local = {int(source): index for index, source in enumerate(context)}
    damaged = {local[index] for index in support}
    def hops(starts):
        distances = np.full(len(context), -1, dtype=np.int64)
        queue = deque(starts)
        for index in queue:
            distances[index] = 0
        while queue:
            index = queue.popleft()
            for neighbor in adjacency[index]:
                if distances[neighbor] < 0:
                    distances[neighbor] = distances[index] + 1
                    queue.append(neighbor)
        return distances
    if not damaged:
        return {"damaged_to_observed_clean_max_hops": 0, "support_diameter_hops": 0, "center_to_support_max_hops": 0}
    to_clean = hops([index for index in range(len(context)) if index not in damaged])
    diameter = max(int(hops([index])[list(damaged)].max()) for index in damaged)
    return {"damaged_to_observed_clean_max_hops": int(to_clean[list(damaged)].max()),
            "support_diameter_hops": diameter, "center_to_support_max_hops": int(hops([local[center]])[list(damaged)].max())}


def error_statistics(delta, mask, mean_edge):
    distances = np.linalg.norm(delta[mask], axis=1)
    if not len(distances):
        return {"count": 0, "rmse_m": None, "p95_m": None, "max_m": None, "rmse_over_mean_edge": None}
    rmse = float(np.sqrt(np.mean(distances * distances)))
    return {"count": len(distances), "rmse_m": rmse, "p95_m": float(np.quantile(distances, .95)),
            "max_m": float(distances.max()), "rmse_over_mean_edge": rmse / mean_edge}


def main():
    started, cpu_started = time.perf_counter(), time.process_time()
    index_path = HERE / "DATASET_INDEX.json"
    if index_path.exists():
        raise RuntimeError("dataset_already_generated_inspect_before_retry")
    log = json.loads((HERE / "RUN_LOG.json").read_bytes())
    event = {"operation": "paired generation", "attempt": 1, "status": "running"}
    log["events"].append(event)
    write(HERE / "RUN_LOG.json", log)
    freeze = json.loads((HERE / "FROZEN_INPUTS.json").read_bytes())
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    for item in freeze["public_files"] + freeze["private_inputs"] + freeze["source_inputs"] + freeze["reused_code"]:
        assert file_record(Path(item["path"])) == item
    for item in freeze["public_files"]:
        relative = Path(item["path"]).relative_to(ROOT).as_posix()
        assert subprocess.check_output(["git", "show", commit + ":" + relative], cwd=ROOT) == Path(item["path"]).read_bytes()
    rules = old_rules()
    selection = json.loads((HERE / "PATCH_SELECTION.json").read_bytes())
    audit = json.loads((HERE / "SOURCE_AUDIT.json").read_bytes())
    plan = json.loads((HERE / "DATA_PLAN.json").read_bytes())
    assert selection["patches_count"] <= 48 and selection["max_observations"] <= 336
    sources = {row["name"]: dict(np.load(row["snapshot"]["path"], allow_pickle=False)) for row in audit["sources"]}
    for source in sources.values():
        source["vertices"].setflags(write=False)
        source["triangles"].setflags(write=False)
    dataset = {"cycle_id": "M6-SHAPE-DATA-001", "generation_commit": commit, "cases": [],
               "group_id": "group_000_unknown_upstream", "purpose": "development_train_pool", "source_counts": {},
               "timings": {"topology_preparation_s": 0., "damage_and_label_s": 0., "observation_features_s": 0., "quality_s": 0., "array_write_s": 0.}}
    for patch in selection["patches"]:
        before = time.perf_counter()
        source = sources[patch["source"]]
        reference, triangles = source["vertices"], source["triangles"]
        folder = Path(patch["private_directory"])
        mapping = dict(np.load(folder / "mapping.npz", allow_pickle=False))
        allowed = mapping["allowed_source_ids"].tolist()
        context = mapping["context_source_ids"]
        edges, boundary = rules.region_topology(triangles, allowed)
        adjacency = {index: [] for index in allowed}
        for first, second in edges:
            length = float(np.linalg.norm(reference[first] - reference[second]))
            adjacency[first].append((second, length))
            adjacency[second].append((first, length))
        distances = rules.shortest_paths(adjacency, patch["center_vertex_id"])
        depth = min(distances[index] for index in boundary)
        assert abs(depth - patch["distance_to_boundary_m"]) < 1e-14
        center_faces = triangles[np.any(triangles == patch["center_vertex_id"], axis=1)]
        normal = np.cross(reference[center_faces[:, 1]] - reference[center_faces[:, 0]],
                          reference[center_faces[:, 2]] - reference[center_faces[:, 0]]).sum(axis=0)
        normal /= np.linalg.norm(normal)
        shared = prepare_topology(triangles, len(reference), allowed)
        assert np.array_equal(shared["context_ids"], context)
        saved_graph = dict(np.load(folder / "graph.npz", allow_pickle=False))
        assert all(np.array_equal(saved_graph[name], shared[name]) for name in saved_graph)
        free = set(allowed) - set(boundary)
        external = np.asarray(sorted(set(range(len(reference))) - free), dtype=np.int64)
        mean_edge = float(np.mean([np.linalg.norm(reference[first] - reference[second]) for first, second in edges]))
        dataset["timings"]["topology_preparation_s"] += time.perf_counter() - before
        cases = [(None, 0.)] + [(radius, amplitude) for radius in plan["generation"]["r_over_D"] for amplitude in plan["generation"]["a_over_r"]]
        for subfolder in ("observed", "inputs", "labels"):
            (folder / subfolder).mkdir(exist_ok=True)
        hop_cache = {}
        for ordinal, (radius_ratio, amplitude_ratio) in enumerate(cases):
            before = time.perf_counter()
            case_id = f"sample_{ordinal:02d}"
            observed = reference.copy()
            support = []
            radius = None if radius_ratio is None else radius_ratio * depth
            amplitude = 0. if radius is None else amplitude_ratio * radius
            if radius is not None:
                support = sorted(index for index in allowed if index in free and distances[index] < radius)
                for index in support:
                    weight = (1 - (distances[index] / radius) ** 2) ** 2
                    observed[index] -= amplitude * weight * normal
            changed = np.flatnonzero(np.any(reference != observed, axis=1))
            assert changed.tolist() == support
            assert np.array_equal(reference[external], observed[external])
            observed.setflags(write=False)
            delta = reference[context] - observed[context]
            damaged = np.isin(context, support)
            if radius_ratio not in hop_cache:
                hop_cache[radius_ratio] = hop_statistics(shared["edge_index"], context, support, patch["center_vertex_id"])
            dataset["timings"]["damage_and_label_s"] += time.perf_counter() - before
            before = time.perf_counter()
            observation = observe(observed, triangles, shared)
            assert np.isfinite(observation["edge_features"]).all()
            normalized_target = (delta / float(observation["scale_m"])).astype(np.float32)
            assert np.all(normalized_target[~shared["free_mask"]] == 0)
            dataset["timings"]["observation_features_s"] += time.perf_counter() - before
            before = time.perf_counter()
            mesh_quality = quality(reference, observed, triangles[mapping["incident_source_face_ids"]])
            reasons = []
            if mesh_quality["degenerate_after"]:
                reasons.append("degenerate_incident_triangle")
            if mesh_quality["normal_reversals"]:
                reasons.append("incident_normal_reversal")
            dataset["timings"]["quality_s"] += time.perf_counter() - before
            before = time.perf_counter()
            observed_path, input_path, label_path = folder / "observed" / (case_id + ".npy"), folder / "inputs" / (case_id + ".npz"), folder / "labels" / (case_id + ".npz")
            np.save(observed_path, observed[context], allow_pickle=False)
            np.savez_compressed(input_path, **observation)
            np.savez_compressed(label_path, target_normalized=normalized_target, target_world_m=delta, damaged_mask=damaged,
                                normal_allowed_mask=shared["allowed_mask"] & ~damaged,
                                normal_free_mask=shared["free_mask"] & ~damaged)
            dataset["timings"]["array_write_s"] += time.perf_counter() - before
            item = {"id": patch["id"] + "/" + case_id, "patch_id": patch["id"], "source": patch["source"],
                    "source_group": dataset["group_id"], "purpose": dataset["purpose"], "stratum": patch["stratum"],
                    "normal_control": ordinal == 0, "accepted": not reasons, "rejection_reasons": reasons,
                    "radius_ratio": radius_ratio, "amplitude_ratio": amplitude_ratio, "radius_m": radius, "amplitude_m": amplitude,
                    "allowed_vertices": len(allowed), "free_vertices": len(free), "context_vertices": len(context),
                    "damaged_vertices": len(support), "normal_allowed_vertices": len(allowed) - len(support),
                    "normal_free_vertices": len(free) - len(support), "boundary_vertices": len(boundary),
                    "damage_max_m": float(np.linalg.norm(delta, axis=1).max()), "observed_scale_m": float(observation["scale_m"]),
                    "no_op_allowed_error": error_statistics(delta, shared["allowed_mask"], mean_edge),
                    "no_op_support_error": error_statistics(delta, damaged, mean_edge), "quality": mesh_quality,
                    "boundary_external_bitwise_preserved": True, "hop_statistics": hop_cache[radius_ratio],
                    "observed": file_record(observed_path), "input": file_record(input_path), "labels": file_record(label_path)}
            dataset["cases"].append(item)
        print(json.dumps({"patch": patch["id"], "cases": len(cases), "accepted": sum(case["accepted"] for case in dataset["cases"] if case["patch_id"] == patch["id"])}), flush=True)
    counts = Counter(case["source"] for case in dataset["cases"])
    dataset["source_counts"] = dict(counts)
    dataset.update(status="generated", attempted_observations=len(dataset["cases"]), accepted_observations=sum(case["accepted"] for case in dataset["cases"]),
                   rejected_observations=sum(not case["accepted"] for case in dataset["cases"]), normal_controls=sum(case["normal_control"] for case in dataset["cases"]),
                   wall_s_before_publication=time.perf_counter() - started, cpu_s_before_publication=time.process_time() - cpu_started,
                   measured_candidate_training_calls=0, contact_queries=0, repair_baseline_runs=0,
                   missing_measurements=["whole-process generation CPU including imports", "generation peak RSS"],
                   online_inference_cost=None, paired_labels_are_model_results=False)
    event.update(status="completed", attempted_observations=dataset["attempted_observations"], generation_commit=commit,
                 wall_s=dataset["wall_s_before_publication"], cpu_s=dataset["cpu_s_before_publication"])
    write(index_path, dataset)
    write(HERE / "RUN_LOG.json", log)
    print(json.dumps({key: dataset[key] for key in ("attempted_observations", "accepted_observations", "rejected_observations", "wall_s_before_publication")}))


if __name__ == "__main__":
    main()
