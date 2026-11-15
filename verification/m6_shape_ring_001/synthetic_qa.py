"""Closed-form checks for the two fixed ring fits and score aggregation."""

import os
for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[name] = "1"

import hashlib
import json
from pathlib import Path
import sys
import time

BOOT_WALL, BOOT_CPU = time.perf_counter(), time.process_time()
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "m6_shape_pretrain_001/private/deps"))
import numpy as np
from qa_math import independent_auc_ap, independent_clusters, independent_fit, independent_frame, resources
from ring_geometry import bfs_ten_hops, make_frame, robust_quadratic
from ring_metrics import component_scores, rank_metrics


def main():
    checks = []

    def check(name, actual, expected, tolerance=1e-10):
        if isinstance(actual, (tuple, list, np.ndarray)) or isinstance(expected, (tuple, list, np.ndarray)):
            passed = bool(np.allclose(actual, expected, rtol=tolerance, atol=tolerance, equal_nan=True))
        elif actual is None or expected is None:
            passed = actual is expected
        elif isinstance(actual, (float, np.floating)):
            passed = bool(np.isclose(actual, expected, rtol=tolerance, atol=tolerance))
        else:
            passed = actual == expected
        passed = bool(passed)
        checks.append({"name": name, "passed": passed})
        if not passed:
            raise ValueError(name)

    grid_u, grid_v = np.meshgrid(np.linspace(-.8, .8, 5), np.linspace(-.7, .7, 5))
    u, v = grid_u.ravel(), grid_v.ravel()
    coefficients = np.array([.1, .05, -.2, .2, -.15, .125])
    z = np.column_stack((u*u, u*v, v*v, u, v, np.ones(len(u)))) @ coefficients
    points = np.column_stack((u, v, z))
    actual = robust_quadratic(points)
    check("closed_quadratic_valid", actual["valid"], True)
    check("closed_quadratic_height", actual["height"], .125)
    check("closed_quadratic_coefficients", actual["coefficients"], coefficients)
    check("independent_quadratic_height", actual["height"], independent_fit(points)["height"])
    check("five_points_unavailable", robust_quadratic(points[:5])["valid"], False)
    check("rank_deficient_unavailable", robust_quadratic(np.column_stack((u, np.zeros_like(u), z)))["valid"], False)
    nonfinite = points.copy()
    nonfinite[0, 0] = np.nan
    check("nonfinite_fit_unavailable", robust_quadratic(nonfinite)["valid"], False)

    for index, normal in enumerate(([0., 0., 1.], [1., 1., 1.], [3., -4., 5.])):
        basis, valid = make_frame(np.asarray(normal))
        check("frame_valid_" + str(index), valid, True)
        check("frame_orthogonal_" + str(index), basis.T @ basis, np.eye(3))
        check("frame_right_handed_" + str(index), np.linalg.det(basis), 1.)
        check("frame_independent_" + str(index), basis, independent_frame(normal)[0])
    check("zero_normal_invalid", make_frame(np.zeros(3))[1], False)
    check("nonfinite_normal_invalid", make_frame(np.array([0., np.inf, 1.]))[1], False)

    adjacency = [[1]] + [[vertex - 1, vertex + 1] for vertex in range(1, 14)] + [[13]]
    offsets = np.r_[0, np.cumsum([len(row) for row in adjacency])].astype(np.int64)
    indices = np.asarray([vertex for row in adjacency for vertex in row], dtype=np.int64)
    neighbors, hops = bfs_ten_hops(offsets, indices, 0)
    check("BFS_excludes_center_and_above10", neighbors, np.arange(1, 11))
    check("BFS_hop_values", hops, np.arange(1, 11))

    residual = np.array([1., -1., 1., -1., 1., 0., 1., 1., 1., 1., 0., 3., .4])
    area = np.ones(len(residual))
    edges = np.vstack((np.arange(len(residual)-1), np.arange(1, len(residual))))
    expected_scores, expected_components = independent_clusters(residual, area, 2., edges, .2)
    actual_scores, component_ids, records = component_scores(residual, area, 2., edges, .2)
    check("cluster_no_pre_sign_split", actual_scores, expected_scores)
    check("five_mixed_sign_points_retained", actual_scores[:5], np.full(5, .125))
    check("four_point_cluster_discarded", actual_scores[6:10], np.zeros(4))
    check("exact_seed_threshold_excluded", actual_scores[12], 0.)
    check("strict_operating_threshold", np.count_nonzero(actual_scores > .125), 0)
    check("linear_quantile90", np.quantile(np.arange(10.), .9, method="linear"), 8.1)
    check("linear_quantile95", np.quantile(np.arange(33.), .95, method="linear"), 30.4)

    labels = np.array([False, True, False, True])
    score = np.array([0., .5, .5, 1.])
    expected = independent_auc_ap(labels, score)
    actual = rank_metrics(labels, score)
    check("tied_ROC_closed_form", expected["ROC_AUC"], .875)
    check("tied_AP_closed_form", expected["AP"], 5./6.)
    for field in ("ROC_AUC", "AP"):
        candidate = actual.get(field, actual.get("roc_auc" if field == "ROC_AUC" else "average_precision"))
        check("implementation_" + field, candidate, expected[field])
    actual = rank_metrics(np.zeros(4, dtype=bool), score)
    check("no_positive_AUC_unavailable", actual.get("ROC_AUC", actual.get("roc_auc")), None)
    check("no_positive_AP_unavailable", actual.get("AP", actual.get("average_precision")), None)
    actual = rank_metrics(labels, np.zeros(4))
    check("all_tied_AUC", actual.get("ROC_AUC", actual.get("roc_auc")), .5)
    check("all_tied_AP", actual.get("AP", actual.get("average_precision")), .5)
    report = {"cycle_id": "M6-SHAPE-RING-001", "status": "passed_closed_form_ring_QA",
              "checks": checks, "check_count": len(checks), "failures": [], "real_observations_read": 0,
              "new_model_forwards": 0, "training": 0, "repair_outputs": 0, "Bunny_arrays": 0,
              "source_sha256": {name: hashlib.sha256((HERE/name).read_bytes()).hexdigest()
                                for name in ("synthetic_qa.py", "qa_math.py", "ring_geometry.py", "ring_metrics.py")},
              "bootstrap_wall_s_before_final_write": time.perf_counter() - BOOT_WALL,
              "bootstrap_CPU_s_before_final_write": time.process_time() - BOOT_CPU,
              "own_process_before_final_write": resources(),
              "measurement_scope": "imports and body until final JSON serialization, outer process ledger supplies startup/exit"}
    (HERE / "SYNTHETIC_QA.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf8", newline="\n")
    print(json.dumps({"status": report["status"], "checks": len(checks)}))


if __name__ == "__main__":
    main()
