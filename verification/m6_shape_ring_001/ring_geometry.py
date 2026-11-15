"""Fixed full-topology neighborhoods, observed frames and robust height fits."""

from contextlib import contextmanager
import ctypes
import time

import numpy as np


FAILURE_CODES = {
    0: "available",
    1: "invalid_observed_normal",
    2: "nonpositive_or_nonfinite_R",
    3: "fewer_than_six_points",
    4: "nonfinite_fit_points",
    5: "rank_deficient_weighted_design",
    6: "nonfinite_coefficients",
    7: "linear_algebra_failure",
    8: "nonfinite_height",
}


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
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [
            (name, ctypes.c_size_t) for name in (
                "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
    counters = MemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    handle = ctypes.windll.kernel32.GetCurrentProcess()
    ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    if not ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
        raise ctypes.WinError()
    return {"process_CPU_s": time.process_time(), "working_set_bytes": counters.WorkingSetSize,
            "peak_working_set_bytes": counters.PeakWorkingSetSize}


def full_topology(triangles, vertex_count):
    """Build deterministic undirected edges and complete source CSR adjacency."""
    triangles = np.asarray(triangles, dtype=np.int64)
    if triangles.ndim != 2 or triangles.shape[1] != 3:
        raise ValueError("source_triangles_must_be_M_by_3")
    if len(triangles) and (triangles.min() < 0 or triangles.max() >= vertex_count):
        raise ValueError("source_triangle_index_outside_vertex_domain")
    edges = np.concatenate((triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]))
    edges.sort(axis=1)
    edges = np.unique(edges[edges[:, 0] != edges[:, 1]], axis=0)
    directed = np.concatenate((edges, edges[:, ::-1]))
    directed = directed[np.lexsort((directed[:, 1], directed[:, 0]))]
    counts = np.bincount(directed[:, 0], minlength=vertex_count)
    indptr = np.concatenate((np.zeros(1, dtype=np.int64), np.cumsum(counts, dtype=np.int64)))
    return {"edges": edges, "indptr": indptr, "indices": directed[:, 1]}


def bfs_ten_hops(indptr, indices, query_source_id):
    """Return every vertex at hops1 through10, ordered by hop then source ID."""
    query_source_id = int(query_source_id)
    visited = {query_source_id}
    frontier = [query_source_id]
    vertices, distances = [], []
    for hop in range(1, 11):
        next_vertices = set()
        for source_id in frontier:
            next_vertices.update(indices[indptr[source_id]:indptr[source_id + 1]].tolist())
        next_vertices.difference_update(visited)
        frontier = sorted(next_vertices)
        vertices.extend(frontier)
        distances.extend([hop] * len(frontier))
        visited.update(frontier)
        if not frontier:
            break
    return np.asarray(vertices, dtype=np.int64), np.asarray(distances, dtype=np.uint8)


def make_frame(normal):
    """Return column basis[t1,t2,n] from the fixed least-aligned-axis rule."""
    normal = np.asarray(normal, dtype=np.float64)
    length = np.linalg.norm(normal)
    if normal.shape != (3,) or not np.isfinite(normal).all() or not np.isfinite(length) or length == 0:
        return np.zeros((3, 3), dtype=np.float64), False
    unit = normal / length
    axis = np.eye(3, dtype=np.float64)[int(np.argmin(np.abs(unit)))]
    first = np.cross(unit, axis)
    first /= np.linalg.norm(first)
    second = np.cross(unit, first)
    return np.column_stack((first, second, unit)), True


def robust_quadratic(points):
    """Fit the fixed six coefficients with WLS and exactly three Tukey updates."""
    points = np.asarray(points, dtype=np.float64)
    result = {"height": 0.0, "valid": False, "failure_code": 0,
              "point_count": len(points), "rank": 0, "condition": None,
              "coefficients": np.zeros(6, dtype=np.float64),
              "rank_trace": np.zeros(4, dtype=np.int64),
              "condition_trace": np.full(4, np.nan), "completed_fits": 0}
    if len(points) < 6:
        result["failure_code"] = 3
        return result
    if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all():
        result["failure_code"] = 4
        return result
    u, v, height = points.T
    design = np.column_stack((u * u, u * v, v * v, u, v, np.ones(len(points))))
    spatial_weight = np.exp(-4.0 * np.sum(points * points, axis=1))
    weights = spatial_weight.copy()
    try:
        for fit_index in range(4):
            root_weights = np.sqrt(weights)
            coefficients, _, rank, singular = np.linalg.lstsq(
                design * root_weights[:, None], height * root_weights, rcond=None)
            condition = float(singular[0] / singular[-1]) if len(singular) and singular[-1] > 0 else None
            result.update(rank=int(rank), condition=condition if condition is not None and np.isfinite(condition) else None,
                          completed_fits=fit_index + 1)
            result["rank_trace"][fit_index] = rank
            result["condition_trace"][fit_index] = result["condition"] if result["condition"] is not None else np.nan
            if rank != 6:
                result["failure_code"] = 5
                return result
            if not np.isfinite(coefficients).all():
                result["failure_code"] = 6
                return result
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
    except (np.linalg.LinAlgError, FloatingPointError):
        result["failure_code"] = 7
        return result
    if not np.isfinite(coefficients[5]):
        result["failure_code"] = 8
        return result
    result.update(height=float(coefficients[5]), valid=True, coefficients=coefficients)
    return result


def free_vertex_areas(vertices, triangles, incident_triangle_ids, free_source_ids):
    """Sum one-third areas over all complete-source triangles incident to F."""
    faces = triangles[incident_triangle_ids]
    points = vertices[faces]
    area = .5 * np.linalg.norm(np.cross(points[:, 1] - points[:, 0], points[:, 2] - points[:, 0]), axis=1)
    local = np.full(len(vertices), -1, dtype=np.int64)
    local[free_source_ids] = np.arange(len(free_source_ids))
    face_local = local[faces].ravel()
    included = face_local >= 0
    weights = np.repeat(area / 3.0, 3)
    values = np.bincount(face_local[included], weights=weights[included], minlength=len(free_source_ids))
    return values, {"complete_F_incident_triangles": len(faces),
                    "zero_area_incident_triangles": int(np.count_nonzero(area == 0)),
                    "nonfinite_area_incident_triangles": int(np.count_nonzero(~np.isfinite(area)))}
