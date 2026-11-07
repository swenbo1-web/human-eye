"""Bounded owner for one persistent consumer chain using existing adapters."""
import argparse
import ctypes
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import sysconfig
import threading
import time

from verification import visual004_native as native
from verification.visual004_session import client, load_broker_ready


def now():
    return datetime.now(timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--reuse-root", type=Path, required=True)
    parser.add_argument("--case", choices=("control", "assembly"), required=True)
    parser.add_argument("--condition", choices=("N", "P"), required=True)
    parser.add_argument("--deadline-unix", type=float, required=True)
    parser.add_argument("--started-unix", type=float, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    folder = root / "chains" / (args.case + "_" + args.condition)
    folder.mkdir(parents=True, exist_ok=False)
    workspace = root / "runs" / args.case / args.condition
    workspace.parent.mkdir(parents=True, exist_ok=True)
    author = args.reuse_root / "author" / args.case
    started = args.started_unix
    deadline = min(started + 600, args.deadline_unix)
    if args.deadline_unix - started < 600:
        raise ValueError('Full equal 600 second chain budget required')
    seconds = 600
    if seconds <= 0:
        raise ValueError("No remaining chain budget")
    launcher = Path(sysconfig.get_path("purelib")) / "verification/perf010_qualification.py"
    command = [sys.executable, "-I", "-B", str(launcher), "--asset", str(author / "scene.blend"),
               "--workspace", str(workspace), "--blender", "D:/Tools/blender5.2/blender.exe",
               "--condition", args.condition, "--pin",
               "b0b4e1d3fa96a0b9c9676863fc7565215f82557a2936f247a5a4abd5b911103a",
               "--expected-asset-sha256", native.sha(author / "scene.blend"),
               "--seconds", str(seconds), "--qa-vertex-patch", str(author / "qa_patch.json")]
    record = dict(owner_entered_utc=now(), started_unix=started, deadline_unix=deadline,
                  argv=command, workspace=str(workspace), case=args.case, condition=args.condition,
                  status="starting", advance_attempted=False, forced_cleanup=[], model_answers=[])
    native.save(folder / "START.json", record)
    process = None
    worker_handle = None
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
    kernel.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]

    def force_stop():
        event = dict(utc=now(), reason="outer_chain_or_global_deadline")
        if process is not None and process.poll() is None:
            reply = subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                   capture_output=True, text=True, timeout=8,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
            event.update(taskkill_exit=reply.returncode, stdout=reply.stdout, stderr=reply.stderr)
        if worker_handle and kernel.WaitForSingleObject(worker_handle, 0) == 258:
            event["worker_terminate"] = bool(kernel.TerminateProcess(worker_handle, 124))
        record["forced_cleanup"].append(event)

    timer = threading.Timer(max(.001, deadline - time.time()), force_stop)
    timer.daemon = True
    try:
        with (folder / "stdout.log").open("xb") as out, (folder / "stderr.log").open("xb") as err:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                       cwd=str(root), creationflags=subprocess.CREATE_NO_WINDOW)
        record["launcher_pid"] = process.pid
        timer.start()
        while not (workspace / "BROKER_READY.json").exists():
            if process.poll() is not None or time.time() >= deadline:
                raise RuntimeError("Chain launcher failed before readiness")
            time.sleep(.02)
        ready = load_broker_ready(workspace)
        worker_handle = kernel.OpenProcess(0x00100000 | 0x1000 | 0x0001, False, ready["worker_pid"])
        if not worker_handle:
            raise RuntimeError("Cannot retain actual worker handle")
        record.update(status="ready", ready=ready, startup_seconds=time.time() - started)
        native.save(folder / "READY.json", record)
        while process.poll() is None and time.time() < deadline:
            if (folder / "CLOSE").exists():
                break
            if (folder / "ADVANCE").exists() and not record["advance_attempted"]:
                record["advance_attempted"] = True
                native.save(folder / "ADVANCE_ATTEMPT.json", dict(utc=now()))
                receipt = native.NativeSession.open(workspace).qa_advance(
                    timeout_s=min(30, max(.001, deadline - time.time())))
                native.save(folder / "ADVANCE_RECEIPT.json", receipt)
            time.sleep(.05)
        if time.time() >= deadline:
            raise TimeoutError("Chain outer deadline")
        record["status"] = "closed"
    except BaseException as exc:
        record.update(status="failed", error=dict(type=type(exc).__name__, message=str(exc)))
    finally:
        if process is not None and process.poll() is None:
            try:
                record["close_reply"] = client(workspace, dict(
                    request_id="owner-close", operation="close", args={}))
            except BaseException as exc:
                record["close_error"] = dict(type=type(exc).__name__, message=str(exc))
            try:
                process.wait(timeout=max(.001, min(5, deadline - time.time())))
            except subprocess.TimeoutExpired:
                force_stop()
                process.wait(timeout=8)
        timer.cancel()
        if timer.ident is not None:
            timer.join(timeout=9)
        record["watchdog_joined"] = not timer.is_alive()
        record["launcher_exit_code"] = None if process is None else process.poll()
        if worker_handle:
            state = kernel.WaitForSingleObject(worker_handle, 0)
            if state == 258:
                force_stop()
                state = kernel.WaitForSingleObject(worker_handle, 5000)
            code = ctypes.c_uint32()
            record["worker_exited"] = state == 0
            record["worker_exit_code"] = code.value if kernel.GetExitCodeProcess(worker_handle, ctypes.byref(code)) else None
            kernel.CloseHandle(worker_handle)
        record.update(ended_utc=now(), launch_to_reap_seconds=time.time() - started)
        native.save(folder / "FINAL.json", record)
    return 0 if record["status"] == "closed" and not record["forced_cleanup"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
