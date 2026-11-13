"""Minimal held MCP owner for the two registered image-consumption routes.

The original stdio_attach transport forwards its JSON responses unchanged.
This actor reads existing images and executes ordinary Python. It starts no
Blender, product runtime, renderer, provider, or model consumer.
"""

import argparse
import base64
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time
import traceback


HERE = Path(__file__).resolve().parent
MODULE_SPEC = importlib.util.spec_from_file_location("_active_image_content_001", HERE / "image_content.py")
IMAGE = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(IMAGE)
MAX_FRAME = 24 * 1024 * 1024
REFS = ("view-a", "view-b")
GENERIC = {
    "name": "execute_python",
    "description": "Execute ordinary Python in a persistent namespace and return stdout and stderr text. "
        "The image_files mapping provides the two supplied image paths under opaque references view-a and view-b. "
        "Standard Python reading and your own computations are available. Restrict reads to these supplied images "
        "and your own computations. Keep files unchanged. Use read_image to receive an image content block.",
    "inputSchema": {"type": "object", "properties": {"code": {"type": "string"}},
                    "required": ["code"], "additionalProperties": False},
}
READ_IMAGE = {
    "name": "read_image",
    "description": "Read an existing supplied PNG and return its actual image content. "
        "References view-a and view-b are available, each 512x512 image/png. "
        "When obtaining both images, request view-a followed by view-b.",
    "inputSchema": {"type": "object", "properties": {"ref": {"type": "string", "enum": list(REFS)}},
                    "required": ["ref"], "additionalProperties": False},
}
OBSERVE = {
    "name": "human_eye_image_observe",
    "description": "Experimental read-only active-observation image outlet. Return the actual existing supplied "
        "PNG images for the requested opaque references, in view-a then view-b order. "
        "Each image is 512x512 image/png. This outlet replays registered images.",
    "inputSchema": {"type": "object", "properties": {"refs": {"type": "array", "minItems": 1,
        "maxItems": 2, "uniqueItems": True, "items": {"type": "string", "enum": list(REFS)}}},
        "required": ["refs"], "additionalProperties": False},
}


def encoded(value):
    return IMAGE.encoded(value) + b"\n"


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n",
                          encoding="utf-8", newline="\n")


def public_tools(group):
    if group not in ("N", "P"):
        raise ValueError("registered_route")
    tools = [GENERIC, READ_IMAGE] + ([OBSERVE] if group == "P" else [])
    return copy.deepcopy(tools)


def content_metrics(content):
    counts = {"image_blocks": 0, "PNG_bytes": 0, "base64_chars": 0,
              "image_block_JSON_bytes": 0, "text_UTF8_bytes": 0}
    hashes = []
    for block in content:
        if block["type"] == "image":
            if block["mimeType"] != "image/png":
                raise ValueError("public_image_mime")
            raw = base64.b64decode(block["data"], validate=True)
            counts["image_blocks"] += 1
            counts["PNG_bytes"] += len(raw)
            counts["base64_chars"] += len(block["data"])
            counts["image_block_JSON_bytes"] += len(IMAGE.encoded(block))
            hashes.append(hashlib.sha256(raw).hexdigest())
        elif block["type"] == "text":
            counts["text_UTF8_bytes"] += len(block["text"].encode("utf-8"))
        else:
            raise ValueError("public_content_type")
    return dict(counts, PNG_sha256=hashes)


