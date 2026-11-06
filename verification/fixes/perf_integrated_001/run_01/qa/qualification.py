"""One fixed four-session entry qualification, using installed trial adapters.

Run only after installation, regressions, actual asset build and truth freeze.
Every request is issued once. A failed or unknown prefix stops the sequence.
"""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import sysconfig
import threading
import time

from verification import visual004_native as native
from verification.visual004_session import client, load_broker_ready


SNAPSHOT_CODE = r'''
import json as _qa_json
import os as _qa_os
_qa_namespace_count = globals().get('_qa_namespace_count', 0) + 1
_qa_rows = []
for _qa_obj in sorted(bpy.data.objects, key=lambda item: item.name):
    if _qa_obj.type != 'MESH':
        raise ValueError('Qualification fixture has a non-mesh object')
    _qa_matrix = [[float(value) for value in row] for row in _qa_obj.matrix_world]
    _qa_points = [[float(value) for value in vertex.co] for vertex in _qa_obj.data.vertices]
    _qa_world = [[sum(_qa_matrix[axis][k] * point[k] for k in range(3))
                  + _qa_matrix[axis][3] for axis in range(3)] for point in _qa_points]
    _qa_rows.append(dict(name=_qa_obj.name, vertices_local=_qa_points,
                        matrix_world=_qa_matrix, world_vertices=_qa_world,
                        faces=[list(face.vertices) for face in _qa_obj.data.polygons]))
print(_qa_json.dumps(dict(snapshot=dict(schema='perf-integrated-001-mesh-readback-v1',
    case=_qa_case, state=_qa_state,
    unit_scale_m=float(bpy.context.scene.unit_settings.scale_length), objects=_qa_rows),
    namespace_count=_qa_namespace_count, worker_pid=_qa_os.getpid()), allow_nan=False))
'''


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def require(value, reason):
    if not value:
        raise ValueError(reason)


def matching(actual, expected, path="snapshot"):
    """Compare actual readback with the frozen author readback, without solving."""
    if type(expected) is dict:
        require(type(actual) is dict and set(actual) == set(expected), path + " fields")
        for key, value in expected.items():
            matching(actual[key], value, path + "." + key)
    elif type(expected) is list:
        require(type(actual) is list and len(actual) == len(expected), path + " length")
        for index, value in enumerate(expected):
            matching(actual[index], value, path + "[" + str(index) + "]")
    elif type(expected) is float:
        require(type(actual) in (float, int) and math.isfinite(actual)
                and abs(actual - expected) <= 1e-7, path + " coordinate")
    else:
        require(type(actual) is type(expected) and actual == expected, path + " value")


def windows_process_handle(pid):
    require(os.name == "nt", "This qualification uses the fixed Windows runtime")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel.WaitForSingleObject.restype = ctypes.c_uint32
    kernel.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x00100000 | 0x1000 | 0x0001, False, pid)
    require(handle, "Cannot pin the observed worker process handle")
    return kernel, handle


