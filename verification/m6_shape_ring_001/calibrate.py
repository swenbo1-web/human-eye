"""Freeze q90 seeds and q95 patch-max operating points on 33 normal patches."""

import time
BOOT_WALL, BOOT_CPU = time.perf_counter(), time.process_time()

import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from ring_metrics import CONFIGURATIONS, component_scores, measure, process_resources
import numpy as np


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf8", newline="\n")


def main():
    started, cpu = time.perf_counter(), time.process_time()
    if (HERE / "CALIBRATION.json").exists():
        raise RuntimeError("calibration_already_exists_inspect_before_any_recovery")
    timings = {}
    with measure(timings, "normal_residual_index_read"):
        index = json.loads((HERE / "RESIDUALS.json").read_bytes())
        selected = [row for row in index["cases"] if row["purpose"] == "development_train_pool" and row["normal_control"]]
        if len(selected) != 33 or len({row["patch_id"] for row in selected}) != 33:
            raise ValueError("calibration_requires_exactly33_development_normal_patches")
        arrays, identities = {}, []
        for row in selected:
            path = Path(row["path"])
            data = path.read_bytes()
            sha = hashlib.sha256(data).hexdigest()
            if sha != row["sha256"]:
                raise ValueError("normal_residual_identity_changed")
            with np.load(path, allow_pickle=False) as saved:
                arrays[row["id"]] = {key: saved[key].copy() for key in ("solid_r", "ring_r", "area", "free_edge_index", "free_source_ids")}
            identities.append({"path": str(path), "bytes": len(data), "sha256": sha})
    with measure(timings, "normal_F_q90_seed_calibration"):
        seed = {branch: float(np.quantile(np.concatenate([np.abs(arrays[row["id"]][branch + "_r"]) / row["ell"]
                for row in selected]), .90, method="linear")) for branch in ("solid", "ring")}
    cases, maxima = [], {configuration: [] for configuration in CONFIGURATIONS}
    for row in selected:
        values, ell = arrays[row["id"]], row["ell"]
        payload = {"free_source_ids": values["free_source_ids"]}
        record = {"id": row["id"], "patch_id": row["patch_id"], "free_points": len(values["area"]), "ell": ell,
                  "clusters": {}, "maximum_scores": {}}
        for branch in ("solid", "ring"):
            with measure(timings, branch + "_normal_point_scores"):
                payload[branch + "_point"] = np.abs(values[branch + "_r"]) / ell
            with measure(timings, branch + "_normal_components_and_scores"):
                scores, component_ids, clusters = component_scores(values[branch + "_r"], values["area"], ell,
                                                                    values["free_edge_index"], seed[branch])
                payload[branch + "_cluster"] = scores
                payload[branch + "_component_ids"] = component_ids
                record["clusters"][branch] = clusters
        for configuration in CONFIGURATIONS:
            maximum = float(np.max(payload[configuration])) if len(values["area"]) else 0.0
            maxima[configuration].append(maximum)
            record["maximum_scores"][configuration] = maximum
        with measure(timings, "normal_score_save_and_hash"):
            path = HERE / "private/calibration" / (row["patch_id"] + ".npz")
            path.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(path, **payload)
            data = path.read_bytes()
            record.update(path=str(path), sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
        cases.append(record)
    with measure(timings, "patch_max_q95_operating_calibration"):
        operating = {configuration: float(np.quantile(maxima[configuration], .95, method="linear")) for configuration in CONFIGURATIONS}
        false_patches = {configuration: [row["id"] for row in cases if row["maximum_scores"][configuration] > operating[configuration]]
                         for configuration in CONFIGURATIONS}
    report = {"cycle_id": "M6-SHAPE-RING-001", "status": "completed_once_development_normal_calibration",
              "calibration_count": 1, "normal_patches": 33,
              "normal_F_points": sum(row["free_points"] for row in cases),
              "source_case_ids": [row["id"] for row in selected], "cases": cases,
              "seed_thresholds": seed, "operating_thresholds": operating,
              "normal_patch_maxima": maxima, "calibration_normal_false_patch_ids": false_patches,
              "quantile_method": "linear", "selection_comparison": "strictly_greater_than_threshold",
              "invalid_fit_policy": "zero score with all F retained", "minimum_component_vertices": 5,
              "calibration_scope": "same33 development normal controls define both thresholds, actual training false alarm counts are descriptive; validation never used",
              "input_file_identities": identities, "timings": timings,
              "source_sha256": {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest() for name in ("calibrate.py", "ring_metrics.py")},
              "wall_s_before_final_write": time.perf_counter() - started,
              "CPU_s_before_final_write": time.process_time() - cpu,
              "bootstrap_to_report_wall_s": time.perf_counter() - BOOT_WALL,
              "bootstrap_to_report_CPU_s": time.process_time() - BOOT_CPU,
              "own_process_before_report": process_resources(), "reference_or_label_arrays_read": 0,
              "model_forwards": 0, "training": 0, "repair_outputs": 0, "Bunny_arrays": 0}
    write(HERE / "CALIBRATION.json", report)
    files = [{"path": str(HERE / "CALIBRATION.json"), "sha256": hashlib.sha256((HERE / "CALIBRATION.json").read_bytes()).hexdigest()}]
    files.extend({"path": row["path"], "sha256": row["sha256"]} for row in cases)
    files.extend({"path": row["path"], "sha256": row["sha256"]} for row in identities)
    write(HERE / "CALIBRATION_FREEZE.json", {"cycle_id": report["cycle_id"], "before_validation_evaluation": True, "files": files})
    print(json.dumps({"status": report["status"], "normal_patches": 33, "seed": seed, "operating": operating}))


if __name__ == "__main__":
    main()
