"""Independent arithmetic used to check the frozen ring experiment."""

from collections import deque
import ctypes

import numpy as np


def resources():
    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [
            (name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
            "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
    result = Counters()
    result.cb = ctypes.sizeof(result)
    ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    if not ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(result), result.cb):
        raise ctypes.WinError()
    return {"peak_working_set_bytes": result.PeakWorkingSetSize, "working_set_bytes": result.WorkingSetSize}


def independent_bfs(adjacency, query, maximum=10):
    distance = {int(query): 0}
    queue = deque([int(query)])
    while queue:
        vertex = queue.popleft()
        level = distance[vertex]
        if level == maximum:
            continue
        for neighbor in adjacency[vertex]:
            neighbor = int(neighbor)
            if neighbor not in distance:
                distance[neighbor] = level + 1
                queue.append(neighbor)
    ordered = sorted((level, vertex) for vertex, level in distance.items() if level)
    return (np.asarray([vertex for level, vertex in ordered], dtype=np.int64),
            np.asarray([level for level, vertex in ordered], dtype=np.int64))


def independent_frame(normal):
    normal = np.asarray(normal, dtype=np.float64)
    length = np.linalg.norm(normal)
    if not np.isfinite(normal).all() or not np.isfinite(length) or length == 0:
        return np.zeros((3, 3)), False
    z = normal / length
    reference = np.eye(3)[int(np.argmin(np.abs(z)))]
    x = np.cross(z, reference)
    x /= np.linalg.norm(x)
    return np.column_stack((x, np.cross(z, x), z)), True


def independent_fit(points):
    """WLS then three IRLS fits, independently written from fixed equations."""
    points = np.asarray(points, dtype=np.float64)
    if len(points) < 6 or points.shape[1:] != (3,) or not np.isfinite(points).all():
        return {"valid": False, "height": 0.0, "rank": 0}
    u, v, z = points.T
    matrix = np.stack((u ** 2, u * v, v ** 2, u, v, np.ones(len(u))), axis=1)
    spatial = np.exp(-4.0 * np.einsum("ij,ij->i", points, points))
    weights = spatial.copy()
    try:
        for step in range(4):
            root = np.sqrt(weights)
            coefficients, _, rank, singular = np.linalg.lstsq(matrix * root[:, None], z * root, rcond=None)
            if rank != 6 or not np.isfinite(coefficients).all():
                return {"valid": False, "height": 0.0, "rank": int(rank)}
            if step < 3:
                residual = z - matrix.dot(coefficients)
                center = np.median(residual)
                sigma = max(float(1.4826 * np.median(np.abs(residual - center))), 1e-4)
                standardized = residual / (4.685 * sigma)
                inside = np.abs(standardized) < 1
                robust = np.zeros(len(z))
                robust[inside] = (1 - standardized[inside] ** 2) ** 2
                weights = spatial * robust
    except np.linalg.LinAlgError:
        return {"valid": False, "height": 0.0, "rank": 0}
    return {"valid": True, "height": float(coefficients[-1]), "rank": int(rank), "coefficients": coefficients}


def independent_clusters(residual, area, ell, edges, seed_threshold):
    residual, area = np.asarray(residual), np.asarray(area)
    active = np.abs(residual) / ell > seed_threshold
    neighbors = [[] for _ in residual]
    for first, second in np.asarray(edges, dtype=np.int64).T:
        if active[first] and active[second]:
            neighbors[first].append(int(second))
            neighbors[second].append(int(first))
    visited = np.zeros(len(residual), dtype=bool)
    score = np.zeros(len(residual))
    components = []
    for start in np.flatnonzero(active):
        if visited[start]:
            continue
        queue = [int(start)]
        visited[start] = True
        component = []
        while queue:
            vertex = queue.pop()
            component.append(vertex)
            for other in neighbors[vertex]:
                if not visited[other]:
                    visited[other] = True
                    queue.append(other)
        component = np.asarray(sorted(component), dtype=np.int64)
        denominator = float(np.dot(area[component], np.abs(residual[component])))
        signed = float(np.dot(area[component], residual[component]))
        energy = denominator / ell ** 3
        coherence = abs(signed) / denominator if denominator else 0.0
        statistic = abs(signed) / ell ** 3
        kept = len(component) >= 5
        if kept:
            score[component] = statistic
        components.append({"indices": component, "kept": kept, "E": energy,
                           "C": coherence, "T": statistic, "area": float(area[component].sum())})
    return score, components


def independent_auc_ap(labels, scores):
    labels = np.asarray(labels, dtype=bool)
    scores = np.asarray(scores, dtype=np.float64)
    positives = int(labels.sum())
    negatives = len(labels) - positives
    if positives and negatives:
        order = np.argsort(scores, kind="stable")
        sorted_scores, sorted_labels = scores[order], labels[order]
        unique, starts, counts = np.unique(sorted_scores, return_index=True, return_counts=True)
        ranks = np.empty(len(labels), dtype=np.float64)
        for start, count in zip(starts, counts):
            ranks[start:start + count] = start + (count + 1) / 2
        rank_sum = float(ranks[sorted_labels].sum())
        auc = (rank_sum - positives * (positives + 1) / 2) / (positives * negatives)
    else:
        auc = None
    if positives:
        order = np.argsort(-scores, kind="stable")
        sorted_scores, sorted_labels = scores[order], labels[order]
        endings = np.flatnonzero(np.r_[sorted_scores[1:] != sorted_scores[:-1], True])
        tp = np.cumsum(sorted_labels, dtype=np.float64)[endings]
        precision = tp / (endings + 1)
        recall_increment = np.diff(np.r_[0, tp]) / positives
        ap = float(np.dot(precision, recall_increment))
    else:
        ap = None
    return {"ROC_AUC": auc, "AP": ap, "positive_points": positives, "negative_points": negatives}


def independent_operating(labels, scores, area, threshold):
    labels = np.asarray(labels, dtype=bool)
    selected = np.asarray(scores) > threshold
    positive_area = float(np.sum(area[labels]))
    selected_area = float(np.sum(area[selected]))
    true_area = float(np.sum(area[selected & labels]))
    positives, predicted = int(labels.sum()), int(selected.sum())
    tp = int(np.count_nonzero(selected & labels))
    return {"TP": tp, "FP": predicted - tp, "FN": positives - tp,
            "point_recall": tp / positives if positives else None,
            "point_precision": tp / predicted if predicted else None,
            "area_recall": true_area / positive_area if positive_area else None,
            "area_precision": true_area / selected_area if selected_area else None,
            "missed_support_area": positive_area - true_area,
            "selected_normal_area": float(np.sum(area[selected & ~labels])),
            "selected_area": selected_area, "support_area": positive_area,
            "zero_detected_dent": bool(positives and tp == 0), "selected": selected}
