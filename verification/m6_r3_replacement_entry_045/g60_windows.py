"""Scoped Windows clocks for already-owned launcher and audited service PIDs."""
from __future__ import annotations

import ctypes
from ctypes import wintypes as W
from pathlib import Path
import time

K=ctypes.WinDLL("kernel32",use_last_error=True)
NOW=time.perf_counter_ns
INVALID_HANDLE=ctypes.c_void_p(-1).value
SURVIVAL_CLOCK="Windows GetProcessTimes FILETIME 100 ns UTC"
PARENT_CLOCK="parent_perf_counter_ns"
# Applies only to OS FILETIME publication versus the adjacent client timestamp.
OS_BRACKET_100NS=320_000
DRIFT_TOLERANCE_NS=2_000_000


def api(name,args,returns):
    f=getattr(K,name)
    f.argtypes=args
    f.restype=returns
    return f


OpenProcess=api("OpenProcess",[W.DWORD,W.BOOL,W.DWORD],W.HANDLE)
GetProcessId=api("GetProcessId",[W.HANDLE],W.DWORD)
CloseHandle=api("CloseHandle",[W.HANDLE],W.BOOL)
GetProcessTimes=api("GetProcessTimes",[W.HANDLE]+[ctypes.POINTER(W.FILETIME)]*4,W.BOOL)
GetExitCodeProcess=api("GetExitCodeProcess",[W.HANDLE,ctypes.POINTER(W.DWORD)],W.BOOL)
QueryFullProcessImageNameW=api("QueryFullProcessImageNameW",[W.HANDLE,W.DWORD,W.LPWSTR,ctypes.POINTER(W.DWORD)],W.BOOL)
WaitForSingleObject=api("WaitForSingleObject",[W.HANDLE,W.DWORD],W.DWORD)
GetSystemTimePreciseAsFileTime=api("GetSystemTimePreciseAsFileTime",[ctypes.POINTER(W.FILETIME)],None)
Snapshot=api("CreateToolhelp32Snapshot",[W.DWORD,W.DWORD],W.HANDLE)


class ProcessEntry(ctypes.Structure):
    _fields_=[("size",W.DWORD),("usage",W.DWORD),("pid",W.DWORD),("default_heap",ctypes.c_size_t),
              ("module",W.DWORD),("threads",W.DWORD),("parent_pid",W.DWORD),
              ("priority",W.LONG),("flags",W.DWORD),("exe",W.WCHAR*260)]


ProcessFirst=api("Process32FirstW",[W.HANDLE,ctypes.POINTER(ProcessEntry)],W.BOOL)
ProcessNext=api("Process32NextW",[W.HANDLE,ctypes.POINTER(ProcessEntry)],W.BOOL)


def check(ok):
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())


def ticks(ft):
    return (int(ft.dwHighDateTime)<<32) | int(ft.dwLowDateTime)


def mark(name):
    point=W.FILETIME()
    x=NOW()
    GetSystemTimePreciseAsFileTime(ctypes.byref(point))
    return {"name":name,"at_ns":x,"filetime_100ns":ticks(point),"filetime_observation_after_ns":NOW()}


def parent_of(pid):
    h=Snapshot(2,0)
    check(h not in (None,INVALID_HANDLE))
    try:
        row=ProcessEntry()
        row.size=ctypes.sizeof(row)
        ok=ProcessFirst(h,ctypes.byref(row))
        while ok:
            if row.pid==pid:
                return int(row.parent_pid)
            ok=ProcessNext(h,ctypes.byref(row))
        raise ValueError(f"Audited PID {pid} was absent from the process snapshot")
    finally:
        check(CloseHandle(h))


def get_times(handle):
    stamps=[W.FILETIME() for _ in range(4)]
    check(GetProcessTimes(handle,*map(ctypes.byref,stamps)))
    return dict(zip(("creation_time_100ns","exit_time_100ns","kernel_100ns","user_100ns"),map(ticks,stamps),strict=True))


