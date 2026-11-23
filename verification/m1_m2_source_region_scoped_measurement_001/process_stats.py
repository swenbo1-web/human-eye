"""Sample CPU and working set of the actual held child handles on Windows."""

import ctypes
from ctypes import wintypes
from time import perf_counter_ns


class Counters(ctypes.Structure):
    _fields_ = [('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)] + [
        (name,ctypes.c_size_t) for name in ('PeakWorkingSetSize','WorkingSetSize',
            'QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage',
            'QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]


kernel = ctypes.WinDLL('kernel32',use_last_error=True)
kernel.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
kernel.K32GetProcessMemoryInfo.restype = wintypes.BOOL
kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)]*4)]
kernel.GetProcessTimes.restype = wintypes.BOOL


def sample(process):
    begin=perf_counter_ns()
    times=[wintypes.FILETIME() for _ in range(4)]
    memory=Counters()
    memory.cb=ctypes.sizeof(memory)
    handle=int(process._handle)
    if (not kernel.GetProcessTimes(handle,*map(ctypes.byref,times))
            or not kernel.K32GetProcessMemoryInfo(handle,ctypes.byref(memory),memory.cb)):
        raise ctypes.WinError(ctypes.get_last_error())
    cpu=[((t.dwHighDateTime<<32)|t.dwLowDateTime)*100 for t in times[2:]]
    return {'pid':process.pid,'sampled_ns':begin,'kernel_cpu_ns':cpu[0],'user_cpu_ns':cpu[1],
            'working_set_bytes':memory.WorkingSetSize,'working_set_lifetime_peak_bytes':memory.PeakWorkingSetSize}


def slot_samples(slot):
    return {'Blender':sample(slot.runtime.native.process),'engine':sample(slot.client.process)}
