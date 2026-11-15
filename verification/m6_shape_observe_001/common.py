"""Fixed observation-only loading and label-independent query selection."""

import importlib.util
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "m6_shape_data_001"
TRAIN = HERE.parent / "m6_shape_train_001"
OPT = HERE.parent / "m6_shape_opt_001"
spec = importlib.util.spec_from_file_location("_m6_observe_data_io", TRAIN / "data_io.py")
data_io = importlib.util.module_from_spec(spec)
spec.loader.exec_module(data_io)
_old_records = None


def cases():
    development = data_io.cases_at(DATA / "DATASET_INDEX.json")
    validation = data_io.cases_at(TRAIN / "PUBLIC_DATASET_INDEX.json", "validation")
    result = sorted(development + validation, key=lambda case: case["id"])
    if len(result) != 348 or any(case["purpose"] == "reserved_test" for case in result):
        raise ValueError("fixed_observation_scope_mismatch")
    return result


def load_case(case):
    global _old_records
    if case["purpose"] == "development_train_pool":
        patch_root = DATA / "private/patches"
    elif case["purpose"] == "validation" and case["source"] == "Stanford_Armadillo":
        patch_root = TRAIN / "private/public_data/patches"
    else:
        raise ValueError("observation_outside_fixed_scope")
    sample = data_io.load_sample(case, patch_root, with_labels=True)
    if _old_records is None:
        final = json.loads((OPT / "EVAL_FINAL_HARD.json").read_bytes())
        _old_records = {row["id"]: row for group in ("development", "validation")
                        for row in final[group]["cases"]}
    with np.load(_old_records[case["id"]]["component_path"], allow_pickle=False) as saved:
        components = {name: saved[name].copy() for name in ("u", "z", "p")}
    sample["components"] = components
    sample["p"] = components["p"]
    sample["source_ids"] = sample["mapping"]["context_source_ids"]
    sample["target_float64"] = (sample["reference"] - sample["observed"]) / sample["scale"]
    return sample


def sample_indices(sample):
    free = np.flatnonzero(sample["graph"]["free_mask"])
    ordered = free[np.argsort(sample["source_ids"][free], kind="stable")]
    count = min(64, len(ordered))
    if count == 0:
        return ordered
    if count == 1:
        return ordered[:1]
    ranks = np.arange(count, dtype=np.int64) * (len(ordered) - 1) // (count - 1)
    return ordered[ranks]
