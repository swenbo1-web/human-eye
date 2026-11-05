"""Compare the streaming TD summary with a full-tensor NumPy baseline.

Run with python -B verification/benchmark_tensor_deform.py --seed 29017
--output artifacts/td/author.json from a checkout.
"""

import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from time import perf_counter_ns
import tracemalloc

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from human_eye_fast.kernels import deformation_metrics, prepare_reference
from human_eye_fast.tensor_deform import _top_faces, compute_cross_frame_deformation_tensor


FRAME_COUNT = 16
GRID_CELLS = ((100, 100), (200, 250))
TOP_K = 12
PROCESSES = 3
WARMUPS = 5
SAMPLES = 31
PEAK_LIMIT = 0.50
TIME_LIMIT = 1.25
METHODS = ("streaming", "full_tensor")
SUMMARY_FIELDS = (
    "max_principal_stretch", "min_principal_stretch", "max_area_strain",
    "max_normal_angle_deg", "max_centroid_displacement", "score",
)
THREAD_ENV = {
    name: "1"
    for name in (
        "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS",
        "BLIS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS",
    )
}


def fixture(nx, ny, seed):
    """One edge-connected surface with a curved reference and moving vertices."""
    rng = np.random.default_rng(seed)
    x, y = np.meshgrid(np.linspace(-1.0, 1.0, nx + 1), np.linspace(-1.0, 1.0, ny + 1))
    x, y = x.ravel(), y.ravel()
    z = 0.15 * np.sin(2.5 * x + 0.3) * np.cos(2.0 * y)
    z += 0.0002 * rng.standard_normal(z.shape)
    reference_vertices = np.column_stack((x, y, z))
    lower = np.arange((nx + 1) * (ny + 1), dtype=np.intp).reshape(ny + 1, nx + 1)
    lower_left = lower[:-1, :-1].ravel()
    lower_right = lower[:-1, 1:].ravel()
    upper_left = lower[1:, :-1].ravel()
    upper_right = lower[1:, 1:].ravel()
    triangles = np.empty((2 * nx * ny, 3), dtype=np.intp)
    triangles[0::2] = np.column_stack((lower_left, lower_right, upper_right))
    triangles[1::2] = np.column_stack((lower_left, upper_right, upper_left))

    phase = np.linspace(0.25, 2.0 * np.pi + 0.25, FRAME_COUNT, endpoint=False)[:, None]
    frames = np.empty((FRAME_COUNT, x.size, 3), dtype=np.float64)
    frames[..., 0] = (1.0 + 0.12 * np.sin(phase)) * x + 0.06 * np.cos(phase) * y
    frames[..., 1] = (1.0 - 0.09 * np.sin(phase)) * y + 0.05 * np.sin(phase + x)
    frames[..., 2] = z + 0.075 * np.sin(3.0 * x + 1.6 * y + phase) + 0.02 * np.cos(phase)
    return frames, triangles, reference_vertices


def _norm(vectors):
    return np.hypot(np.hypot(vectors[..., 0], vectors[..., 1]), vectors[..., 2])


