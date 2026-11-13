"""Held MCP owner for independent and active finite-camera coverage tasks.

The original stdio_attach transport forwards its JSON responses unchanged.
Both routes use one fresh observation session, raw arrays and image encoder.
Only the P route exposes the frozen active coverage chain.
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
from types import MappingProxyType


HERE = Path(__file__).resolve().parent
MODULE_SPEC = importlib.util.spec_from_file_location("_active_image_content_001", HERE / "image_content.py")
IMAGE = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(IMAGE)
COMMON_SPEC = importlib.util.spec_from_file_location("_coverage_consumption_common", HERE / "common_observation.py")
COMMON = importlib.util.module_from_spec(COMMON_SPEC)
COMMON_SPEC.loader.exec_module(COMMON)
MAX_FRAME = 24 * 1024 * 1024
VIEW_NAMES = ("SCENE", "TOP", "LEFT", "RIGHT", "FRONT", "BACK")
GENERIC = {
    "name": "execute_python",
    "description": "Execute ordinary persistent Python with stdout/stderr. All geometry and cameras are already in variables "
        "geometry={'objects':[{'name':str,'vertices':[[rational_x,rational_y,rational_z],...],'triangles':[[i,j,k],...]}],...} "
        "and cameras={'views':[{'name':str,'view_matrix':4x4,'projection_matrix':4x4,'direction_rational':[x,y,z],"
        "'size_px':[512,512],...}],...}. np and Fraction are available. render_views(names,include_images=False) "
        "batch-renders current cameras and returns [{ref,view,buffer_handle,...}]. Repeated views reuse their cache. "
        "buffers[view] exposes color uint8[H,W,3], owners int32[H,W] and depth float64[H,W]. Rows start at top-left. "
        "Owner is the zero-based geometry.objects index, background -1. Depth is positive camera depth, background infinity. "
        "Boundary count uses unique target-owned pixels incident to horizontal/vertical adjacent different-owner pairs "
        "with squared RGB distance >=24*24, marking both endpoints. read_images(refs) or attach_images(refs) requests "
        "actual image blocks appended to this same Python tool result. render_views(...,include_images=True) also attaches "
        "its images, so computing, batch rendering and delivering images can share one call. Scratch is a writable Path, "
        "image_files maps generated refs to PNG paths. Read supplied geometry, cameras, generated buffers/images and your "
        "own scratch. Keep source inputs unchanged. Use your own algorithms and cached variables.",
    "inputSchema": {"type": "object", "properties": {"code": {"type": "string"}},
                    "required": ["code"], "additionalProperties": False},
}
SCENE_DATA = {
    "name": "scene_data", "description": "Return the complete current geometry and candidate camera parameters. "
        "The same objects are already in execute_python variables geometry and cameras.",
    "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
}
RENDER_VIEWS = {
    "name": "render_views", "description": "Generate one or multiple full-scene views using the shared exact inputs "
        "and common RGB/depth/owner renderer. Return stable current-session refs and raw buffer handles. "
        "Repeated views reuse existing buffers and PNG. include_images requests actual image content in this result.",
    "inputSchema": {"type": "object", "properties": {
        "names": {"type": "array", "minItems": 1, "maxItems": 6,
                  "items": {"type": "string", "enum": list(VIEW_NAMES)}},
        "include_images": {"type": "boolean", "default": False}},
        "required": ["names"], "additionalProperties": False},
}
READ_IMAGES = {
    "name": "read_images", "description": "Return actual 512x512 PNG image content for one or multiple generated "
        "current-session image refs. Input order is retained. The source views reuse their render cache.",
    "inputSchema": {"type": "object", "properties": {"refs": {"type": "array", "minItems": 1,
        "maxItems": 6, "items": {"type": "string"}}},
        "required": ["refs"], "additionalProperties": False},
}
ACTIVE = {
    "name": "active_coverage", "description": "Discover independent rectangular panels and perform current-session "
        "active observation over the supplied finite camera pool. Computes the frozen geometric index, selects views, "
        "uses the common renderer and actual RGB/owner pixel feedback, and returns concise panel status, evidence "
        "refs and remaining reasons. Available immediately. include_images attaches the actual observed images.",
    "inputSchema": {"type": "object", "properties": {"include_images": {"type": "boolean", "default": True}},
                    "additionalProperties": False},
}


def encoded(value):
    return IMAGE.encoded(value) + b"\n"


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n",
                          encoding="utf-8", newline="\n")


def public_tools(group):
    if group not in ("N", "P"):
        raise ValueError("registered_route")
    tools = [GENERIC, SCENE_DATA, RENDER_VIEWS, READ_IMAGES] + ([ACTIVE] if group == "P" else [])
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
        if type(self.deadline_ns) is not int or config.get("max_tool_calls", 12) != 12:
            raise ValueError("fixed_route_deadline_and_twelve_tool_calls")
        IMAGE.deadline(self.deadline_ns)
        self.out = Path(config["output"]).resolve()
        self.out.mkdir(parents=True, exist_ok=False)
        self.started_ns = time.perf_counter_ns()
        self.logs = []
        self.calls = 0
        self.constructions = []
        self.construction_failures = []
        self.post_construction_failures = []
        self.transport_records = []
        self.close_record = None
        self.session = COMMON.ObservationSession(config)
        self.attached_refs = []
        self.image_files = {}
        scratch = self.out / "scratch"
        scratch.mkdir()
        self.namespace = {"__name__": "__consumer_python__", "geometry": copy.deepcopy(self.session.scene),
            "cameras": copy.deepcopy(self.session.cameras), "np": self.session.np, "Fraction": COMMON.Fraction,
            "buffers": MappingProxyType(self.session.buffers), "scratch": scratch,
            "render_views": self.python_render_views, "read_images": self.request_images,
            "attach_images": self.request_images, "image_files": self.image_files}
        save(self.out / "TOOLS_SCHEMA.json", self.tools)
        save(self.out / "IDENTITY.json", {
            "group": self.group, "actor_pid": os.getpid(), "actor_parent_pid": os.getppid(),
            "python": sys.executable, "started_ns": self.started_ns,
            "worker_deadline_ns": self.deadline_ns, "max_tool_calls": 12, "max_render_attempts": 6,
            "image_helper_path": str(HERE / "image_content.py"),
            "image_helper_sha256": hashlib.sha256((HERE / "image_content.py").read_bytes()).hexdigest(),
            "source_inputs": self.session.source_inputs,
            "exposed_tool_names": [tool["name"] for tool in self.tools],
            "Blender_processes": 0, "provider_calls": 0,
            "scope": "Fresh shared whole-scene raster and optional active chain. Default product unchanged."})
        self.save_metrics()

    def save_metrics(self):
        sent = [row for row in self.transport_records if row["send_confirmed"]]
        counts = {
            "tool_attempts": self.calls, "constructed_image_blocks": len(self.constructions),
            "failed_image_constructions": len(self.construction_failures),
            "constructed_PNG_bytes": sum(row["PNG_bytes_read"] for row in self.constructions),
            "constructed_base64_chars": sum(row["base64_chars"] for row in self.constructions),
            "constructed_image_block_JSON_bytes": sum(row["image_block_JSON_bytes"] or 0 for row in self.constructions),
            "constructed_image_JSON_bytes_unknown_count": sum(row["image_block_JSON_bytes"] is None for row in self.constructions),
            "helper_ready_image_blocks": sum(row.get("delivery_ready") is True for row in self.constructions),
            "delivery_ready_image_blocks": sum(row["content_metrics"]["image_blocks"] for row in self.logs
                if row["response_bytes"] is not None),
            "post_construction_failures": len(self.post_construction_failures),
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
            "provider_internal_wire": "unobserved", "new_renders": len(self.session.attempts), "Blender_processes": 0,
            "common": {**self.session.metrics(), "runtime_faults": self.session.runtime_faults,
                       "audit": self.session.audit},
            "tools": self.logs,
        }
        save(self.out / "TOOLS.json", {"calls": self.calls,
            "wire_tool_bytes": sum(row["response_bytes"] or 0 for row in self.logs), "tools": self.logs})
        save(self.out / "METRICS.json", counts)
        save(self.out / "IMAGE_CONSTRUCTIONS.json", {
            "constructed": self.constructions, "failed": self.construction_failures,
            "post_construction_failures": self.post_construction_failures})
        return counts

    def record_constructed(self, receipt):
        receipt["tool_attempt"] = self.calls
        self.constructions.append(receipt)
        self.session.trace.emit("image_constructed", durable=True, ref=receipt["ref"],
            tool_attempt=self.calls, constructed_ns=receipt["constructed_ns"],
            PNG_bytes=receipt["PNG_bytes_read"], PNG_sha256=receipt["PNG_sha256"],
            base64_chars=receipt["base64_chars"], constructed_image_blocks=len(self.constructions))
        self.save_metrics()

    def request_images(self, refs):
        if not isinstance(refs, (list, tuple)) or not refs or len(refs) > 6 or any(type(ref) is not str for ref in refs):
            raise ValueError("generated_image_references_required")
        for ref in refs:
            self.session.image_specification(ref)
        self.attached_refs.extend(refs)
        return list(refs)

    def python_render_views(self, names, include_images=False):
        if type(include_images) is not bool:
            raise ValueError("include_images_boolean")
        frames = self.session.render_views(names)
        for frame in frames:
            self.image_files[frame["ref"]] = self.session.by_view[frame["view"]]["PNG"]
        if include_images:
            self.request_images([frame["ref"] for frame in frames])
        return frames

    def image_result(self, refs):
        content = []
        if not isinstance(refs, (list, tuple)) or not refs or len(refs) > 6 or any(type(ref) is not str for ref in refs):
            raise ValueError("generated_image_references_required")
        for ref in refs:
            try:
                specification, input_directory = self.session.image_specification(ref)
                block, receipt = IMAGE.image_content(specification, input_directory, self.deadline_ns,
                                                     on_constructed=self.record_constructed)
            except IMAGE.ImageContentError as error:
                if error.receipt["constructed"]:
                    self.post_construction_failures.append(error.receipt)
                else:
                    self.construction_failures.append(error.receipt)
                self.save_metrics()
                raise
            content.extend([{"type": "text", "text": ref + " (512x512, image/png)"}, block])
        self.save_metrics()
        return {"content": content, "isError": False}

    def execute_python(self, arguments):
        if set(arguments) != {"code"} or type(arguments["code"]) is not str:
            raise ValueError("python_code_argument")
        stdout = io.StringIO()
        stderr = io.StringIO()
        error = None
        self.attached_refs = []
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                exec(compile(arguments["code"], "<consumer-python>", "exec"), self.namespace, self.namespace)
            except BaseException as exception:
                error = {"type": type(exception).__name__, "message": str(exception)}
                traceback.print_exc()
        IMAGE.deadline(self.deadline_ns)
        result = {"stdout": stdout.getvalue(), "stderr": stderr.getvalue(), "error": error}
        content = [{"type": "text", "text": json.dumps(result, ensure_ascii=False, allow_nan=False)}]
        if self.attached_refs:
            content.extend(self.image_result(self.attached_refs)["content"])
        return {"content": content, "isError": error is not None}

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
            if self.calls > 12:
                raise ValueError("route_twelve_tool_call_limit")
            if type(params) is not dict:
                raise ValueError("tool_params_object")
            arguments = params.get("arguments", {})
            if type(arguments) is not dict:
                raise ValueError("tool_arguments_object")
            if name == "execute_python":
                result = self.execute_python(arguments)
            elif name == "scene_data":
                if arguments:
                    raise ValueError("scene_data_empty_arguments")
                result = {"content": [{"type": "text", "text": json.dumps({
                    "geometry": self.session.scene, "cameras": self.session.cameras}, ensure_ascii=False, allow_nan=False)}],
                    "isError": False}
            elif name == "render_views":
                if set(arguments) - {"names", "include_images"} or "names" not in arguments:
                    raise ValueError("render_views_arguments")
                include_images = arguments.get("include_images", False)
                if type(include_images) is not bool:
                    raise ValueError("include_images_boolean")
                self.attached_refs = []
                frames = self.python_render_views(arguments["names"], include_images)
                content = [{"type": "text", "text": json.dumps({"images": frames}, ensure_ascii=False, allow_nan=False)}]
                if self.attached_refs:
                    content.extend(self.image_result(self.attached_refs)["content"])
                result = {"content": content, "isError": False}
            elif name == "read_images":
                if set(arguments) != {"refs"}:
                    raise ValueError("read_images_arguments")
                result = self.image_result(arguments["refs"])
            elif name == "active_coverage" and self.group == "P":
                if set(arguments) - {"include_images"} or type(arguments.get("include_images", True)) is not bool:
                    raise ValueError("active_coverage_arguments")
                facts = self.session.active_coverage()
                for frame in facts["images"]:
                    self.image_files[frame["ref"]] = self.session.by_view[frame["view"]]["PNG"]
                content = [{"type": "text", "text": json.dumps(facts, ensure_ascii=False, allow_nan=False)}]
                if arguments.get("include_images", True) and facts["image_refs"]:
                    content.extend(self.image_result(facts["image_refs"])["content"])
                result = {"content": content, "isError": False}
            else:
                raise ValueError("tool_not_available")
            IMAGE.deadline(self.deadline_ns)
        except BaseException as error:
            private_error = {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}
            result = {"content": [{"type": "text", "text": "Tool failed. " + type(error).__name__}], "isError": True}
        response = {"jsonrpc": "2.0", "id": request["id"], "result": result}
        closed = time.perf_counter_ns()
        response_bytes = None
        serialization_error = None
        actual_content_metrics = {"image_blocks": 0, "PNG_bytes": 0, "base64_chars": 0,
                                  "image_block_JSON_bytes": 0, "text_UTF8_bytes": 0, "PNG_sha256": []}
        try:
            response_bytes = len(encoded(response))
            actual_content_metrics = content_metrics(result["content"])
        except BaseException as error:
            serialization_error = {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}
        row = {"attempt": self.calls, "name": name, "started_ns": mark, "closed_ns": closed,
               "elapsed_ns": closed - mark, "response_bytes": response_bytes,
               "is_error": bool(result["isError"]) or serialization_error is not None, "error": private_error,
               "response_serialization_error": serialization_error, "content_metrics": actual_content_metrics}
        self.logs.append(row)
        save(folder / "RECEIPT.json", row)
        self.save_metrics()
        if serialization_error is not None:
            raise RuntimeError("tool_response_serialization_failed")
        save(folder / "RESPONSE.json", response)
        self.session.save()
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
                      "serverInfo": {"name": "finite-scene-observation", "version": "1"}}
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
        self.session.save()
        metrics = self.save_metrics()
        self.session.trace.emit("owner_close", durable=True, render_attempts=len(self.session.attempts),
                                constructed_image_blocks=len(self.constructions), server_thread_stopped=server_thread_stopped)
        self.session.trace.close()
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
