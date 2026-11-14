"""Check real training-array batching, loss denominators and root relocation."""
import json
from pathlib import Path
import shutil
import sys

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from data_io import batch_samples, cases_at, fit_standardization, load_sample
from model import graph_loss


def main():
    torch.set_num_threads(1)
    root = HERE.parent / "m6_shape_data_001"
    cases = cases_at(root / "DATASET_INDEX.json")
    chosen = [cases[0], next(case for case in cases if case["source"] == "Richie" and case["id"].endswith("sample_01"))]
    samples = [load_sample(case, root / "private/patches") for case in chosen]
    stats = fit_standardization(samples)
    args, labels = batch_samples(samples, stats)
    checks = {}
    checks["batch_nodes_sum"] = len(args[0]) == sum(len(sample["observed"]) for sample in samples)
    checks["no_cross_graph_edges"] = bool(torch.all(labels["graph_index"][args[4][0]] == labels["graph_index"][args[4][1]]))
    loss, records = graph_loss(torch.zeros_like(labels["target"]), **labels)
    for index, (sample, record) in enumerate(zip(samples, records)):
        allowed = sample["graph"]["allowed_mask"]
        support = sample["labels"]["damaged_mask"]
        normal_free = sample["labels"]["normal_free_mask"]
        checks[f"graph{index}_denominators"] = record["denominators"]["A"] == int(allowed.sum()) and record["denominators"]["S"] == int(support.sum()) and record["denominators"]["normal_free"] == int(normal_free.sum())
        error = (sample["labels"]["target_normalized"] ** 2).sum(axis=1)
        checks[f"graph{index}_A_loss"] = abs(record["mse"]["A"] - float(error[allowed].mean())) < 1e-8
    checks["loss_finite"] = bool(torch.isfinite(loss))
    relocated = HERE / "private/qa_relocated"
    sample_name = samples[0]["sample_name"]
    source = samples[0]["folder"]
    destination = relocated / chosen[0]["patch_id"]
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("graph.npz", "mapping.npz", "reference_local.npy"):
        shutil.copyfile(source / name, destination / name)
    for kind, suffix in (("inputs", ".npz"), ("labels", ".npz"), ("observed", ".npy")):
        (destination / kind).mkdir(exist_ok=True)
        shutil.copyfile(source / kind / (sample_name + suffix), destination / kind / (sample_name + suffix))
    metadata = dict(chosen[0])
    metadata["input"] = {"path": "Z:/nonexistent/author_directory/" + sample_name + ".npz"}
    rebuilt = load_sample(metadata, relocated)
    checks["relocated_root_no_author_absolute_path_dependency"] = all(np.array_equal(samples[0]["inputs"][name], rebuilt["inputs"][name]) for name in samples[0]["inputs"])
    reserved = {"purpose": "reserved_test"}
    try:
        load_sample(reserved, HERE / "private/does_not_exist")
        checks["reserved_test_guard_before_array_read"] = False
    except ValueError:
        checks["reserved_test_guard_before_array_read"] = True
    validation_sample = {"case": {"purpose": "validation"}}
    try:
        fit_standardization([validation_sample])
        checks["normalization_train_only_guard"] = False
    except ValueError:
        checks["normalization_train_only_guard"] = True
    assert all(checks.values()), checks
    (HERE / "INTEGRATION_QA.json").write_text(json.dumps({"status": "passed", "checks": checks, "records": records,
                                                        "training_steps": 0, "public_arrays_read": 0}, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
