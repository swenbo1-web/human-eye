"""Fixed unsigned-seed components and common-denominator ranking metrics."""

from contextlib import contextmanager
import ctypes
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
environment = json.loads((HERE.parent / "m6_shape_pretrain_001/ENVIRONMENT.json").read_bytes())
for directory in reversed(environment["dependency_paths"]):
    if directory not in sys.path:
        sys.path.insert(0, directory)

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

CONFIGURATIONS = ("solid_point", "ring_point", "solid_cluster", "ring_cluster")


@contextmanager
def measure(timings, name):
    started, cpu = time.perf_counter(), time.process_time()
    try:
        yield
    finally:
        row = timings.setdefault(name, {"wall_s": 0.0, "CPU_s": 0.0, "calls": 0})
        row["wall_s"] += time.perf_counter() - started
        row["CPU_s"] += time.process_time() - cpu
        row["calls"] += 1


def process_resources():
    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [
            (key, ctypes.c_size_t) for key in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
            "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    process = ctypes.windll.kernel32.GetCurrentProcess()
    ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    if not ctypes.windll.psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb):
        raise ctypes.WinError()
    return {"process_CPU_s": time.process_time(), "working_set_bytes": counters.WorkingSetSize,
            "peak_working_set_bytes": counters.PeakWorkingSetSize}


def distribution(values):
    raw = list(values)
    valid = np.asarray([value for value in raw if value is not None], dtype=np.float64)
    return {"requested_values": len(raw), "count": len(valid), "not_applicable_values": len(raw) - len(valid),
            "min": float(valid.min()) if len(valid) else None,
            "median": float(np.median(valid)) if len(valid) else None,
            "mean": float(valid.mean()) if len(valid) else None,
            "p95": float(np.quantile(valid, .95, method="linear")) if len(valid) else None,
            "max": float(valid.max()) if len(valid) else None}


def components(mask, edge_index):
    mask = np.asarray(mask, dtype=bool)
    adjacency = [[] for _ in mask]
    for first, second in np.asarray(edge_index, dtype=np.int64).T:
        adjacency[first].append(int(second))
        adjacency[second].append(int(first))
    visited = np.zeros(len(mask), dtype=bool)
    result = []
    for start in np.flatnonzero(mask):
        if visited[start]:
            continue
        visited[start] = True
        stack, member_rows = [int(start)], []
        while stack:
            current = stack.pop()
            member_rows.append(current)
            for neighbor in adjacency[current]:
                if mask[neighbor] and not visited[neighbor]:
                    visited[neighbor] = True
                    stack.append(neighbor)
        result.append(np.asarray(sorted(member_rows), dtype=np.int64))
    return result


def component_scores(residual, area, ell, edge_index, seed_threshold):
    residual, area = np.asarray(residual, dtype=np.float64), np.asarray(area, dtype=np.float64)
    if residual.shape != area.shape or not np.isfinite(residual).all() or not np.isfinite(area).all():
        raise ValueError("invalid_residual_or_area")
    seed = np.abs(residual) / ell > seed_threshold
    scores = np.zeros(len(residual), dtype=np.float64)
    component_ids = np.zeros(len(residual), dtype=np.int64)
    records = []
    for ordinal, rows in enumerate(components(seed, edge_index), start=1):
        component_ids[rows] = ordinal
        unsigned = float(np.sum(area[rows] * np.abs(residual[rows])))
        signed = float(np.sum(area[rows] * residual[rows]))
        energy = unsigned / ell ** 3
        coherence = abs(signed) / unsigned if unsigned > 0 else 0.0
        score = abs(signed) / ell ** 3
        retained = len(rows) >= 5
        if retained:
            scores[rows] = score
        records.append({"component_id": ordinal, "vertices": len(rows), "retained_at_least5": retained,
                        "area_native": float(area[rows].sum()), "area_over_ell2": float(area[rows].sum()) / ell ** 2,
                        "energy_E": energy, "coherence_C": coherence, "score_T": score,
                        "weighted_signed_sum_native": signed})
    return scores, component_ids, records


def rank_metrics(labels, scores):
    labels, scores = np.asarray(labels, dtype=bool), np.asarray(scores, dtype=np.float64)
    if labels.shape != scores.shape or not np.isfinite(scores).all():
        raise ValueError("rank_metric_nonfinite_or_shape_mismatch")
    positive = int(labels.sum())
    negative = len(labels) - positive
    return {"points": len(labels), "positive": positive, "negative": negative,
            "ROC_AUC": float(roc_auc_score(labels, scores)) if positive and negative else None,
            "AP": float(average_precision_score(labels, scores)) if positive else None,
            "AUC_not_applicable": not (positive and negative), "AP_not_applicable": positive == 0}


def operating_metrics(labels, selected, area, ell, edge_index):
    labels, selected, area = np.asarray(labels, dtype=bool), np.asarray(selected, dtype=bool), np.asarray(area, dtype=np.float64)
    tp, fp = int(np.count_nonzero(selected & labels)), int(np.count_nonzero(selected & ~labels))
    fn, tn = int(np.count_nonzero(~selected & labels)), int(np.count_nonzero(~selected & ~labels))
    total_positive_area = float(area[labels].sum())
    true_selected_area = float(area[selected & labels].sum())
    false_selected_area = float(area[selected & ~labels].sum())
    selected_area = true_selected_area + false_selected_area
    normal_area = float(area[~labels].sum())
    sizes = [len(rows) for rows in components(selected, edge_index)]
    return {"points": len(labels), "TP": tp, "FP": fp, "FN": fn, "TN": tn,
            "point_recall": tp / (tp + fn) if tp + fn else None,
            "point_precision": tp / (tp + fp) if tp + fp else None,
            "point_FPR": fp / (fp + tn) if fp + tn else None,
            "positive_area_native": total_positive_area, "selected_positive_area_native": true_selected_area,
            "missed_positive_area_native": total_positive_area - true_selected_area,
            "selected_normal_area_native": false_selected_area, "normal_area_native": normal_area,
            "positive_area_over_ell2": total_positive_area / ell ** 2,
            "selected_positive_area_over_ell2": true_selected_area / ell ** 2,
            "missed_positive_area_over_ell2": (total_positive_area - true_selected_area) / ell ** 2,
            "selected_normal_area_over_ell2": false_selected_area / ell ** 2,
            "normal_area_over_ell2": normal_area / ell ** 2,
            "area_recall": true_selected_area / total_positive_area if total_positive_area else None,
            "area_precision": true_selected_area / selected_area if selected_area else None,
            "zero_true_detection": bool(tp == 0) if tp + fn else None,
            "normal_case_any_selection": bool(tp + fp) if not np.any(labels) else None,
            "selected_component_count": len(sizes), "selected_component_sizes": sizes}
