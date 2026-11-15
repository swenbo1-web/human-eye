"""Build complete observed source inputs from saved current values and task IDs."""

import time
BOOT_WALL, BOOT_CPU = time.perf_counter(), time.process_time()

import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / "m6_shape_data_001"
TRAIN = HERE.parent / "m6_shape_train_001"


def main():
    started, cpu = time.perf_counter(), time.process_time()
    used = {}

    def record(path, expected=None):
        path = Path(path)
        data = path.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        if expected is not None and sha != expected:
            raise ValueError("old_input_identity_mismatch_" + str(path))
        used[str(path)] = {"path": str(path), "bytes": len(data), "sha256": sha}
        return used[str(path)]

    cases = []
    for path in (OLD / "DATASET_INDEX.json", TRAIN / "PUBLIC_DATASET_INDEX.json"):
        record(path)
        cases.extend(json.loads(path.read_bytes())["cases"])
    old_cases = {row["id"]: row for row in cases if row["purpose"] != "reserved_test"}
    sources = {}
    for path in (OLD / "SOURCE_AUDIT.json", TRAIN / "PUBLIC_SOURCES.json"):
        record(path)
        sources.update({row["name"]: row for row in json.loads(path.read_bytes())["sources"]
                        if row["name"] != "Stanford_Bunny"})
    selected = sorted(json.loads((HERE / "CASE_SELECTION.json").read_bytes())["cases"], key=lambda row: row["id"])
    snapshots, rows = {}, []
    source_read_wall = construction_wall = save_wall = 0.0
    for chosen in selected:
        row = old_cases[chosen["id"]]
        source = row["source"]
        before = time.perf_counter()
        if source not in snapshots:
            source_record = sources[source]["snapshot"]
            record(source_record["path"], source_record["sha256"])
            with np.load(source_record["path"], allow_pickle=False) as saved:
                snapshots[source] = np.asarray(saved["vertices"], dtype=np.float64)
        folder = Path(row["observed"]["path"]).parents[1]
        record(row["observed"]["path"], row["observed"]["sha256"])
        record(folder / "mapping.npz")
        record(folder / "graph.npz")
        observed = np.load(row["observed"]["path"], allow_pickle=False)
        with np.load(folder / "mapping.npz", allow_pickle=False) as saved:
            context = saved["context_source_ids"].astype(np.int64)
        with np.load(folder / "graph.npz", allow_pickle=False) as saved:
            free_mask = saved["free_mask"].astype(bool)
        source_read_wall += time.perf_counter() - before
        before = time.perf_counter()
        full = snapshots[source].copy()
        if observed.shape != full[context].shape or observed.dtype != np.float64:
            raise ValueError("old_observed_geometry_shape_or_dtype_changed")
        full[context] = observed
        free_ids = np.sort(context[free_mask])
        if len(free_ids) != row["free_vertices"] or len(context) != row["context_vertices"]:
            raise ValueError("task_domain_count_mismatch")
        fixed_ids = np.ones(len(full), dtype=bool)
        fixed_ids[free_ids] = False
        if not np.array_equal(full[fixed_ids], snapshots[source][fixed_ids]):
            raise ValueError("observation_changed_outside_task_free_domain")
        construction_wall += time.perf_counter() - before
        before = time.perf_counter()
        patch, sample = row["id"].split("/")
        path = HERE / "private/inference_inputs" / patch / (sample + ".npz")
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, vertices=full, free_source_ids=free_ids, context_source_ids=context)
        data = path.read_bytes()
        rows.append({"id": row["id"], "path": str(path), "sha256": hashlib.sha256(data).hexdigest(),
                     "bytes": len(data), "full_source_vertices": len(full), "free_vertices": len(free_ids),
                     "context_vertices": len(context)})
        save_wall += time.perf_counter() - before
    report = {"cycle_id": "M6-SHAPE-PRETRAIN-001", "status": "completed_inference_inputs",
              "cases": rows, "case_count": len(rows), "NPZ_keys": ["vertices", "free_source_ids", "context_source_ids"],
              "inference_package_reference_label_support_or_target_normal_fields": 0,
              "complete_source_count": len(snapshots), "Bunny_arrays_read": 0,
              "model_forwards": 0, "training": 0,
              "timings": {"old_metadata_source_observed_mapping_read_wall_s": source_read_wall,
                          "full_observed_construction_wall_s": construction_wall, "NPZ_save_hash_wall_s": save_wall},
              "wall_s_before_final_write": time.perf_counter() - started,
              "CPU_s_before_final_write": time.process_time() - cpu,
              "bootstrap_to_report_wall_s": time.perf_counter() - BOOT_WALL,
              "bootstrap_to_report_CPU_s": time.process_time() - BOOT_CPU}
    (HERE / "INPUT_INDEX.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf8", newline="\n")
    (HERE / "INPUT_PROVENANCE.json").write_text(json.dumps({"files": list(used.values()),
              "scope": "Only current observation/mapping/free graph/source arrays were read; no label/reference array deserialization"}, indent=2) + "\n", encoding="utf8", newline="\n")
    print(json.dumps({"case_count": len(rows), "complete_sources": len(snapshots), "old_files": len(used)}))


if __name__ == "__main__":
    main()
