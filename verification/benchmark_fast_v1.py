"""Reproducible local comparisons for the trusted-input fast experiment.

Run from a source checkout with ``python -B verification/benchmark_fast_v1.py``.
No Blender, model, asset, source verification or physical acquisition is timed.
The old fact function produces richer, conservatively guarded results. Its
speed ratio therefore combines algorithm changes AND a different contract.
The independent batched QR/SVD baseline separates some of that effect.
"""
from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from human_eye_plugin import deformation_region, surface_deformation
from human_eye_fast.kernels import (
    deformation_metrics, prepare_reference, triangle_box_mask,
)
from human_eye_fast.engine import FastSession


def fixture(face_count, seed=29017):
    """Disconnected, well-conditioned triangles with varied orientation.

    This is a deterministic synthetic throughput fixture, not an author asset
    or a representative production mesh. Each face has its own three vertices.
    """
    rng = np.random.default_rng(seed)
    centers = rng.uniform(-2.0, 2.0, (face_count, 3))
    first = rng.normal(size=(face_count, 3))
    first /= np.linalg.norm(first, axis=1)[:, None]
    second = rng.normal(size=(face_count, 3))
    second -= np.sum(first * second, axis=1)[:, None] * first
    second /= np.linalg.norm(second, axis=1)[:, None]
    first *= rng.uniform(0.25, 0.6, (face_count, 1))
    second *= rng.uniform(0.25, 0.6, (face_count, 1))
    vertices = np.stack((centers, centers + first, centers + second), axis=1).reshape(-1, 3)
    triangles = np.arange(face_count * 3, dtype=np.int64).reshape(-1, 3)
    transform_a = np.array([[1.25, 0.17, 0.04], [0.02, 0.78, 0.05], [0.0, 0.0, 1.04]])
    transform_b = np.array([[0.83, -0.12, 0.08], [0.05, 1.32, 0.01], [0.0, 0.03, 0.94]])
    current = vertices @ transform_a.T
    alternate = vertices @ transform_b.T
    return vertices, triangles, current, alternate


def qr_svd_reference(original_points):
    before = np.swapaxes(original_points[:, 1:] - original_points[:, :1], 1, 2)
    _, upper = np.linalg.qr(before, mode="reduced")
    area = np.linalg.norm(np.cross(before[:, :, 0], before[:, :, 1]), axis=1)
    return upper, area


def qr_svd_metrics(original_points, current_points, reference=None):
    """Independent batched thin QR / solve / SVD, with no guarded old code."""
    after = np.swapaxes(current_points[:, 1:] - current_points[:, :1], 1, 2)
    upper, original_area = qr_svd_reference(original_points) if reference is None else reference
    gradient = np.swapaxes(np.linalg.solve(np.swapaxes(upper, 1, 2), np.swapaxes(after, 1, 2)), 1, 2)
    stretches = np.linalg.svd(gradient, compute_uv=False)
    area = np.linalg.norm(np.cross(after[:, :, 0], after[:, :, 1]), axis=1) / original_area
    return {"stretches": stretches, "area_ratio": area}


def legacy_metrics(original_lists, current_lists):
    deadline = time.perf_counter_ns() + 600_000_000_000
    rational_cache = {}
    return [surface_deformation.triangle_facts(before, after,
            deadline_ns=deadline, _rational_cache=rational_cache)
            for before, after in zip(original_lists, current_lists)]


def rational_points(points):
    return [[tuple(Fraction(float(value)) for value in vertex) for vertex in face]
            for face in points]


def legacy_membership(prepared, low, high):
    deadline = time.perf_counter_ns() + 600_000_000_000
    return np.asarray([deformation_region.clipped(face, low, high, deadline_ns=deadline)
                       for face in prepared], dtype=bool)


def _errors(actual, expected):
    actual = np.asarray(actual, dtype=float)
    expected = np.asarray(expected, dtype=float)
    if not actual.size:
        return {"max_absolute_error": None, "max_relative_error": None}
    difference = np.abs(actual - expected)
    return {"max_absolute_error": float(difference.max()),
            "max_relative_error": float((difference / np.maximum(np.abs(expected), np.finfo(float).tiny)).max())}