def parse_task(reply, pin, candidate, expected):
    require(reply.get("ok") is True and reply.get("operation_succeeded") is True,
            "Product broker operation failed")
    result = reply["result"]
    require(not result.get("mcp_is_error") and result.get("rpc_error") is None,
            "Product MCP returned an error")
    require(len(result.get("mcp_text", [])) == 1 and not result.get("image_refs"),
            "Expected exactly one numeric task payload")
    payload = json.loads(result["mcp_text"][0])
    require(payload.get("result_kind") == "task_query"
            and payload.get("schema_version") == "task-query-v2"
            and payload.get("unit") == "m"
            and payload.get("execution_authority") is False, "Task payload contract")
    binding = payload["binding"]
    require(binding.get("source_sha256") == pin, "Installed product source binding")
    require([row.get("name") for row in binding["objects"]] == ["Object_01", candidate],
            "Actual selected pair names/order")
    require(binding.get("scene_fingerprint") and binding.get("scene_revision"),
            "Current task binding is missing")
    facts = payload["facts"]
    require(set(facts) == {"surface_clearance", "solid_relation"}, "Task fact set")
    clearance, relation = facts["surface_clearance"], facts["solid_relation"]
    if relation["status"] == "unknown":
        require(expected["case"] == "assembly"
                and relation.get("reason") == "unsupported_solid_geometry"
                and clearance.get("status") == "unknown"
                and clearance.get("reason") == "unsupported_solid_geometry",
                "Unexpected unknown/rejection reason")
    else:
        penetrating = expected["truth"]["relation"] == "penetrating"
        require(relation["status"] == "measured"
                and relation.get("value") == ("penetrating" if penetrating else "not_penetrating"),
                "Product solid relation disagrees with the independent truth")
        require(clearance["status"] == "measured"
                and type(clearance.get("value")) in (float, int)
                and math.isfinite(clearance["value"]), "Product scalar missing")
        if penetrating:
            require(clearance["value"] <= 0, "Penetration scalar has a positive sign")
            if expected["case"] == "control":
                require(abs(clearance["value"] + .005) <= 1e-6, "Control penetration scalar")
        else:
            require(abs(clearance["value"] - expected["truth"]["minimum_gap_m"]) <= 1e-6,
                    "Product separation scalar disagrees with independent truth")
    return payload