class OwnedProcess:
    """Keep the same handle open from the live identity bind to the exit check."""

    def __init__(self,pid,parent,image):
        self.handle=OpenProcess(0x00100000|0x1000,False,pid)
        check(self.handle)
        try:
            assert GetProcessId(self.handle)==pid
            buffer=ctypes.create_unicode_buffer(2048)
            size=W.DWORD(len(buffer))
            check(QueryFullProcessImageNameW(self.handle,0,buffer,ctypes.byref(size)))
            assert Path(buffer.value).resolve()==Path(image).resolve(), buffer.value
            actual_parent=parent_of(pid)
            assert actual_parent==parent,(pid,actual_parent,parent)
            state=WaitForSingleObject(self.handle,0)
            assert state==258, (pid,state)
            self.binding={"pid":pid,"parent_pid":actual_parent,"image":buffer.value,
                          "alive_at_bind":True,"bind_times":get_times(self.handle)}
            assert self.binding["bind_times"]["exit_time_100ns"]==0
        except BaseException:
            self.release()
            raise

    def wait_zero(self):
        status=WaitForSingleObject(self.handle,0)
        assert status in (0,258)
        return status

    def final(self):
        begin=mark("observed_exit_begin")
        state=self.wait_zero()
        code=W.DWORD()
        check(GetExitCodeProcess(self.handle,ctypes.byref(code)))
        stats=get_times(self.handle)
        end=mark("observed_exit_end")
        assert stats["creation_time_100ns"]==self.binding["bind_times"]["creation_time_100ns"]
        return {**self.binding,**stats,"exit_code":code.value,"wait_result":state,
                "exit_observation":[begin,end],"owned_held_handle":True}

    def release(self):
        if self.handle:
            check(CloseHandle(self.handle))
            self.handle=None


def verify_clock(events,processes,controller_pid,exited_at_wrapper_wait):
    by_name={e["name"]:e for e in events}
    assert len(by_name)==len(events)
    paired=sorted((e for e in events if "filetime_100ns" in e),key=lambda row:row["at_ns"])
    assert all(a["at_ns"]<=a["filetime_observation_after_ns"] for a in paired)
    start,finish=by_name["client_begin"],by_name["client_end"]
    assert paired[0]["name"]=="client_begin" and paired[-1]["name"]=="client_end"
    for e in paired:
        elapsed=(e["filetime_100ns"]-start["filetime_100ns"])*100
        expected=e["at_ns"]-start["at_ns"]
        span=(e["filetime_observation_after_ns"]-e["at_ns"] +
              start["filetime_observation_after_ns"]-start["at_ns"])
        assert abs(elapsed-expected)<=DRIFT_TOLERANCE_NS+span,(e["name"],elapsed,expected)
    wrapper,service=processes["wrapper"],processes["service"]
    begin=by_name["popen_begin"]["filetime_100ns"]
    after=by_name["popen_end"]["filetime_100ns"]
    exit_deadline=finish["filetime_100ns"]
    created=wrapper["creation_time_100ns"]
    assert wrapper["parent_pid"]==controller_pid
    assert begin-OS_BRACKET_100NS<=created<=after+OS_BRACKET_100NS
    assert service["parent_pid"]==(wrapper["pid"] if service["pid"]!=wrapper["pid"] else controller_pid)
    assert created<=service["creation_time_100ns"]<=after+(
        by_name["handle_bind_end"]["filetime_100ns"]-after)+OS_BRACKET_100NS
    assert by_name["last_business_decode"]["filetime_100ns"]<=by_name["stdin_close_begin"]["filetime_100ns"] \
        if "last_business_decode" in by_name else True
    assert all(p["exit_code"]==0 and p["wait_result"]==0 and p["owned_held_handle"] for p in processes.values())
    assert all(p["creation_time_100ns"]<p["exit_time_100ns"]<=exit_deadline+OS_BRACKET_100NS for p in processes.values())
    assert exited_at_wrapper_wait["wrapper"]==0
    archive=by_name["archive_begin"]["filetime_100ns"]
    if exited_at_wrapper_wait["service"]==0:
        assert max(p["exit_time_100ns"] for p in processes.values())<=archive+OS_BRACKET_100NS
    return (max(p["exit_time_100ns"] for p in processes.values())-created)*100
