"""Collect CF cold-load, memory and train-only retrieval evidence out of band."""

from argparse import ArgumentParser
import ctypes
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sys
from time import perf_counter_ns
import tracemalloc

import numpy as np

from verification.cf_training import capacity_check, load_frozen


def _process_rss():
    if sys.platform != "win32":
        import resource

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return {"peak_rss_bytes": int(peak * (1 if sys.platform == "darwin" else 1024))}

    from ctypes import wintypes

    class MemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.argtypes = ()
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    query = psapi.GetProcessMemoryInfo
    query.argtypes = (wintypes.HANDLE, ctypes.POINTER(MemoryCounters), wintypes.DWORD)
    query.restype = wintypes.BOOL
    counters = MemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    if not query(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return {"rss_bytes": counters.WorkingSetSize, "peak_rss_bytes": counters.PeakWorkingSetSize}


def _numpy_bytes(*objects):
    # These model objects own their NumPy arrays. Count shared array identities once.
    def arrays(values):
        for value in values:
            if isinstance(value, np.ndarray):
                yield value
            elif isinstance(value, tuple):
                yield from arrays(value)

    unique = {id(array): array for obj in objects for array in arrays(vars(obj).values())}
    return sum(array.nbytes for array in unique.values())


def _traced(call):
    tracemalloc.start()
    try:
        before, _ = tracemalloc.get_traced_memory()
        value = call()
        current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return value, {"current_extra_bytes": current - before, "peak_extra_bytes": peak - before}


def _retrieval(session, queries):
    samples = []
    for query in queries:
        start = perf_counter_ns()
        ranking = session.rank_view(query, "R")
        samples.append(perf_counter_ns() - start)
        assert sorted(ranking) == list(range(16))
    _, memory = _traced(lambda: session.rank_view(queries[0], "R"))
    return {"raw_ns": samples, "median_ns": float(np.median(samples)),
            "p95_ns": float(np.quantile(samples, .95, method="linear")),
            "one_lookup_tracemalloc": memory}


def collect(snapshot):
    path = Path(snapshot).resolve()
    initial_rss = _process_rss()
    start = perf_counter_ns()
    content = path.read_bytes()
    models = load_frozen(BytesIO(content))
    loaded = perf_counter_ns()
    session = models.session()
    initialized = perf_counter_ns()
    ready_rss = _process_rss()

    bank = models.banks
    indices = np.linspace(0, len(bank.view_keys) - 1, 32, dtype=np.intp)
    queries = bank.view_keys[indices]
    train_occupancy = len(session.views)
    regular = _retrieval(session, queries)
    for i in range(train_occupancy, session.views.capacity):
        row = i % train_occupancy
        session.views.append(bank.view_keys[row], bank.view_feedback[row])
    full = _retrieval(session, queries)

    resident = {
        "deployed_view_bank_bytes": _numpy_bytes(session.views),
        "deployed_action_bank_bytes": _numpy_bytes(session.actions),
        "deployed_models_and_retrieval_scale_bytes": _numpy_bytes(
            session, session.view_head, session.action_head),
        "snapshot_train_and_all_model_arrays_bytes": _numpy_bytes(
            bank, models.view_head, models.action_head, models.view_zero,
            models.view_shuffle, models.action_shuffle),
    }
    session.close()
    traced_models, load_memory = _traced(lambda: load_frozen(BytesIO(content)))
    traced_session, init_memory = _traced(traced_models.session)
    traced_session.close()
    pressure = capacity_check(models)
    return {
        "file_whitelist": [str(path)],
        "actual_reads": [{"path": str(path), "sha256": sha256(content).hexdigest(),
                          "bytes": len(content)}],
        "cold_process": {"read_and_unpack_snapshot_ns": loaded - start,
                         "initialize_session_from_snapshot_ns": initialized - loaded,
                         "unpack_from_memory_tracemalloc": load_memory,
                         "initialize_session_tracemalloc": init_memory},
        "process_memory": {"before_load": initial_rss, "session_ready": ready_rss,
                           "after_stress": _process_rss()},
        "resident_numpy": resident,
        "retrieval_query_train_indices": indices.tolist(),
        "retrieval_by_occupancy": {str(train_occupancy): regular,
                                   str(pressure["capacity"]): full},
        "capacity": pressure,
        "boundary": "Separate CPU-only process; lookups and capacity fill use train rows only. "
                    "Lookup latency excludes tracemalloc, sorting check and file output. "
                    "Tracemalloc includes Python and tracked NumPy allocations; "
                    "process RSS includes imports and all other process memory.",
        "numpy": np.__version__,
    }


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    result = collect(args.snapshot)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