def full_tensor_summary(frames, triangles, reference_vertices, top_k):
    """Batch facts over the fixture's moderate-range geometry in all T × F."""
    if not len(frames) or not len(triangles):
        return {
            **{field: np.full(len(triangles), np.nan) for field in SUMMARY_FIELDS},
            "witness_triangle_ids": np.empty(0, dtype=np.intp),
        }
    reference = prepare_reference(reference_vertices, triangles)
    stretches = np.empty((len(frames), len(triangles), 2))
    for i, frame in enumerate(frames):
        stretches[i] = deformation_metrics(reference, frame)["stretches"]
    max_stretch = np.fmax.reduce(stretches[..., 0], axis=0)
    min_stretch = np.fmin.reduce(stretches[..., 1], axis=0)
    del stretches

    before = reference_vertices[triangles]
    before_normal = np.cross(before[:, 1] - before[:, 0], before[:, 2] - before[:, 0])
    before_area = _norm(before_normal)
    before_centroid = (before[:, 0] + before[:, 1] + before[:, 2]) / 3.0
    points = frames[:, triangles]
    p0, p1, p2 = points[:, :, 0], points[:, :, 1], points[:, :, 2]
    centroid_delta = (p0 + p1 + p2) / 3.0 - before_centroid
    max_displacement = np.fmax.reduce(_norm(centroid_delta), axis=0)
    del centroid_delta
    normals = np.cross(p1 - p0, p2 - p0)
    del p0, p1, p2, points
    areas = _norm(normals)
    valid_reference = ~np.isnan(reference.inv_length) & (before_area > 0.0)
    max_stretch[~valid_reference] = np.nan
    min_stretch[~valid_reference] = np.nan
    min_stretch[np.any(areas == 0.0, axis=0) & valid_reference] = 0.0
    with np.errstate(divide="ignore", invalid="ignore"):
        area_strain = np.abs(areas / before_area - 1.0)
        area_strain[:, ~valid_reference] = np.nan
        normals /= areas[..., None]
        before_normal /= before_area[:, None]
    max_area_strain = np.fmax.reduce(area_strain, axis=0)
    del area_strain, areas
    dot = np.einsum("tfi,fi->tf", normals, before_normal)
    cross_length = _norm(np.cross(normals, before_normal))
    angles = np.degrees(np.arctan2(cross_length, dot))
    angles[:, ~valid_reference] = np.nan
    max_angle = np.fmax.reduce(angles, axis=0)

    scale = _norm(np.ptp(reference_vertices, axis=0))
    with np.errstate(divide="ignore", invalid="ignore"):
        score = (
            np.maximum(np.abs(max_stretch - 1.0), np.abs(min_stretch - 1.0))
            + 2.0 * max_area_strain
            + 3.0 * (np.where(np.isnan(max_angle), 0.0, max_angle) / 180.0)
            + max_displacement / scale
        )
    return {
        "max_principal_stretch": max_stretch,
        "min_principal_stretch": min_stretch,
        "max_area_strain": max_area_strain,
        "max_normal_angle_deg": max_angle,
        "max_centroid_displacement": max_displacement,
        "score": score,
        "witness_triangle_ids": _top_faces(score, top_k),
    }


def _orders(count, rng):
    """Balance which method runs first, then shuffle the paired order."""
    start = int(rng.integers(2))
    flips = (np.arange(count) + start) % 2
    rng.shuffle(flips)
    return [list(METHODS[::-1] if flip else METHODS) for flip in flips]


def _time_calls(functions, orders):
    samples = {name: [] for name in METHODS}
    if tracemalloc.is_tracing():
        raise RuntimeError("benchmark timings require tracemalloc to be off")
    for order in orders:
        for name in order:
            started = perf_counter_ns()
            result = functions[name]()
            elapsed = perf_counter_ns() - started
            samples[name].append(elapsed)
            del result
    return samples


def _extra_peak(call):
    gc.collect()
    tracemalloc.start()
    try:
        result = call()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return peak


def _compare_summaries(streaming, full_tensor):
    if streaming.keys() != full_tensor.keys():
        raise AssertionError(f"summary fields differ: {streaming.keys()} vs {full_tensor.keys()}")
    errors = {}
    for key, expected in full_tensor.items():
        actual = streaming[key]
        if key == "witness_triangle_ids":
            # Check the shared timed selector independently by sorting all faces.
            scores = full_tensor["score"]
            face_ids = np.flatnonzero(~np.isnan(scores))
            order = np.lexsort((face_ids, -scores[face_ids]))
            independent = face_ids[order[:TOP_K]]
            np.testing.assert_array_equal(expected, independent, err_msg=key)
            np.testing.assert_array_equal(actual, independent, err_msg=key)
            continue
        np.testing.assert_allclose(actual, expected, rtol=1e-11, atol=1e-11, err_msg=key)
        finite = np.isfinite(expected)
        errors[key] = float(np.max(np.abs(actual[finite] - expected[finite]), initial=0.0))
    return {
        "all_fields_match": True,
        "rtol": 1e-11,
        "atol": 1e-11,
        "max_absolute_errors": errors,
        "witness_triangle_ids": streaming["witness_triangle_ids"].tolist(),
    }


