"""Relocatable array loading with an explicit observation/label boundary."""
import json
from pathlib import Path

import numpy as np


INPUT_KEYS = ("node_features", "edge_features", "positions", "normals")


def cases_at(index_path, purpose=None):
    cases = json.loads(Path(index_path).read_bytes())["cases"]
    return [case for case in cases if purpose is None or case["purpose"] == purpose]


def load_sample(case, patch_root, with_labels=True):
    if case.get("purpose") == "reserved_test":
        raise ValueError("reserved_test_scoring_is_locked_for_this_batch")
    sample_name = case.get("sample_name", Path(case["input"]["path"]).stem)
    folder = Path(patch_root) / case["patch_id"]
    with np.load(folder / "inputs" / (sample_name + ".npz"), allow_pickle=False) as saved:
        inputs = {name: saved[name].copy() for name in INPUT_KEYS}
        scale = float(saved["scale_m"])
        origin = saved["origin_world_m"].copy()
    with np.load(folder / "graph.npz", allow_pickle=False) as saved:
        graph = {name: saved[name].copy() for name in ("edge_index", "allowed_mask", "boundary_mask", "free_mask")}
    observed = np.load(folder / "observed" / (sample_name + ".npy"), allow_pickle=False)
    sample = {"case": case, "inputs": inputs, "graph": graph, "scale": scale, "origin": origin,
              "observed": observed, "folder": folder, "sample_name": sample_name}
    if with_labels:
        with np.load(folder / "labels" / (sample_name + ".npz"), allow_pickle=False) as saved:
            sample["labels"] = {name: saved[name].copy() for name in saved.files}
        sample["reference"] = np.load(folder / "reference_local.npy", allow_pickle=False)
        with np.load(folder / "mapping.npz", allow_pickle=False) as saved:
            sample["mapping"] = {name: saved[name].copy() for name in saved.files}
    return sample


def fit_standardization(samples):
    if any(sample["case"]["purpose"] != "development_train_pool" for sample in samples):
        raise ValueError("standardization_must_use_training_observations_only")
    node = np.concatenate([sample["inputs"]["node_features"][:, :5] for sample in samples]).astype(np.float64)
    edge = np.concatenate([sample["inputs"]["edge_features"] for sample in samples]).astype(np.float64)
    return {"node_mean": node.mean(axis=0), "node_std": np.maximum(node.std(axis=0), 1e-6),
            "edge_mean": edge.mean(axis=0), "edge_std": np.maximum(edge.std(axis=0), 1e-6)}


def forward_arrays(sample, stats):
    node = sample["inputs"]["node_features"].copy()
    node[:, :5] = (node[:, :5] - stats["node_mean"]) / stats["node_std"]
    edge = ((sample["inputs"]["edge_features"] - stats["edge_mean"]) / stats["edge_std"]).astype(np.float32)
    return (node, edge, sample["inputs"]["positions"], sample["inputs"]["normals"],
            sample["graph"]["edge_index"], sample["graph"]["free_mask"])


def forward_tensors(sample, stats):
    import torch
    return tuple(torch.from_numpy(np.ascontiguousarray(value)) for value in forward_arrays(sample, stats))


def batch_samples(samples, stats):
    import torch
    fields = [[] for _ in range(6)]
    targets, allowed, damaged, normal_free, graph_ids = [], [], [], [], []
    offset = 0
    for graph_id, sample in enumerate(samples):
        values = list(forward_arrays(sample, stats))
        values[4] = values[4] + offset
        for index, value in enumerate(values):
            fields[index].append(value)
        count = len(values[0])
        targets.append(sample["labels"]["target_normalized"])
        allowed.append(sample["graph"]["allowed_mask"])
        damaged.append(sample["labels"]["damaged_mask"])
        normal_free.append(sample["labels"]["normal_free_mask"])
        graph_ids.append(np.full(count, graph_id, dtype=np.int64))
        offset += count
    tensors = tuple(torch.from_numpy(np.ascontiguousarray(np.concatenate(values, axis=1 if index == 4 else 0))) for index, values in enumerate(fields))
    supervision = {"target": torch.from_numpy(np.concatenate(targets)), "allowed_mask": torch.from_numpy(np.concatenate(allowed)),
                   "damaged_mask": torch.from_numpy(np.concatenate(damaged)), "normal_free_mask": torch.from_numpy(np.concatenate(normal_free)),
                   "edge_index": tensors[4], "graph_index": torch.from_numpy(np.concatenate(graph_ids))}
    return tensors, supervision


def candidate_from_prediction(sample, prediction):
    prediction = np.asarray(prediction, dtype=np.float64)
    if prediction.shape != sample["observed"].shape or not np.isfinite(prediction).all():
        raise ValueError("invalid_normalized_prediction")
    candidate = sample["observed"].copy()
    free = sample["graph"]["free_mask"]
    correction = prediction * sample["scale"]
    active = free[:, None] & (correction != 0)
    candidate[active] += correction[active]
    return candidate