def check_metrics(fast, independent, legacy, *, rtol=2e-10, atol=2e-11):
    """Do not silently promote legacy unknown rows into equivalent results."""
    np.testing.assert_allclose(fast["stretches"], independent["stretches"], rtol=rtol, atol=atol)
    np.testing.assert_allclose(fast["area_ratio"], independent["area_ratio"], rtol=rtol, atol=atol)
    states = Counter(row["state"] for row in legacy)
    measured = np.asarray([i for i, row in enumerate(legacy) if row["state"] == "measured"], dtype=np.int64)
    collapsed = np.asarray([i for i, row in enumerate(legacy) if row["state"] == "collapsed"], dtype=np.int64)
    old_stretches = np.asarray([legacy[i]["principal_stretches"] for i in measured], dtype=float).reshape(-1, 2)
    old_area = np.asarray([legacy[i]["area_ratio"] for i in measured], dtype=float)
    np.testing.assert_allclose(fast["stretches"][measured], old_stretches, rtol=rtol, atol=atol)
    np.testing.assert_allclose(fast["area_ratio"][measured], old_area, rtol=rtol, atol=atol)
    if len(collapsed):
        np.testing.assert_allclose(fast["stretches"][collapsed],
                                   [legacy[i]["principal_stretches"] for i in collapsed], rtol=rtol, atol=atol)
        np.testing.assert_allclose(fast["area_ratio"][collapsed], 0, rtol=rtol, atol=atol)
    return {
        "input_faces": len(legacy), "legacy_states": dict(states),
        "legacy_measured_rows_compared": len(measured),
        "legacy_collapsed_rows_compared_separately": len(collapsed),
        "legacy_unknown_rows_not_claimed_equivalent": states.get("unknown", 0),
        "independent_numeric_rows_compared": len(independent["area_ratio"]),
        "rtol": rtol, "atol": atol,
        "vs_legacy_measured_stretches": _errors(fast["stretches"][measured], old_stretches),
        "vs_legacy_measured_area": _errors(fast["area_ratio"][measured], old_area),
        "vs_independent_stretches": _errors(fast["stretches"], independent["stretches"]),
        "vs_independent_area": _errors(fast["area_ratio"], independent["area_ratio"]),
    }


def measure_group(functions, repeats, warmup, *, seed=17):
    """Interleave methods in recorded deterministic randomized order.

    Samples measure one call each. Cold methods rebuild their reference on each
    call; Python/module startup is never part of these microbenchmarks.
    """
    names = list(functions)
    for _ in range(warmup):
        for name in names:
            functions[name]()
    samples = {name: [] for name in names}
    rng = np.random.default_rng(seed)
    orders = []
    for _ in range(repeats):
        order = [str(value) for value in rng.permutation(names)]
        orders.append(order)
        for name in order:
            started = time.perf_counter_ns()
            functions[name]()
            samples[name].append((time.perf_counter_ns() - started) / 1_000_000)
    return {"sample_order": orders, "methods": {
        name: {"samples_ms": values, "median_ms": float(np.median(values)),
               "p95_ms": float(np.percentile(values, 95)), "min_ms": min(values)}
        for name, values in samples.items()}}


def ratios(timings, denominator, numerators):
    methods = timings["methods"]
    return {name + "_over_" + denominator:
            methods[name]["median_ms"] / methods[denominator]["median_ms"]
            for name in numerators}


