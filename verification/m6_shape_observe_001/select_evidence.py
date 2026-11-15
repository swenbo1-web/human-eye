"""Select six witnesses from the frozen failure record before new retrieval."""

import os
for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import ctypes
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
OPT = HERE.parent / "m6_shape_opt_001"
TRAIN = HERE.parent / "m6_shape_train_001"
DATA = HERE.parent / "m6_shape_data_001"
sys.path.append(str(TRAIN))
from data_io import cases_at, load_sample


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def own_resources():
    sys.path.insert(0, str(OPT))
    from process_runner import process_metrics
    ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    return process_metrics(ctypes.windll.kernel32.GetCurrentProcess())


def main():
    started, cpu_started = time.perf_counter(), time.process_time()
    output = HERE / "EVIDENCE_PLAN.json"
    if output.exists():
        raise RuntimeError("evidence_selection_already_frozen")
    cases = sorted(cases_at(DATA / "DATASET_INDEX.json")
                   + cases_at(TRAIN / "PUBLIC_DATASET_INDEX.json", "validation"), key=lambda c: c["id"])
    previous = json.loads((OPT / "EVAL_FINAL_HARD.json").read_bytes())
    predictions = {case["id"]: case for group in ("development", "validation")
                   for case in previous[group]["cases"]}
    read_seconds = 0.0

    def load(case):
        nonlocal read_seconds
        before = time.perf_counter()
        root = DATA / "private/patches" if case["purpose"] == "development_train_pool" else TRAIN / "private/public_data/patches"
        sample = load_sample(case, root)
        with np.load(predictions[case["id"]]["component_path"], allow_pickle=False) as saved:
            scores = saved["p"].copy()
        sample["p"] = scores
        read_seconds += time.perf_counter() - before
        return sample

    def record(case, sample, index, kind, case_energy):
        source_id = int(sample["mapping"]["context_source_ids"][index])
        target = (sample["reference"] - sample["observed"]) / sample["scale"]
        return {"evidence_id": kind, "case_id": case["id"], "id": case["id"],
                "source": case["source"], "purpose": case["purpose"],
                "position_group": case.get("position_group", "center"),
                "local_index": int(index), "source_vertex_id": source_id,
                "support_label": bool(sample["labels"]["damaged_mask"][index]),
                "frozen_score": float(sample["p"][index]),
                "target_norm_over_observed_scale": float(np.linalg.norm(target[index])),
                "case_target_energy": case_energy,
                "paired_normal_case_id": case["patch_id"] + "/sample_00",
                "old_component_path": predictions[case["id"]]["component_path"],
                "old_component_sha256": sha256(predictions[case["id"]]["component_path"])}

    selections = []
    for source in ("Yanyite", "Richie", "Chipow", "Yunhex"):
        candidates = []
        for case in cases:
            if case["source"] != source or not case["normal_control"]:
                continue
            sample = load(case)
            indices = np.flatnonzero(sample["graph"]["free_mask"])
            source_ids = sample["mapping"]["context_source_ids"][indices]
            ordering = np.lexsort((source_ids, -sample["p"][indices].astype(np.float64)))
            index = int(indices[ordering[0]])
            candidates.append((-float(sample["p"][index]), case["id"],
                               int(sample["mapping"]["context_source_ids"][index]), case, sample, index))
        winner = min(candidates, key=lambda row: row[:3])
        selections.append(record(winner[3], winner[4], winner[5], "development_" + source, 0.0))
    for position in ("center", "offcenter"):
        candidates = []
        for case in cases:
            if case["purpose"] != "validation" or case["normal_control"] or case.get("position_group", "center") != position:
                continue
            sample = load(case)
            target = (sample["reference"] - sample["observed"]) / sample["scale"]
            energy = np.einsum("ij,ij->i", target, target)
            indices = np.flatnonzero(sample["labels"]["damaged_mask"])
            source_ids = sample["mapping"]["context_source_ids"][indices]
            ordering = np.lexsort((source_ids, -energy[indices]))
            index = int(indices[ordering[0]])
            candidates.append((-float(energy.sum()), case["id"],
                               int(sample["mapping"]["context_source_ids"][index]), case, sample, index))
        winner = min(candidates, key=lambda row: row[:3])
        selections.append(record(winner[3], winner[4], winner[5], "validation_" + position, -winner[0]))
    identities = {case_id for row in selections for case_id in (row["case_id"], row["paired_normal_case_id"])}
    report = {"cycle_id": "M6-SHAPE-OBSERVE-001", "status": "preselected_from_old_failure_records",
              "source_result_sha256": sha256(OPT / "EVAL_FINAL_HARD.json"),
              "selection_rule": "per local member max frozen p on normal-control free points; validation position max normalized target energy case then max target energy point; ties case_id/source_vertex_id",
              "energy_definition": "sum of squared binary64 reference-minus-observed displacement divided by observed scale squared",
              "evidence": selections, "selections": selections,
              "evidence_count": 6, "unique_forward_case_count_planned": len(identities),
              "maximum_forward_calls": 12,
              "duplicate_normal_pair_policy": "reuse an identical case forward within the frozen case cache",
              "new_descriptor_or_retrieval_results_read": 0, "model_forward_calls": 0,
              "training_updates": 0, "threshold_candidates": 0, "Bunny_arrays_loaded": 0,
              "costs": {"read_arrays_wall_s": read_seconds, "main_wall_s": time.perf_counter() - started,
                        "main_cpu_s": time.process_time() - cpu_started, "own_process": own_resources()}}
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"evidence": [{k: row[k] for k in ("evidence_id", "case_id", "source_vertex_id", "frozen_score", "case_target_energy")} for row in selections],
                      "unique_forward_cases": len(identities), "wall_s": report["costs"]["main_wall_s"]}))


if __name__ == "__main__":
    main()
