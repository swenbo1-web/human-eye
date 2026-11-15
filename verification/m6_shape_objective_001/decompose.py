"""Decompose the 306 saved synthetic targets using their saved reference normals."""

import time
BOOT_WALL, BOOT_CPU = time.perf_counter(), time.process_time()

import os
for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import ctypes
import hashlib
import importlib.util
import io
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "m6_shape_data_001"
TRAIN = HERE.parent / "m6_shape_train_001"


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8", newline="\n")


def own_resources():
    spec = importlib.util.spec_from_file_location("_objective_decompose_monitor", TRAIN / "process_runner.py")
    monitor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitor)
    ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    return monitor.process_metrics(ctypes.windll.kernel32.GetCurrentProcess())


def stamp():
    return time.perf_counter(), time.process_time()


def charge(stages, name, before):
    stages[name]["wall_s"] += time.perf_counter() - before[0]
    stages[name]["cpu_s"] += time.process_time() - before[1]


def record_bytes(path, identities):
    blob = path.read_bytes()
    identities[str(path.resolve())] = {"path": str(path.resolve()), "bytes": len(blob),
                                     "sha256": hashlib.sha256(blob).hexdigest()}
    return blob


def load_npz(path, names, identities):
    blob = record_bytes(path, identities)
    with np.load(io.BytesIO(blob), allow_pickle=False) as saved:
        return {name: saved[name].copy() for name in names}


def load_npy(path, identities):
    return np.load(io.BytesIO(record_bytes(path, identities)), allow_pickle=False)


def distribution(values):
    values = np.asarray([value for value in values if value is not None], dtype=np.float64)
    if not len(values):
        return {"count": 0, "minimum": None, "median": None, "p95": None, "maximum": None}
    return {"count": len(values), "minimum": float(values.min()), "median": float(np.median(values)),
            "p95": float(np.quantile(values, .95, method="linear")), "maximum": float(values.max())}


def group_keys(case):
    primary = "development_center" if case["purpose"] == "development_train_pool" else "validation_" + case.get("position_group", "center")
    source = "source_" + case["source"]
    radius, amplitude = case["radius_ratio"], case["amplitude_ratio"]
    return ("all", primary, source, f"{primary}_amplitude_{amplitude}",
            f"{primary}_r{radius}_a{amplitude}", f"{source}_amplitude_{amplitude}",
            f"amplitude_{amplitude}")


def summarize(rows):
    counts = {name: sum(row["denominators"][name] for row in rows) for name in rows[0]["denominators"]}
    energy_names = ("finite_target_energy", "decomposable_target_energy", "normal_energy", "tangent_energy",
                    "invalid_normal_finite_target_energy")
    energies = {name: float(sum(row[name] for row in rows)) for name in energy_names}
    complete_target = all(row["total_target_energy"] is not None for row in rows)
    total = energies["finite_target_energy"] if complete_target else None
    denominator = energies["decomposable_target_energy"]
    return {"case_count": len(rows), "patch_count": len({row["patch_id"] for row in rows}),
            "source_count": len({row["source"] for row in rows}),
            "case_ids": [row["id"] for row in rows], "denominators": counts,
            "total_target_energy": total, **energies,
            "tangent_fraction_of_decomposable_target": energies["tangent_energy"] / denominator if denominator > 0 else None,
            "normal_fraction_of_decomposable_target": energies["normal_energy"] / denominator if denominator > 0 else None,
            "per_case_tangent_fraction": distribution([row["tangent_fraction_of_decomposable_target"] for row in rows]),
            "per_case_target_energy": distribution([row["total_target_energy"] for row in rows]),
            "maximum_energy_closure_abs_error": max(row["maximum_energy_closure_abs_error"] for row in rows),
            "maximum_normal_tangent_abs_dot": max(row["maximum_normal_tangent_abs_dot"] for row in rows)}