class Owner:
    def __init__(self, config):
        self.config = config
        self.group = config["group"]
        self.tools = public_tools(self.group)
        self.deadline_ns = config["worker_deadline_ns"]
        if type(self.deadline_ns) is not int or config.get("max_tool_calls", 4) != 4:
            raise ValueError("fixed_route_deadline_and_four_tool_calls")
        IMAGE.deadline(self.deadline_ns)
        manifest_path = Path(config["images_manifest"]).resolve()
        manifest = json.loads(manifest_path.read_bytes())
        if manifest["schema"] != "active-image-consumption-001-inputs-v1":
            raise ValueError("registered_images_manifest")
        if [value["ref"] for value in manifest["images"]] != list(REFS):
            raise ValueError("registered_image_reference_order")
        self.images = {value["ref"]: value for value in manifest["images"]}
        self.input_directory = manifest_path.parent
        self.out = Path(config["output"]).resolve()
        self.out.mkdir(parents=True, exist_ok=False)
        self.started_ns = time.perf_counter_ns()
        self.logs = []
        self.calls = 0
        self.constructions = []
        self.construction_failures = []
        self.transport_records = []
        self.close_record = None
        self.namespace = {"__name__": "__consumer_python__", "image_files": {
            ref: str((self.input_directory / self.images[ref]["file"]).resolve()) for ref in REFS}}
        save(self.out / "TOOLS_SCHEMA.json", self.tools)
        save(self.out / "IDENTITY.json", {
            "group": self.group, "actor_pid": os.getpid(), "actor_parent_pid": os.getppid(),
            "python": sys.executable, "started_ns": self.started_ns,
            "worker_deadline_ns": self.deadline_ns, "max_tool_calls": 4,
            "image_helper_path": str(HERE / "image_content.py"),
            "image_helper_sha256": hashlib.sha256((HERE / "image_content.py").read_bytes()).hexdigest(),
            "manifest_path": str(manifest_path), "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "exposed_tool_names": [tool["name"] for tool in self.tools],
            "Blender_processes": 0, "render_attempts": 0, "provider_calls": 0,
            "scope": "Experimental registered-PNG outlet. Product installation unchanged."})
        self.save_metrics()

    def save_metrics(self):
        sent = [row for row in self.transport_records if row["send_confirmed"]]
        counts = {
            "tool_attempts": self.calls, "constructed_image_blocks": len(self.constructions),
            "failed_image_constructions": len(self.construction_failures),
            "constructed_PNG_bytes": sum(row["PNG_bytes_read"] for row in self.constructions),
            "constructed_base64_chars": sum(row["base64_chars"] for row in self.constructions),
            "constructed_image_block_JSON_bytes": sum(row["image_block_JSON_bytes"] for row in self.constructions),
            "server_socket_sent_image_blocks": sum(row["content_metrics"]["image_blocks"] for row in sent),
            "server_socket_sent_PNG_bytes": sum(row["content_metrics"]["PNG_bytes"] for row in sent),
            "server_socket_sent_base64_chars": sum(row["content_metrics"]["base64_chars"] for row in sent),
            "server_socket_sent_image_block_JSON_bytes": sum(row["content_metrics"]["image_block_JSON_bytes"] for row in sent),
            "server_socket_sent_text_UTF8_bytes": sum(row["content_metrics"]["text_UTF8_bytes"] for row in sent),
            "server_socket_sent_MCP_JSON_bytes": sum(row["MCP_JSON_bytes"] for row in sent),
            "server_socket_sent_outer_TCP_JSON_bytes": sum(row["outer_TCP_JSON_bytes"] for row in sent),
            "server_socket_request_bytes": sum(row["request_bytes"] for row in self.transport_records),
            "failed_or_unknown_socket_sends": sum(not row["send_confirmed"] for row in self.transport_records),
            "model_CLI_receipt_scope": "Server sendall confirmation only. Actual CLI receipt is verified independently.",
            "provider_internal_wire": "unobserved", "new_renders": 0, "Blender_processes": 0,
            "tools": self.logs,
        }
        save(self.out / "TOOLS.json", {"calls": self.calls,
            "wire_tool_bytes": sum(row["response_bytes"] for row in self.logs), "tools": self.logs})
        save(self.out / "METRICS.json", counts)
        save(self.out / "IMAGE_CONSTRUCTIONS.json", {
            "constructed": self.constructions, "failed": self.construction_failures})
        return counts

    def image_result(self, refs):
        content = []
        for ref in REFS:
            if ref not in refs:
                continue
            try:
                block, receipt = IMAGE.image_content(self.images[ref], self.input_directory, self.deadline_ns)
            except IMAGE.ImageContentError as error:
                self.construction_failures.append(error.receipt)
                raise
            receipt["tool_attempt"] = self.calls
            self.constructions.append(receipt)
            content.extend([{"type": "text", "text": ref + " (512x512, image/png)"}, block])
        return {"content": content, "isError": False}

    def execute_python(self, arguments):
        if set(arguments) != {"code"} or type(arguments["code"]) is not str:
            raise ValueError("python_code_argument")
        stdout = io.StringIO()
        stderr = io.StringIO()
        error = None
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                exec(compile(arguments["code"], "<consumer-python>", "exec"), self.namespace, self.namespace)
            except BaseException as exception:
                error = {"type": type(exception).__name__, "message": str(exception)}
                traceback.print_exc()
        IMAGE.deadline(self.deadline_ns)
        result = {"stdout": stdout.getvalue(), "stderr": stderr.getvalue(), "error": error}
        return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, allow_nan=False)}],
                "isError": error is not None}

    def tool_call(self, request):
        self.calls += 1
        mark = time.perf_counter_ns()
        folder = self.out / ("tool_" + str(self.calls).zfill(2))
        folder.mkdir()
        save(folder / "REQUEST.json", request)
        params = request.get("params")
        name = params.get("name") if type(params) is dict else None
        private_error = None
        try:
            IMAGE.deadline(self.deadline_ns)
            if self.calls > 4:
                raise ValueError("route_four_tool_call_limit")
            if type(params) is not dict:
                raise ValueError("tool_params_object")
            arguments = params.get("arguments", {})
            if type(arguments) is not dict:
                raise ValueError("tool_arguments_object")
            if name == "execute_python":
                result = self.execute_python(arguments)
            elif name == "read_image":
                if set(arguments) != {"ref"} or arguments["ref"] not in REFS:
                    raise ValueError("image_reference_argument")
                result = self.image_result([arguments["ref"]])
            elif name == "human_eye_image_observe" and self.group == "P":
                refs = arguments.get("refs")
                if set(arguments) != {"refs"} or type(refs) is not list or not 1 <= len(refs) <= 2 or \
                        any(type(ref) is not str or ref not in REFS for ref in refs) or len(set(refs)) != len(refs):
                    raise ValueError("image_references_argument")
                result = self.image_result(refs)
            else:
                raise ValueError("tool_not_available")
            IMAGE.deadline(self.deadline_ns)
        except BaseException as error:
            private_error = {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}
            result = {"content": [{"type": "text", "text": "Tool failed. " + type(error).__name__}], "isError": True}
        response = {"jsonrpc": "2.0", "id": request["id"], "result": result}
        closed = time.perf_counter_ns()
        row = {"attempt": self.calls, "name": name, "started_ns": mark, "closed_ns": closed,
               "elapsed_ns": closed - mark, "response_bytes": len(encoded(response)),
               "is_error": bool(result["isError"]), "error": private_error,
               "content_metrics": content_metrics(result["content"])}
        self.logs.append(row)
        save(folder / "RESPONSE.json", response)
        save(folder / "RECEIPT.json", row)
        self.save_metrics()
        return response

    def handle(self, request):
        rid = request.get("id")
        if rid is None:
            return None
        method = request.get("method")
        if method == "tools/call":
            return self.tool_call(request)
        IMAGE.deadline(self.deadline_ns)
        if method == "initialize":
            result = {"protocolVersion": request.get("params", {}).get("protocolVersion", "2025-03-26"),
                      "capabilities": {"tools": {}},
                      "serverInfo": {"name": "registered-image-outlet", "version": "1"}}
        elif method == "tools/list":
            result = {"tools": self.tools}
        elif method == "ping":
            result = {}
        else:
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "Method not found"}}
        return {"jsonrpc": "2.0", "id": rid, "result": result}

    def record_transport(self, request_bytes, reply, send_confirmed, send_error, started_ns, closed_ns):
        result = reply.get("result") or {}
        public = result.get("result", {}) if type(result) is dict else {}
        metrics = content_metrics(public.get("content", []))
        row = {"sequence": len(self.transport_records) + 1, "started_ns": started_ns, "closed_ns": closed_ns,
               "request_bytes": len(request_bytes), "MCP_JSON_bytes": 0 if result is None else len(encoded(result)),
               "outer_TCP_JSON_bytes": len(encoded(reply)), "send_confirmed": send_confirmed,
               "send_error": send_error, "content_metrics": metrics}
        self.transport_records.append(row)
        save(self.out / "TRANSPORT.json", self.transport_records)
        self.save_metrics()

    def close(self, server_thread_stopped, errors):
        if self.close_record is not None:
            return self.close_record
        metrics = self.save_metrics()
        self.close_record = {"started_ns": self.started_ns, "ended_ns": time.perf_counter_ns(),
            "actor_pid": os.getpid(), "server_thread_stopped": server_thread_stopped, "errors": errors,
            "confirmed": server_thread_stopped and not errors, "metrics": metrics,
            "scope": "Actor listener closed and serving thread stopped. Parent owns process wait and handle cleanup."}
        save(self.out / "CLOSE.json", self.close_record)
        return self.close_record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    options = parser.parse_args()
    config = json.loads(options.config.read_bytes())
    owner = Owner(config)
    stop = threading.Event()
    listener = socket.socket()
    thread = None
    errors = []
    rpc_sequence = 0
    try:
        listener.bind(("127.0.0.1", 0))
        listener.listen(2)
        listener.settimeout(.2)

        def serve():
            nonlocal rpc_sequence
            while not stop.is_set():
                try:
                    IMAGE.deadline(owner.deadline_ns)
                    connection, _ = listener.accept()
                except socket.timeout:
                    if time.perf_counter_ns() >= owner.deadline_ns:
                        break
                    continue
                except TimeoutError:
                    break
                except OSError:
                    if not stop.is_set():
                        errors.append("listener_accept_failed")
                    break
                rpc_sequence += 1
                folder = owner.out / ("rpc_" + str(rpc_sequence).zfill(3))
                folder.mkdir()
                started = time.perf_counter_ns()
                request_bytes = bytearray()
                reply = None
                confirmed = False
                send_error = None
                request = {}
                with connection:
                    try:
                        while True:
                            left = (owner.deadline_ns - time.perf_counter_ns()) / 1e9
                            if left <= 0:
                                raise TimeoutError("original_route_deadline")
                            connection.settimeout(min(left, 30))
                            block = connection.recv(65536)
                            if not block:
                                break
                            request_bytes.extend(block)
                            if len(request_bytes) > MAX_FRAME:
                                raise ValueError("MCP_frame_limit")
                        (folder / "TCP_TX.bin").write_bytes(request_bytes)
                        request = json.loads(request_bytes)
                        if request["operation"] != "attached_mcp" or request["args"]["kind"] not in ("native", "he"):
                            raise ValueError("attached_MCP_operation")
                        response = owner.handle(request["args"]["message"])
                        reply = {"request_id": request["request_id"], "ok": True, "result": response}
                    except BaseException as error:
                        if not (folder / "TCP_TX.bin").exists():
                            (folder / "TCP_TX.bin").write_bytes(request_bytes)
                        reply = {"request_id": request.get("request_id"), "ok": False,
                                 "error": type(error).__name__}
                        save(folder / "ERROR.json", {"type": type(error).__name__, "message": str(error),
                                                     "traceback": traceback.format_exc()})
                    raw = encoded(reply)
                    (folder / "TCP_RX.bin").write_bytes(raw)
                    try:
                        IMAGE.deadline(owner.deadline_ns)
                        if len(raw) > MAX_FRAME:
                            raise ValueError("MCP_frame_limit")
                        connection.sendall(raw)
                        confirmed = True
                    except BaseException as error:
                        send_error = {"type": type(error).__name__, "message": str(error)}
                owner.record_transport(bytes(request_bytes), reply, confirmed, send_error,
                                       started, time.perf_counter_ns())

        def guarded_serve():
            try:
                serve()
            except BaseException as error:
                errors.append({"type": type(error).__name__, "message": str(error),
                               "traceback": traceback.format_exc()})

        thread = threading.Thread(target=guarded_serve, daemon=True)
        thread.start()
        save(config["endpoint"], {"host": "127.0.0.1", "port": listener.getsockname()[1],
             "chain_deadline_ns": owner.deadline_ns, "actor_pid": os.getpid()})
        sys.stdin.readline()
    except BaseException as error:
        errors.append({"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()})
        raise
    finally:
        stop.set()
        listener.close()
        if thread is not None:
            thread.join(timeout=5)
        owner.close(thread is None or not thread.is_alive(), errors)


if __name__ == "__main__":
    main()