def measure_case(nx, ny, seed, worker, *, warmups=WARMUPS, samples=SAMPLES):
    frames, triangles, reference = fixture(nx, ny, seed)
    functions = {
        "streaming": lambda: compute_cross_frame_deformation_tensor(
            frames, triangles, reference_vertices=reference, top_k=TOP_K
        ),
        "full_tensor": lambda: full_tensor_summary(frames, triangles, reference, TOP_K),
    }
    rng = np.random.default_rng([seed, nx, ny, worker])
    warmup_orders = _orders(warmups, rng)
    sample_orders = _orders(samples, rng)
    for order in warmup_orders:
        for name in order:
            functions[name]()
    timings = _time_calls(functions, sample_orders)
    memory_order = _orders(1, rng)[0]
    peaks = {name: _extra_peak(functions[name]) for name in memory_order}
    try:
        quality = _compare_summaries(functions["streaming"](), functions["full_tensor"]())
    except AssertionError as error:
        quality = {"all_fields_match": False, "error": str(error)}
    return {
        "grid_cells": [nx, ny],
        "vertex_count": frames.shape[1],
        "face_count": len(triangles),
        "frame_count": len(frames),
        "input_bytes": frames.nbytes + triangles.nbytes + reference.nbytes,
        "warmup_orders": warmup_orders,
        "sample_orders": sample_orders,
        "time_samples_ns": timings,
        "memory_order": memory_order,
        "extra_peak_bytes": peaks,
        "quality": quality,
    }


def _worker_result(seed, worker):
    return {
        "pid": os.getpid(),
        "worker": worker,
        "cases": [measure_case(nx, ny, seed, worker) for nx, ny in GRID_CELLS],
    }


def _ratio(metrics):
    return metrics["streaming"] / metrics["full_tensor"]


def _summarize(case_runs):
    medians = [
        {name: float(np.median(run["time_samples_ns"][name])) for name in METHODS}
        for run in case_runs
    ]
    pooled_p95 = {
        name: float(np.percentile([ns for run in case_runs for ns in run["time_samples_ns"][name]], 95))
        for name in METHODS
    }
    median_ratios = [_ratio(median) for median in medians]
    memory_ratios = [_ratio(run["extra_peak_bytes"]) for run in case_runs]
    p95_ratio = _ratio(pooled_p95)
    gates = {
        "full_summary_equivalent": all(run["quality"]["all_fields_match"] for run in case_runs),
        "each_process_median": all(ratio <= TIME_LIMIT for ratio in median_ratios),
        "pooled_p95": p95_ratio <= TIME_LIMIT,
        "each_process_extra_peak": all(ratio <= PEAK_LIMIT for ratio in memory_ratios),
    }
    return {
        "face_count": case_runs[0]["face_count"],
        "process_medians_ns": medians,
        "pooled_p95_ns": pooled_p95,
        "process_median_ratios": median_ratios,
        "pooled_p95_ratio": p95_ratio,
        "process_extra_peak_ratios": memory_ratios,
        "gates": gates,
        "all_gates_met": all(gates.values()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=29017)
    parser.add_argument("--output", type=Path, default=Path("artifacts/td/author.json"))
    parser.add_argument("--worker", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.seed < 0:
        parser.error("--seed must be nonnegative")
    if args.worker is not None:
        print(json.dumps(_worker_result(args.seed, args.worker), allow_nan=False))
        return 0

    workers = []
    for i in range(PROCESSES):
        output = subprocess.check_output(
            [sys.executable, "-B", str(Path(__file__).resolve()), "--seed", str(args.seed), "--worker", str(i)],
            env={**os.environ, **THREAD_ENV},
            text=True,
        )
        workers.append(json.loads(output))
    cases = [_summarize(runs) for runs in zip(*(worker["cases"] for worker in workers))]
    source_files = (
        ROOT / "human_eye_fast" / "kernels.py",
        ROOT / "human_eye_fast" / "tensor_deform.py",
        Path(__file__).resolve(),
    )
    report = {
        "seed": args.seed,
        "fixture": "edge-connected rectangular grid, explicit curved reference",
        "python": sys.version,
        "numpy": np.__version__,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "logical_cpu_count": os.cpu_count(),
        "worker_thread_env": THREAD_ENV,
        "source_sha256": {
            path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in source_files
        },
        "protocol": {
            "processes": PROCESSES,
            "warmups_per_method_per_process": WARMUPS,
            "samples_per_method_per_process": SAMPLES,
            "top_k": TOP_K,
            "latency_ratio_limit": TIME_LIMIT,
            "extra_peak_ratio_limit": PEAK_LIMIT,
            "memory_metric": "tracemalloc peak of a single summary call after gc.collect; excludes pre-existing inputs, not RSS",
            "time_metric": "perf_counter_ns, paired and interleaved, excludes memory tracing and checks",
            "baseline": "existing stretch kernel per frame, batched area/normal/centroid over frames and faces",
        },
        "workers": workers,
        "cases": cases,
        "all_gates_met": all(case["all_gates_met"] for case in cases),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output.resolve()), "cases": cases}, indent=2, allow_nan=False))
    return 0 if report["all_gates_met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