def qualify_session(args, case, condition, counts):
    run_root = args.run_root
    parent = run_root / "qualification" / case
    parent.mkdir(parents=True, exist_ok=True)
    workspace = parent / condition
    require(not workspace.exists(), "Qualification workspace already exists")
    author = run_root / "author" / case
    asset = author / "scene.blend"
    patch = author / "qa_patch.json"
    snapshots = native.load(author / "author_mesh_snapshots.json")
    truth = native.load(author / "TRUTH.json")
    asset_sha = native.sha(asset)
    purelib = Path(sysconfig.get_path("purelib")).resolve()
    launcher = purelib / "verification" / "perf010_qualification.py"
    require(Path(native.__file__).resolve().is_relative_to(purelib), "QA imported outside installed purelib")
    command = [sys.executable, "-I", "-B", str(launcher), "--asset", str(asset),
               "--workspace", str(workspace), "--blender", str(args.blender),
               "--condition", condition, "--pin", args.pin,
               "--expected-asset-sha256", asset_sha, "--seconds", "120",
               "--qa-vertex-patch", str(patch)]
    started = time.perf_counter_ns()
    deadline = min(time.monotonic() + 120, time.monotonic() + args.deadline_unix - time.time())
    require(deadline > time.monotonic(), "Global deadline before qualification launch")
    record = dict(case=case, condition=condition, argv=command, started_utc=utc_now(),
                  started_ns=started, asset_sha256=asset_sha, patch_sha256=native.sha(patch),
                  qualification_source_sha256=native.sha(__file__), states=[], cleanup={}, passed=False)
    process = None
    timer = None
    worker_kernel = None
    worker_handle = None
    force_events = []
    error = None

    def stop_owned_tree():
        event = dict(at_utc=utc_now(), reason="qualification_outer_deadline_or_cleanup")
        if process is not None and process.poll() is None:
            killed = subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                    capture_output=True, text=True, timeout=8,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            event.update(launcher_pid=process.pid, taskkill_returncode=killed.returncode,
                         stdout=killed.stdout, stderr=killed.stderr)
        if worker_handle and worker_kernel.WaitForSingleObject(worker_handle, 0) == 258:
            event["worker_terminate_called"] = bool(worker_kernel.TerminateProcess(worker_handle, 124))
        force_events.append(event)

    def check_time():
        require(time.monotonic() < deadline and not force_events, "Qualification outer deadline")

    def request(operation, arguments, request_id):
        check_time()
        request_value = dict(request_id=request_id, operation=operation, args=arguments)
        folder = workspace / "qualification_calls" / request_id
        folder.mkdir(parents=True, exist_ok=False)
        native.save(folder / "REQUEST.json", request_value)
        key = "native" if operation == "native_run" else "observe"
        counts[key + "_started"] += 1
        call_started = time.perf_counter_ns()
        try:
            reply = client(workspace, request_value)
            counts[key + "_responses"] += 1
            native.save(folder / "REPLY.json", reply)
            check_time()
            return reply
        finally:
            native.save(folder / "TIMING.json", dict(started_ns=call_started,
                        elapsed_ns=time.perf_counter_ns() - call_started))

    try:
        with (parent / (condition + ".stdout.log")).open("xb") as stdout, \
             (parent / (condition + ".stderr.log")).open("xb") as stderr:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                       cwd=str(run_root),
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        record["launcher_pid"] = process.pid
        timer = threading.Timer(max(.001, deadline - time.monotonic()), stop_owned_tree)
        timer.daemon = True
        timer.start()
        while not (workspace / "BROKER_READY.json").exists():
            check_time()
            require(process.poll() is None, "Qualification launcher exited before ready")
            time.sleep(.02)
        ready = load_broker_ready(workspace)
        record["ready"] = ready
        record["startup_ns_from_before_binding"] = time.perf_counter_ns() - started
        worker_kernel, worker_handle = windows_process_handle(ready["worker_pid"])
        record["worker_handle_pinned"] = True
        payloads = {}
        for index, (stage, snapshot_state, truth_state) in enumerate((
                ("initial", "initial", "initial"),
                ("unchanged_current", "initial", "unchanged"),
                ("changed_current", "changed", "changed"))):
            check_time()
            if stage == "changed_current":
                counts["qa_started"] += 1
                receipt = native.NativeSession.open(workspace).qa_advance(
                    timeout_s=min(30, max(.001, deadline - time.monotonic())))
                counts["qa_responses"] += 1
                native.save(workspace / "QUALIFICATION_QA_RECEIPT.json", receipt)
                check_time()
            code = "_qa_case = " + repr(case) + "\n_qa_state = " + repr(snapshot_state) + "\n" + SNAPSHOT_CODE
            reply = request("native_run", dict(code=code, timeout_s=min(30, deadline - time.monotonic())),
                            stage + "_native")
            require(reply.get("ok") is True and reply.get("operation_succeeded") is True,
                    "Native broker operation failed")
            require(reply["result"].get("script_error") is None, "Native snapshot script failed")
            readback = json.loads(reply["result"]["stdout"])
            require(readback["namespace_count"] == index + 1
                    and readback["worker_pid"] == ready["worker_pid"], "Worker/namespace continuity")
            matching(readback["snapshot"], snapshots[snapshot_state])
            stage_record = dict(stage=stage, native_snapshot_equal=True,
                                worker_pid=readback["worker_pid"], namespace_count=index + 1,
                                product_pairs=[])
            record["states"].append(stage_record)
            if condition == "P":
                for candidate, expected_truth in truth["states"][truth_state]["probes"].items():
                    query = dict(mode="task", objects=[dict(name="Object_01"), dict(name=candidate)],
                                 requested_facts=["surface_clearance", "solid_relation"])
                    arguments = dict(include_image=False, query=query, response_detail="brief")
                    reply = request("observe", dict(arguments=arguments), stage + "_" + candidate)
                    payload = parse_task(reply, args.pin, candidate,
                                         dict(case=case, truth=expected_truth))
                    if stage == "unchanged_current":
                        require(payload["facts"] == payloads[candidate]["facts"]
                                and payload["binding"]["scene_fingerprint"] ==
                                payloads[candidate]["binding"]["scene_fingerprint"],
                                "Unchanged product facts/current fingerprint changed")
                    if stage == "changed_current":
                        require(payload["binding"]["scene_fingerprint"] !=
                                payloads[candidate]["binding"]["scene_fingerprint"],
                                "Changed target reused an old product fingerprint")
                    payloads[candidate] = payload
                    stage_record["product_pairs"].append(dict(candidate=candidate,
                        facts=payload["facts"], binding=payload["binding"]))
            require(native.sha(asset) == asset_sha, "Source asset changed")
        record["passed"] = True
    except BaseException as exc:
        error = dict(type=type(exc).__name__, message=str(exc))
        record["error"] = error
    finally:
        cleanup = record["cleanup"]
        if (workspace / "BROKER_READY.json").exists() and process is not None and process.poll() is None:
            try:
                cleanup["close_reply"] = client(workspace, dict(
                    request_id="qualification-close", operation="close", args={}))
            except BaseException as exc:
                cleanup["close_error"] = dict(type=type(exc).__name__, message=str(exc))
        if process is not None:
            try:
                process.wait(timeout=max(.001, min(5, deadline - time.monotonic())))
            except subprocess.TimeoutExpired:
                stop_owned_tree()
                process.wait(timeout=8)
            cleanup["launcher_exit_code"] = process.returncode
            cleanup["launcher_reaped"] = process.poll() is not None
        if timer is not None:
            timer.cancel()
            timer.join(timeout=9)
            cleanup["watchdog_joined"] = not timer.is_alive()
        if worker_handle:
            state = worker_kernel.WaitForSingleObject(worker_handle, 0)
            if state == 258:
                stop_owned_tree()
                state = worker_kernel.WaitForSingleObject(worker_handle, 5000)
            code = ctypes.c_uint32()
            cleanup["worker_exit_observed"] = state == 0
            cleanup["worker_exit_code"] = (code.value if worker_kernel.GetExitCodeProcess(
                worker_handle, ctypes.byref(code)) else None)
            worker_kernel.CloseHandle(worker_handle)
        cleanup["forced_events"] = force_events
        cleanup["closed_receipt"] = (native.load(workspace / "WORKER_CLOSED.json")
                                     if (workspace / "WORKER_CLOSED.json").exists() else None)
        record["ended_utc"] = utc_now()
        record["launch_to_cleanup_ns"] = time.perf_counter_ns() - started
        if not cleanup.get("launcher_reaped") or not cleanup.get("worker_exit_observed") or force_events:
            record["passed"] = False
            record.setdefault("error", dict(type="CleanupOrDeadlineFailure", message="Qualification cleanup/cap failed"))
        native.save(parent / (condition + ".QUALIFICATION.json"), record)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--pin", required=True)
    parser.add_argument("--deadline-unix", type=float, required=True)
    args = parser.parse_args()
    args.run_root = args.run_root.resolve()
    require(args.run_root.name == "run_01" and args.run_root.is_dir(), "Fixed existing run_01 required")
    output = args.run_root / "qualification"
    output.mkdir(exist_ok=False)
    counts = dict(native_started=0, native_responses=0, observe_started=0,
                  observe_responses=0, qa_started=0, qa_responses=0)
    result = dict(schema="perf-integrated-001-qualification-v1", started_utc=utc_now(),
                  counts=counts, sessions=[], completed=False, passed=False, model_answers=0)
    try:
        for case, condition in (("control", "N"), ("control", "P"),
                                ("assembly", "P"), ("assembly", "N")):
            session = qualify_session(args, case, condition, counts)
            result["sessions"].append(dict(case=case, condition=condition, passed=session["passed"]))
            require(session["passed"], "Qualification failed; fixed prefix retained without retry")
        require(counts == dict(native_started=12, native_responses=12, observe_started=12,
                               observe_responses=12, qa_started=4, qa_responses=4), "Fixed qualification denominator")
        result.update(completed=True, passed=True)
    except BaseException as exc:
        result["error"] = dict(type=type(exc).__name__, message=str(exc))
    finally:
        result["ended_utc"] = utc_now()
        native.save(output / "STATUS.json", result)
    print(json.dumps(result, allow_nan=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