def compare_case(face_count, *, seed, repeats, warmup, region_faces):
    original, triangles, current, alternate = fixture(face_count, seed)
    before_points, after_points = original[triangles], current[triangles]
    before_lists, after_lists = before_points.tolist(), after_points.tolist()
    reference = prepare_reference(original, triangles)
    independent_reference = qr_svd_reference(before_points)
    independent = qr_svd_metrics(before_points, after_points)
    old = legacy_metrics(before_lists, after_lists)
    fast = deformation_metrics(reference, current)
    quality = check_metrics(fast, independent, old)
    numeric = measure_group({
        "legacy_full_fact_loop": lambda: legacy_metrics(before_lists, after_lists),
        "independent_batched_qr_svd": lambda: qr_svd_metrics(before_points, after_points),
        "independent_cached_reference_svd": lambda: qr_svd_metrics(before_points, after_points, independent_reference),
        "fast_reference_prepare_only": lambda: prepare_reference(original, triangles),
        "fast_cold_prepare_and_evaluate": lambda: deformation_metrics(prepare_reference(original, triangles), current),
        "fast_warm_evaluate": lambda: deformation_metrics(reference, current),
    }, repeats, warmup, seed=seed)
    numeric["median_ratios"] = ratios(numeric, "fast_warm_evaluate",
        ("legacy_full_fact_loop", "independent_batched_qr_svd", "independent_cached_reference_svd", "fast_cold_prepare_and_evaluate"))

    region_count = face_count if region_faces == 0 else min(region_faces, face_count)
    region_points = after_points[:region_count]
    low, high = np.full(3, -0.6), np.full(3, 0.6)
    rational_low = tuple(Fraction(float(x)) for x in low)
    rational_high = tuple(Fraction(float(x)) for x in high)
    prepared = rational_points(region_points)
    expected = legacy_membership(prepared, rational_low, rational_high)
    actual = triangle_box_mask(region_points, low, high)
    np.testing.assert_array_equal(actual, expected)
    region = measure_group({
        "legacy_cold_rational_prepare_and_clip": lambda: legacy_membership(rational_points(region_points), rational_low, rational_high),
        "legacy_warm_rational_clip": lambda: legacy_membership(prepared, rational_low, rational_high),
        "fast_float64_sat": lambda: triangle_box_mask(region_points, low, high),
    }, repeats, warmup, seed=seed + 1)
    region.update(input_faces=region_count, full_fixture_faces=face_count,
                  matched_faces=int(expected.sum()), membership_mismatches=0,
                  bounds=[low.tolist(), high.tolist()],
                  numeric_contract="float64 SAT compared with exact rational clipping on these supplied binary coordinates")
    region["median_ratios"] = ratios(region, "fast_float64_sat",
        ("legacy_warm_rational_clip", "legacy_cold_rational_prepare_and_clip"))

    dirty = np.arange(max(1, len(original) // 100), dtype=np.int64)
    modified = current.copy()
    modified[dirty] += np.array([0.017, -0.011, 0.009])
    full_session, sparse_session = FastSession(original, triangles), FastSession(original, triangles)
    full_session.set_frame("frame", current)
    sparse_session.set_frame("frame", current)
    variants = [modified, current]
    counters = [0, 0]

    def update(which):
        index = counters[which]
        counters[which] += 1
        session = (full_session, sparse_session)[which]
        return session.set_frame("frame", variants[index % 2],
                                 changed_vertices=None if which == 0 else dirty)

    updates = measure_group({"full_update": lambda: update(0), "sparse_update": lambda: update(1)},
                            repeats, warmup, seed=seed + 2)
    full_stats = full_session.set_frame("frame", modified)
    sparse_stats = sparse_session.set_frame("frame", modified, changed_vertices=dirty)
    full_rows = full_session.rows("frame", np.arange(face_count))
    sparse_rows = sparse_session.rows("frame", np.arange(face_count))
    if full_rows != sparse_rows:
        raise AssertionError("Sparse update output differs from a full update on identical final coordinates")
    updates.update(changed_vertices=len(dirty), total_vertices=len(original),
                   full_stats=full_stats, sparse_stats=sparse_stats, all_face_rows_equal=True)
    updates["median_ratios"] = ratios(updates, "sparse_update", ("full_update",))

    session = FastSession(original, triangles)
    session.set_frame("a", current)
    session.set_frame("b", alternate)
    bounds = [low.tolist(), high.tolist()]

    def cold_workflow():
        candidate = FastSession(original, triangles)
        candidate.set_frame("a", current)
        candidate.set_frame("b", alternate)
        return json.dumps(candidate.query(["a", "b"], bounds=bounds), separators=(",", ":"), allow_nan=False)

    def warm_workflow():
        return json.dumps(session.query(["a", "b"], bounds=bounds), separators=(",", ":"), allow_nan=False)

    workflow = measure_group({"cold_two_frame_query_json": cold_workflow,
                              "warm_two_frame_query_json": warm_workflow}, repeats, warmup, seed=seed + 3)
    workflow.update(report_json_bytes=len(warm_workflow().encode("utf-8")),
                    scope="supplied arrays to two-frame region query and JSON; no host, physical acquisition, model or disk")
    return {"faces": face_count, "vertices": len(original), "quality": quality,
            "deformation": numeric, "region": region, "incremental_update": updates, "in_memory_workflow": workflow}


def source_metadata():
    paths = ["verification/benchmark_fast_v1.py", "human_eye_fast/kernels.py", "human_eye_fast/engine.py",
             "human_eye_plugin/surface_deformation.py", "human_eye_plugin/deformation_region.py"]
    hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in paths}
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        status = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).splitlines()
    except (OSError, subprocess.CalledProcessError):
        commit, status = None, None
    return {"git_head": commit, "git_status_at_run": status, "sha256": hashes}


