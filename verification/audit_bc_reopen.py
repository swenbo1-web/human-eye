"""Independently audit a completed BC reopen report from raw paired samples.

No candidate or benchmark code is imported or executed. CPU measurements are
descriptive only. Final adoption also needs numerical and Blender evidence
outside this comparison file.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

import numpy as np


BASELINE_SHA256 = "03bb9ce3bd5da99299a55d47122b38ceb2bef04aba37d998b80e0ad8de4ffa09"
METHODS = ("implementation", "candidate")
OLD_SEEDS = (20261105, 79463)
NEW_SEEDS = (314159, 271828)
EXTRA_SEEDS = (141421, 161803)
THREAD_KEYS = ("BLIS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS",
               "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS")
BOOTSTRAP_SEED = 1173951
BOOTSTRAP_REPLICATES = 6000


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _array_digest(*arrays):
    digest = hashlib.sha256()
    for array in arrays:
        digest.update(repr((array.shape, array.dtype.str)).encode("ascii"))
        digest.update(array.tobytes())
    return digest.hexdigest()


def _grid(cells, gap, seed):
    rng = np.random.default_rng([seed, cells, round(100 * gap)])
    values = np.linspace(-.5, .5, cells + 1)
    xx, yy = np.meshgrid(values, values)
    x, y = xx.ravel(), yy.ravel()
    stride = cells + 1
    origins = np.arange(stride * stride).reshape(stride, stride)[:-1, :-1].ravel()
    faces = np.empty((2 * cells * cells, 3), dtype=np.intp)
    faces[0::2] = np.column_stack((origins, origins + 1, origins + stride + 1))
    faces[1::2] = np.column_stack((origins, origins + stride + 1, origins + stride))

    def mesh(z_base):
        dx, dy = rng.uniform(-.075, .075, 2)
        px, py = rng.uniform(0, 2 * np.pi, 2)
        z = z_base + .009 * np.sin(7 * x + px) * np.cos(8 * y + py)
        return np.column_stack((x + dx, y + dy, z))

    return {"states": tuple((mesh(0.), mesh(gap)) for _ in range(2)),
            "faces": (faces, faces.copy()), "expected": None, "group": "regular", "seed": seed}


def _dense():
    rng = np.random.default_rng(512)
    anchor = np.array(((-1., -.7), (1., -.6), (0., 1.)))

    def mesh(slope, z_base):
        xy = (anchor + rng.uniform(-.1, .1, (512, 3, 2))).reshape(-1, 2)
        return np.column_stack((xy, slope * xy[:, 0] + .5 * xy[:, 1] + z_base))

    states = ((mesh(.5, 0.), mesh(.5, .005 * np.sqrt(1.5))),
              (mesh(.5, 0.), mesh(-.5, 0.)))
    faces = np.arange(512 * 3, dtype=np.intp).reshape(-1, 3)
    return {"states": states, "faces": (faces, faces.copy()), "expected": (.005, 0.),
            "group": "dense", "seed": 512}


def _tiny():
    s = .01
    a = np.array(((0., 0., 0.), (-4*s, -2*s, -2*s), (-4*s, 2*s, -2*s), (-2*s, 0., -4*s)))
    faces = np.array(((0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)), dtype=np.intp)
    states = []
    for phase, gap in enumerate((.000025, .0004)):
        b = a.copy()
        b[:, 0] = gap - b[:, 0]
        rotation = np.eye(3) if not phase else np.array(((0., -1., 0.), (1., 0., 0.), (0., 0., 1.)))
        shift = np.zeros(3) if not phase else np.array((.003, -.002, .001))
        states.append((a @ rotation.T + shift, b @ rotation.T + shift))
    return {"states": tuple(states), "faces": (faces, faces.copy()), "expected": (.000025, .0004),
            "group": "tiny", "seed": None}


def _expected_cases(mode, tiny, extra_heldout=False):
    result = {}
    seeds = (79463,) if mode == "diagnostic_aa" else OLD_SEEDS if mode == "pilot" else OLD_SEEDS + NEW_SEEDS
    if extra_heldout:
        if mode != "formal":
            raise ValueError("Extra held-out seeds belong to a frozen formal run only")
        seeds += EXTRA_SEEDS
    for seed in seeds:
        for cells in ((8,) if mode == "diagnostic_aa" else (8, 16)):
            for gap, kind in ((.5, "separated"), (.05, "near")):
                result[f"seed_{seed}_grid_{2*cells*cells}_{kind}"] = _grid(cells, gap, seed)
    if mode != "diagnostic_aa":
        result["dense_512"] = _dense()
    if tiny and mode != "diagnostic_aa":
        result["tiny_tetrahedra"] = _tiny()
    return result


def _order(index, worker, case_id):
    return METHODS[::-1] if ((index // 2) + worker + case_id) % 2 else METHODS


def _tolerance(fixture, phase):
    surface = np.concatenate([vertices[faces].reshape(-1, 3)
                              for vertices, faces in zip(fixture["states"][phase], fixture["faces"])])
    return float(1e-10 * np.linalg.norm(np.ptp(surface, axis=0))
                 + 32 * np.finfo(np.float64).eps * np.abs(surface).max())


def _point_error(point, triangle):
    basis = (triangle[1:] - triangle[0]).T
    coefficients = np.linalg.lstsq(basis, point - triangle[0], rcond=None)[0]
    residual = np.linalg.norm(basis @ coefficients - (point - triangle[0]))
    outside = max(0., -float(coefficients.min()), float(coefficients.sum() - 1))
    return float(max(residual, outside * np.linalg.norm(basis)))


def _quality(fixture, phase, outputs):
    tolerance = _tolerance(fixture, phase)
    errors = {}
    try:
        for method, output in outputs.items():
            distance = float(output["distance_m"])
            pa, pb = np.asarray(output["point_a"], dtype=float), np.asarray(output["point_b"], dtype=float)
            if distance < 0 or not np.isfinite(distance) or pa.shape != (3,) or pb.shape != (3,) or not np.isfinite([pa, pb]).all():
                return {"passed": False, "reason": f"invalid output {method}"}
            points = (pa, pb)
            check = {"separation_error_m": float(abs(np.linalg.norm(pa - pb) - distance))}
            for side, key in enumerate(("triangle_a", "triangle_b")):
                face_id = output[key]
                if type(face_id) is not int or not 0 <= face_id < len(fixture["faces"][side]):
                    return {"passed": False, "reason": f"invalid source face {method}/{key}"}
                triangle = fixture["states"][phase][side][fixture["faces"][side][face_id]]
                check[f"face_{side}_error_m"] = _point_error(points[side], triangle)
            if fixture["expected"] is not None:
                expected = fixture["expected"][phase]
                check["analytic_distance_error_m"] = abs(distance - expected)
                if (distance == 0.) != (expected == 0.):
                    return {"passed": False, "reason": f"zero-distance semantics {method}"}
            errors[method] = check
        delta = abs(float(outputs["candidate"]["distance_m"]) - float(outputs["implementation"]["distance_m"]))
        passed = delta <= tolerance and all(np.isfinite(value) and value <= tolerance
                                          for check in errors.values() for value in check.values())
        return {"passed": bool(passed), "tolerance_m": tolerance, "distance_delta_m": delta,
                "max_witness_or_analytic_error_m": max(value for check in errors.values() for value in check.values())}
    except (KeyError, TypeError, ValueError, IndexError) as error:
        return {"passed": False, "reason": repr(error)}


class Checks:
    def __init__(self):
        self.counts = Counter()
        self.failures = []

    def check(self, condition, category, location, detail=None):
        self.counts[category] += 1
        if not condition:
            self.failures.append({"category": category, "location": location, "detail": detail})

    def passed(self, *categories):
        return not any(item["category"] in categories for item in self.failures)


def _verify_sources(data, archive, checks):
    sources = data["source_sha256_before"]
    checks.check(data.get("source_sha256_after") == sources, "sources", "parent before/after")
    checks.check(sources.get("implementation", {}).get("sha256") == BASELINE_SHA256,
                 "sources", "accepted baseline digest")
    checks.check(sources.get("fixture_imported_production_kernel", {}).get("sha256") == BASELINE_SHA256,
                 "sources", "production kernel remains qualified A")
    result = {}
    for label, source in sources.items():
        path = archive / f"{label}{Path(source['path']).suffix}"
        actual = _sha(path.read_bytes()) if path.exists() else None
        checks.check(actual == source["sha256"], "sources", f"archive/{label}", {"actual": actual})
        result[label] = {"path": str(path), "sha256": actual}
    manifest = archive / "manifest.json"
    checks.check(manifest.exists() and json.loads(manifest.read_text(encoding="utf-8")) == sources,
                 "sources", "source manifest")
    for worker in data["workers"]:
        checks.check(worker.get("source_sha256_before") == sources and worker.get("source_sha256_after") == sources,
                     "sources", f"worker {worker.get('worker')} source binding")
    return result


def _sample_check(sample, fixture, phase, hashes, checks, location, quality_key="quality"):
    outputs = {}
    checks.check(set(sample["methods"]) == set(METHODS), "samples", location + "/methods")
    for method in METHODS:
        item = sample["methods"][method]
        checks.check(type(item["wall_ns"]) is int and item["wall_ns"] > 0,
                     "samples", location + f"/{method}/wall clock")
        checks.check(type(item["thread_cpu_ns"]) is int and item["thread_cpu_ns"] >= 0,
                     "samples", location + f"/{method}/auxiliary CPU clock")
        checks.check(item.get("input_unchanged") is True and item.get("input_state_sha256_after") == hashes,
                     "inputs", location + f"/{method}/input hash")
        output = item["result"]
        serialized = json.dumps(output, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        checks.check(_sha(serialized) == item.get("result_sha256"), "outputs", location + f"/{method}/result hash")
        outputs[method] = output
    independent = _quality(fixture, phase, outputs)
    checks.check(independent["passed"], "quality", location, independent if not independent["passed"] else None)
    checks.check(sample.get(quality_key, {}).get("passed") is True, "reported_quality", location)
    return independent


def _distribution(values, tail=True):
    return {"count": len(values), "median_ns": float(np.median(values)),
            "p95_ns": float(np.percentile(values, 95)) if tail else None,
            "min_ns": float(np.min(values)), "max_ns": float(np.max(values))}


def _metrics(pairs, tail=True):
    a, r = pairs[:, 0], pairs[:, 1]
    stats_a, stats_r = _distribution(a, tail), _distribution(r, tail)
    return {"implementation": stats_a, "candidate": stats_r,
            "median_ratio_R_over_A": stats_r["median_ns"] / stats_a["median_ns"],
            "median_difference_ns": stats_r["median_ns"] - stats_a["median_ns"],
            "p95_ratio_R_over_A": stats_r["p95_ns"] / stats_a["p95_ns"] if tail else None,
            "paired_difference_median_ns": float(np.median(r - a)),
            "paired_difference_p95_ns": float(np.percentile(r - a, 95)) if tail else None}


def _local_gates(metrics, group):
    ratio, delta = metrics["median_ratio_R_over_A"], metrics["median_difference_ns"]
    if group == "regular":
        median = ratio <= 1.10 or delta <= 250_000
        tail = metrics["p95_ratio_R_over_A"] <= 1.25
        return {"median_ratio_le_1_10_or_delta_le_250000_ns": median,
                "p95_ratio_le_1_25": tail, "passed": median and tail}
    if group == "dense":
        return {"median_ratio_le_1_10": ratio <= 1.10, "passed": ratio <= 1.10}
    return {"median_delta_le_250000_ns": delta <= 250_000, "passed": delta <= 250_000}


def _aggregate(states, worker=None):
    rows = [state["pooled"] if worker is None else state["per_process"][worker] for state in states]
    if not rows:
        return {"state_count": 0, "sum_state_medians_ratio_R_over_A": None,
                "sum_state_medians_difference_ns": None, "geometric_mean_state_ratio_R_over_A": None}
    total_a = sum(row["implementation"]["median_ns"] for row in rows)
    total_r = sum(row["candidate"]["median_ns"] for row in rows)
    ratios = [row["median_ratio_R_over_A"] for row in rows]
    return {"state_count": len(rows), "sum_state_medians_ns": {"implementation": total_a, "candidate": total_r},
            "sum_state_medians_ratio_R_over_A": total_r / total_a,
            "sum_state_medians_difference_ns": total_r - total_a,
            "geometric_mean_state_ratio_R_over_A": float(np.exp(np.mean(np.log(ratios)))),
            "states_faster": sum(ratio < 1 for ratio in ratios),
            "states_slower": sum(ratio > 1 for ratio in ratios),
            "states_equal": sum(ratio == 1 for ratio in ratios)}


def _bootstrap_aggregates(states, arrays, processes, replicates=BOOTSTRAP_REPLICATES):
    """Resample pairs independently within each process x geometry state."""
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    sums = {group: {"pooled": np.zeros((replicates, 2)),
                    "per_process": np.zeros((processes, replicates, 2)), "states": 0}
            for group in ("all", "old_seeds", "new_seeds", "extra_heldout", "all_observed_regular")}
    for state in states:
        groups = arrays[state["state_id"]]
        sampled = [values[rng.integers(0, len(values), size=(replicates, len(values)))] for values in groups]
        pooled_medians = np.median(np.concatenate(sampled, axis=1), axis=1)
        process_medians = np.stack([np.median(values, axis=1) for values in sampled])
        keys = ["all_observed_regular"]
        if state["seed"] in OLD_SEEDS:
            keys += ["all", "old_seeds"]
        elif state["seed"] in NEW_SEEDS:
            keys += ["all", "new_seeds"]
        elif state["seed"] in EXTRA_SEEDS:
            keys += ["extra_heldout"]
        else:
            raise ValueError(f"Unfrozen seed {state['seed']}")
        for key in keys:
            sums[key]["pooled"] += pooled_medians
            sums[key]["per_process"] += process_medians
            sums[key]["states"] += 1

    def interval(values):
        a, r = values[:, 0], values[:, 1]
        return {"sum_state_medians_ratio_R_over_A_ci95": np.percentile(r / a, (2.5, 97.5)).tolist(),
                "sum_state_medians_difference_ns_ci95": np.percentile(r - a, (2.5, 97.5)).tolist()}

    result = {"seed": BOOTSTRAP_SEED, "replicates": replicates, "confidence": .95,
              "pairing": "A and R use the same resampled index in each process x state stratum",
              "aggregation": "Within each replicate: pool resampled processes within each state, take separate A/R state medians, then sum exactly one median per state; ratio and difference of those sums",
              "scope": "Conditional on the measured processes and fixed states, not future-process or deployment-frequency uncertainty",
              "groups": {}}
    for name, values in sums.items():
        result["groups"][name] = {"state_count": values["states"],
            "pooled": interval(values["pooled"]) if values["states"] else None,
            "per_process": [interval(value) for value in values["per_process"]] if values["states"] else []}
    return result


def _audit(data, archive, replicates=BOOTSTRAP_REPLICATES):
    checks = Checks()
    config = data["config"]
    mode = config["mode"]
    if mode not in ("formal", "pilot", "diagnostic_aa"):
        raise ValueError(f"Unknown mode {mode}")
    processes = 1 if mode == "pilot" else 3
    regular_pairs = 8 if mode == "pilot" else 64
    dense_pairs = 2 if mode == "pilot" else 8
    tiny = bool(config.get("tiny"))
    extra_heldout = bool(config.get("extra_heldout", False))
    expected = _expected_cases(mode, tiny, extra_heldout)
    workers = data["workers"]
    checks.check(len(workers) == processes, "schedule", "worker count")
    checks.check(config.get("processes") == processes and config.get("regular_pairs") == regular_pairs
                 and config.get("dense_pairs") == dense_pairs and config.get("warmups") == 5,
                 "schedule", "frozen sample configuration")
    pids = [worker.get("pid") for worker in workers]
    checks.check(all(type(pid) is int for pid in pids) and len(set(pids)) == processes,
                 "schedule", "distinct native PIDs", pids)
    provenance = _verify_sources(data, archive, checks)
    arrays, states, cpu_auxiliary = {}, [], []
    quality_count, maximum_distance_delta, maximum_witness_error = 0, 0., 0.
    for worker_id, worker in enumerate(workers):
        checks.check(worker.get("worker") == worker_id and worker.get("status") == "completed" and worker.get("exit_code") == 0,
                     "schedule", f"worker {worker_id} completed")
        checks.check(worker.get("config") == config, "schedule", f"worker {worker_id} config")
        checks.check(worker.get("thread_env") == dict.fromkeys(THREAD_KEYS, "1"),
                     "schedule", f"worker {worker_id} single-thread BLAS environment")
        checks.check(list(worker.get("cases", {})) == list(expected), "schedule", f"worker {worker_id} exact case matrix")
        cpu_auxiliary.append({"worker": worker_id, "pid": worker.get("pid"),
            "clock_info_before": worker.get("clock_overhead_before", {}).get("clock_info"),
            "clock_overhead_before_summary": worker.get("clock_overhead_before", {}).get("summary"),
            "clock_overhead_after_summary": worker.get("clock_overhead_after", {}).get("summary"),
            "affinity_before": worker.get("affinity_before"), "affinity_after": worker.get("affinity_after"),
            "zero_counts": {}, "continuous_blocks": {}})

    for case_id, (name, fixture) in enumerate(expected.items()):
        group = fixture["group"]
        hashes = [_array_digest(*fixture["faces"], *vertices) for vertices in fixture["states"]]
        for worker_id, worker in enumerate(workers):
            run = worker["cases"][name]
            location = f"worker {worker_id}/{name}"
            checks.check(run.get("case_id") == case_id and run.get("group") == group and run.get("seed") == fixture["seed"],
                         "inputs", location + "/identity")
            checks.check(run.get("state_sha256") == hashes, "inputs", location + "/regenerated fixture hashes")
            changes = [int(np.any(a != b, axis=1).sum()) for a, b in zip(*fixture["states"])]
            checks.check(run.get("vertex_counts") == [len(v) for v in fixture["states"][0]]
                         and run.get("changed_vertex_counts") == changes
                         and changes == [len(v) for v in fixture["states"][0]], "inputs", location + "/full updates")
            checks.check(run.get("face_counts") == [len(faces) for faces in fixture["faces"]],
                         "inputs", location + "/face count")
            expected_count = dense_pairs if group == "dense" else regular_pairs
            checks.check(len(run.get("warmups", [])) == 5 and len(run.get("samples", [])) == expected_count,
                         "schedule", location + "/pair counts")
            tagged = [("cold", 0, run["cold"])] + [("warmups", i, sample) for i, sample in enumerate(run["warmups"])]
            tagged += [("samples", i, sample) for i, sample in enumerate(run["samples"])]
            for kind, index, sample in tagged:
                phase = 0 if kind == "cold" else (index + 1) % 2 if kind == "warmups" else index % 2
                item_location = f"{location}/{kind}/{index}"
                checks.check(sample.get("phase") == phase and tuple(sample.get("order", ())) == _order(index, worker_id, case_id),
                             "schedule", item_location)
                if kind != "cold":
                    checks.check(sample.get("index") == index and sample.get("input_state_sha256") == hashes[phase],
                                 "inputs", item_location + "/phase binding")
                quality = _sample_check(sample, fixture, phase, hashes, checks, item_location)
                quality_count += 1
                maximum_distance_delta = max(maximum_distance_delta, quality.get("distance_delta_m", 0))
                maximum_witness_error = max(maximum_witness_error, quality.get("max_witness_or_analytic_error_m", 0))
                maximum_distance_delta = max(maximum_distance_delta, quality.get("distance_delta_m", 0))
                maximum_witness_error = max(maximum_witness_error, quality.get("max_witness_or_analytic_error_m", 0))
            for block in run.get("cpu_blocks", {}).get("blocks", ()):
                quality = _sample_check(block, fixture, 1, hashes, checks,
                    f"{location}/auxiliary CPU block/{block['block']}", quality_key="last_result_quality")
                quality_count += 1
            cpu_auxiliary[worker_id]["zero_counts"][name] = {
                method: sum(sample["methods"][method]["thread_cpu_ns"] == 0 for sample in run["samples"])
                for method in METHODS}
            cpu_auxiliary[worker_id]["continuous_blocks"][name] = {
                "performed": run.get("cpu_blocks", {}).get("performed", False),
                "iterations_per_method": run.get("cpu_blocks", {}).get("iterations_per_method"),
                "blocks": [{"block": block["block"], "order": block["order"],
                            "methods": {method: {key: block["methods"][method].get(key)
                                for key in ("wall_ns", "thread_cpu_ns", "wall_ns_per_iteration", "thread_cpu_ns_per_iteration")}
                                for method in METHODS}} for block in run.get("cpu_blocks", {}).get("blocks", ())]}

        for phase in (0, 1):
            state_id = f"{name}/phase_{phase}"
            paired, order_counts = [], []
            for worker_id, worker in enumerate(workers):
                samples = [sample for sample in worker["cases"][name]["samples"] if sample["phase"] == phase]
                order_counts.append(dict(Counter("/".join(sample["order"]) for sample in samples)))
                checks.check(len(samples) == (dense_pairs if group == "dense" else regular_pairs) // 2,
                             "schedule", f"worker {worker_id}/{state_id}/state count")
                if not (mode == "pilot" and group == "dense"):
                    checks.check(len(order_counts[-1]) == 2 and len(set(order_counts[-1].values())) == 1,
                                 "schedule", f"worker {worker_id}/{state_id}/AB BA balance")
                paired.append(np.array([[sample["methods"][method]["wall_ns"] for method in METHODS]
                                         for sample in samples], dtype=np.float64))
            arrays[state_id] = paired
            pooled = _metrics(np.concatenate(paired), tail=group != "dense")
            per_process = [_metrics(values, tail=group != "dense") for values in paired]
            state = {"state_id": state_id, "case": name, "phase": phase, "seed": fixture["seed"], "group": group,
                     "pooled": pooled, "per_process": per_process, "order_counts_per_process": order_counts,
                     "local_gates": _local_gates(pooled, group),
                     "local_thresholds_per_process_descriptive_only": [_local_gates(item, group) for item in per_process]}
            states.append(state)
            previous_state = data.get("cases", {}).get(name, {}).get("states", {}).get(str(phase), {}).get("wall_ns", {})
            for key in ("median_ratio_R_over_A", "p95_ratio_R_over_A"):
                actual, reported = pooled[key], previous_state.get(key)
                checks.check((actual is None and reported is None) or
                             (actual is not None and reported is not None and math.isclose(actual, reported, rel_tol=1e-12, abs_tol=1e-12)),
                             "summary", f"{state_id}/{key}", {"recomputed": actual, "reported": reported})

    ordinary = [state for state in states if state["group"] == "regular"]
    primary = [state for state in ordinary if state["seed"] in OLD_SEEDS + NEW_SEEDS]
    grouped = {"all": primary, "old_seeds": [state for state in ordinary if state["seed"] in OLD_SEEDS],
               "new_seeds": [state for state in ordinary if state["seed"] in NEW_SEEDS],
               "extra_heldout": [state for state in ordinary if state["seed"] in EXTRA_SEEDS],
               "all_observed_regular": ordinary}
    aggregate = {name: {"pooled": _aggregate(selected),
                        "per_process": [_aggregate(selected, worker) for worker in range(processes)]}
                 for name, selected in grouped.items()}
    by_seed = {str(seed): {"pooled": _aggregate([state for state in ordinary if state["seed"] == seed]),
                          "per_process": [_aggregate([state for state in ordinary if state["seed"] == seed], worker)
                                          for worker in range(processes)]}
               for seed in (*OLD_SEEDS, *NEW_SEEDS, *EXTRA_SEEDS) if any(state["seed"] == seed for state in ordinary)}
    declared = data.get("regular_equal_state_statistics", {}).get("wall_ns", {})
    for index, calculated in [(None, aggregate["all"]["pooled"])] + list(enumerate(aggregate["all"]["per_process"])):
        source = declared.get("pooled", {}) if index is None else declared.get("per_process", [{}] * processes)[index]
        for key in ("sum_state_medians_ratio_R_over_A", "geometric_mean_state_ratio_R_over_A"):
            checks.check(source.get(key) is not None and math.isclose(calculated[key], source[key], rel_tol=1e-12),
                         "summary", f"aggregate/{index}/{key}")
    bootstrap = _bootstrap_aggregates(ordinary, arrays, processes, replicates)
    formal = mode == "formal" and not config.get("aa")
    all_stats = aggregate["all"]
    new_group = aggregate["new_seeds"]["pooled"]
    extra_group = aggregate["extra_heldout"]["pooled"]
    dense_states = [state for state in states if state["group"] == "dense"]
    tiny_states = [state for state in states if state["group"] == "tiny"]
    difference_ci = bootstrap["groups"]["all"]["pooled"]["sum_state_medians_difference_ns_ci95"]
    gates = {
        "formal_candidate_32_primary_states": {"passed": formal and len(primary) == 32, "value": len(primary)},
        "source_schedule_hash_integrity": {"passed": checks.passed("sources", "schedule", "inputs", "outputs", "samples")},
        "independent_witness_and_distance_quality": {"passed": checks.passed("quality", "reported_quality")},
        "benchmark_summary_matches_independent_reduction": {"passed": checks.passed("summary")},
        "overall_ratio_le_0_80": {"passed": all_stats["pooled"]["sum_state_medians_ratio_R_over_A"] <= .80,
                                  "value": all_stats["pooled"]["sum_state_medians_ratio_R_over_A"]},
        "every_process_overall_ratio_le_0_85": {
            "passed": all(row["sum_state_medians_ratio_R_over_A"] <= .85 for row in all_stats["per_process"]),
            "values": [row["sum_state_medians_ratio_R_over_A"] for row in all_stats["per_process"]]},
        "overall_paired_bootstrap_difference_supports_gain": {"passed": difference_ci[1] < 0,
                                                              "ci95_ns": difference_ci},
        "all_ordinary_state_local_limits": {"passed": all(state["local_gates"]["passed"] for state in ordinary),
            "exceeding_states": [state["state_id"] for state in ordinary if not state["local_gates"]["passed"]]},
        "new_seed_group_does_not_slow": {"passed": new_group["state_count"] == 16 and new_group["sum_state_medians_ratio_R_over_A"] <= 1.,
                                         "value": new_group["sum_state_medians_ratio_R_over_A"], "state_count": new_group["state_count"]},
        "extra_heldout_16_states_ratio_le_0_85": {
            "applicable": extra_heldout,
            "passed": (extra_group["state_count"] == 16 and extra_group["sum_state_medians_ratio_R_over_A"] <= .85)
                       if extra_heldout else extra_group["state_count"] == 0,
            "value": extra_group["sum_state_medians_ratio_R_over_A"], "state_count": extra_group["state_count"]},
        "dense_both_state_median_ratios_le_1_10": {"passed": len(dense_states) == 2 and all(state["local_gates"]["passed"] for state in dense_states),
            "values": {state["state_id"]: state["pooled"]["median_ratio_R_over_A"] for state in dense_states}},
        "tiny_both_state_median_delta_le_250000_ns": {"passed": len(tiny_states) == 2 and all(state["local_gates"]["passed"] for state in tiny_states),
            "values": {state["state_id"]: state["pooled"]["median_difference_ns"] for state in tiny_states}},
    }
    return {"mode": mode, "formal_gates_applicable": formal, "gates": gates,
            "comparison_gates_passed": all(gate["passed"] for gate in gates.values()),
            "final_acceptance": "PENDING_EXTERNAL_TEST_EVIDENCE_AND_PRIMARY_REVIEW",
            "external_requirements_not_established_by_this_file": [
                "Original BC reasonable full-pair baseline benefit gates for the new candidate",
                "Independent numerical/degenerate/update oracle tests for the new candidate",
                "Real Blender wiring tests for the new candidate",
                "Review any exceeded local gate using retained same-state supplemental evidence, without deleting this run"],
            "checks": {"counts": dict(checks.counts), "failures": checks.failures,
                       "independent_quality_pairs": quality_count,
                       "max_distance_delta_m": maximum_distance_delta, "max_witness_or_analytic_error_m": maximum_witness_error},
            "source_archive_verification": provenance,
            "aggregate": aggregate, "by_seed": by_seed, "bootstrap": bootstrap, "states": states,
            "cpu_auxiliary": {"not_an_acceptance_gate": True,
                "warning": "Single-call thread CPU readings may be quantized (observed zeros are not zero cost). The continuous blocks and clock overhead are descriptive only.",
                "per_process": cpu_auxiliary},
            "statistical_scope": "aggregate.all is the original four seeds/32 primary states; optional extra_heldout has two separately gated seeds/16 states; all_observed_regular=48 is disclosure only. No production-frequency weighting. State p95 uses linear interpolation; dense p95 omitted. Per-process local threshold flags are descriptive; protocol gates pooled state metrics."}


def _audit_supplement(data, initial, archive, initial_archive):
    """Resolve only the predeclared local question; preserve initial FAIL."""
    name = "seed_79463_grid_128_near"
    fixture = _grid(8, .05, 79463)
    hashes = [_array_digest(*fixture["faces"], *vertices) for vertices in fixture["states"]]
    checks = Checks()
    config = data["config"]
    checks.check(config.get("mode") == "focused_supplement" and config.get("focus_case") == name
                 and config.get("processes") == 3 and config.get("regular_pairs") == 256
                 and config.get("warmups") == 5 and config.get("seeds") == [79463]
                 and not config.get("aa") and not config.get("tiny") and not config.get("extra_heldout"),
                 "schedule", "predeclared single-case supplemental configuration")
    checks.check(initial["config"].get("mode") == "formal" and initial["config"].get("processes") == 3
                 and initial["config"].get("regular_pairs") == 64 and initial["config"].get("warmups") == 5
                 and not initial["config"].get("aa"), "schedule", "initial formal configuration")
    archives = {"initial": _verify_sources(initial, initial_archive, checks),
                "supplement": _verify_sources(data, archive, checks)}
    first_sources, next_sources = initial["source_sha256_before"], data["source_sha256_before"]
    changed_sources = [key for key in set(first_sources) | set(next_sources)
                       if first_sources.get(key, {}).get("sha256") != next_sources.get(key, {}).get("sha256")]
    checks.check(set(changed_sources).issubset({"benchmark", "reopen_protocol"}),
                 "sources", "only predeclared sampling/protocol changed", changed_sources)
    for key in ("implementation", "candidate", "quality_helpers", "fixture_helpers", "fixture_imported_production_kernel"):
        checks.check(first_sources.get(key, {}).get("sha256") == next_sources.get(key, {}).get("sha256"),
                     "sources", f"same algorithm and fixture source/{key}")
    all_pids = [worker.get("pid") for report in (initial, data) for worker in report["workers"]]
    checks.check(len(all_pids) == 6 and all(type(pid) is int for pid in all_pids) and len(set(all_pids)) == 6,
                 "schedule", "six independent initial and supplemental PIDs", all_pids)
    arrays = {"initial": {0: [], 1: []}, "supplement": {0: [], 1: []}}
    counts, quality_count = {}, 0
    maximum_distance_delta, maximum_witness_error = 0., 0.
    for label, report, sample_count in (("initial", initial, 64), ("supplement", data, 256)):
        order_counts = {}
        expected_names = list(_expected_cases("formal", bool(initial["config"].get("tiny")),
            bool(initial["config"].get("extra_heldout", False)))) if label == "initial" else [name]
        case_id = expected_names.index(name)
        for worker_id, worker in enumerate(report["workers"]):
            location = f"{label}/worker {worker_id}/{name}"
            checks.check(worker.get("worker") == worker_id and worker.get("status") == "completed"
                         and worker.get("exit_code") == 0 and worker.get("config") == report["config"],
                         "schedule", location + "/worker binding")
            checks.check(list(worker["cases"]) == expected_names, "schedule", location + "/exact case matrix")
            checks.check(worker.get("thread_env") == dict.fromkeys(THREAD_KEYS, "1"),
                         "schedule", location + "/single-thread BLAS")
            run = worker["cases"][name]
            checks.check(run.get("case_id") == case_id and run.get("group") == "regular"
                         and run.get("seed") == 79463 and run.get("face_counts") == [128, 128],
                         "inputs", location + "/case identity")
            checks.check(run.get("state_sha256") == hashes and run.get("changed_vertex_counts") == [81, 81]
                         and run.get("vertex_counts") == [81, 81], "inputs", location + "/same full-update geometry")
            checks.check(len(run["warmups"]) == 5 and len(run["samples"]) == sample_count,
                         "schedule", location + "/pair counts")
            tagged = [("cold", 0, run["cold"])] + [("warmups", index, sample) for index, sample in enumerate(run["warmups"])]
            tagged += [("samples", index, sample) for index, sample in enumerate(run["samples"])]
            for kind, index, sample in tagged:
                phase = 0 if kind == "cold" else (index + 1) % 2 if kind == "warmups" else index % 2
                item_location = f"{location}/{kind}/{index}"
                checks.check(sample.get("phase") == phase and tuple(sample.get("order", ())) == _order(index, worker_id, case_id),
                             "schedule", item_location + "/phase and order")
                if kind != "cold":
                    checks.check(sample.get("index") == index and sample.get("input_state_sha256") == hashes[phase],
                                 "inputs", item_location + "/input phase binding")
                quality = _sample_check(sample, fixture, phase, hashes, checks, item_location)
                quality_count += 1
                maximum_distance_delta = max(maximum_distance_delta, quality.get("distance_delta_m", 0))
                maximum_witness_error = max(maximum_witness_error, quality.get("max_witness_or_analytic_error_m", 0))
            for block in run.get("cpu_blocks", {}).get("blocks", ()):
                quality = _sample_check(block, fixture, 1, hashes, checks,
                    f"{location}/auxiliary CPU block/{block['block']}", quality_key="last_result_quality")
                quality_count += 1
                maximum_distance_delta = max(maximum_distance_delta, quality.get("distance_delta_m", 0))
                maximum_witness_error = max(maximum_witness_error, quality.get("max_witness_or_analytic_error_m", 0))
            for phase in (0, 1):
                samples = [sample for sample in run["samples"] if sample["phase"] == phase]
                orders = dict(Counter("/".join(sample["order"]) for sample in samples))
                checks.check(len(samples) == sample_count // 2 and len(orders) == 2
                             and set(orders.values()) == {sample_count // 4},
                             "schedule", f"{location}/phase {phase}/balanced state samples")
                order_counts[f"worker_{worker_id}/phase_{phase}"] = orders
                arrays[label][phase].append(np.array([[sample["methods"][method]["wall_ns"] for method in METHODS]
                                                     for sample in samples], dtype=np.float64))
        counts[label] = order_counts

    result_states = {}
    for label in ("initial", "supplement", "combined"):
        result_states[label] = {}
        for phase in (0, 1):
            groups = (arrays["initial"][phase] + arrays["supplement"][phase]) if label == "combined" else arrays[label][phase]
            pooled = _metrics(np.concatenate(groups))
            result_states[label][str(phase)] = {
                "sample_count": sum(len(group) for group in groups), "pooled": pooled,
                "per_process": [_metrics(group) for group in groups],
                "local_gates": _local_gates(pooled, "regular")}
            expected_count = 480 if label == "combined" else 96 if label == "initial" else 384
            checks.check(result_states[label][str(phase)]["sample_count"] == expected_count,
                         "schedule", f"{label}/phase {phase}/pooled count")
            if label != "combined":
                source = initial if label == "initial" else data
                declared = source["cases"][name]["states"][str(phase)]["wall_ns"]
                checks.check(all(math.isclose(pooled[key], declared[key], rel_tol=1e-12, abs_tol=1e-12)
                                 for key in ("median_ratio_R_over_A", "p95_ratio_R_over_A")),
                             "summary", f"{label}/phase {phase}/reported summary")

    # Recompute the original 32-state point statistic using initial samples
    # only. Supplemental observations never replace a state in that metric.
    primary_states = []
    for case_name, run in initial["workers"][0]["cases"].items():
        if run.get("group") != "regular" or run.get("seed") not in OLD_SEEDS + NEW_SEEDS:
            continue
        for phase in (0, 1):
            values = np.array([[sample["methods"][method]["wall_ns"] for method in METHODS]
                for worker in initial["workers"] for sample in worker["cases"][case_name]["samples"] if sample["phase"] == phase],
                dtype=np.float64)
            primary_states.append({"pooled": _metrics(values)})
    primary = _aggregate(primary_states)
    declared_primary = initial["regular_equal_state_statistics"]["wall_ns"]["pooled"]["sum_state_medians_ratio_R_over_A"]
    checks.check(primary["state_count"] == 32 and math.isclose(primary["sum_state_medians_ratio_R_over_A"], declared_primary, rel_tol=1e-12),
                 "summary", "original 32-state primary aggregate preserved")
    gates = {
        "source_input_output_schedule_integrity": {"passed": checks.passed("sources", "schedule", "inputs", "outputs", "samples")},
        "independent_witness_quality": {"passed": checks.passed("quality", "reported_quality")},
        "independent_summary_agrees": {"passed": checks.passed("summary")},
        "supplement_both_states_original_local_limits": {
            "passed": all(state["local_gates"]["passed"] for state in result_states["supplement"].values())},
        "initial_plus_supplement_both_states_original_local_limits": {
            "passed": all(state["local_gates"]["passed"] for state in result_states["combined"].values())},
    }
    return {"mode": "focused_supplement_audit", "case": name, "gates": gates,
            "supplement_gates_passed": all(gate["passed"] for gate in gates.values()),
            "initial_formal_decision": "Original formal FAIL is retained; this report does not modify its audit or samples",
            "initial_local_failures": [phase for phase, state in result_states["initial"].items() if not state["local_gates"]["passed"]],
            "final_acceptance": "NOT_DECIDED; supplemental local evidence only, pending all original comparison/external requirements and primary review",
            "states": result_states, "state_order_counts": counts,
            "preserved_primary_32": {"recomputed_from_initial_only": primary,
                                      "supplementary_samples_included": False, "initial_reported_ratio": declared_primary},
            "source_archive_verification": archives, "changed_source_labels_between_runs": changed_sources,
            "checks": {"counts": dict(checks.counts), "failures": checks.failures,
                       "independent_quality_pairs": quality_count, "max_distance_delta_m": maximum_distance_delta,
                       "max_witness_or_analytic_error_m": maximum_witness_error},
            "cpu_is_not_an_acceptance_gate": True, "bootstrap_performed": False,
            "statistical_scope": "Original local median ratio <=1.10 OR delta <=0.25ms, AND pooled state p95 ratio <=1.25. Both supplement alone (384/state) and initial+supplement (480/state) must pass; all initial samples retained. Six independent processes in combined distribution."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Completed comparison JSON")
    parser.add_argument("--output", type=Path, required=True, help="Fresh audit JSON; existing files are never overwritten")
    parser.add_argument("--sources", type=Path, help="Explicit source archive location if original paths moved")
    parser.add_argument("--supplement", type=Path, help="Initial completed formal report; input is the predeclared focused supplemental run")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Audit output exists; choose a fresh path")
    raw = args.input.read_bytes()
    data = json.loads(raw)
    if "source_sha256_after" not in data or "regular_equal_state_statistics" not in data:
        parser.error("Input has no completed final reduction; do not audit an in-progress run")
    if len(data.get("workers", [])) != data["config"]["processes"] or any(worker.get("status") != "completed" for worker in data["workers"]):
        parser.error("Input workers are incomplete or failed; retain raw failures and complete evidence before this acceptance audit")
    archive = args.sources or Path(data["source_archive"])
    initial_raw = None
    if args.supplement is not None:
        initial_raw = args.supplement.read_bytes()
        initial = json.loads(initial_raw)
        if "source_sha256_after" not in initial or "regular_equal_state_statistics" not in initial:
            parser.error("Initial report is incomplete")
        output = _audit_supplement(data, initial, archive, Path(initial["source_archive"]))
        if _sha(args.supplement.read_bytes()) != _sha(initial_raw):
            raise RuntimeError("Initial report changed during supplemental audit")
        output["initial_input"] = {"path": str(args.supplement.resolve()), "sha256": _sha(initial_raw)}
    else:
        output = _audit(data, archive)
    if _sha(args.input.read_bytes()) != _sha(raw):
        raise RuntimeError("Input changed during audit; result cannot be bound to a stable report")
    output["input"] = {"path": str(args.input.resolve()), "sha256": _sha(raw)}
    output["audit_source"] = {"path": str(Path(__file__).resolve()), "sha256": _sha(Path(__file__).read_bytes())}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(output, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"output": str(args.output.resolve()),
                      "comparison_gates_passed": output.get("comparison_gates_passed"),
                      "supplement_gates_passed": output.get("supplement_gates_passed"),
                      "gates": output["gates"], "aggregate": output.get("aggregate"),
                      "supplement_states": output.get("states") if args.supplement else None,
                      "independent_quality_pairs": output["checks"]["independent_quality_pairs"],
                      "audit_failure_count": len(output["checks"]["failures"]),
                      "final_acceptance": output["final_acceptance"]}, indent=2, allow_nan=False))
    return 0 if output.get("comparison_gates_passed", output.get("supplement_gates_passed", False)) else 2


if __name__ == "__main__":
    raise SystemExit(main())
