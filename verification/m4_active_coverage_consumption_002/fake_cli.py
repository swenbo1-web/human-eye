"""Two local tool calls proving error recovery through the real stdio chain.

The fixture emits CLI-shaped events and waits for the controller's live runtime
binding before closing its held thin-client stdin normally. Both groups use
exactly this path. Importing this file starts nothing.
"""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import tomllib
import traceback
import uuid


HERE = Path(__file__).resolve().parent
MAX_FRAME = 24 * 1024 * 1024
LOCAL_ERROR_MESSAGE = "newlocal_m4_active_coverage_consumption_002_value_error"
LOCAL_CALLS = (
    ("execute_python", {"code": "raise ValueError('" + LOCAL_ERROR_MESSAGE + "')"}),
    ("execute_python", {"code": "print(6 * 7)"}),
)


def emit(value):
    print(json.dumps(value, ensure_ascii=False, allow_nan=False), flush=True)


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8")


def remaining_seconds(deadline_ns, maximum):
    remaining = (deadline_ns - time.perf_counter_ns()) / 1e9
    if remaining <= 0:
        raise TimeoutError("original_local_route_deadline")
    return min(remaining, maximum)


def main():
    args = sys.argv[1:]
    config = None
    for position, value in enumerate(args[:-1]):
        if value == "-c" and args[position + 1].startswith("mcp_servers.arm_engine="):
            config = tomllib.loads("value=" + args[position + 1].split("=", 1)[1])["value"]
    if config is None:
        raise ValueError("actual_MCP_config_missing")
    final_path = Path(args[args.index("-o") + 1])
    binding_path = final_path.parent / "RUNTIME_BINDING.json"
    endpoint_path = Path(config["args"][config["args"].index("--endpoint") + 1])
    endpoint = json.loads(endpoint_path.read_bytes())
    deadline_ns = endpoint["chain_deadline_ns"]
    if type(deadline_ns) is not int:
        raise ValueError("actual_original_route_deadline_missing")
    remaining_seconds(deadline_ns, 450)
    # The supplied common prompt is consumed as stdin data. Only the two new
    # literal LOCAL_CALLS above are submitted as ordinary Python tool inputs.
    sys.stdin.buffer.read()
    specification = importlib.util.spec_from_file_location(
        "_local_fixture_original_handles", HERE.parent / "m4_active_coverage_003/launch.py")
    launch = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(launch)
    process = None
    sequence = 0
    record = {"schema": "active-coverage-consumption-002-local-fixture-v1", "pid": os.getpid(),
        "started_ns": time.perf_counter_ns(), "original_deadline_ns": deadline_ns,
        "commands": [config["command"], *config["args"]], "RPC": [], "tool_results": [],
        "normal_EOF_requested": False, "normal_exit_observed": False,
        "runtime_binding_confirmed": False, "thin_cleanup": None, "error": None,
        "new_model_provider_render_image_Blender_calls": 0}

    def rpc(method, params):
        nonlocal sequence
        remaining_seconds(deadline_ns, 450)
        sequence += 1
        request = {"jsonrpc": "2.0", "id": sequence, "method": method, "params": params}
        raw_request = (json.dumps(request, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
        process.stdin.write(raw_request)
        process.stdin.flush()
        raw_response = process.stdout.readline(MAX_FRAME + 1)
        if not raw_response or len(raw_response) > MAX_FRAME:
            raise ValueError("actual_stdio_response_missing_or_oversized")
        response = json.loads(raw_response)
        record["RPC"].append({"request": request, "response": response,
                               "request_bytes": len(raw_request), "response_bytes": len(raw_response),
                               "received_ns": time.perf_counter_ns()})
        if type(response.get("id")) is not int or response["id"] != sequence or "error" in response:
            raise ValueError("actual_stdio_rpc_receipt")
        remaining_seconds(deadline_ns, 450)
        return response["result"]

    try:
        process = subprocess.Popen([config["command"], *config["args"]], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        record["thin_pid"] = process.pid
        rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                           "clientInfo": {"name": "newlocal-error-recovery-fixture", "version": "1"}})
        names = {tool["name"] for tool in rpc("tools/list", {})["tools"]}
        if "execute_python" not in names:
            raise ValueError("common_execute_python_missing")
        emit({"type": "thread.started", "thread_id": str(uuid.uuid4())})
        emit({"type": "turn.started"})
        recovered_stdout = None
        for index, (name, arguments) in enumerate(LOCAL_CALLS):
            item = {"id": "newlocal-tool-" + str(index + 1), "type": "mcp_tool_call", "server": "arm_engine",
                    "tool": name, "arguments": arguments, "status": "in_progress"}
            emit({"type": "item.started", "item": item})
            response = rpc("tools/call", {"name": name, "arguments": arguments})
            if set(response) != {"content", "isError"} or type(response["isError"]) is not bool:
                raise ValueError("actual_tool_result_envelope")
            item = dict(item, status="failed" if response["isError"] else "completed", error=None,
                        result={"content": response["content"], "structured_content": None})
            emit({"type": "item.completed", "item": item})
            body = json.loads(response["content"][0]["text"])
            record["tool_results"].append({"attempt": index + 1, "owner_isError": response["isError"],
                "CLI_item": item, "ordinary_Python_error": body["error"], "stdout": body["stdout"]})
            if index == 0:
                if response["isError"] is not True or body["error"] != {
                        "type": "ValueError", "message": LOCAL_ERROR_MESSAGE}:
                    raise ValueError("actual_expected_ValueError_not_observed")
            else:
                if response["isError"] is not False or body["error"] is not None or body["stdout"] != "42\n":
                    raise ValueError("actual_42_recovery_not_observed")
                recovered_stdout = body["stdout"].strip()
        final = "LOCAL_RECOVERED_" + recovered_stdout
        final_path.write_text(final, encoding="utf-8")
        emit({"type": "item.completed", "item": {"id": "local-final", "type": "agent_message", "text": final}})
        emit({"type": "turn.completed", "usage": {"input_tokens": 0, "cached_input_tokens": 0,
            "cache_write_input_tokens": 0, "output_tokens": 0, "reasoning_output_tokens": 0}})

        binding_deadline_ns = min(deadline_ns, time.perf_counter_ns() + 15 * 10**9)
        while True:
            remaining_seconds(binding_deadline_ns, 15)
            if binding_path.exists():
                try:
                    binding = json.loads(binding_path.read_bytes())
                except json.JSONDecodeError:
                    binding = None
                if binding is not None:
                    if (binding.get("confirmed") is not True or binding.get("runtime_pid") != process.pid
                            or binding.get("launcher_pid") != os.getpid()):
                        raise ValueError("actual_live_thin_runtime_binding")
                    record["runtime_binding_confirmed"] = True
                    record["runtime_binding"] = binding
                    break
            time.sleep(.01)
        record["normal_EOF_requested"] = True
        record["normal_EOF_requested_ns"] = time.perf_counter_ns()
        process.stdin.close()
        exit_code = process.wait(timeout=remaining_seconds(deadline_ns, 5))
        record["thin_wait_exit_code"] = exit_code
        record["normal_exit_observed"] = exit_code == 0
        if exit_code != 0:
            raise RuntimeError("actual_thin_normal_EOF_exit_nonzero")
    except BaseException as error:
        record["error"] = {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}
        raise
    finally:
        if process is not None:
            record["thin_cleanup"] = launch.stop_process(process, timeout=5)
        record["closed_ns"] = time.perf_counter_ns()
        record["passed"] = bool(record["error"] is None and record["runtime_binding_confirmed"]
            and record["normal_EOF_requested"] and record["normal_exit_observed"] and record["thin_cleanup"]
            and record["thin_cleanup"]["confirmed"] is True and record["thin_cleanup"]["exit_code"] == 0
            and record["thin_cleanup"]["kill_requested"] is False)
        save(final_path.parent / "LOCAL_FIXTURE.json", record)
        if record["error"] is None and not record["passed"]:
            raise RuntimeError("fixture_normal_EOF_handle_cleanup_failed")


if __name__ == "__main__":
    main()
