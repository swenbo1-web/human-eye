"""Single frozen MLS calibration and observation-only baseline evaluation.

The calling entry point supplies this directory on sys.path. Calibration loads
observation inputs with with_labels=False. Evaluation passes the resulting
corrections to the shared metric implementation after fitting is complete.
"""

from contextlib import contextmanager
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import time

import numpy as np

from data_io import load_sample
import mls


HERE = Path(__file__).resolve().parent
CALIBRATION_PATH = HERE / "MLS_CALIBRATION.json"
CACHE_VERSION = 1
EXPECTED_CONTROL_COUNT = 33
COUNT_KEYS = ("total", "free", "fixed", "applicable", *mls.FAILURE_REASONS)


def _clock():
    return time.perf_counter(), time.process_time()


def _elapsed(started):
    return {
        "wall_s": time.perf_counter() - started[0],
        "cpu_s": time.process_time() - started[1],
    }


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as saved:
        for chunk in iter(lambda: saved.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _identity_sha256(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _atomic_bytes(path, contents):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as saved:
            temporary = Path(saved.name)
            saved.write(contents)
            saved.flush()
            os.fsync(saved.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _write_json(path, value):
    contents = json.dumps(value, indent=2, allow_nan=False).encode("utf-8") + b"\n"
    _atomic_bytes(path, contents)


def _guard_cases(cases):
    """Check the complete requested batch before loading or writing any case."""
    cases = list(cases)
    for case in cases:
        if case.get("purpose") == "reserved_test" or case.get("source") == "Stanford_Bunny":
            raise ValueError("reserved_test_scoring_is_locked_for_this_batch")
    identifiers = [case["id"] for case in cases]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("duplicate_case_ids_in_baseline_batch")
    return cases


def _private_cache_dir(cache_dir):
    directory = Path(cache_dir).resolve()
    if not directory.is_relative_to(HERE):
        raise ValueError("MLS_cache_must_be_inside_the_TRAIN_001_directory")
    if "private" not in directory.relative_to(HERE).parts:
        raise ValueError("MLS_fit_arrays_and_diagnostics_require_a_private_directory")
    return directory


@contextmanager
def _calibration_lock():
    """An OS-held lock releases automatically when its process exits."""
    lock_dir = HERE / "private" / "mls_calibration"
    lock_dir.mkdir(parents=True, exist_ok=True)
    with (lock_dir / "MLS_CALIBRATION.lock").open("a+b") as lock:
        lock.seek(0, os.SEEK_END)
        if lock.tell() == 0:
            lock.write(b"\0")
            lock.flush()
        lock.seek(0)
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise RuntimeError("MLS_calibration_already_running") from error
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == "nt":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _case_identity(case, patch_root, implementation_sha256):
    sample_name = case.get("sample_name")
    if sample_name is None:
        sample_name = Path(case["input"]["path"]).stem
    folder = Path(patch_root) / case["patch_id"]
    input_sha256 = _sha256(folder / "inputs" / (sample_name + ".npz"))
    expected_sha256 = case.get("input", {}).get("sha256")
    if expected_sha256 is not None and input_sha256 != expected_sha256:
        raise ValueError(f"input_SHA256_mismatch_for_{case['id']}")
    return {
        "cache_version": CACHE_VERSION,
        "id": case["id"],
        "patch_id": case["patch_id"],
        "sample_name": sample_name,
        "purpose": case["purpose"],
        "normal_control": case.get("normal_control") is True,
        "input_sha256": input_sha256,
        "graph_sha256": _sha256(folder / "graph.npz"),
        "mls_implementation_sha256": implementation_sha256,
    }


def _validate_fit(raw, applicable, diagnostics, free):
    expected_shape = (len(free),)
    if raw.shape != expected_shape or applicable.shape != expected_shape:
        raise ValueError("cached_MLS_array_shape_mismatch")
    if applicable.dtype != np.dtype(bool) or not np.isfinite(raw).all():
        raise ValueError("cached_MLS_invalid_numeric_or_mask")
    if np.any(applicable & ~free) or np.any(raw[~applicable] != 0):
        raise ValueError("cached_MLS_fixed_or_failed_point_mismatch")
    counts = diagnostics["counts"]
    if counts["total"] != len(free) or counts["free"] != int(np.count_nonzero(free)):
        raise ValueError("cached_MLS_denominator_mismatch")
    if counts["fixed"] != int(np.count_nonzero(~free)):
        raise ValueError("cached_MLS_fixed_denominator_mismatch")
    if counts["applicable"] != int(np.count_nonzero(applicable)):
        raise ValueError("cached_MLS_applicability_count_mismatch")
    if sum(counts[key] for key in ("applicable", *mls.FAILURE_REASONS)) != counts["free"]:
        raise ValueError("cached_MLS_failure_denominator_mismatch")
    reasons = np.asarray(diagnostics["per_point_reason"])
    if reasons.shape != expected_shape or not np.array_equal(reasons == "applicable", applicable):
        raise ValueError("cached_MLS_per_point_reason_mismatch")


def _load_fit_cache(folder, identity, free):
    metadata_path = folder / "metadata.json"
    if not metadata_path.exists():
        return None, "miss"
    try:
        metadata = json.loads(metadata_path.read_bytes())
        if metadata["identity"] != identity:
            raise ValueError("cached_identity_mismatch")
        for name, digest in metadata["artifacts_sha256"].items():
            if _sha256(folder / name) != digest:
                raise ValueError("cached_artifact_SHA256_mismatch")
        with np.load(folder / "residuals.npz", allow_pickle=False) as saved:
            raw = saved["raw_signed_residual"].copy()
            applicable = saved["applicable"].copy()
        diagnostics = json.loads((folder / "diagnostics.json").read_bytes())
        _validate_fit(raw, applicable, diagnostics, free)
        return (raw, applicable, diagnostics, metadata), "reused"
    except (OSError, ValueError, KeyError) as error:
        return None, f"recovered_{type(error).__name__}_{error}"


def _obtain_fit(sample, identity, cache_dir):
    started = _clock()
    folder = cache_dir / _identity_sha256(identity)
    free = np.asarray(sample["graph"]["free_mask"], dtype=bool)
    cached, cache_status = _load_fit_cache(folder, identity, free)
    reused = cached is not None
    current_fit = {"wall_s": 0.0, "cpu_s": 0.0}
    if reused:
        raw, applicable, diagnostics, metadata = cached
    else:
        fit_started = _clock()
        raw, applicable, diagnostics = mls.fit_residuals(
            sample["inputs"]["positions"], sample["inputs"]["normals"],
            sample["graph"]["edge_index"], free,
        )
        current_fit = _elapsed(fit_started)
        _validate_fit(raw, applicable, diagnostics, free)
        arrays = io.BytesIO()
        np.savez_compressed(arrays, raw_signed_residual=raw, applicable=applicable)
        _atomic_bytes(folder / "residuals.npz", arrays.getvalue())
        _write_json(folder / "diagnostics.json", diagnostics)
        metadata = {
            "identity": identity,
            "fit_timing": current_fit,
            "counts": diagnostics["counts"],
            "artifacts_sha256": {
                name: _sha256(folder / name)
                for name in ("residuals.npz", "diagnostics.json")
            },
        }
        # Metadata is the commit marker for a complete cache entry.
        _write_json(folder / "metadata.json", metadata)
    info = {
        "reused_fit": reused,
        "cache_status": cache_status,
        "fit_compute": current_fit,
        "original_fit_compute": metadata["fit_timing"],
        "fit_or_cache_access": _elapsed(started),
        "private_diagnostics_path": str(folder / "diagnostics.json"),
        "private_residuals_path": str(folder / "residuals.npz"),
    }
    return raw, applicable, diagnostics, info


def _sum_counts(records):
    totals = {key: sum(record["counts"][key] for record in records) for key in COUNT_KEYS}
    totals["fallback_noop_free"] = totals["free"] - totals["applicable"]
    return totals


def calibrate_mls(train_cases, train_patch_root, cache_dir):
    """Return the one 99.5% pooled normal-control calibration report.

    The report is persisted at TRAIN-001/MLS_CALIBRATION.json. Calls with the
    same frozen control identities reuse that report. Completed fit cache
    entries support recovery if a first calibration is interrupted.
    """
    cases = _guard_cases(train_cases)
    started = _clock()
    controls = sorted(
        (case for case in cases if case.get("purpose") == "development_train_pool"
         and case.get("normal_control") is True),
        key=lambda case: case["id"],
    )
    if len(controls) != EXPECTED_CONTROL_COUNT:
        raise ValueError(f"MLS_calibration_requires_{EXPECTED_CONTROL_COUNT}_training_controls")
    if len({case["patch_id"] for case in controls}) != EXPECTED_CONTROL_COUNT:
        raise ValueError("MLS_calibration_requires_one_control_per_training_patch")
    cache_dir = _private_cache_dir(cache_dir)
    implementation_sha256 = _sha256(Path(mls.__file__))
    identities = [
        _case_identity(case, train_patch_root, implementation_sha256) for case in controls
    ]
    identity_sha256 = _identity_sha256(identities)
    with _calibration_lock():
        if CALIBRATION_PATH.exists():
            report = json.loads(CALIBRATION_PATH.read_bytes())
            if report["training_control_inputs_sha256"] != identity_sha256:
                raise ValueError("MLS_calibration_is_frozen_for_different_inputs_or_implementation")
            report["reused_calibration"] = True
            report["reuse_call_timing"] = _elapsed(started)
            return report

        pooled = []
        records = []
        for case, identity in zip(controls, identities):
            case_started = _clock()
            load_started = _clock()
            sample = load_sample(case, train_patch_root, with_labels=False)
            load_timing = _elapsed(load_started)
            raw, applicable, diagnostics, fit_info = _obtain_fit(sample, identity, cache_dir)
            selected = np.asarray(sample["graph"]["free_mask"], dtype=bool) & applicable
            pooled.append(np.abs(raw[selected]))
            records.append({
                "id": case["id"],
                "input_identity": identity,
                "counts": diagnostics["counts"],
                "pooled_residual_count": int(np.count_nonzero(selected)),
                "timing": {"load_observation": load_timing, **fit_info, "case": _elapsed(case_started)},
            })
        residuals = np.concatenate(pooled)
        if len(residuals) == 0:
            raise RuntimeError("MLS_calibration_has_zero_applicable_free_residuals")
        quantile_started = _clock()
        tau = float(np.quantile(residuals, 0.995, method="linear"))
        quantile_timing = _elapsed(quantile_started)
        totals = _sum_counts(records)
        if len(residuals) != totals["applicable"]:
            raise RuntimeError("MLS_calibration_pool_denominator_mismatch")
        report = {
            "task": "M6-SHAPE-TRAIN-001",
            "status": "complete_frozen_calibration",
            "tau": tau,
            "units": "observation_edge_length_normalized",
            "quantile": 0.995,
            "quantile_method": "linear",
            "calibration_count": 1,
            "reused_calibration": False,
            "control_count": len(controls),
            "pooled_residual_count": len(residuals),
            "counts": totals,
            "training_control_inputs_sha256": identity_sha256,
            "mls_implementation_sha256": implementation_sha256,
            "controls": records,
            "timing": {
                "quantile": quantile_timing,
                "fit_wall_s_including_resumed_cache": sum(
                    record["timing"]["original_fit_compute"]["wall_s"] for record in records
                ),
                "fit_cpu_s_including_resumed_cache": sum(
                    record["timing"]["original_fit_compute"]["cpu_s"] for record in records
                ),
                "reused_control_fits": sum(record["timing"]["reused_fit"] for record in records),
                "function_before_report_write": _elapsed(started),
            },
        }
        _write_json(CALIBRATION_PATH, report)
        return report


def evaluate_baselines(cases, patch_root, tau, output_dir, cache_dir=None):
    """Return per-case no-op/MLS metrics with fit and reuse denominators.

    Private cache entries contain complete fit diagnostics. The public summary
    carries counts for every requested case and records original calibration
    fit cost separately from the current evaluation's cache-read cost.
    """
    cases = _guard_cases(cases)
    started = _clock()
    tau_array = np.asarray(tau, dtype=np.float64)
    if tau_array.ndim != 0 or not np.isfinite(tau_array) or tau_array < 0:
        raise ValueError("tau_must_be_a_finite_nonnegative_scalar")
    tau = float(tau_array)
    output_dir = Path(output_dir).resolve()
    if not output_dir.is_relative_to(HERE):
        raise ValueError("baseline_outputs_must_be_inside_the_TRAIN_001_directory")
    cache_dir = _private_cache_dir(
        cache_dir if cache_dir is not None else output_dir / "private" / "mls_fits"
    )
    from evaluate import measure_case

    implementation_sha256 = _sha256(Path(mls.__file__))
    records = []
    summary = {
        "task": "M6-SHAPE-TRAIN-001",
        "status": "incomplete",
        "tau": tau,
        "requested_cases": len(cases),
        "mls_implementation_sha256": implementation_sha256,
        "cases": records,
    }
    active_case_id = None
    try:
        for case in cases:
            active_case_id = case["id"]
            case_started = _clock()
            identity_started = _clock()
            identity = _case_identity(case, patch_root, implementation_sha256)
            identity_timing = _elapsed(identity_started)
            load_started = _clock()
            sample = load_sample(case, patch_root)
            load_timing = _elapsed(load_started)
            raw, applicable, diagnostics, fit_info = _obtain_fit(sample, identity, cache_dir)
            gate_started = _clock()
            prediction = mls.gate_displacement(
                sample["inputs"]["normals"], raw, applicable,
                sample["graph"]["free_mask"], tau,
            )
            gate_timing = _elapsed(gate_started)
            measure_started = _clock()
            no_op = measure_case(sample, np.zeros_like(prediction), "no_op", output_dir)
            no_op_timing = _elapsed(measure_started)
            measure_started = _clock()
            metric = measure_case(sample, prediction, "mls", output_dir)
            metric_timing = _elapsed(measure_started)
            records.append({
                "id": case["id"],
                "no_op": no_op,
                "mls": metric,
                "counts": diagnostics["counts"],
                "timing": {
                    "input_identity": identity_timing,
                    "load_sample": load_timing,
                    **fit_info,
                    "gate": gate_timing,
                    "measure_no_op": no_op_timing,
                    "measure_mls": metric_timing,
                    "case": _elapsed(case_started),
                },
            })
        summary["status"] = "complete"
    except Exception as error:
        summary["failed_case_id"] = active_case_id
        summary["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        summary["completed_cases"] = len(records)
        summary["counts"] = _sum_counts(records)
        summary["reused_fits"] = sum(record["timing"]["reused_fit"] for record in records)
        summary["timing_before_report_write"] = _elapsed(started)
        _write_json(output_dir / "BASELINE_RESULTS.json", summary)
    return summary