def run(*, sizes=(128, 2048), seed=29017, repeats=5, warmup=1, region_faces=2048):
    cases = []
    for size in sizes:
        print(f"Benchmarking {size} faces...", file=sys.stderr, flush=True)
        cases.append(compare_case(size, seed=seed, repeats=repeats, warmup=warmup, region_faces=region_faces))
    return {
        "schema": "human-eye-fast-v1-local-comparison-1",
        "configuration": {"sizes": list(sizes), "seed": seed, "repeats": repeats, "warmup": warmup,
                          "region_face_limit": region_faces, "region_limit_zero_means_all": True},
        "environment": {"python": sys.version, "numpy": np.__version__, "platform": platform.platform(),
                        "processor": platform.processor(), "clock": "perf_counter_ns"},
        "sources": source_metadata(), "cases": cases,
        "interpretation": {
            "fixture": "deterministic synthetic disconnected well-conditioned triangles; 1% contiguous dirty vertices",
            "timing": "single-call samples after warmup, deterministic shuffled order; p95 descriptive for small repeat counts",
            "legacy_fact_contract": "richer fields, source-coordinate error guards, rational zero tests and deadline checks; not output-contract equivalent",
            "fast_contract": "trusted supplied arrays, float64 metrics and SAT, no conservative input-precision rejection",
            "independent_baseline": "batched QR/solve/SVD on identical pre-gathered triangle arrays; uncached and cached-reference variants both measured; excludes host work",
            "region_preparation": "cold rational path includes Fraction conversion; warm path excludes it; SAT includes array arithmetic and AABB pruning",
            "not_measured": ["Blender capture", "MCP/Hook", "source authentication", "model consumption",
                             "model quality", "token usage", "USD", "whole product latency", "process peak RSS"],
            "ratios": "numerator median divided by denominator median; values below one are slower for the proposed denominator",
            "legacy_unknowns": "reported and excluded from legacy equivalence counts; never relabeled as agreement",
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", default="128,2048", help="Comma-separated triangle counts; e.g. 128,2048,20000")
    parser.add_argument("--seed", type=int, default=29017)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--region-faces", type=int, default=2048, help="Exact rational region benchmark prefix size; 0 runs all faces")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    sizes = tuple(int(value) for value in args.sizes.split(","))
    if not sizes or min(sizes) <= 0 or args.repeats < 1 or args.warmup < 0 or args.region_faces < 0:
        parser.error("positive sizes/repeats and nonnegative warmup/region-faces required")
    result = run(sizes=sizes, seed=args.seed, repeats=args.repeats, warmup=args.warmup, region_faces=args.region_faces)
    blob = json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(blob, encoding="utf-8")
        print(str(args.output), flush=True)
    else:
        print(blob, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
