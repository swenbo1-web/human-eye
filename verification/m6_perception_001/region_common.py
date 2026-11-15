"""Small shared I/O helpers for the offline region-reference contract."""

from contextlib import contextmanager
import ctypes
import hashlib
import json
from pathlib import Path
import time

import numpy as np

HERE = Path(__file__).resolve().parent
REFERENCE_PREFIX = "m6perception://v1/region/"
MODEL_IDENTITY_KEYS = ("encoder_tensor_sha256", "head_final_sha256", "normalization_sha256")


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
            (name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize",
            "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
            "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
    counter = Counters()
    counter.cb = ctypes.sizeof(counter)
    ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    handle = ctypes.windll.kernel32.GetCurrentProcess()
    ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    if not ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counter), counter.cb):
        raise ctypes.WinError()
    return {"process_CPU_s": time.process_time(), "working_set_bytes": counter.WorkingSetSize,
            "peak_working_set_bytes": counter.PeakWorkingSetSize}


def resolve_path(path):
    path = Path(path)
    return path if path.is_absolute() else HERE / path


def read_json(path):
    return json.loads(resolve_path(path).read_bytes())


def write_json(path, value):
    path = resolve_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf8", newline="\n")


def file_identity(path):
    path = resolve_path(path)
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def checked_identity(path, expected_sha256=None):
    record = file_identity(path)
    if expected_sha256 is not None and record["sha256"] != expected_sha256:
        raise ValueError("file_identity_changed_" + str(path))
    return record


def source_ids_digest(source_ids):
    values = np.ascontiguousarray(source_ids, dtype="<i8")
    return hashlib.sha256(values.tobytes()).hexdigest()


def reference_for(identity):
    canonical = json.dumps(identity, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return REFERENCE_PREFIX + hashlib.sha256(canonical.encode("utf8")).hexdigest()


def model_identity_values(identity):
    values = {"encoder_tensor_sha256": identity.get("encoder_tensor_sha256", identity.get("encoder_final_tensor_sha256")),
              "head_final_sha256": identity["head_final_sha256"],
              "normalization_sha256": identity["normalization_sha256"]}
    for key, value in values.items():
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError("invalid_model_identity_" + key)
    return values


def components(selected, edge_index):
    selected = np.asarray(selected, dtype=bool)
    adjacency = [[] for _ in selected]
    for first, second in np.asarray(edge_index, dtype=np.int64).T:
        adjacency[first].append(int(second))
        adjacency[second].append(int(first))
    visited = np.zeros(len(selected), dtype=bool)
    groups = []
    for start in np.flatnonzero(selected):
        if visited[start]:
            continue
        visited[start] = True
        queue, members = [int(start)], []
        while queue:
            current = queue.pop()
            members.append(current)
            for neighbor in adjacency[current]:
                if selected[neighbor] and not visited[neighbor]:
                    visited[neighbor] = True
                    queue.append(neighbor)
        groups.append(np.asarray(sorted(members), dtype=np.int64))
    return groups


def geometry_facts(points, area):
    total = float(np.sum(area))
    centroid = np.sum(points * area[:, None], axis=0) / total if total > 0 else np.mean(points, axis=0)
    return {"coordinate_space": "source_native", "physical_unit": "unknown",
            "centroid_native": centroid.tolist(),
            "centroid_definition": "lumped_vertex_area_weighted" if total > 0 else "vertex_mean_zero_area",
            "bbox_native": {"min": points.min(axis=0).tolist(), "max": points.max(axis=0).tolist()}}
