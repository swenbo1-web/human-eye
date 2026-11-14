"""One fresh-process online measurement for one frozen observation and method."""

import time

BOOT_WALL = time.perf_counter()
BOOT_CPU = time.process_time()

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import sys

for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

NUMPY_START = time.perf_counter(), time.process_time()
import numpy as np
NUMPY_IMPORT = {
    "wall_s": time.perf_counter() - NUMPY_START[0],
    "cpu_s": time.process_time() - NUMPY_START[1],
}

HERE = Path(__file__).resolve().parent
TRAIN = HERE.parent / "m6_shape_train_001"
DATA = HERE.parent / "m6_shape_data_001"
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(TRAIN))
sys.path.insert(2, str(DATA))


def clock():
    return time.perf_counter(), time.process_time()


def elapsed(started):
    return {"wall_s": time.perf_counter() - started[0], "cpu_s": time.process_time() - started[1]}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as saved:
        for chunk in iter(lambda: saved.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def bitwise_equal(first, second):
    return bool(np.array_equal(
        np.ascontiguousarray(first).view(np.uint64),
        np.ascontiguousarray(second).view(np.uint64),
    ))


def own_resources(process_metrics):
    ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    return process_metrics(ctypes.windll.kernel32.GetCurrentProcess())


def selected_case(sample_name):
    identifier = "Stanford_Armadillo_patch_00/" + sample_name
    index = json.loads((TRAIN / "PUBLIC_DATASET_INDEX.json").read_bytes())
    selected = [case for case in index["cases"] if case["id"] == identifier]
    if len(selected) != 1:
        raise ValueError("frozen_online_case_missing_or_duplicated")
    case = selected[0]
    if case["purpose"] != "validation" or case["source"] != "Stanford_Armadillo":
        raise ValueError("online_case_must_be_frozen_Armadillo_validation")
    return {key: case[key] for key in ("id", "patch_id", "source", "purpose", "input")} | {
        "sample_name": sample_name,
    }


def compare_inputs(current, saved, origin, scale):
    differences = {}
    for key in ("node_features", "edge_features", "positions", "normals"):
        if current[key].shape != saved["inputs"][key].shape:
            raise ValueError("dynamic_input_shape_mismatch_" + key)
        if not np.isfinite(current[key]).all():
            raise ValueError("dynamic_input_nonfinite_" + key)
        differences[key] = {
            "maximum_absolute_difference": float(np.max(np.abs(
                current[key].astype(np.float64) - saved["inputs"][key].astype(np.float64)
            ))),
            "exactly_equal": bool(np.array_equal(current[key], saved["inputs"][key])),
        }
    return {
        "whitelist": differences,
        "origin_maximum_absolute_difference": float(np.max(np.abs(origin - saved["origin"]))),
        "scale_absolute_difference": abs(scale - saved["scale"]),
        "all_whitelist_values_exact": all(value["exactly_equal"] for value in differences.values()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method", choices=("model", "mls"), required=True)
    parser.add_argument("--sample", choices=("sample_00", "sample_06", "sample_12"), required=True)
    parser.add_argument("--weights-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    private_root = HERE / "private" / "online"
    if not output.is_relative_to(private_root):
        raise ValueError("online_worker_output_requires_private_online_directory")
    case = selected_case(args.sample)
    patch_root = TRAIN / "private" / "public_data" / "patches"
    snapshot_path = TRAIN / "private/public_data/sources/Stanford_Armadillo/snapshot.npz"
    weights_path = HERE / "private/weights/step_1200.pt"
    normalization_path = HERE / "private/normalization.npz"
    startup = {
        "standard_library_bootstrap": {
            "wall_s": NUMPY_START[0] - BOOT_WALL,
            "cpu_s": NUMPY_START[1] - BOOT_CPU,
        },
        "numpy_import": NUMPY_IMPORT,
    }
    before = clock()
    from data_io import candidate_from_prediction, forward_tensors, load_sample
    from features import observe, prepare_topology
    from process_runner import process_metrics
    startup["observation_modules_import"] = elapsed(before)

    before = clock()
    train_log = json.loads((HERE / "TRAIN_LOG.json").read_bytes())
    final_weights = train_log["final_weights"]
    if train_log["steps_completed"] != 1200 or final_weights["step"] != 1200:
        raise ValueError("online_requires_fixed_1200_step_weights")
    if Path(final_weights["path"]).name != weights_path.name:
        raise ValueError("unexpected_final_checkpoint_basename")
    actual_weights_sha = sha256(weights_path)
    if actual_weights_sha != args.weights_sha256 or actual_weights_sha != final_weights["sha256"]:
        raise ValueError("fixed_weights_SHA256_mismatch")
    loc_calibration_path = HERE / "LOC_CALIBRATION.json"
    mls_calibration_path = TRAIN / "MLS_CALIBRATION.json"
    loc_calibration_sha = sha256(loc_calibration_path)
    mls_calibration_sha = sha256(mls_calibration_path)
    normalization_sha = sha256(normalization_path)
    if normalization_sha != sha256(TRAIN / "private/normalization.npz"):
        raise ValueError("training_normalization_changed_from_frozen_first_round")
    loc_calibration = json.loads(loc_calibration_path.read_bytes())
    if loc_calibration["calibration_count"] != 1 or loc_calibration["free_point_count"] != 10405:
        raise ValueError("online_requires_one_location_calibration_with_frozen_denominator")
    if loc_calibration["normalization_sha256"] != normalization_sha:
        raise ValueError("location_calibration_normalization_identity_mismatch")
    if loc_calibration["weights_sha256"] != actual_weights_sha:
        raise ValueError("location_calibration_weights_identity_mismatch")
    model_tau = float(loc_calibration["tau"])
    if not np.isfinite(model_tau) or not 0.5 <= model_tau <= 1.0:
        raise ValueError("online_location_threshold_out_of_contract")
    startup["frozen_artifact_verification"] = elapsed(before)

    model = None
    stats = None
    tau = None
    library_versions = {"numpy": np.__version__}
    if args.method == "model":
        before = clock()
        import torch
        from model import ResidualExpert
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        torch.use_deterministic_algorithms(True)
        library_versions["torch"] = torch.__version__
        startup["model_import_and_thread_setup"] = elapsed(before)
        tau = model_tau
        before = clock()
        checkpoint = torch.load(weights_path, map_location="cpu", weights_only=True)
        if checkpoint["step"] != 1200 or checkpoint["parameters"] != 6339:
            raise ValueError("unexpected_online_checkpoint_identity")
        model = ResidualExpert()
        model.load_state_dict(checkpoint["model"])
        model.eval()
        del checkpoint
        startup["weights_load_and_model_construct"] = elapsed(before)
        before = clock()
        with np.load(normalization_path, allow_pickle=False) as saved:
            stats = {key: saved[key].copy() for key in ("node_mean", "node_std", "edge_mean", "edge_std")}
        if sum(value.size for value in stats.values()) != 18:
            raise ValueError("online_normalization_requires_18_training_scalars")
        startup["normalization_load"] = elapsed(before)
    else:
        before = clock()
        import mls
        startup["MLS_module_import"] = elapsed(before)
        before = clock()
        calibration = json.loads((TRAIN / "MLS_CALIBRATION.json").read_bytes())
        tau = float(calibration["tau"])
        if calibration["calibration_count"] != 1 or not np.isfinite(tau) or tau < 0:
            raise ValueError("online_requires_one_frozen_MLS_calibration")
        startup["frozen_tau_load"] = elapsed(before)

    report = {
        "task": "M6-SHAPE-OPT-001",
        "status": "incomplete",
        "method": args.method,
        "id": case["id"],
        "units": "native Stanford coordinates, physical unit unspecified",
        "versions": library_versions,
        "weights_sha256_before": actual_weights_sha,
        "location_calibration_sha256_before": loc_calibration_sha,
        "MLS_calibration_sha256_before": mls_calibration_sha,
        "normalization_sha256_before": normalization_sha,
        "tau": tau,
        "model_location_tau": model_tau,
        "gate_semantics": "p > tau for hard output; fixed and halo correction zero",
        "startup": startup,
        "cold_definition": "new Python process; operating-system file caches uncontrolled",
        "warm_definition": "same process, source snapshot and prepared topology reused; full observation preparation and readback repeated",
        "includes_coupling": False,
        "rounds": [],
    }
    source_vertices = triangles = shared = mapping = None
    active_round = None
    try:
        for ordinal in range(4):
            active_round = ordinal
            call_started = clock()
            timings = {}
            before = clock()
            sample = load_sample(case, patch_root, with_labels=False)
            timings["load_observation_and_saved_whitelist"] = elapsed(before)
            if ordinal == 0:
                before = clock()
                with np.load(sample["folder"] / "mapping.npz", allow_pickle=False) as saved:
                    mapping = {key: saved[key].copy() for key in (
                        "context_source_ids", "allowed_source_ids", "boundary_source_ids"
                    )}
                timings["mapping_load"] = elapsed(before)
                before = clock()
                with np.load(snapshot_path, allow_pickle=False) as saved:
                    source_vertices = saved["vertices"].copy()
                    triangles = saved["triangles"].copy()
                if source_vertices.dtype != np.float64 or len(source_vertices) != 172974:
                    raise ValueError("unexpected_Armadillo_source_snapshot")
                timings["source_snapshot_load"] = elapsed(before)
                before = clock()
                shared = prepare_topology(triangles, len(source_vertices), mapping["allowed_source_ids"])
                timings["prepare_static_topology"] = elapsed(before)
                if not np.array_equal(shared["context_ids"], mapping["context_source_ids"]):
                    raise ValueError("rebuilt_context_order_mismatch")
                report["denominators"] = {
                    "full_source_vertices": len(source_vertices),
                    "full_source_triangles": len(triangles),
                    "context_vertices": len(shared["context_ids"]),
                    "allowed_vertices": int(np.count_nonzero(shared["allowed_mask"])),
                    "free_vertices": int(np.count_nonzero(shared["free_mask"])),
                    "boundary_vertices": len(mapping["boundary_source_ids"]),
                }
            before = clock()
            for key in ("edge_index", "allowed_mask", "boundary_mask", "free_mask"):
                if not np.array_equal(shared[key], sample["graph"][key]):
                    raise ValueError("rebuilt_saved_graph_mismatch_" + key)
            context_ids = shared["context_ids"]
            free = shared["free_mask"]
            free_source_ids = context_ids[free]
            full_observed = source_vertices.copy()
            full_observed[context_ids] = sample["observed"]
            timings["full_observation_assembly"] = elapsed(before)

            before = clock()
            dynamic = observe(full_observed, triangles, shared)
            timings["full_dynamic_normals_and_features"] = elapsed(before)
            before = clock()
            current_inputs = {key: dynamic[key] for key in (
                "node_features", "edge_features", "positions", "normals"
            )}
            current_origin = dynamic["origin_world_m"]
            current_scale = float(dynamic["scale_m"])
            alignment = compare_inputs(current_inputs, sample, current_origin, current_scale)
            if (not alignment["all_whitelist_values_exact"]
                    or alignment["origin_maximum_absolute_difference"] != 0.0
                    or alignment["scale_absolute_difference"] != 0.0):
                raise ValueError("online_dynamic_whitelist_or_normalization_frame_mismatch")
            sample["inputs"] = current_inputs
            sample["graph"] = {key: shared[key] for key in (
                "edge_index", "allowed_mask", "boundary_mask", "free_mask"
            )}
            sample["origin"] = current_origin
            sample["scale"] = current_scale
            timings["input_alignment_and_gather"] = elapsed(before)

            diagnostics = None
            if args.method == "model":
                before = clock()
                tensors = forward_tensors(sample, stats)
                timings["standardize_and_tensorize"] = elapsed(before)
                before = clock()
                with torch.inference_mode():
                    prediction = model.hard_prediction(*tensors, tau=tau).cpu().numpy().copy()
                timings["forward_and_output_conversion"] = elapsed(before)
            else:
                before = clock()
                residual, applicable, diagnostics = mls.fit_residuals(
                    current_inputs["positions"], current_inputs["normals"],
                    shared["edge_index"], free,
                )
                timings["MLS_fit"] = elapsed(before)
                before = clock()
                prediction = mls.gate_displacement(
                    current_inputs["normals"], residual, applicable, free, tau
                )
                timings["MLS_gate"] = elapsed(before)
            if np.any(prediction[~free] != 0):
                raise ValueError("online_prediction_writes_fixed_vertices")

            before = clock()
            local_candidate = candidate_from_prediction(sample, prediction)
            full_candidate = full_observed.copy()
            full_candidate[free_source_ids] = local_candidate[free]
            timings["candidate_restore_full_binary64"] = elapsed(before)
            candidate_path = output.parent / f"round_{ordinal:02d}_full.npy"
            before = clock()
            np.save(candidate_path, full_candidate, allow_pickle=False)
            timings["save_full_candidate"] = elapsed(before)
            before = clock()
            readback = np.load(candidate_path, allow_pickle=False)
            timings["load_full_readback"] = elapsed(before)
            before = clock()
            outside_free = np.ones(len(full_observed), dtype=bool)
            outside_free[free_source_ids] = False
            if readback.dtype != np.float64 or readback.shape != full_observed.shape:
                raise ValueError("full_candidate_readback_dtype_or_shape_mismatch")
            preservation = {
                "full_readback_bitwise_equal": bitwise_equal(readback, full_candidate),
                "boundary_bitwise_preserved": bitwise_equal(
                    readback[mapping["boundary_source_ids"]],
                    full_observed[mapping["boundary_source_ids"]],
                ),
                "all_outside_free_bitwise_preserved": bitwise_equal(
                    readback[outside_free], full_observed[outside_free]
                ),
                "outside_free_vertices": int(np.count_nonzero(outside_free)),
            }
            if not all(preservation[key] for key in (
                "full_readback_bitwise_equal", "boundary_bitwise_preserved",
                "all_outside_free_bitwise_preserved",
            )):
                raise ValueError("full_candidate_readback_preservation_failure")
            artifact = {
                "path": str(candidate_path),
                "file_bytes": candidate_path.stat().st_size,
                "array_bytes": int(readback.nbytes),
                "sha256": sha256(candidate_path),
            }
            timings["readback_verify_and_hash"] = elapsed(before)
            before = clock()
            changes = np.linalg.norm(readback[free_source_ids] - full_observed[free_source_ids], axis=1)
            changed_rows = np.any(
                readback[free_source_ids].view(np.uint64)
                != full_observed[free_source_ids].view(np.uint64), axis=1,
            )
            change_summary = {
                "changed_free_vertices": int(np.count_nonzero(changed_rows)),
                "free_change_max_native": float(np.max(changes)),
                "free_change_p95_native": float(np.quantile(changes, 0.95)),
                "free_change_max_over_scale": float(np.max(changes)) / current_scale,
            }
            timings["observed_change_summary"] = elapsed(before)
            round_record = {
                "ordinal": ordinal,
                "mode": "cold" if ordinal == 0 else "warm",
                "static_source_and_graph_reused": ordinal > 0,
                "input_alignment": alignment,
                "scale_native": current_scale,
                "timings": timings,
                "full_call": elapsed(call_started),
                "artifact": artifact,
                "preservation": preservation,
                "observed_changes": change_summary,
                "at_end_resources": own_resources(process_metrics),
            }
            if diagnostics is not None:
                round_record["MLS_diagnostics"] = diagnostics
            report["rounds"].append(round_record)
            if ordinal == 0:
                report["cold_start_to_first_complete"] = elapsed((BOOT_WALL, BOOT_CPU))
            write_json(output, report)
        report["status"] = "complete"
    except Exception as error:
        report["failed_round"] = active_round
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        report["weights_sha256_after"] = sha256(weights_path)
        report["weights_unchanged"] = report["weights_sha256_after"] == actual_weights_sha
        report["location_calibration_sha256_after"] = sha256(loc_calibration_path)
        report["MLS_calibration_sha256_after"] = sha256(mls_calibration_path)
        report["normalization_sha256_after"] = sha256(normalization_path)
        report["calibrations_and_normalization_unchanged"] = (
            report["location_calibration_sha256_after"] == loc_calibration_sha
            and report["MLS_calibration_sha256_after"] == mls_calibration_sha
            and report["normalization_sha256_after"] == normalization_sha
        )
        report["worker_code_sha256"] = sha256(Path(__file__))
        report["torch_loaded"] = "torch" in sys.modules
        report["worker_before_final_report"] = elapsed((BOOT_WALL, BOOT_CPU))
        report["at_end_resources"] = own_resources(process_metrics)
        if args.method == "mls" and report["torch_loaded"]:
            report["status"] = "invalid_torch_loaded_in_MLS_worker"
        if not report["weights_unchanged"]:
            report["status"] = "invalid_weights_changed"
        if not report["calibrations_and_normalization_unchanged"]:
            report["status"] = "invalid_calibration_or_normalization_changed"
        write_json(output, report)
    if report["status"] != "complete":
        raise RuntimeError(report["status"])
    print(json.dumps({
        "method": args.method, "sample": args.sample, "status": report["status"],
        "rounds": len(report["rounds"]), "output": str(output),
    }), flush=True)


if __name__ == "__main__":
    main()
