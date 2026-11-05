"""Compare a BC refinement directly with the frozen, accepted implementation.

This is development-time measurement, not a runtime fallback. Exit zero means
complete, internally consistent evidence and matching quality, not acceptance
of the performance change. The reviewer decides benefit and regression gates.
"""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from time import perf_counter_ns
import traceback

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BASELINE_PATH = ROOT / "verification/baselines/bc_implementation.py"
BASELINE_SHA256 = "03bb9ce3bd5da99299a55d47122b38ceb2bef04aba37d998b80e0ad8de4ffa09"
SEEDS = (20261105, 79463)
METHODS = ("implementation", "candidate")
THREAD_ENV = dict.fromkeys(
    ("BLIS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS",
     "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"), "1",
)
BOOTSTRAP_SEED = 651083
BOOTSTRAP_REPLICATES = 6000


def _configuration(pilot):
    return {"processes": 1 if pilot else 3,
            "warmups": 1 if pilot else 5,
            "samples": 5 if pilot else 31,
            "stage_samples": 2 if pilot else 6}


def _source_digests():
    paths = (Path(__file__).resolve(), BASELINE_PATH,
             ROOT / "human_eye_fast/fast_bvh_clearance.py",
             ROOT / "verification/benchmark_fast_bvh_clearance.py")
    return {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths}


