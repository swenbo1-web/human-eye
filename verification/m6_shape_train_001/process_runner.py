"""Outer process wall/CPU/working-set ledger for this isolated research batch."""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import subprocess
import time


HERE = Path(__file__).resolve().parent


def process_metrics(handle):
    class MemoryCounters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
            "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage", "PrivateUsage")]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    times = [wintypes.FILETIME() for _ in range(4)]
    cpu = None
    if kernel.GetProcessTimes(handle, *[ctypes.byref(value) for value in times]):
        cpu = sum((value.dwHighDateTime << 32) + value.dwLowDateTime for value in times[2:]) / 10_000_000
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(MemoryCounters), wintypes.DWORD]
    memory = MemoryCounters()
    memory.cb = ctypes.sizeof(memory)
    valid = psapi.GetProcessMemoryInfo(handle, ctypes.byref(memory), memory.cb)
    return {"cpu_s": cpu, "peak_working_set_bytes": int(memory.PeakWorkingSetSize) if valid else None,
            "working_set_bytes": int(memory.WorkingSetSize) if valid else None}


def descendants(root_pid):
    class Entry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", wintypes.WCHAR * 260)]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    entry = Entry(); entry.dwSize = ctypes.sizeof(entry)
    parents = {}
    present = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
    while present:
        parents[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
        present = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    kernel.CloseHandle(snapshot)
    family = {root_pid}
    for _ in range(8):
        children = {pid for pid, parent in parents.items() if parent in family}
        if children.issubset(family):
            break
        family.update(children)
    return family


def run(command, label, timeout_s=3600, rss_limit_bytes=None):
    folder = HERE / "private/processes"
    folder.mkdir(parents=True, exist_ok=True)
    ledger = folder / (label + ".json")
    if ledger.exists():
        raise RuntimeError("process_label_already_exists_" + label)
    started = time.perf_counter()
    record = {"label": label, "command": [str(value) for value in command], "status": "running",
              "stdout": str(folder / (label + ".stdout.log")), "stderr": str(folder / (label + ".stderr.log"))}
    ledger.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
    peak, samples = 0, 0
    handles = {}
    lifetime_peaks = {}
    tree_sampled_peak = 0
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    with Path(record["stdout"]).open("wb") as stdout, Path(record["stderr"]).open("wb") as stderr:
        with subprocess.Popen(command, cwd=HERE.parents[1], stdout=stdout, stderr=stderr,
                              creationflags=subprocess.CREATE_NO_WINDOW) as process:
            record["pid"] = process.pid
            handles[process.pid] = int(process._handle)
            while process.poll() is None:
                for pid in descendants(process.pid) - handles.keys():
                    handle = kernel.OpenProcess(0x411, False, pid)
                    if handle:
                        handles[pid] = handle
                metrics = process_metrics(int(process._handle))
                samples += 1
                peak = max(peak, metrics["peak_working_set_bytes"] or 0)
                current = 0
                for pid, handle in handles.items():
                    item = process_metrics(handle)
                    lifetime_peaks[pid] = max(lifetime_peaks.get(pid, 0), item["peak_working_set_bytes"] or 0)
                    current += item["working_set_bytes"] or 0
                tree_sampled_peak = max(tree_sampled_peak, current)
                if time.perf_counter() - started > timeout_s:
                    record["status"] = "timeout"
                    for pid, handle in handles.items():
                        if pid != process.pid:
                            kernel.TerminateProcess(wintypes.HANDLE(handle), 42)
                    process.kill()
                    break
                if rss_limit_bytes is not None and tree_sampled_peak > rss_limit_bytes:
                    record["status"] = "memory_budget_exceeded"
                    for pid, handle in handles.items():
                        if pid != process.pid:
                            kernel.TerminateProcess(wintypes.HANDLE(handle), 42)
                    process.kill()
                    break
                time.sleep(.05)
            process.wait()
            final = process_metrics(int(process._handle))
            peak = max(peak, final["peak_working_set_bytes"] or 0)
            record.update(returncode=process.returncode, full_process_cpu_s=final["cpu_s"],
                          full_process_wall_s=time.perf_counter() - started, peak_working_set_bytes=peak or None,
                          memory_samples=samples, final_memory_query=final)
            record["process_tree"] = [{"pid": pid, **process_metrics(handle), "observed_lifetime_peak_bytes": lifetime_peaks.get(pid)} for pid, handle in handles.items()]
            record["tree_cpu_s"] = sum(item["cpu_s"] or 0 for item in record["process_tree"])
            record["tree_sampled_peak_working_set_bytes"] = tree_sampled_peak
            for pid, handle in handles.items():
                if pid != process.pid:
                    kernel.CloseHandle(handle)
    if record["status"] == "running":
        record["status"] = "completed" if record["returncode"] == 0 else "failed"
    record["memory_scope"] = "max Windows process-lifetime PeakWorkingSetSize sampled every50ms and after exit; child process only"
    record["tree_scope"] = "Windows venv launcher descendants discovered by Toolhelp every50ms, handles retained for final CPU; brief undiscovered descendants remain unmeasured"
    ledger.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({key: record[key] for key in ("label", "status", "returncode", "full_process_wall_s", "full_process_cpu_s", "peak_working_set_bytes")}), flush=True)
    return record
