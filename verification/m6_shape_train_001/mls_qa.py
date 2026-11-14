"""Finite synthetic implementation checks for the single TRAIN-001 MLS.

Run with the existing isolated Python and -I -B -X utf8. Inputs are finite
synthetic graphs and prescribed implementation-test thresholds.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import sys
import time

import numpy as np


HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE / "mls.py"
MODULE_SPEC = importlib.util.spec_from_file_location("train_001_mls", MODULE_PATH)
mls = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(mls)


def _grid(size=9, spacing=0.75):
    coordinate = (np.arange(size) - size // 2) * spacing
    x, y = np.meshgrid(coordinate, coordinate, indexing="ij")
    positions = np.column_stack((x.ravel(), y.ravel(), np.zeros(size * size)))
    undirected = []
    for row in range(size):
        for column in range(size):
            point = row * size + column
            if row + 1 < size:
                undirected.append((point, point + size))
            if column + 1 < size:
                undirected.append((point, point + 1))
            if row + 1 < size and column + 1 < size:
                undirected.append((point, point + size + 1))
    forward = np.asarray(undirected, dtype=np.int64).T
    edges = np.concatenate((forward, forward[::-1]), axis=1)
    normals = np.tile([0.0, 0.0, 1.0], (len(positions), 1))
    return positions, normals, edges, size * size // 2


def _star_edges(count, center, excluded=()):
    pairs = [
        (center, point)
        for point in range(count)
        if point != center and point not in excluded
    ]
    forward = np.asarray(pairs, dtype=np.int64).T
    return np.concatenate((forward, forward[::-1]), axis=1)


def _center_mask(count, center):
    free = np.zeros(count, dtype=bool)
    free[center] = True
    return free


def _check_diagnostics(raw, applicable, diagnostics, free):
    counts = diagnostics["counts"]
    reasons = diagnostics["per_point_reason"]
    assert counts["total"] == len(raw)
    assert counts["free"] == int(np.count_nonzero(free))
    assert counts["fixed"] == int(np.count_nonzero(~free))
    assert sum(counts[reason] for reason in ("applicable", *mls.FAILURE_REASONS)) == counts["free"]
    assert counts["applicable"] == int(np.count_nonzero(applicable))
    assert len(reasons) == len(raw)
    assert all(reasons[point] == "fixed" for point in np.flatnonzero(~free))
    assert np.array_equal(applicable, np.asarray(reasons) == "applicable")
    assert np.all(raw[~applicable] == 0.0)
    assert np.isfinite(raw).all()
    assert all(
        diagnostics["irls_passes_completed"][point] == 3
        for point in np.flatnonzero(applicable)
    )
    json.dumps(diagnostics, allow_nan=False)


def _run_fit(positions, normals, edges, free):
    raw, applicable, diagnostics = mls.fit_residuals(positions, normals, edges, free)
    _check_diagnostics(raw, applicable, diagnostics, free)
    return raw, applicable, diagnostics


def check_plane_and_frozen_inputs():
    positions, normals, edges, _ = _grid()
    positions[:, 2] = 0.2 * positions[:, 0] - 0.1 * positions[:, 1] + 0.3
    normal = np.asarray([-0.2, 0.1, 1.0])
    normal /= np.linalg.norm(normal)
    normals[:] = normal
    free = np.zeros(81, dtype=bool)
    free.reshape(9, 9)[1:-1, 1:-1] = True
    snapshots = [value.copy() for value in (positions, normals, edges, free)]
    raw, applicable, diagnostics = _run_fit(positions, normals, edges, free)
    assert np.array_equal(applicable, free)
    error = float(np.max(np.abs(raw)))
    assert error < 1.0e-12
    correction = mls.gate_displacement(normals, raw, applicable, free, 1.0e-8)
    assert np.all(correction == 0)
    assert all(
        np.array_equal(value, snapshot)
        for value, snapshot in zip((positions, normals, edges, free), snapshots)
    )
    return {
        "maximum_absolute_residual": error,
        "counts": diagnostics["counts"],
        "inputs_preserved": True,
    }


def check_quadratic_reproduction():
    positions, normals, edges, center = _grid(spacing=0.5)
    x, y = positions[:, 0], positions[:, 1]
    positions[:, 2] = 0.04 * x * x + 0.02 * x * y - 0.03 * y * y + 0.07 * x - 0.05 * y + 0.1
    free = np.zeros(len(positions), dtype=bool)
    free[[center - 10, center - 1, center, center + 1, center + 10]] = True
    raw, applicable, diagnostics = _run_fit(positions, normals, edges, free)
    error = float(np.max(np.abs(raw)))
    assert np.array_equal(applicable, free)
    assert error < 1.0e-12
    return {
        "maximum_absolute_residual": error,
        "counts": diagnostics["counts"],
        "normal_field": "constant prescribed tangent direction for exact polynomial reproduction",
    }


def check_signed_isolated_outliers():
    results = []
    for height in (0.4, -0.4):
        positions, normals, edges, center = _grid()
        positions[center, 2] = height
        free = _center_mask(len(positions), center)
        raw, applicable, diagnostics = _run_fit(positions, normals, edges, free)
        assert applicable[center]
        assert abs(raw[center] - height) < 1.0e-10
        correction = mls.gate_displacement(normals, raw, applicable, free, 0.05)
        expected_step = -np.sign(height) * (abs(height) - 0.05)
        assert abs(correction[center, 2] - expected_step) < 1.0e-10
        assert np.all(correction[~free] == 0)
        results.append({
            "observed_center_height": height,
            "raw_signed_residual": float(raw[center]),
            "gated_center_step": float(correction[center, 2]),
            "IRLS_passes": diagnostics["irls_passes_completed"][center],
        })
    return {
        "synthetic_threshold": 0.05,
        "probes": results,
        "evidence_scope": "isolated outlier implementation behavior",
    }


def check_fixed_pass_weighting_reference():
    positions, normals, _, center = _grid()
    x, y = positions[:, 0], positions[:, 1]
    positions[:, 2] = (
        0.04 * np.sin(0.9 * x)
        + 0.03 * np.cos(1.3 * y)
        + 0.015 * x * y
    )
    positions[center, 2] -= 0.12
    positions[[1, 20, 78], 2] += [0.35, -0.4, 0.6]
    free = _center_mask(len(positions), center)
    edges = _star_edges(len(positions), center)
    raw, applicable, _ = _run_fit(positions, normals, edges, free)
    assert applicable[center]

    # This independent reference uses the fixed world x/y polynomial basis.
    # Every graph path is a spoke, so its distance is known analytically.
    offset = positions - positions[center]
    x, y, height = offset.T
    design = np.column_stack((x * x, x * y, y * y, x, y, np.ones(len(x))))
    distances = np.linalg.norm(offset, axis=1)
    spatial = np.exp(-(distances / 4.0) ** 2)
    coefficients = np.linalg.lstsq(
        design * np.sqrt(spatial)[:, None], height * np.sqrt(spatial), rcond=None
    )[0]
    intercept_trace = [-float(coefficients[-1])]
    median_trace = []
    scale_trace = []
    for _ in range(3):
        error = height - design @ coefficients
        median = float(np.median(error))
        scale = max(1.4826 * float(np.median(np.abs(error - median))), 1.0e-4)
        ratio = error / (4.685 * scale)
        robust = np.zeros(len(error))
        inside = np.abs(ratio) < 1
        robust[inside] = (1 - ratio[inside] ** 2) ** 2
        root_weight = np.sqrt(spatial * robust)
        coefficients, _, rank, _ = np.linalg.lstsq(
            design * root_weight[:, None], height * root_weight, rcond=None
        )
        assert rank == 6
        intercept_trace.append(-float(coefficients[-1]))
        median_trace.append(median)
        scale_trace.append(scale)
    assert abs(raw[center] - intercept_trace[-1]) < 1.0e-12
    assert abs(intercept_trace[0] - intercept_trace[-1]) > 1.0e-3
    assert abs(intercept_trace[-2] - intercept_trace[-1]) > 1.0e-6
    return {
        "reference_basis": "world x/y full quadratic on a synthetic star graph",
        "raw_residual_initial_and_after_each_IRLS": intercept_trace,
        "unweighted_signed_residual_medians": median_trace,
        "MAD_scales": scale_trace,
        "implementation_reference_error": float(abs(raw[center] - intercept_trace[-1])),
    }


def check_smooth_quadratic_depression():
    positions, normals, edges, center = _grid(spacing=0.5)
    positions[:, 2] = 0.02 * np.sum(positions[:, :2] ** 2, axis=1) - 0.6
    free = _center_mask(len(positions), center)
    raw, applicable, _ = _run_fit(positions, normals, edges, free)
    correction = mls.gate_displacement(normals, raw, applicable, free, 0.05)
    assert applicable[center]
    assert abs(raw[center]) < 1.0e-12
    assert np.all(correction == 0)
    return {
        "observed_center_height": float(positions[center, 2]),
        "raw_signed_residual": float(raw[center]),
        "center_correction_norm": float(np.linalg.norm(correction[center])),
        "evidence_scope": "smooth quadratic reproduction in a synthetic prescribed normal field",
        "continuous_dent_recovery_quality": "unmeasured",
    }


def check_missing_neighbors():
    positions = np.zeros((4, 3))
    normals = np.tile([0.0, 0.0, 1.0], (4, 1))
    edges = np.empty((2, 0), dtype=np.int64)
    free = _center_mask(4, 0)
    raw, applicable, diagnostics = _run_fit(positions, normals, edges, free)
    assert diagnostics["counts"]["too_few_points"] == 1
    assert diagnostics["neighbor_count"][0] == 1
    assert np.all(raw == 0) and not applicable.any()
    return {"counts": diagnostics["counts"], "center_samples_including_self": 1}


def check_initial_rank_failure():
    positions = np.column_stack((np.arange(15) - 7, np.zeros(15), np.zeros(15))).astype(float)
    normals = np.tile([0.0, 0.0, 1.0], (15, 1))
    forward = np.stack((np.arange(14), np.arange(1, 15)))
    edges = np.concatenate((forward, forward[::-1]), axis=1)
    free = _center_mask(15, 7)
    _, applicable, diagnostics = _run_fit(positions, normals, edges, free)
    assert not applicable.any()
    assert diagnostics["counts"]["rank_deficient"] == 1
    assert diagnostics["neighbor_count"][7] == 15
    return {"counts": diagnostics["counts"], "geometry": "collinear samples"}


def check_irls_rank_failure():
    line = np.column_stack((np.linspace(-4, 4, 17), np.zeros(17), np.zeros(17)))
    off_line = np.array([
        [x, y, z]
        for x, y in ((-1, -1), (-1, 1), (1, -1), (1, 1))
        for z in (-0.5, 0.5, -0.5, 0.5)
    ])
    positions = np.concatenate((line, off_line))
    normals = np.tile([0.0, 0.0, 1.0], (len(positions), 1))
    edges = _star_edges(len(positions), 8)
    free = _center_mask(len(positions), 8)
    _, applicable, diagnostics = _run_fit(positions, normals, edges, free)
    assert not applicable.any()
    assert diagnostics["counts"]["irls_rank_deficient"] == 1
    assert diagnostics["irls_passes_completed"][8] == 0
    return {
        "counts": diagnostics["counts"],
        "geometry": "full-rank symmetric outliers rejected onto a rank-deficient line",
        "completed_IRLS_passes": diagnostics["irls_passes_completed"][8],
    }


def check_invalid_points_and_fixed_counts():
    positions = np.zeros((6, 3))
    normals = np.tile([0.0, 0.0, 1.0], (6, 1))
    normals[0] = 0
    normals[1] = np.nan
    positions[2, 0] = np.nan
    normals[4] = np.nan
    edges = np.array([[0, 2], [2, 0]], dtype=np.int64)
    free = np.array([True, True, True, True, False, False])
    raw, applicable, diagnostics = _run_fit(positions, normals, edges, free)
    assert diagnostics["counts"]["invalid_normal"] == 2
    assert diagnostics["counts"]["invalid_numeric"] == 1
    assert diagnostics["counts"]["too_few_points"] == 1
    assert diagnostics["counts"]["fixed"] == 2
    assert diagnostics["invalid_directed_edges_excluded"] == 2
    assert np.all(mls.gate_displacement(normals, raw, applicable, free, 0.05) == 0)
    return {"counts": diagnostics["counts"], "per_point_reason": diagnostics["per_point_reason"]}


def check_graph_radius_and_normal_filter():
    positions, normals, _, center = _grid(size=5, spacing=0.5)
    base_count = len(positions)
    extras = np.array([
        [8.0, 0, 0],
        [8.0 + 1.0e-6, 0, 0],
        [0, 0.2, 0],
        [0, -0.2, 0],
        [0, 0.3, 0],
        [0, 0.4, 0],
        [7.0, 0, 0],
        [0.1, 0, 0],
    ])
    positions = np.concatenate((positions, extras))
    normals = np.concatenate((normals, np.tile([0.0, 0.0, 1.0], (len(extras), 1))))
    normals[base_count + 2] = [np.sqrt(0.75), 0, 0.5]
    below = 0.5 - 1.0e-6
    normals[base_count + 3] = [np.sqrt(1 - below * below), 0, below]
    normals[base_count + 4] = 0
    excluded = (base_count + 5, base_count + 7)
    edges = _star_edges(len(positions), center, excluded)
    detour = np.array([[base_count + 6, base_count + 7], [base_count + 7, base_count + 6]])
    edges = np.concatenate((edges, detour), axis=1)
    free = _center_mask(len(positions), center)
    raw, applicable, diagnostics = _run_fit(positions, normals, edges, free)
    assert applicable[center]
    assert diagnostics["geodesic_count"][center] == 30
    assert diagnostics["neighbor_count"][center] == 28
    assert diagnostics["invalid_normal_neighbor_occurrences_excluded"] == 1
    assert abs(raw[center]) < 1.0e-12
    return {
        "geodesic_samples": diagnostics["geodesic_count"][center],
        "filtered_samples": diagnostics["neighbor_count"][center],
        "probes": [
            "distance exactly 8",
            "distance greater than 8",
            "normal dot exactly 0.5",
            "normal dot below 0.5",
            "invalid neighbor normal",
            "disconnected Euclidean-near point",
            "Euclidean-near point beyond graph radius",
        ],
    }


def check_rotation_translation_and_permutation():
    positions, normals, edges, center = _grid()
    positions[center, 2] = -0.4
    free = np.zeros(len(positions), dtype=bool)
    free[[center - 10, center - 1, center, center + 1, center + 10]] = True
    raw, applicable, _ = _run_fit(positions, normals, edges, free)
    correction = mls.gate_displacement(normals, raw, applicable, free, 0.05)
    random = np.random.default_rng(1729)
    residual_errors = []
    correction_errors = []
    for _ in range(3):
        rotation, _ = np.linalg.qr(random.normal(size=(3, 3)))
        if np.linalg.det(rotation) < 0:
            rotation[:, 0] *= -1
        rotated_positions = positions @ rotation.T + np.array([17.0, -5.0, 3.0])
        rotated_normals = normals @ rotation.T
        rotated_raw, rotated_applicable, _ = _run_fit(
            rotated_positions, rotated_normals, edges, free
        )
        rotated_correction = mls.gate_displacement(
            rotated_normals, rotated_raw, rotated_applicable, free, 0.05
        )
        assert np.array_equal(rotated_applicable, applicable)
        residual_errors.append(float(np.max(np.abs(rotated_raw - raw))))
        correction_errors.append(
            float(np.max(np.abs(rotated_correction - correction @ rotation.T)))
        )
    assert max(residual_errors) < 1.0e-10
    assert max(correction_errors) < 1.0e-10
    permutation = random.permutation(len(positions))
    inverse = np.argsort(permutation)
    permuted_raw, permuted_applicable, _ = _run_fit(
        positions[permutation], normals[permutation], inverse[edges], free[permutation]
    )
    assert np.array_equal(permuted_applicable[inverse], applicable)
    permutation_error = float(np.max(np.abs(permuted_raw[inverse] - raw)))
    assert permutation_error < 1.0e-10
    return {
        "proper_rotations": 3,
        "maximum_residual_error": max(residual_errors),
        "maximum_correction_covariance_error": max(correction_errors),
        "maximum_permutation_error": permutation_error,
    }


def check_gate_and_invalid_interface_inputs():
    normals = np.tile([0.0, 0.0, 1.0], (7, 1))
    raw = np.array([-0.3, -0.1, 0, 0.1, 0.3, np.nan, 0.4])
    applicable = np.array([True, True, True, True, False, True, True])
    free = np.array([True, True, True, True, True, True, False])
    correction = mls.gate_displacement(normals, raw, applicable, free, 0.1)
    expected = np.zeros((7, 3))
    expected[0, 2] = 0.2
    assert np.allclose(correction, expected, rtol=0, atol=1.0e-15)
    three_positions = np.zeros((3, 3))
    three_normals = np.zeros((3, 3))
    three_free = np.ones(3, dtype=bool)
    rejected = []
    for label, invoke in (
        (
            "negative threshold",
            lambda: mls.gate_displacement(normals, raw, applicable, free, -0.1),
        ),
        (
            "nonfinite threshold",
            lambda: mls.gate_displacement(normals, raw, applicable, free, np.inf),
        ),
        (
            "vector threshold",
            lambda: mls.gate_displacement(normals, raw, applicable, free, [0.1]),
        ),
        (
            "malformed positions",
            lambda: mls.fit_residuals(
                np.zeros((3, 2)), three_normals,
                np.empty((2, 0), dtype=int), three_free,
            ),
        ),
        (
            "noninteger edges",
            lambda: mls.fit_residuals(
                three_positions, three_normals, np.zeros((2, 1)), three_free
            ),
        ),
        (
            "invalid local index",
            lambda: mls.fit_residuals(
                three_positions, three_normals, np.array([[0], [3]]), three_free
            ),
        ),
    ):
        try:
            invoke()
        except ValueError:
            rejected.append(label)
        else:
            raise AssertionError(f"Expected ValueError for {label}")
    raw_empty, applicable_empty, diagnostics = _run_fit(
        np.empty((0, 3)), np.empty((0, 3)),
        np.empty((2, 0), dtype=np.int64), np.empty(0, dtype=bool),
    )
    assert raw_empty.shape == applicable_empty.shape == (0,)
    empty_correction = mls.gate_displacement(
        np.empty((0, 3)), raw_empty, applicable_empty, np.empty(0, dtype=bool), 0.1
    )
    assert empty_correction.shape == (0, 3)
    return {
        "synthetic_threshold": 0.1,
        "rejected_inputs": rejected,
        "empty_graph_counts": diagnostics["counts"],
    }


def run_qa():
    started_wall = time.perf_counter()
    started_cpu = time.process_time()
    checks = (
        check_plane_and_frozen_inputs,
        check_quadratic_reproduction,
        check_signed_isolated_outliers,
        check_fixed_pass_weighting_reference,
        check_smooth_quadratic_depression,
        check_missing_neighbors,
        check_initial_rank_failure,
        check_irls_rank_failure,
        check_invalid_points_and_fixed_counts,
        check_graph_radius_and_normal_filter,
        check_rotation_translation_and_permutation,
        check_gate_and_invalid_interface_inputs,
    )
    results = []
    for check in checks:
        started = time.perf_counter()
        try:
            details = check()
            result = {"name": check.__name__, "passed": True, "details": details}
        except Exception as error:
            result = {
                "name": check.__name__,
                "passed": False,
                "error": f"{type(error).__name__}: {error}",
            }
        result["wall_s"] = time.perf_counter() - started
        results.append(result)
    return {
        "task": "M6-SHAPE-TRAIN-001",
        "evidence_scope": "synthetic graphs for finite implementation verification",
        "thresholds": "fixed synthetic test constants, calibration delegated to root",
        "continuous_dent_recovery_quality": "unmeasured",
        "dataset_scoring": "delegated to root",
        "runtime": {
            "python": sys.version,
            "numpy": np.__version__,
            "platform": platform.platform(),
        },
        "sources_sha256": {
            source.name: hashlib.sha256(source.read_bytes()).hexdigest()
            for source in (MODULE_PATH, Path(__file__).resolve())
        },
        "passed": all(result["passed"] for result in results),
        "checks": results,
        "wall_s": time.perf_counter() - started_wall,
        "cpu_s": time.process_time() - started_cpu,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "MLS_QA.json")
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    if output.parent != HERE or output.suffix.lower() != ".json":
        parser.error("QA JSON output must be directly inside the TRAIN-001 directory")
    report = run_qa()
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "passed": report["passed"],
        "checks": len(report["checks"]),
        "output": str(output),
        "wall_s": report["wall_s"],
    }))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