def _load_versions():
    # The dataclass loader needs its own registered module; no candidate
    # function is patched or reused by the frozen implementation.
    if hashlib.sha256(BASELINE_PATH.read_bytes()).hexdigest() != BASELINE_SHA256:
        raise RuntimeError("The frozen implementation does not match its accepted SHA256")
    name = "_bc_frozen_implementation_for_refinement"
    spec = importlib.util.spec_from_file_location(name, BASELINE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    from human_eye_fast import fast_bvh_clearance as candidate
    from verification import benchmark_fast_bvh_clearance as fixtures
    return {"implementation": module, "candidate": candidate}, fixtures


class _Query:
    def __init__(self, api, case, state):
        self.api = api
        self.a = api.SurfaceIndex(state[0], case.faces_a)
        self.b = api.SurfaceIndex(state[1], case.faces_b)

    def update(self, state):
        self.a.update(state[0])
        self.b.update(state[1])

    def query(self):
        return self.api.surface_distance(self.a, self.b)


def _cases(fixtures):
    result = []
    for seed in SEEDS:
        for cells in (8, 16):
            for offset in (0.5, 0.05):
                case = fixtures._grid_case(cells, offset, seed)
                result.append((f"seed_{seed}_{case.name}", seed, case))
    result.append(("dense_512", fixtures.DENSE_SEED, fixtures._dense_case()))
    return result


def _quality(fixtures, case, phase, results):
    # This reuses only the independent barycentric fixture checker, never
    # either implementation's distance primitive or BVH.
    va, vb = case.states[phase]
    surface = np.concatenate((va[case.faces_a].reshape(-1, 3),
                              vb[case.faces_b].reshape(-1, 3)))
    tolerance = float(1e-10 * np.linalg.norm(np.ptp(surface, axis=0))
                      + 32 * np.finfo(np.float64).eps * np.abs(surface).max())
    expected = None if case.expected_m is None else case.expected_m[phase]
    checks = {}
    for name, result in results.items():
        valid = (np.isfinite(result.distance_m) and result.distance_m >= 0
                 and isinstance(result.triangle_a, (int, np.integer))
                 and isinstance(result.triangle_b, (int, np.integer))
                 and 0 <= result.triangle_a < len(case.faces_a)
                 and 0 <= result.triangle_b < len(case.faces_b)
                 and np.shape(result.point_a) == (3,) and np.shape(result.point_b) == (3,))
        if not valid or not np.isfinite([result.point_a, result.point_b]).all():
            checks[name] = {"valid_output": False}
            continue
        errors = {
            "face_a_error_m": fixtures._witness_error(
                result.point_a, va[case.faces_a[result.triangle_a]]),
            "face_b_error_m": fixtures._witness_error(
                result.point_b, vb[case.faces_b[result.triangle_b]]),
            "separation_error_m": float(abs(
                np.linalg.norm(np.subtract(result.point_a, result.point_b)) - result.distance_m)),
        }
        if expected is not None:
            errors["analytic_distance_error_m"] = float(abs(result.distance_m - expected))
        sign_matches = expected is None or ((expected == 0.) == (result.distance_m == 0.))
        checks[name] = {**errors, "valid_output": bool(sign_matches and all(
            np.isfinite(value) and value <= tolerance for value in errors.values()))}
    difference = abs(results["candidate"].distance_m - results["implementation"].distance_m)
    difference = float(difference) if np.isfinite(difference) else None
    return {"tolerance_m": tolerance, "expected_m": expected,
            "distance_delta_m": difference, "witness_checks": checks,
            "passed": bool(difference is not None and difference <= tolerance
                           and all(item["valid_output"] for item in checks.values()))}


def _order(sequence, worker, case_id):
    # Two consecutive geometry phases use each order before flipping it;
    # per-pair alternation would confound phase and method order in a worker.
    return METHODS[::-1] if (sequence // 2 + worker + case_id) % 2 else METHODS


def _check_inputs(fixtures, case, expected, record):
    actual = [fixtures._array_digest(case.faces_a, case.faces_b, *state)
              for state in case.states]
    record["input_unchanged"] = actual == expected
    if actual != expected:
        record["changed_input_sha256"] = actual
        raise RuntimeError("An implementation changed fixture input; stop before contaminating its opponent")


def _run_case(versions, fixtures, case, seed, worker, case_id, config, run):
    run.update({"seed": seed, "face_counts": [len(case.faces_a), len(case.faces_b)],
                "vertex_counts": [len(v) for v in case.states[0]],
                "state_sha256": [fixtures._array_digest(case.faces_a, case.faces_b, *state)
                                  for state in case.states],
                "changed_vertex_counts": [int(np.any(a != b, axis=1).sum())
                                          for a, b in zip(*case.states)],
                "z_offset_m": case.z_offset_m, "expected_m": case.expected_m})
    if case.expected_m is not None:
        run["overlapping_face_aabb_fraction"] = [
            fixtures._overlap_fraction(a[case.faces_a], b[case.faces_b])
            for a, b in case.states]
    cold = {"phase": 0, "order": _order(0, worker, case_id), "methods": {}}
    run["cold"] = cold
    queries, results = {}, {}
    for name in cold["order"]:
        start = perf_counter_ns()
        query = _Query(versions[name], case, case.states[0])
        ready = perf_counter_ns()
        result = query.query()
        done = perf_counter_ns()
        queries[name], results[name] = query, result
        cold["methods"][name] = {"initial_prepare_ns": ready - start,
                                  "query_ns": done - ready, "total_ns": done - start,
                                  "result": fixtures._record(result)}
        _check_inputs(fixtures, case, run["state_sha256"], cold["methods"][name])
    cold["quality"] = _quality(fixtures, case, 0, results)

    count = config["warmups"] + config["samples"] + config["stage_samples"]
    for sequence in range(count):
        phase = (sequence + 1) % 2
        state = case.states[phase]
        kind = ("warmups" if sequence < config["warmups"] else
                "samples" if sequence < config["warmups"] + config["samples"] else "stages")
        sample = {"sequence": sequence, "phase": phase,
                  "order": _order(sequence, worker, case_id), "methods": {}}
        run[kind].append(sample)
        results = {}
        for name in sample["order"]:
            query = queries[name]
            if kind == "warmups":
                query.update(state)
                result = query.query()
                timing = {}
            elif kind == "samples":
                start = perf_counter_ns()
                query.update(state)
                result = query.query()
                done = perf_counter_ns()
                timing = {"total_ns": done - start}
            else:
                start = perf_counter_ns()
                query.update(state)
                ready = perf_counter_ns()
                result = query.query()
                done = perf_counter_ns()
                timing = {"prepare_ns": ready - start, "query_ns": done - ready,
                          "total_ns": done - start}
            results[name] = result
            sample["methods"][name] = {**timing, "result": fixtures._record(result)}
            _check_inputs(fixtures, case, run["state_sha256"], sample["methods"][name])
        sample["quality"] = _quality(fixtures, case, phase, results)


def _checkpoint(stream, value):
    # Already-created per-run files only. Writes and serialization are outside
    # measured calls, preserving completed cases if a later worker fails.
    stream.seek(0)
    json.dump(value, stream, indent=2, allow_nan=False)
    stream.write("\n")
    stream.truncate()
    stream.flush()


def _worker(worker, pilot, stream):
    config = _configuration(pilot)
    report = {"worker": worker, "pid": os.getpid(), "pilot": pilot,
              "python": sys.version, "numpy": np.__version__,
              "source_sha256_before": _source_digests(),
              "thread_env": {key: os.environ.get(key) for key in THREAD_ENV}, "cases": {}}
    _checkpoint(stream, report)
    try:
        versions, fixtures = _load_versions()
        for case_id, (name, seed, case) in enumerate(_cases(fixtures)):
            run = {"case_id": case_id, "warmups": [], "samples": [], "stages": []}
            report["cases"][name] = run
            try:
                _run_case(versions, fixtures, case, seed, worker, case_id, config, run)
            except Exception:
                run["error"] = traceback.format_exc()
            finally:
                _checkpoint(stream, report)
    except BaseException:
        report["error"] = traceback.format_exc()
        raise
    finally:
        report["source_sha256_after"] = _source_digests()
        _checkpoint(stream, report)
    return 0 if not any("error" in run for run in report["cases"].values()) else 1


def _bootstrap_ci(groups, seed):
    """Paired differences resampled within each process, never timed work."""
    rng = np.random.default_rng(seed)
    draws = [np.asarray(group, dtype=np.float64)[rng.integers(
        0, len(group), size=(BOOTSTRAP_REPLICATES, len(group)))] for group in groups]
    statistics = np.median(np.concatenate(draws, axis=1), axis=1)
    return [float(value) for value in np.percentile(statistics, [2.5, 97.5])]


def _timing_summary(groups, seed):
    per_process, differences = [], []
    for index, samples in enumerate(groups):
        timing = {name: np.array([s["methods"][name]["total_ns"] for s in samples], dtype=np.float64)
                  for name in METHODS}
        delta = timing["candidate"] - timing["implementation"]
        differences.append(delta)
        medians = {name: float(np.median(values)) for name, values in timing.items()}
        per_process.append({"sample_count": len(samples), "median_ns": medians,
                            "candidate_over_implementation_median_ratio": medians["candidate"] / medians["implementation"],
                            "paired_difference_median_ns": float(np.median(delta)),
                            "paired_difference_median_ci95_ns": _bootstrap_ci([delta], seed + index + 1)})
    samples = [sample for group in groups for sample in group]
    p95 = {name: float(np.percentile([s["methods"][name]["total_ns"] for s in samples], 95))
           for name in METHODS}
    delta = np.concatenate(differences)
    return {"sample_count": len(samples), "per_process": per_process,
            "pooled_p95_ns": p95,
            "candidate_over_implementation_p95_ratio": p95["candidate"] / p95["implementation"],
            "difference_of_p95_ns": p95["candidate"] - p95["implementation"],
            "paired_difference_median_ns": float(np.median(delta)),
            "paired_difference_p95_ns": float(np.percentile(delta, 95)),
            "paired_difference_median_ci95_ns": _bootstrap_ci(differences, seed)}


def _summarize_case(runs, config, case_id):
    if any("error" in run for run in runs):
        return {"evidence_complete": False, "errors": [r.get("error") for r in runs]}
    expected_counts = {"warmups": config["warmups"], "samples": config["samples"],
                       "stages": config["stage_samples"]}
    counts_ok = all(len(run[key]) == count for run in runs for key, count in expected_counts.items())
    changes_ok = all(run["changed_vertex_counts"] == run["vertex_counts"]
                     and run["state_sha256"][0] != run["state_sha256"][1] for run in runs)
    fixtures_ok = all(run["state_sha256"] == runs[0]["state_sha256"] for run in runs)
    ordered = True
    for worker_id, run in enumerate(runs):
        items = run["warmups"] + run["samples"] + run["stages"]
        for sequence, item in enumerate(items):
            ordered &= item["phase"] == (sequence + 1) % 2
            ordered &= tuple(item["order"]) == _order(sequence, worker_id, case_id)
    quality = [item["quality"] for run in runs
               for item in [run["cold"], *run["warmups"], *run["samples"], *run["stages"]]]
    summary = _timing_summary([run["samples"] for run in runs], BOOTSTRAP_SEED + 100 * case_id)
    summary.update({"face_counts": runs[0]["face_counts"], "seed": runs[0]["seed"],
                    "expected_m": runs[0]["expected_m"], "quality_passed": all(q["passed"] for q in quality),
                    "counts_valid": counts_ok, "full_vertex_changes_valid": changes_ok,
                    "same_fixtures": fixtures_ok, "order_and_phase_valid": bool(ordered),
                    "evidence_complete": bool(counts_ok and changes_ok and fixtures_ok and ordered),
                    "max_distance_delta_m": max((q["distance_delta_m"] for q in quality
                                                 if q["distance_delta_m"] is not None), default=None),
                    "cold_per_process": [run["cold"] for run in runs],
                    "phase_statistics": {str(phase): _timing_summary(
                        [[s for s in run["samples"] if s["phase"] == phase] for run in runs],
                        BOOTSTRAP_SEED + 100 * case_id + 20 * (phase + 1)) for phase in (0, 1)}})
    stages = [sample for run in runs for sample in run["stages"]]
    summary["stage_medians_ns"] = {field: {name: float(np.median([
        sample["methods"][name][field] for sample in stages])) for name in METHODS}
        for field in ("prepare_ns", "query_ns", "total_ns")}
    if "overlapping_face_aabb_fraction" in runs[0]:
        summary["overlapping_face_aabb_fraction"] = runs[0]["overlapping_face_aabb_fraction"]
    return summary


def _run_all(args, report, stream):
    config = _configuration(args.pilot)
    for worker in range(config["processes"]):
        worker_path = args.output.with_name(f"{args.output.stem}.worker-{worker}.json")
        command = [sys.executable, "-B", str(Path(__file__).resolve()), "--worker", str(worker),
                   "--worker-output", str(worker_path)]
        if args.pilot:
            command.append("--pilot")
        completed = subprocess.run(command, env={**os.environ, **THREAD_ENV}, capture_output=True,
                                   text=True, encoding="utf-8", errors="replace", check=False)
        try:
            data = json.loads(worker_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {"error": "Worker did not leave a valid JSON record"}
        data["worker_output_path"] = str(worker_path.resolve())
        data["exit_code"] = completed.returncode
        if completed.stdout:
            data["stdout"] = completed.stdout
        if completed.stderr:
            data["stderr"] = completed.stderr
        if completed.returncode:
            data.setdefault("error", f"Worker exited {completed.returncode}")
        report["workers"].append(data)
        _checkpoint(stream, report)

    workers = report["workers"]
    report["source_sha256_after"] = _source_digests()
    report["same_code"] = all(
        worker.get("source_sha256_before") == report["source_sha256_before"]
        and worker.get("source_sha256_after") == report["source_sha256_before"] for worker in workers)
    report["same_code"] &= report["source_sha256_after"] == report["source_sha256_before"]
    report["thread_env_confirmed"] = all(worker.get("thread_env") == THREAD_ENV for worker in workers)
    report["independent_processes"] = len({w.get("pid") for w in workers}) == config["processes"]
    if any("error" in worker for worker in workers):
        return
    names = list(workers[0]["cases"])
    if len(names) != 9 or any(list(worker["cases"]) != names for worker in workers):
        report["error"] = "Missing, reordered or inconsistent case sets"
        return
    report["cases"] = {name: _summarize_case([w["cases"][name] for w in workers], config, case_id)
                       for case_id, name in enumerate(names)}
    report["quality_passed"] = all(case.get("quality_passed", False) for case in report["cases"].values())
    report["evidence_complete"] = bool(
        report["same_code"] and report["thread_env_confirmed"] and report["independent_processes"]
        and all(case["evidence_complete"] for case in report["cases"].values()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pilot", action="store_true", help="Exploration only: one process, 1 warmup and 5 pairs")
    parser.add_argument("--worker", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--worker-output", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker is not None:
        if args.worker_output is None:
            parser.error("--worker-output is required for an internal worker")
        with args.worker_output.open("x", encoding="utf-8") as stream:
            return _worker(args.worker, args.pilot, stream)
    if args.output is None:
        parser.error("--output is required")
    config = _configuration(args.pilot)
    report = {
        "comparison": "candidate versus frozen accepted implementation",
        "pilot": args.pilot, "formal_sampling_requested": not args.pilot,
        "performance_accepted": None, "evidence_complete": False, "quality_passed": False,
        "source_sha256_before": _source_digests(), "expected_implementation_sha256": BASELINE_SHA256,
        "python": sys.version, "numpy": np.__version__, "platform": platform.platform(),
        "processor": platform.processor(), "logical_cpu_count": os.cpu_count(),
        "protocol": {**config, "grid_seeds": SEEDS, "methods": METHODS, "worker_thread_env": THREAD_ENV,
                     "main_boundary": "both full vertex updates followed by complete distance and witness",
                     "order_balance": "pair order changes every two geometry states; each phase sees AB and BA in every process",
                     "cold_boundary": "two independent indexes and the first complete query",
                     "stage_boundary": "separate update and query instrumentation, outside main samples",
                     "quality": "distance equality plus independent barycentric witness membership and analytic dense gaps",
                     "input_ownership_check": "both states and topology hashed after each method, outside timing; mutation aborts the case before the opponent runs",
                     "dense_phases": ["positive 0.005 m separation", "intersecting surfaces"],
                     "bootstrap_seed": BOOTSTRAP_SEED, "bootstrap_replicates": BOOTSTRAP_REPLICATES,
                     "ci_statistic": "median of paired candidate-minus-implementation time differences",
                     "ci_resampling": "paired samples resampled within each process; pooled CI stratified by process",
                     "ci_scope": "conditional on measured processes; not a machine-population or future-run interval",
                     "acceptance": "no performance thresholds decided by this script; reviewer must assess both layers"},
        "workers": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Reject existing output names before starting work. Each process creates
    # its own file exclusively; a failed worker cannot count as complete evidence.
    paths = [args.output] + [args.output.with_name(f"{args.output.stem}.worker-{i}.json")
                            for i in range(config["processes"])]
    if any(path.exists() for path in paths):
        parser.error("Output or a worker sidecar exists; choose a fresh output filename")
    with args.output.open("x", encoding="utf-8") as stream:
        _checkpoint(stream, report)
        try:
            _run_all(args, report, stream)
        except BaseException:
            report["error"] = traceback.format_exc()
            raise
        finally:
            _checkpoint(stream, report)
    print(json.dumps({"output": str(args.output.resolve()), "pilot": args.pilot,
                      "evidence_complete": report["evidence_complete"],
                      "quality_passed": report["quality_passed"],
                      "performance_accepted": None, "cases": report.get("cases")}, indent=2, allow_nan=False))
    return 0 if report["evidence_complete"] and report["quality_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
