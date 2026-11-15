"""Extract the frozen official Pointfilter encoder features for all fixed F."""

import time
BOOT_WALL, BOOT_CPU = time.perf_counter(), time.process_time()

import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from head import adapter, configure_torch, file_record, load_frozen_encoder, measure, process_resources, tensor_digest, write_json
import numpy as np
import torch


def main():
    started, cpu = time.perf_counter(), time.process_time()
    configure_torch()
    if (HERE / "FEATURES.json").exists():
        raise RuntimeError("feature_report_exists_inspect_before_explicit_recovery")
    timings, used = {}, {}

    def old_file(path, expected=None):
        record = file_record(path)
        if expected is not None and record["sha256"] != expected:
            raise ValueError("old_input_hash_changed_" + str(path))
        used[str(Path(path))] = record
        return Path(path)

    with measure(timings, "frozen_plan_and_whitelist_read"):
        for row in json.loads((HERE / "PLAN_FREEZE.json").read_bytes())["files"]:
            if file_record(HERE / row["path"])["sha256"] != row["sha256"]:
                raise ValueError("frozen_plan_changed_" + row["path"])
        cases = sorted(json.loads((HERE / "INPUT_WHITELIST.json").read_bytes())["cases"], key=lambda row: row["id"])
        if len(cases) != 348 or any("Bunny" in row["source"] for row in cases):
            raise ValueError("fixed348_without_Bunny_required")
    with measure(timings, "official_PCA_import"):
        pca = adapter.load_official_pca()
    model, decoder_guard, checkpoint = load_frozen_encoder(timings)
    initial_digest = tensor_digest(model.encoder.state_dict())
    if sum(value.numel() for value in model.encoder.parameters()) != 702464:
        raise ValueError("official_encoder_parameter_count_changed")
    model_folder = HERE / "private/model"
    model_folder.mkdir(parents=True, exist_ok=True)
    initial_path = model_folder / "encoder_initial.pth"
    torch.save(model.encoder.state_dict(), initial_path)
    report = {"cycle_id": "M6-PERCEPTION-001", "status": "running", "cases": [], "failures": [],
              "requested_cases": 348, "encoder_parameters": sum(value.numel() for value in model.encoder.parameters()),
              "full_upstream_checkpoint_parameters": sum(value.numel() for value in model.parameters()),
              "encoder_initial_tensor_sha256": initial_digest, "encoder_initial_checkpoint": file_record(initial_path),
              "official_checkpoint": checkpoint, "timings": timings, "seed": 1729,
              "decoder_forward_calls": 0, "training": 0, "reference_or_label_arrays_read": 0, "Bunny_arrays": 0,
              "schema": "float32 features(N,1024), F source/context IDs and validity mask; actual sampling/PCA details separately private",
              "source_sha256": {name: file_record(HERE / name)["sha256"] for name in ("features.py", "head.py")},
              "reused_source_sha256": {str(adapter.HERE / "adapter.py"): file_record(adapter.HERE / "adapter.py")["sha256"]}}
    sources, patches = {}, {}
    for case in cases:
        case_started, case_cpu = time.perf_counter(), time.process_time()
        case_timings = {}
        with measure(case_timings, "source_and_task_domain_read"):
            if case["source"] not in sources:
                source_record = case["snapshot"]
                path = old_file(source_record["path"], source_record["sha256"])
                with np.load(path, allow_pickle=False) as package:
                    sources[case["source"]] = package["vertices"].astype(np.float64)
            if case["patch_id"] not in patches:
                with np.load(old_file(case["mapping_path"]), allow_pickle=False) as package:
                    context = package["context_source_ids"].astype(np.int64)
                with np.load(old_file(case["graph_path"]), allow_pickle=False) as package:
                    free_context = np.flatnonzero(package["free_mask"])
                free_context = free_context[np.argsort(context[free_context])]
                patches[case["patch_id"]] = (context, free_context, context[free_context])
            context, free_context, free_source = patches[case["patch_id"]]
            observed_path = old_file(case["observed"]["path"], case["observed"]["sha256"])
            observed = np.load(observed_path, allow_pickle=False)
            with np.load(old_file(case["input"]["path"], case["input"]["sha256"]), allow_pickle=False) as package:
                ell = float(package["scale_m"])
        with measure(case_timings, "full_current_source_construction"):
            vertices = sources[case["source"]].copy()
            vertices[context] = observed
        detail = adapter.prepare_neighborhoods(vertices, free_source, np.random.RandomState(1729), pca, case_timings)
        valid = detail["query_status_codes"] == 0
        feature = np.zeros((len(free_source), 1024), dtype=np.float32)
        batches = 0
        with torch.inference_mode():
            rows = np.flatnonzero(valid)
            for start in range(0, len(rows), 64):
                selected = rows[start:start + 64]
                with measure(case_timings, "encoder_input_conversion"):
                    tensor = torch.from_numpy(detail["normalized_points"][selected]).transpose(2, 1).contiguous()
                with measure(case_timings, "encoder_forward"):
                    value = model.encoder(tensor)
                    batches += 1
                with measure(case_timings, "encoder_output_validation"):
                    if value.shape != (len(selected), 1024):
                        raise ValueError("encoder_output_shape_changed")
                    finite = torch.isfinite(value).all(dim=1).numpy()
                    feature[selected[finite]] = value[finite].numpy()
                    valid[selected[~finite]] = False
                    detail["query_status_codes"][selected[~finite]] = 2
        with measure(case_timings, "feature_and_sampling_cache_save_hash"):
            path = HERE / "private/features" / (case["id"] + ".npz")
            detail_path = HERE / "private/sampling" / (case["id"] + ".npz")
            path.parent.mkdir(parents=True, exist_ok=True)
            detail_path.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(path, features=feature, free_source_ids=free_source,
                                free_context_ids=free_context, valid_mask=valid)
            np.savez_compressed(detail_path, **detail)
            row = {key: case[key] for key in ("id", "patch_id", "source", "purpose", "normal_control", "position_group")}
            detail_record = file_record(detail_path)
            row.update(file_record(path), detail_path=str(detail_path), detail_sha256=detail_record["sha256"],
                       detail_bytes=detail_record["bytes"],
                       points=len(free_source), valid_points=int(np.count_nonzero(valid)),
                       unavailable_points=int(np.count_nonzero(~valid)), ell=ell,
                       free_ids_sha256=hashlib.sha256(free_source.tobytes()).hexdigest(),
                       neighbor_count={"min": int(detail["neighbor_count"].min()), "median": float(np.median(detail["neighbor_count"])), "max": int(detail["neighbor_count"].max())},
                       sampling_duplicate_total=int(detail["sampling_duplicate_count"].sum()),
                       radius_native=float(detail["radius"]), encoder_forward_batches=batches,
                       timings=case_timings, full_case_wall_s=time.perf_counter() - case_started,
                       full_case_CPU_s=time.process_time() - case_cpu, resources_at_end=process_resources())
        report["cases"].append(row)
        if row["unavailable_points"]:
            report["failures"].append({"id": row["id"], "unavailable_points": row["unavailable_points"],
                                       "reason": "query status1 fewerthan3 neighbors or status2 nonfinite encoder features"})
        for name, values in case_timings.items():
            target = timings.setdefault(name, {"wall_s": 0.0, "CPU_s": 0.0, "calls": 0})
            for key in target:
                target[key] += values[key]
        report.update(case_count=len(report["cases"]), decoder_forward_calls=decoder_guard["decoder_forward_calls"],
                      bootstrap_to_progress_wall_s=time.perf_counter() - BOOT_WALL)
        write_json("FEATURES.json", report)
        print(json.dumps({"case": row["id"], "points": row["points"], "available": row["valid_points"]}), flush=True)
    final_digest = tensor_digest(model.encoder.state_dict())
    if initial_digest != final_digest or decoder_guard["decoder_forward_calls"]:
        raise ValueError("encoder_state_mutated_or_decoder_executed")
    final_path = model_folder / "encoder_after_features.pth"
    torch.save(model.encoder.state_dict(), final_path)
    report.update(status="completed_fixed348_encoder_features", case_count=348,
                  total_query_points=sum(row["points"] for row in report["cases"]),
                  encoder_forward_batches=sum(row["encoder_forward_batches"] for row in report["cases"]),
                  encoder_final_tensor_sha256=final_digest, encoder_after_features_checkpoint=file_record(final_path),
                  input_file_identities=list(used.values()),
                  feature_cache_bytes=sum(row["bytes"] for row in report["cases"]),
                  feature_raw_array_bytes=sum(row["points"] * 1024 * 4 for row in report["cases"]),
                  sampling_cache_bytes=sum(row["detail_bytes"] for row in report["cases"]),
                  wall_s_before_final_report=time.perf_counter() - started, CPU_s_before_final_report=time.process_time() - cpu,
                  bootstrap_wall_s_before_final_report=time.perf_counter() - BOOT_WALL,
                  bootstrap_CPU_s_before_final_report=time.process_time() - BOOT_CPU,
                  own_process_before_report=process_resources())
    write_json("FEATURES.json", report)


if __name__ == "__main__":
    main()
