"""Official Pointfilter neighborhoods and local-task synchronous updates."""

from contextlib import contextmanager
import ctypes
import importlib.util
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent


def configure_dependencies():
    environment = json.loads((HERE / "ENVIRONMENT.json").read_bytes())
    for directory in reversed(environment["dependency_paths"]):
        if directory not in sys.path:
            sys.path.insert(0, directory)
    return environment


configure_dependencies()
import numpy as np
from scipy.spatial import cKDTree
import torch


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
    class MemoryCounters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
    counters = MemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    handle = ctypes.windll.kernel32.GetCurrentProcess()
    ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    if not ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
        raise ctypes.WinError()
    return {"process_CPU_s": time.process_time(), "working_set_bytes": counters.WorkingSetSize,
            "peak_working_set_bytes": counters.PeakWorkingSetSize}


def load_official_pca():
    path = HERE / "private/pointfilter/Pointfilter_Utils.py"
    spec = importlib.util.spec_from_file_location("_m6_official_pointfilter_utils", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.pca_alignment


def prepare_neighborhoods(vertices, query_source_ids, rng, pca_alignment, timings=None):
    """Match the upstream scalar radius query, PCA, normalization and sampling."""
    if timings is None:
        timings = {}
    vertices = np.asarray(vertices)
    query_source_ids = np.asarray(query_source_ids, dtype=np.int64)
    if vertices.ndim != 2 or vertices.shape[1] != 3 or not np.isfinite(vertices).all():
        raise ValueError("source points must be finite N by 3")
    if query_source_ids.ndim != 1 or len(np.unique(query_source_ids)) != len(query_source_ids):
        raise ValueError("query IDs must be unique")
    if len(query_source_ids) and (query_source_ids.min() < 0 or query_source_ids.max() >= len(vertices)):
        raise ValueError("query ID outside source")
    if not np.array_equal(query_source_ids, np.sort(query_source_ids)):
        raise ValueError("query IDs must be sorted in source order")
    with measure(timings, "full_source_bbox_and_index"):
        diagonal = float(np.linalg.norm(vertices.max(axis=0) - vertices.min(axis=0), 2))
        radius = diagonal * 0.05
        if not np.isfinite(radius) or radius <= 0:
            raise ValueError("nonpositive or nonfinite source radius")
        tree = cKDTree(vertices)

    count = len(query_source_ids)
    normalized = np.full((count, 500, 3), np.nan, dtype=np.float32)
    inverse = np.full((count, 3, 3), np.nan, dtype=np.float64)
    sample_ids = np.full((count, 500), -1, dtype=np.int64)
    neighbor_lists = []
    status = np.zeros(count, dtype=np.int8)
    duplicate_counts = np.zeros(count, dtype=np.int64)
    for row, source_id in enumerate(query_source_ids):
        with measure(timings, "radius_queries"):
            # Scalar call intentionally preserves the upstream cKDTree list order.
            neighbors = np.asarray(tree.query_ball_point(vertices[source_id], radius), dtype=np.int64)
            neighbor_lists.append(neighbors)
        if len(neighbors) < 3:
            status[row] = 1
            continue
        with measure(timings, "PCA_and_normalization"):
            patch = vertices[neighbors] - vertices[source_id]
            patch, patch_inverse = pca_alignment(patch)
            patch /= radius
        with measure(timings, "500_point_sampling"):
            # Upstream uses replacement for every neighborhood of size <=500.
            chosen = rng.choice(range(len(neighbors)), 500, replace=len(neighbors) <= 500)
            normalized[row] = patch[chosen].astype(np.float32)
            inverse[row] = patch_inverse
            sample_ids[row] = neighbors[chosen]
            duplicate_counts[row] = 500 - len(np.unique(chosen))
        if not np.isfinite(normalized[row]).all() or not np.isfinite(inverse[row]).all():
            raise ValueError("nonfinite neighborhood preprocessing")
    lengths = np.array([len(values) for values in neighbor_lists], dtype=np.int64)
    offsets = np.concatenate((np.zeros(1, dtype=np.int64), np.cumsum(lengths)))
    flat = np.concatenate(neighbor_lists) if neighbor_lists else np.empty(0, dtype=np.int64)
    return {"query_source_ids": query_source_ids, "radius": np.array(radius),
            "full_source_bbox_diagonal": np.array(diagonal), "radius_per_query": np.full(count, radius),
            "neighbor_offsets": offsets, "neighbor_source_ids": flat, "neighbor_count": lengths,
            "sampled_source_ids": sample_ids, "normalized_points": normalized,
            "pca_inverse": inverse, "sampling_duplicate_count": duplicate_counts,
            "query_status_codes": status}


def robust_quadratic_point(points):
    """Radius-normalized quadratic MLS, initial weighted fit and three IRLS fits."""
    points = np.asarray(points, dtype=np.float64)
    u, v, height = points.T
    design = np.column_stack((u * u, u * v, v * v, u, v, np.ones(len(points))))
    spatial_weight = np.exp(-4.0 * np.sum(points * points, axis=1))
    weights = spatial_weight.copy()
    completed = 0
    try:
        for fit_index in range(4):
            root_weights = np.sqrt(weights)
            coefficients, _, rank, _ = np.linalg.lstsq(design * root_weights[:, None], height * root_weights, rcond=None)
            if rank != 6:
                return np.zeros(3), "rank_deficient", completed
            if not np.isfinite(coefficients).all():
                return np.zeros(3), "nonfinite_fit", completed
            if fit_index == 3:
                break
            residual = height - design @ coefficients
            median = np.median(residual)
            scale = max(1.4826 * float(np.median(np.abs(residual - median))), 1.0e-4)
            standardized = residual / (4.685 * scale)
            tukey = np.zeros(len(points), dtype=np.float64)
            inside = np.abs(standardized) < 1.0
            tukey[inside] = np.square(1.0 - np.square(standardized[inside]))
            weights = spatial_weight * tukey
            completed += 1
    except (np.linalg.LinAlgError, FloatingPointError):
        return np.zeros(3), "numeric_fit_failure", completed
    return np.array([0.0, 0.0, float(coefficients[5])]), "ok", completed


def run_iteration(vertices, query_source_ids, method, rng, pca_alignment, model=None, timings=None):
    """Predict from one frozen current source, then update all query points together."""
    if timings is None:
        timings = {}
    if method not in ("pointfilter", "robust_mls"):
        raise ValueError("unsupported method")
    detail = prepare_neighborhoods(vertices, query_source_ids, rng, pca_alignment, timings)
    valid_rows = np.flatnonzero(detail["query_status_codes"] == 0)
    predictions = np.zeros((len(query_source_ids), 3), dtype=np.float32 if method == "pointfilter" else np.float64)
    displacements = np.zeros((len(query_source_ids), 3), dtype=np.float64)
    reasons = {}
    forward_batches = 0
    if method == "pointfilter":
        if model is None:
            raise ValueError("pointfilter requires loaded model")
        with torch.inference_mode():
            for start in range(0, len(valid_rows), 64):
                rows = valid_rows[start:start + 64]
                with measure(timings, "network_input_conversion"):
                    tensor = torch.from_numpy(detail["normalized_points"][rows]).transpose(2, 1).contiguous()
                with measure(timings, "network_forward"):
                    predicted = model(tensor)
                    forward_batches += 1
                with measure(timings, "inverse_rotation_and_float64_center_restore"):
                    if not torch.isfinite(predicted).all():
                        raise ValueError("nonfinite network prediction")
                    predictions[rows] = predicted.cpu().numpy()
                    rotation = torch.from_numpy(detail["pca_inverse"][rows].astype(np.float32))
                    rotated = torch.bmm(rotation, predicted.unsqueeze(2)).squeeze(2).cpu().numpy()
                    displacements[rows] = rotated.astype(np.float64) * float(detail["radius"])
    else:
        with measure(timings, "robust_quadratic_MLS"):
            for row in valid_rows:
                prediction, reason, completed = robust_quadratic_point(detail["normalized_points"][row])
                predictions[row] = prediction
                reasons[reason] = reasons.get(reason, 0) + 1
                if reason != "ok":
                    detail["query_status_codes"][row] = 2
        with measure(timings, "inverse_rotation_and_float64_center_restore"):
            displacements[valid_rows] = np.einsum("nij,nj->ni", detail["pca_inverse"][valid_rows], predictions[valid_rows]) * float(detail["radius"])
    with measure(timings, "synchronous_full_source_update"):
        candidate = np.asarray(vertices, dtype=np.float64).copy()
        candidate[query_source_ids] += displacements
        if not np.isfinite(candidate).all():
            raise ValueError("nonfinite restored candidate")
    detail["local_prediction"] = predictions
    detail["network_prediction"] = predictions if method == "pointfilter" else np.empty((0, 3), dtype=np.float32)
    detail["restored_displacement"] = displacements
    statistics = {"query_count": len(query_source_ids), "source_point_count": len(vertices),
                  "radius_native": float(detail["radius"]), "bbox_diagonal_native": float(detail["full_source_bbox_diagonal"]),
                  "valid_preprocessed_queries": len(valid_rows),
                  "too_few_neighbor_queries": int(np.count_nonzero(detail["query_status_codes"] == 1)),
                  "MLS_fit_failure_queries": int(np.count_nonzero(detail["query_status_codes"] == 2)),
                  "MLS_fit_outcomes": reasons, "network_forward_batches": forward_batches,
                  "network_forward_query_count": len(valid_rows) if method == "pointfilter" else 0,
                  "neighbor_count": {"min": int(detail["neighbor_count"].min()), "median": float(np.median(detail["neighbor_count"])),
                                     "max": int(detail["neighbor_count"].max())},
                  "sampling_duplicate_total": int(detail["sampling_duplicate_count"].sum()),
                  "sampling_duplicate_queries": int(np.count_nonzero(detail["sampling_duplicate_count"])),
                  "sampling_with_replacement_queries": int(np.count_nonzero((detail["neighbor_count"] >= 3) & (detail["neighbor_count"] <= 500))),
                  "query_status_codes": {"0": "processed", "1": "fewer than three neighbors, unchanged", "2": "MLS fit failed, unchanged"}}
    return candidate, detail, statistics
