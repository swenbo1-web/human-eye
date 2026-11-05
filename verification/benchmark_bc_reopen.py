"""Independent BC A/A diagnosis and frozen-implementation/candidate comparison.

Candidates are imported from an explicit path, never patched into production.
Raw wall and calling-thread CPU clocks are retained; CPU is auxiliary. This
script describes evidence and does not decide performance acceptance.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
from time import perf_counter_ns, thread_time_ns
import traceback

import numpy as np


SCRIPT = Path(__file__).resolve()
ROOT = SCRIPT.parents[1]
sys.path.insert(0, str(ROOT))
from verification import benchmark_bc_refinement as previous
from verification import benchmark_fast_bvh_clearance as fixtures

BASELINE = ROOT / "verification/baselines/bc_implementation.py"
BASELINE_SHA256 = "03bb9ce3bd5da99299a55d47122b38ceb2bef04aba37d998b80e0ad8de4ffa09"
OLD_SEEDS = (20261105, 79463)
HELD_OUT_SEEDS = (314159, 271828)
EXTRA_HELD_OUT_SEEDS = (141421, 161803)
METHODS = ("implementation", "candidate")
CLOCK_FIELDS = ("wall_ns", "thread_cpu_ns")
THREAD_ENV = previous.THREAD_ENV
BOOTSTRAP_SEED = 830719
BOOTSTRAP_REPLICATES = 6000


def _configuration(args):
    config = {"mode": "diagnostic_aa" if args.diagnostic else "pilot" if args.pilot else "formal",
            "processes": 1 if args.pilot else 3, "warmups": 5,
            "regular_pairs": 8 if args.pilot else 64,
            "dense_pairs": 2 if args.pilot else 8,
            "aa": bool(args.aa or args.diagnostic), "tiny": bool(args.include_tiny and not args.diagnostic),
            "seeds": [79463] if args.diagnostic else list(OLD_SEEDS if args.pilot else OLD_SEEDS + HELD_OUT_SEEDS)}
    if args.extra_heldout:
        if args.pilot or args.diagnostic:
            raise ValueError('Additional held-out inputs are for frozen formal candidates only')
        config['seeds'].extend(EXTRA_HELD_OUT_SEEDS)
        config['primary_seeds'] = list(OLD_SEEDS + HELD_OUT_SEEDS)
        config['extra_heldout_seeds'] = list(EXTRA_HELD_OUT_SEEDS)
        config['extra_heldout'] = True
    return config


def _order(index, worker, case_id):
    # A0 B0 / A1 B1 / B0 A0 / B1 A1: each state gets AB and BA.
    # Changing order on every pair would couple it to alternating geometry.
    return METHODS[::-1] if (index // 2 + worker + case_id) % 2 else METHODS


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sources(candidate):
    paths = {"benchmark": SCRIPT, "implementation": BASELINE, "candidate": candidate,
             "quality_helpers": Path(previous.__file__).resolve(),
             "fixture_helpers": Path(fixtures.__file__).resolve(),
             "fixture_imported_production_kernel": ROOT / "human_eye_fast/fast_bvh_clearance.py"}
    protocol = ROOT / "docs/BC_REOPEN_PROTOCOL.md"
    if protocol.exists():
        paths["reopen_protocol"] = protocol
    result = {name: {"path": str(path), "sha256": _digest(path)} for name, path in paths.items()}
    if result["implementation"]["sha256"] != BASELINE_SHA256:
        raise RuntimeError("The frozen implementation no longer matches the accepted source")
    return result


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class _Query:
    def __init__(self, api, case, state):
        self.api = api
        self.a = api.SurfaceIndex(state[0], case.faces_a)
        self.b = api.SurfaceIndex(state[1], case.faces_b)

    def evaluate(self, state):
        self.a.update(state[0])
        self.b.update(state[1])
        return self.api.surface_distance(self.a, self.b)

    def query(self):
        return self.api.surface_distance(self.a, self.b)


def _cold_query(api, case, state):
    query = _Query(api, case, state)
    return query, query.query()


def _measure(call, *args):
    # Identical clock-read ordering for both versions. Wall encloses both
    # CPU clock reads. No overhead correction is subtracted from samples.
    wall_start = perf_counter_ns()
    cpu_start = thread_time_ns()
    result = call(*args)
    cpu_stop = thread_time_ns()
    wall_stop = perf_counter_ns()
    return result, {"wall_ns": wall_stop - wall_start, "thread_cpu_ns": cpu_stop - cpu_start}


def _clock_overhead():
    def empty():
        return None

    raw = [_measure(empty)[1] for _ in range(256)]
    return {"operation": "same _measure wrapper around empty Python callable; not subtracted",
            "clock_info": {name: vars(time.get_clock_info(name)) for name in ("perf_counter", "thread_time")},
            "raw": raw,
            "summary": {field: _distribution([item[field] for item in raw]) for field in CLOCK_FIELDS}}


def _affinity():
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.GetCurrentProcess.restype = wintypes.HANDLE
            kernel.GetProcessAffinityMask.argtypes = (wintypes.HANDLE,
                ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t))
            kernel.GetProcessAffinityMask.restype = wintypes.BOOL
            process, system = ctypes.c_size_t(), ctypes.c_size_t()
            if not kernel.GetProcessAffinityMask(kernel.GetCurrentProcess(),
                                                  ctypes.byref(process), ctypes.byref(system)):
                raise ctypes.WinError(ctypes.get_last_error())
            return {"read_only": True, "api": "GetProcessAffinityMask",
                    "process_mask_hex": hex(process.value), "system_mask_hex": hex(system.value),
                    "scope": "current processor group on systems with multiple processor groups"}
        if hasattr(os, "sched_getaffinity"):
            return {"read_only": True, "api": "sched_getaffinity", "cpus": sorted(os.sched_getaffinity(0))}
        return {"read_only": True, "available": False}
    except Exception as error:
        return {"read_only": True, "available": False, "error": repr(error)}


def _tiny_case():
    # Pure NumPy equivalent of VG's two closest tetrahedral tips. It is a
    # supplementary workload, never mixed into the regular-state statistic.
    s = .01
    a = np.array(((0., 0., 0.), (-4*s, -2*s, -2*s), (-4*s, 2*s, -2*s), (-2*s, 0., -4*s)))
    faces = np.array(((0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)), dtype=np.intp)
    states = []
    for phase, gap in enumerate((.000025, .0004)):
        b = a.copy()
        b[:, 0] = gap - b[:, 0]
        rotation = np.eye(3) if phase == 0 else np.array(((0., -1., 0.), (1., 0., 0.), (0., 0., 1.)))
        translation = np.zeros(3) if phase == 0 else np.array((.003, -.002, .001))
        states.append((a @ rotation.T + translation, b @ rotation.T + translation))
    return fixtures.Case("tiny_tetrahedra", tuple(states), faces, faces.copy(),
                         expected_m=(.000025, .0004))


def _cases(config):
    items = []
    cells_values = (8,) if config["mode"] == "diagnostic_aa" else (8, 16)
    for seed in config["seeds"]:
        for cells in cells_values:
            for gap in (.5, .05):
                case = fixtures._grid_case(cells, gap, seed)
                items.append((f"seed_{seed}_{case.name}", "regular", seed, case))
    if config["mode"] != "diagnostic_aa":
        items.append(("dense_512", "dense", fixtures.DENSE_SEED, fixtures._dense_case()))
    if config["tiny"]:
        items.append(("tiny_tetrahedra", "tiny", None, _tiny_case()))
    return items


def _hash_inputs(case):
    return [fixtures._array_digest(case.faces_a, case.faces_b, *state) for state in case.states]


def _record_result(result):
    record = fixtures._record(result)
    encoded = json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return record, hashlib.sha256(encoded).hexdigest()


def _finish_method(result, timing, case, expected_inputs):
    output, result_hash = _record_result(result)
    observed_inputs = _hash_inputs(case)
    item = {**timing, "result": output, "result_sha256": result_hash,
            "input_state_sha256_after": observed_inputs, "input_unchanged": observed_inputs == expected_inputs,
            "thread_cpu_zero_observed": timing["thread_cpu_ns"] == 0}
    return item


def _assert_inputs(item):
    if not item["input_unchanged"]:
        raise RuntimeError("A method mutated fixture input; stopped before contaminating its opponent")


def _pair(queries, case, phase, order, index, expected_inputs):
    record = {"index": index, "phase": phase, "order": list(order),
              "input_state_sha256": expected_inputs[phase], "methods": {}}
    results = {}
    for method in order:
        result, timing = _measure(queries[method].evaluate, case.states[phase])
        results[method] = result
        item = _finish_method(result, timing, case, expected_inputs)
        record["methods"][method] = item
        _assert_inputs(item)
    record["quality"] = previous._quality(fixtures, case, phase, results)
    return record


def _cpu_block(queries, case, run, worker, case_id):
    zero_counts = {method: sum(item["methods"][method]["thread_cpu_ns"] == 0 for item in run["samples"])
                   for method in METHODS}
    run["cpu_zero_observations"] = zero_counts
    if run["group"] == "dense":
        run["cpu_blocks"] = {"performed": False,
                             "reason": "Dense states already have separate main CPU/wall samples; do not multiply the expensive positive-distance state to resolve quantization of the fast intersection state"}
        return
    if not any(zero_counts.values()):
        run["cpu_blocks"] = {"performed": False, "reason": "No zero single-call CPU readings"}
        return
    measured = [item["methods"][method]["wall_ns"] for item in run["samples"] for method in METHODS]
    average_wall = float(np.mean(measured))
    iterations = max(32, min(1024, int(math.ceil(150_000_000 / max(average_wall, 1)))))
    iterations += iterations % 2

    def continuous(query):
        last = None
        for index in range(iterations):
            last = query.evaluate(case.states[index % 2])
        return last

    diagnostic = {"performed": True, "reason": "At least one single-call thread CPU delta was zero",
                  "iterations_per_method": iterations, "states_per_method": {"0": iterations // 2, "1": iterations // 2},
                  "scope": "Auxiliary continuous update+query loop; includes Python loop, excludes per-call quality/hash. Never part of main benefit statistics.",
                  "blocks": []}
    run["cpu_blocks"] = diagnostic
    for block_id in range(2):
        order = _order(2 * block_id, worker, case_id)
        block = {"block": block_id, "order": list(order), "methods": {}}
        diagnostic["blocks"].append(block)
        results = {}
        for method in order:
            result, timing = _measure(continuous, queries[method])
            results[method] = result
            item = _finish_method(result, timing, case, run["state_sha256"])
            item["wall_ns_per_iteration"] = timing["wall_ns"] / iterations
            item["thread_cpu_ns_per_iteration"] = timing["thread_cpu_ns"] / iterations
            block["methods"][method] = item
            _assert_inputs(item)
        block["last_result_quality"] = previous._quality(fixtures, case, 1, results)


def _run_case(versions, case, group, seed, worker, case_id, config, run):
    expected_inputs = _hash_inputs(case)
    run.update({"case_id": case_id, "group": group, "seed": seed,
                "face_counts": [len(case.faces_a), len(case.faces_b)],
                "vertex_counts": [len(array) for array in case.states[0]],
                "changed_vertex_counts": [int(np.any(a != b, axis=1).sum()) for a, b in zip(*case.states)],
                "state_sha256": expected_inputs, "expected_m": case.expected_m, "z_offset_m": case.z_offset_m,
                "warmups": [], "samples": []})
    if group == "dense":
        run["overlapping_face_aabb_fraction"] = [fixtures._overlap_fraction(a[case.faces_a], b[case.faces_b])
                                                for a, b in case.states]
    queries, results = {}, {}
    cold = {"phase": 0, "order": list(_order(0, worker, case_id)), "methods": {}}
    run["cold"] = cold
    for method in cold["order"]:
        (query, result), timing = _measure(_cold_query, versions[method], case, case.states[0])
        queries[method], results[method] = query, result
        item = _finish_method(result, timing, case, expected_inputs)
        cold["methods"][method] = item
        _assert_inputs(item)
    cold["quality"] = previous._quality(fixtures, case, 0, results)
    for index in range(config["warmups"]):
        run["warmups"].append(_pair(queries, case, (index + 1) % 2,
            _order(index, worker, case_id), index, expected_inputs))
    count = config["dense_pairs"] if group == "dense" else config["regular_pairs"]
    for index in range(count):
        # Five warmups end on phase 1; the first measured phase 0 is a change.
        run["samples"].append(_pair(queries, case, index % 2,
            _order(index, worker, case_id), index, expected_inputs))
    _cpu_block(queries, case, run, worker, case_id)


def _checkpoint(stream, record):
    stream.seek(0)
    json.dump(record, stream, indent=2, allow_nan=False)
    stream.write("\n")
    stream.truncate()
    stream.flush()


def _worker(args, config, candidate, stream):
    record = {"worker": args.worker, "pid": os.getpid(), "status": "running", "config": config,
              "python": sys.version, "numpy": np.__version__, "platform": platform.platform(),
              "affinity_before": _affinity(), "thread_env": {key: os.environ.get(key) for key in THREAD_ENV},
              "source_sha256_before": _sources(candidate), "cases": {}}
    _checkpoint(stream, record)
    try:
        versions = {"implementation": _load(BASELINE, "_bc_reopen_A"),
                    "candidate": _load(candidate, "_bc_reopen_R")}
        record["clock_overhead_before"] = _clock_overhead()
        for case_id, (name, group, seed, case) in enumerate(_cases(config)):
            run = {}
            record["cases"][name] = run
            try:
                _run_case(versions, case, group, seed, args.worker, case_id, config, run)
            except Exception:
                run["error"] = traceback.format_exc()
            finally:
                _checkpoint(stream, record)
        record["clock_overhead_after"] = _clock_overhead()
        record["status"] = "completed" if all("error" not in run for run in record["cases"].values()) else "case_failed"
    except BaseException:
        record["status"] = "failed"
        record["error"] = traceback.format_exc()
        raise
    finally:
        record["source_sha256_after"] = _sources(candidate)
        record["affinity_after"] = _affinity()
        _checkpoint(stream, record)
    return 0 if record["status"] == "completed" else 1


def _distribution(values, tail=True):
    values = np.asarray(values, dtype=np.float64)
    return {"count": len(values), "median_ns": float(np.median(values)),
            "p95_ns": float(np.percentile(values, 95)) if tail else None,
            "min_ns": float(values.min()), "max_ns": float(values.max()),
            "sum_ns": float(values.sum()), "zero_count": int((values == 0).sum())}


def _ratio(numerator, denominator):
    return float(numerator / denominator) if denominator > 0 else None


def _bootstrap(groups, seed):
    rng = np.random.default_rng(seed)
    sampled = [np.asarray(values, dtype=np.float64)[rng.integers(
        0, len(values), size=(BOOTSTRAP_REPLICATES, len(values)))] for values in groups]
    medians = np.median(np.concatenate(sampled, axis=1), axis=1)
    return [float(value) for value in np.percentile(medians, (2.5, 97.5))]


def _clock_summary(groups, field, seed, tail):
    per_process, paired_groups = [], []
    for process_index, samples in enumerate(groups):
        values = {method: np.array([item["methods"][method][field] for item in samples], dtype=np.float64)
                  for method in METHODS}
        differences = values["candidate"] - values["implementation"]
        paired_groups.append(differences)
        summary = {method: _distribution(values[method], tail) for method in METHODS}
        summary.update({"worker": process_index,
            "median_ratio_R_over_A": _ratio(summary["candidate"]["median_ns"], summary["implementation"]["median_ns"]),
            "p95_ratio_R_over_A": _ratio(summary["candidate"]["p95_ns"], summary["implementation"]["p95_ns"]) if tail else None,
            "paired_difference": _distribution(differences, tail),
            "paired_median_difference_ci95_ns": _bootstrap([differences], seed + process_index + 1)})
        per_process.append(summary)
    samples = [sample for group in groups for sample in group]
    result = {method: _distribution([item["methods"][method][field] for item in samples], tail) for method in METHODS}
    result.update({"per_process": per_process,
        "median_ratio_R_over_A": _ratio(result["candidate"]["median_ns"], result["implementation"]["median_ns"]),
        "p95_ratio_R_over_A": _ratio(result["candidate"]["p95_ns"], result["implementation"]["p95_ns"]) if tail else None,
        "paired_difference": _distribution(np.concatenate(paired_groups), tail),
        "paired_median_difference_ci95_ns": _bootstrap(paired_groups, seed),
        "ci_scope": "Conditional on these workers; paired resampling stratified by worker, not a future-run interval"})
    if field == "thread_cpu_ns":
        result["interpretation"] = "Auxiliary quantized calling-thread clock; zero means observed zero delta, not zero work; no CPU acceptance gate"
    return result


def _case_summary(runs, config, case_id):
    if any("error" in run for run in runs):
        return {"evidence_complete": False, "errors": [run.get("error") for run in runs]}
    group = runs[0]["group"]
    count = config["dense_pairs"] if group == "dense" else config["regular_pairs"]
    counts_valid = all(len(run["warmups"]) == config["warmups"] and len(run["samples"]) == count for run in runs)
    schedule_valid = True
    for worker, run in enumerate(runs):
        for kind, samples in (("warmups", run["warmups"]), ("samples", run["samples"])):
            for index, sample in enumerate(samples):
                expected_phase = (index + 1) % 2 if kind == "warmups" else index % 2
                schedule_valid &= (sample["index"] == index and sample["phase"] == expected_phase
                                   and tuple(sample["order"]) == _order(index, worker, case_id))
    checks = [item for run in runs for item in (run["cold"], *run["warmups"], *run["samples"])]
    quality_passed = all(item["quality"]["passed"] for item in checks)
    quality_passed &= all(block["last_result_quality"]["passed"] for run in runs
                          for block in run["cpu_blocks"].get("blocks", ()))
    unchanged = all(item["methods"][method]["input_unchanged"] for item in checks for method in METHODS)
    same_fixtures = all(run["state_sha256"] == runs[0]["state_sha256"] for run in runs)
    full_changes = all(run["changed_vertex_counts"] == run["vertex_counts"]
                       and run["state_sha256"][0] != run["state_sha256"][1] for run in runs)
    result = {"group": group, "seed": runs[0]["seed"], "face_counts": runs[0]["face_counts"],
              "expected_m": runs[0]["expected_m"], "quality_passed": bool(quality_passed),
              "counts_valid": counts_valid, "schedule_valid": bool(schedule_valid),
              "same_fixtures": same_fixtures, "all_input_hashes_unchanged": unchanged,
              "full_vertex_changes": full_changes,
              "evidence_complete": bool(counts_valid and schedule_valid and unchanged and same_fixtures and full_changes),
              "cold_per_process": [run["cold"] for run in runs], "states": {}}
    for phase in (0, 1):
        samples = [[item for item in run["samples"] if item["phase"] == phase] for run in runs]
        result["states"][str(phase)] = {
            "sample_count": sum(map(len, samples)),
            "order_counts_per_process": [dict(Counter("/".join(item["order"]) for item in group_samples))
                                         for group_samples in samples],
            **{field: _clock_summary(samples, field, BOOTSTRAP_SEED + 1000 * case_id + 20 * phase + clock_id,
                                    tail=group != "dense") for clock_id, field in enumerate(CLOCK_FIELDS)}}
    if group == "dense":
        result["tail_interpretation"] = "Only four observations per state per process in formal mode; p95 deliberately omitted; report worst observed cost, not a tail estimate"
    elif config["mode"] == "pilot":
        result["tail_interpretation"] = "Pilot has only four observations per state; p95 is descriptive and cannot establish a tail conclusion"
    return result


def _aggregate(cases, field, worker=None):
    # Every regular geometry state contributes exactly one median to each
    # sum. Dense and optional tiny controls are excluded from this statistic.
    entries = []
    for name, case in cases.items():
        if case.get("group") != "regular" or not case.get("evidence_complete"):
            continue
        for phase, state in case["states"].items():
            stats = state[field] if worker is None else state[field]["per_process"][worker]
            entries.append({"case": name, "phase": int(phase),
                            "implementation_median_ns": stats["implementation"]["median_ns"],
                            "candidate_median_ns": stats["candidate"]["median_ns"],
                            "ratio_R_over_A": stats["median_ratio_R_over_A"]})
    sum_a = sum(item["implementation_median_ns"] for item in entries)
    sum_r = sum(item["candidate_median_ns"] for item in entries)
    positive = [item["ratio_R_over_A"] for item in entries if item["ratio_R_over_A"] is not None
                and item["ratio_R_over_A"] > 0]
    return {"regular_state_count": len(entries), "sum_state_medians_ns": {"implementation": sum_a, "candidate": sum_r},
            "sum_state_medians_ratio_R_over_A": _ratio(sum_r, sum_a),
            "geometric_mean_state_ratio_R_over_A": float(np.exp(np.log(positive).mean()))
                if len(positive) == len(entries) and entries else None,
            "geometric_mean_available": bool(entries and len(positive) == len(entries)),
            "equal_state_weight_definition": "sum of each state's candidate median divided by sum of each state's implementation median; same fixed states on both sides",
            "state_medians": entries}


def _summarize(report, config, candidate):
    workers = report["workers"]
    report["source_sha256_after"] = _sources(candidate)
    report["same_sources"] = report["source_sha256_after"] == report["source_sha256_before"] and all(
        worker.get("source_sha256_before") == report["source_sha256_before"]
        and worker.get("source_sha256_after") == report["source_sha256_before"] for worker in workers)
    pids = [worker.get("pid") for worker in workers]
    report["independent_pids"] = None not in pids and len(set(pids)) == config["processes"]
    report["thread_env_confirmed"] = all(worker.get("thread_env") == THREAD_ENV for worker in workers)
    names = [item[0] for item in _cases(config)]
    report["case_sets_complete"] = all(list(worker.get("cases", {})) == names for worker in workers)
    if not report["case_sets_complete"]:
        return
    report["cases"] = {name: _case_summary([worker["cases"][name] for worker in workers], config, case_id)
                       for case_id, name in enumerate(names)}
    regular_count = 4 if config["mode"] == "diagnostic_aa" else 16 if config["mode"] == "pilot" else 32
    primary_cases = {name: case for name, case in report['cases'].items()
                     if case.get('seed') not in config.get('extra_heldout_seeds', [])}
    report["regular_equal_state_statistics"] = {
        field: {"pooled": _aggregate(primary_cases, field),
                "per_process": [_aggregate(primary_cases, field, worker) for worker in range(config["processes"])]}
        for field in CLOCK_FIELDS}
    if config.get('extra_heldout'):
        extra_cases = {name: case for name, case in report['cases'].items()
                       if case.get('seed') in EXTRA_HELD_OUT_SEEDS}
        report['extra_heldout_statistics'] = {
            field: {'pooled': _aggregate(extra_cases, field),
                    'per_process': [_aggregate(extra_cases, field, worker) for worker in range(config['processes'])]}
            for field in CLOCK_FIELDS}
        report['all_observed_regular_statistics'] = {
            field: _aggregate(report['cases'], field) for field in CLOCK_FIELDS}
    report["expected_regular_state_count"] = regular_count
    report["quality_passed"] = all(case.get("quality_passed", False) for case in report["cases"].values())
    report["evidence_complete"] = bool(report["same_sources"] and report["independent_pids"]
        and report["thread_env_confirmed"] and all(worker.get("status") == "completed" for worker in workers)
        and all(case["evidence_complete"] for case in report["cases"].values())
        and report["regular_equal_state_statistics"]["wall_ns"]["pooled"]["regular_state_count"] == regular_count)


def _run_all(args, config, candidate, report, stream):
    for worker in range(config["processes"]):
        worker_path = args.output.with_name(f"{args.output.stem}.worker-{worker}.json")
        command = [sys.executable, "-B", str(SCRIPT), "--worker", str(worker),
                   "--worker-output", str(worker_path)]
        if args.diagnostic:
            command.append("--diagnostic")
        elif args.pilot:
            command.append("--pilot")
        if config["aa"]:
            command.append("--aa")
        else:
            command.extend(("--candidate", str(candidate)))
        if config["tiny"]:
            command.append("--include-tiny")
        if args.extra_heldout:
            command.append("--extra-heldout")
        print(f"BC {config['mode']} worker {worker}: {worker_path}", flush=True)
        completed = subprocess.run(command, cwd=ROOT, env={**os.environ, **THREAD_ENV, "PYTHONDONTWRITEBYTECODE": "1"},
                                   capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        try:
            data = json.loads(worker_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {"status": "missing_evidence", "error": "Worker did not leave valid JSON"}
        data.update({"worker_output_path": str(worker_path), "worker_command": command,
                     "exit_code": completed.returncode})
        if completed.stdout:
            data["stdout"] = completed.stdout
        if completed.stderr:
            data["stderr"] = completed.stderr
        report["workers"].append(data)
        _checkpoint(stream, report)
    _summarize(report, config, candidate)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, help="Standalone Python candidate; never copied over production")
    parser.add_argument("--aa", action="store_true", help="Load the same accepted source as two independent modules")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--diagnostic", action="store_true", help="A/A only: seed 79463, 128-face separated/near, 3 workers and 64 pairs")
    mode.add_argument("--pilot", action="store_true", help="Only the two old seeds: 1 worker, 8 pairs/case, dense 2 pairs")
    parser.add_argument("--include-tiny", action="store_true", help="Supplementary 4-face-per-object tetrahedra, excluded from regular aggregate")
    parser.add_argument("--extra-heldout", action="store_true", help="Append 16 new blind states; original 32-state gate remains separate")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--worker", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--worker-output", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    config = _configuration(args)
    if config["aa"] and args.candidate is not None:
        parser.error("--aa/--diagnostic and --candidate are mutually exclusive")
    if not config["aa"] and args.candidate is None:
        parser.error("Specify --candidate PATH, --aa, or --diagnostic")
    candidate = BASELINE if config["aa"] else args.candidate.resolve()
    if args.worker is not None:
        if args.worker_output is None:
            parser.error("An internal worker needs --worker-output")
        with args.worker_output.open("x", encoding="utf-8") as stream:
            return _worker(args, config, candidate, stream)
    if args.output is None:
        parser.error("--output NEW_JSON is required")
    args.output = args.output.resolve()
    archive = args.output.with_name(f"{args.output.stem}.sources")
    reserved = [args.output, archive] + [args.output.with_name(f"{args.output.stem}.worker-{worker}.json")
                                       for worker in range(config["processes"])]
    if any(path.exists() for path in reserved):
        parser.error("Output, source archive, or worker sidecar exists; choose a new output name")
    sources = _sources(candidate)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    archive.mkdir()
    for name, source in sources.items():
        path = Path(source["path"])
        archived = archive / f"{name}{path.suffix}"
        shutil.copyfile(path, archived)
        if _digest(archived) != source["sha256"]:
            raise RuntimeError(f"Source changed while archiving {name}; retained failed archive")
    (archive / "manifest.json").write_text(json.dumps(sources, indent=2) + "\n", encoding="utf-8")
    report = {"comparison": "same-source A/A" if config["aa"] else "standalone candidate versus frozen accepted implementation",
              "config": config, "candidate_path": str(candidate), "expected_implementation_sha256": BASELINE_SHA256,
              "source_sha256_before": sources, "source_archive": str(archive),
              "python": sys.version, "numpy": np.__version__, "platform": platform.platform(),
              "processor": platform.processor(), "logical_cpu_count": os.cpu_count(),
              "evidence_complete": False, "quality_passed": False, "performance_accepted": None,
              "protocol": {"boundary": "both full vertex updates plus complete distance and witness; includes candidate projection-table construction inside update/query",
                           "cold_boundary": "two independent index constructions and complete first query",
                           "wall_clock": "perf_counter_ns, outer span containing both CPU clock reads",
                           "cpu_clock": "thread_time_ns for the calling thread only; auxiliary, may be quantized, not a gate",
                           "overhead": "256 identical empty-call measurements before/after; raw values retained, never subtracted",
                           "cpu_zero_policy": "zero delta is not zero cost; affected cases additionally run separate continuous balanced-state CPU blocks",
                           "order": "AB on two consecutive opposite states, then BA on two; every formal state has both orders in each worker",
                           "warmups": "5, ending phase1; measured sequence starts phase0 and changes all vertices on both objects",
                           "quality": "frozen accepted distance comparison and independent barycentric witnesses; dense/tiny analytic distance",
                           "hashes": "both complete fixture states checked after each method before opponent; result and per-state hashes outside timing",
                           "held_out_seeds": "314159 and 271828 appear in formal mode only, excluded from pilot and diagnostic",
                           "p95": "numpy percentile 95, linear interpolation; dense p95 omitted due small sample count",
                           "bootstrap_replicates": BOOTSTRAP_REPLICATES, "bootstrap_seed": BOOTSTRAP_SEED,
                           "bootstrap": "paired candidate-minus-implementation median difference, stratified by worker",
                           "regular_primary_statistic": "sum of the 32 fixed ordinary-state candidate medians / sum of their implementation medians; geometric mean ratio also reported",
                           "excluded_from_regular_statistic": ["dense positive/intersection", "optional tiny tetrahedra"],
                           "review": "No performance threshold or PASS is assigned by this script"}, "workers": []}
    with args.output.open("x", encoding="utf-8") as stream:
        _checkpoint(stream, report)
        try:
            _run_all(args, config, candidate, report, stream)
        except BaseException:
            report["error"] = traceback.format_exc()
            raise
        finally:
            _checkpoint(stream, report)
    print(json.dumps({"output": str(args.output), "mode": config["mode"],
                      "evidence_complete": report["evidence_complete"], "quality_passed": report["quality_passed"],
                      "performance_accepted": None,
                      "regular_equal_state_statistics": {
                          field: {key: value for key, value in data["pooled"].items() if key != "state_medians"}
                          for field, data in report.get("regular_equal_state_statistics", {}).items()}
                      }, indent=2, allow_nan=False))
    return 0 if report["evidence_complete"] and report["quality_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