def main():
    started, cpu_started = stamp()
    report_path = HERE / "DECOMPOSITION.json"
    marker_path = HERE / "DECOMPOSITION_STARTED.json"
    if marker_path.exists() or report_path.exists():
        raise RuntimeError("decomposition_attempt_exists_inspect_preserved_records")
    frozen = json.loads((HERE / "PLAN_FREEZE.json").read_bytes())
    for row in frozen["files"]:
        if hashlib.sha256((HERE / row["path"]).read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError("frozen_plan_changed_" + row["path"])
    write(marker_path, {"cycle_id": "M6-SHAPE-OBJECTIVE-001", "status": "started", "cases_requested": 306,
                        "model_forwards": 0, "training_updates": 0, "Bunny_arrays": 0})
    stages = {name: {"wall_s": 0.0, "cpu_s": 0.0}
              for name in ("metadata_read", "reference_and_normal_read", "observation_label_scale_read",
                           "decomposition", "private_array_save", "summary")}
    report = {"cycle_id": "M6-SHAPE-OBJECTIVE-001", "status": "incomplete", "cases": [], "failures": [],
              "new_model_forwards": 0, "training_updates": 0, "new_repair_candidates": 0,
              "Bunny_arrays": 0, "threshold_searches": 0,
              "preparation_read_incident": {"operation": "optional historical script path lookup",
                                            "path": "verification/m6_shape_observe_001/decompose.py",
                                            "result": "file absent, read command exited1; current contract/source files read successfully",
                                            "read_command_wall_s": .1400163, "CPU_or_peak": None,
                                            "scientific_actions": 0},
              "stages": stages}
    identities, cache = {}, {}
    try:
        before = stamp()
        development = json.loads(record_bytes(DATA / "DATASET_INDEX.json", identities))["cases"]
        public = json.loads(record_bytes(TRAIN / "PUBLIC_DATASET_INDEX.json", identities))["cases"]
        validation = [case for case in public if case["purpose"] == "validation"]
        all_cases = sorted(development + validation, key=lambda case: case["id"])
        cases = [case for case in all_cases if not case["normal_control"]]
        normal_cases = {case["patch_id"]: case for case in all_cases if case["normal_control"]}
        if len(all_cases) != 348 or len(cases) != 306 or len(normal_cases) != 42:
            raise ValueError("fixed_case_or_reference_denominator_mismatch")
        if any(case["purpose"] != "development_train_pool" for case in development):
            raise ValueError("unexpected_training_pool_case")
        if any(case["source"] != "Stanford_Armadillo" for case in validation):
            raise ValueError("unexpected_validation_source")
        charge(stages, "metadata_read", before)
        output_root = HERE / "private/decomposition"
        for ordinal, case in enumerate(cases):
            case_id, patch = case["id"], case["patch_id"]
            sample_name = case_id.split("/")[-1]
            root = DATA / "private/patches" if case["purpose"] == "development_train_pool" else TRAIN / "private/public_data/patches"
            folder = root / patch
            if patch not in cache:
                before = stamp()
                normal_case = normal_cases[patch]
                if normal_case["id"] != patch + "/sample_00":
                    raise ValueError("reference_normal_observation_is_not_sample00")
                normals = load_npz(folder / "inputs/sample_00.npz", ("normals",), identities)["normals"].astype(np.float64)
                reference = load_npy(folder / "reference_local.npy", identities)
                source_ids = load_npz(folder / "mapping.npz", ("context_source_ids",), identities)["context_source_ids"]
                if reference.dtype != np.float64 or reference.shape != normals.shape or normals.ndim != 2 or normals.shape[1] != 3:
                    raise ValueError("reference_coordinates_or_normals_shape_dtype_mismatch")
                if source_ids.shape != (len(reference),):
                    raise ValueError("reference_source_vertex_id_mismatch")
                with np.errstate(over="ignore", invalid="ignore"):
                    length = np.linalg.norm(normals, axis=1)
                finite_components = np.isfinite(normals).all(axis=1)
                finite_length = np.isfinite(length)
                valid_normal = finite_components & finite_length & (length > 0)
                unit_normal = np.full_like(normals, np.nan)
                unit_normal[valid_normal] = normals[valid_normal] / length[valid_normal, None]
                cache[patch] = {"reference": reference, "source_ids": source_ids, "unit_normal": unit_normal,
                                "normal_component_nonfinite": ~finite_components,
                                "normal_length_nonfinite": ~finite_length,
                                "normal_zero": finite_components & finite_length & (length == 0),
                                "valid_normal": valid_normal, "normal_case_id": normal_case["id"]}
                charge(stages, "reference_and_normal_read", before)
            fixed = cache[patch]
            before = stamp()
            observed = load_npy(folder / "observed" / (sample_name + ".npy"), identities)
            labels = load_npz(folder / "labels" / (sample_name + ".npz"), ("damaged_mask",), identities)
            support = labels["damaged_mask"]
            scale = float(load_npz(folder / "inputs" / (sample_name + ".npz"), ("scale_m",), identities)["scale_m"])
            if observed.dtype != np.float64 or observed.shape != fixed["reference"].shape:
                raise ValueError("observation_shape_dtype_mismatch_" + case_id)
            if support.shape != (len(observed),) or support.dtype != np.bool_:
                raise ValueError("support_mask_shape_dtype_mismatch_" + case_id)
            if not np.isfinite(scale) or scale <= 0:
                raise ValueError("invalid_observation_scale_" + case_id)
            charge(stages, "observation_label_scale_read", before)
            before = stamp()
            displacement = (fixed["reference"] - observed)[support] / scale
            normals = fixed["unit_normal"][support]
            valid_normal = fixed["valid_normal"][support]
            with np.errstate(over="ignore", invalid="ignore"):
                target_energy = np.einsum("ij,ij->i", displacement, displacement)
            finite_target = np.isfinite(displacement).all(axis=1) & np.isfinite(target_energy)
            usable = valid_normal & finite_target
            normal_component = np.full_like(displacement, np.nan)
            tangent_component = np.full_like(displacement, np.nan)
            dot = np.einsum("ij,ij->i", displacement[usable], normals[usable])
            normal_component[usable] = dot[:, None] * normals[usable]
            tangent_component[usable] = displacement[usable] - normal_component[usable]
            normal_energy = np.einsum("ij,ij->i", normal_component[usable], normal_component[usable])
            tangent_energy = np.einsum("ij,ij->i", tangent_component[usable], tangent_component[usable])
            closure = normal_energy + tangent_energy - target_energy[usable]
            orthogonality = np.einsum("ij,ij->i", normal_component[usable], tangent_component[usable])
            decomposable_energy = float(target_energy[usable].sum())
            tangent_sum = float(tangent_energy.sum())
            row = {"id": case_id, "patch_id": patch, "source": case["source"], "source_group": case["source_group"],
                   "purpose": case["purpose"], "position_group": case.get("position_group", "center"),
                   "radius_ratio": case["radius_ratio"], "amplitude_ratio": case["amplitude_ratio"],
                   "normal_reference_case_id": fixed["normal_case_id"], "observed_scale_native": scale,
                   "denominators": {"support_points": int(support.sum()), "valid_normal_points": int(valid_normal.sum()),
                                    "invalid_normal_points": int(np.count_nonzero(~valid_normal)),
                                    "nonfinite_normal_component_points": int(fixed["normal_component_nonfinite"][support].sum()),
                                    "nonfinite_normal_length_points": int(fixed["normal_length_nonfinite"][support].sum()),
                                    "zero_normal_points": int(fixed["normal_zero"][support].sum()),
                                    "finite_target_points": int(finite_target.sum()),
                                    "nonfinite_target_points": int(np.count_nonzero(~finite_target)),
                                    "decomposable_points": int(usable.sum())},
                   "total_target_energy": float(target_energy.sum()) if finite_target.all() else None,
                   "finite_target_energy": float(target_energy[finite_target].sum()),
                   "decomposable_target_energy": decomposable_energy,
                   "normal_energy": float(normal_energy.sum()), "tangent_energy": tangent_sum,
                   "invalid_normal_finite_target_energy": float(target_energy[finite_target & ~valid_normal].sum()),
                   "tangent_fraction_of_decomposable_target": tangent_sum / decomposable_energy if decomposable_energy > 0 else None,
                   "normal_fraction_of_decomposable_target": float(normal_energy.sum()) / decomposable_energy if decomposable_energy > 0 else None,
                   "maximum_energy_closure_abs_error": float(np.abs(closure).max()) if len(closure) else 0.0,
                   "maximum_normal_tangent_abs_dot": float(np.abs(orthogonality).max()) if len(orthogonality) else 0.0}
            charge(stages, "decomposition", before)
            before = stamp()
            output = output_root / patch / (sample_name + ".npz")
            output.parent.mkdir(parents=True, exist_ok=True)
            np.savez(output, source_vertex_ids=fixed["source_ids"][support], target_normalized_float64=displacement,
                     reference_unit_normal=normals, valid_normal=valid_normal, finite_target=finite_target,
                     decomposable=usable, normal_component=normal_component, tangent_component=tangent_component,
                     target_energy=target_energy)
            blob = output.read_bytes()
            row["private_point_components"] = {"path": str(output.resolve()), "bytes": len(blob),
                                                "sha256": hashlib.sha256(blob).hexdigest()}
            report["cases"].append(row)
            charge(stages, "private_array_save", before)
            if (ordinal + 1) % 50 == 0:
                print(json.dumps({"decomposed_cases": ordinal + 1, "wall_s": time.perf_counter() - BOOT_WALL}), flush=True)
        before = stamp()
        report["summaries"] = {name: summarize([row for row in report["cases"] if name in group_keys(row)])
                               for name in sorted({key for row in report["cases"] for key in group_keys(row)})}
        report.update(status="completed_decomposition", dented_observations=306, metadata_observations=348,
                      reference_normal_observations=len(cache), public_reserved_metadata_filtered=True,
                      input_file_identities=list(identities.values()), input_files_count=len(identities),
                      plan_sha256=hashlib.sha256((HERE / "PLAN.json").read_bytes()).hexdigest(),
                      source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      formula={"d": "binary64(reference_local-observed)/observed_scale", "n": "sample00 saved normal liftedfloat64 then normalized",
                               "normal": "(d dot n)n", "tangent": "d-normal"},
                      invalid_policy="nonfinite components, nonfinite computed norm or zero norm invalid; no geometric reliability threshold; invalid target/normal denominators and finite energy retained",
                      energy_units="squared observed median-edge units; Stanford physical units unspecified",
                      interpretation="label-assisted description of existing target, no causal failure claim or learnability conclusion",
                      observation_dependence="support points sum over synthetic observations and repeated source vertices; cases and patch/source counts reported separately")
        charge(stages, "summary", before)
    except Exception as error:
        report["status"] = "failed"
        report["failures"].append({"type": type(error).__name__, "message": str(error), "completed_cases": len(report["cases"])})
        raise
    finally:
        report["main_wall_s_before_final_write"] = time.perf_counter() - started
        report["main_CPU_s_before_final_write"] = time.process_time() - cpu_started
        report["bootstrap_to_final_report_wall_s"] = time.perf_counter() - BOOT_WALL
        report["bootstrap_to_final_report_CPU_s"] = time.process_time() - BOOT_CPU
        report["own_process_at_end"] = own_resources()
        write(report_path, report)
        write(marker_path, {"cycle_id": "M6-SHAPE-OBJECTIVE-001", "status": report["status"],
                            "completed_cases": len(report["cases"]), "model_forwards": 0,
                            "training_updates": 0, "Bunny_arrays": 0})
    print(json.dumps({"status": report["status"], "cases": len(report["cases"]),
                      "tangent_energy_fractions": {group: report["summaries"][group]["tangent_fraction_of_decomposable_target"]
                                                   for group in ("development_center", "validation_center", "validation_offcenter")}}), flush=True)


if __name__ == "__main__":
    main()
