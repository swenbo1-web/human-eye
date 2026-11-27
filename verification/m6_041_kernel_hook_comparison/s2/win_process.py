"""Invoke one Hook command under an owned Windows Job, using ordinary binary pipes."""
import _winapi
import importlib.util
import msvcrt
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from time import perf_counter_ns, sleep

ARCHIVE = Path("C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_independent_pair_dual_spawn_039/job.py")


def load_job():
    sys.path.insert(0, str(ARCHIVE.parent))
    try:
        spec = importlib.util.spec_from_file_location("m6_041_job_api", ARCHIVE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


def invoke(argv, payload, cwd, *, timeout_s, cancellation_s=None):
    """The sample ends after the command, all Job children and pipe collection."""
    api = load_job()
    app = shutil.which(argv[0])
    assert app is not None
    t0 = perf_counter_ns()
    job = api.Job()
    handles = set()
    child_process = thread = None
    child_links = []
    calls = []
    owned = False
    memory_samples = []
    errors = []
    stdout, stderr = bytearray(), bytearray()
    terminal, error = "completed", None
    end_observed = None

    def detach(raw):
        handles.remove(raw)
        return raw

    def release(raw):
        _winapi.CloseHandle(raw)
        handles.discard(raw)

    def pipe(input_to_child):
        recv, send = _winapi.CreatePipe(None, 0)
        handles.update((recv, send))
        child, parent = (recv, send) if input_to_child else (send, recv)
        os.set_handle_inheritable(child, True)
        child_links.append(child)
        return parent

    def stream_read(handle, output):
        try:
            fd = msvcrt.open_osfhandle(handle, os.O_BINARY | os.O_RDONLY)
            with os.fdopen(fd, "rb") as stream:
                output.extend(stream.read())
        except OSError as exc:
            errors.append(type(exc).__name__ + ":" + str(exc))

    def stream_write(handle):
        try:
            fd = msvcrt.open_osfhandle(handle, os.O_BINARY | os.O_WRONLY)
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
        except BrokenPipeError:
            if terminal == "completed":
                errors.append("stdin_closed_early")
        except OSError as exc:
            errors.append(type(exc).__name__ + ":" + str(exc))

    try:
        stdin, out, err = (pipe(i) for i in (True, False, False))
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESTDHANDLES
        startup.hStdInput, startup.hStdOutput, startup.hStdError = child_links
        startup.lpAttributeList = {"handle_list": list(child_links)}
        env = os.environ.copy()
        child_process, thread, pid, _ = _winapi.CreateProcess(
            app, subprocess.list2cmdline(argv), None, None, True,
            0x00000004 | subprocess.CREATE_NO_WINDOW, env, str(cwd), startup,
        )
        api.checked(api.assign(job.handle, int(child_process)))
        owned = True
        if api.resume(int(thread)) == 0xffffffff:
            raise OSError("ResumeThread failed")
        release(thread)
        thread = None
        for raw in child_links:
            release(raw)
        for target, args in ((stream_read, (detach(out), stdout)),
                             (stream_read, (detach(err), stderr)), (stream_write, (detach(stdin),))):
            worker = threading.Thread(target=target, args=args, daemon=True)
            worker.start()
            calls.append(worker)
        deadline = t0 + int(timeout_s * 1_000_000_000)
        cancel = None if cancellation_s is None else t0 + int(cancellation_s * 1_000_000_000)
        next_sample = t0
        while job.accounting()["active_processes"]:
            now = perf_counter_ns()
            if cancel is not None and now >= cancel:
                terminal = "cancelled_by_harness"
                break
            if now >= deadline:
                terminal = "expired_in_harness"
                break
            if now >= next_sample:
                memory_samples.append(job.sample())
                next_sample = now + 20_000_000
            sleep(.005)
    except Exception as exc:
        terminal, error = "harness_error", type(exc).__name__ + ":" + str(exc)
    finally:
        for raw in tuple(handles):
            release(raw)
        if thread is not None:
            release(thread)
        if child_process is not None:
            if not owned:
                _winapi.TerminateProcess(child_process, 126)
                _winapi.WaitForSingleObject(child_process, 5_000)
            elif job.accounting()["active_processes"] and terminal != "completed":
                job.kill()
        cleanup_limit = perf_counter_ns() + 5_000_000_000
        while job.accounting()["active_processes"] and perf_counter_ns() < cleanup_limit:
            sleep(.005)
        active = job.accounting()
        last_owners = job.pids()
        for call in calls:
            call.join(max(0, cleanup_limit - perf_counter_ns()) / 1e9)
        reader_joined = len(calls) == 3 and all(not call.is_alive() for call in calls)
        code = None if child_process is None else _winapi.GetExitCodeProcess(child_process)
        if child_process is not None:
            release(child_process)
        job.close()
        end_observed = perf_counter_ns()
    valid_samples = [row for row in memory_samples if row["group_working_bytes"] is not None]
    return {
        "resolved_executable": app, "terminal": terminal, "error": error,
        "T_ns": end_observed - t0, "returncode": code,
        "job_accounting": active, "job_pids_at_cleanup": last_owners,
        "pipe_threads_joined": reader_joined, "pipe_errors": errors,
        "samples": memory_samples,
        "sampled_peak_working_set_bytes": max((row["group_working_bytes"] for row in valid_samples), default=None),
        "sampled_peak_private_bytes": max((row["group_private_bytes"] for row in valid_samples), default=None),
    }, bytes(stdout), bytes(stderr)