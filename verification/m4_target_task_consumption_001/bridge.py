"""Thin held MCP listener for the live target-task N/P consumers."""

import base64
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import os
import sys
import threading
import time
import traceback


HERE = Path(__file__).resolve().parent
MAX_FRAME = 24 * 1024 * 1024


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


COMMON = load("_target_task_common_python", HERE / "native_tools.py")
IMAGE_PATH = HERE.with_name("m4_active_coverage_consumption_001") / "image_content.py"
IMAGE = load("_target_task_image_delivery", IMAGE_PATH)
encoded, save = COMMON.encoded, COMMON.save


def schema(name, description, properties, required=()):
    return {"name": name, "description": description, "inputSchema": {
        "type": "object", "properties": properties, "required": list(required),
        "additionalProperties": False}}


TOOLS = [
    schema("execute_python", "Run ordinary persistent Python. np, Fraction, PIL, Image, shapely, cameras, buffers and scratch are available. blender(code,timeout=30) runs ordinary persistent Python in the current Blender. scene_data(selectors=None) reads current raw world geometry. render_views(names,include_images=False,fresh=False) obtains current shared frames. read_images(refs) attaches current images. Printed data are returned. Keep the scene read-only. Use public attributes and current task inputs. Private reflection, administrator/project files, product implementation APIs, external processes and network access are outside this experiment's source boundary. scratch supports ordinary file operations.", {"code": {"type": "string"}}, ("code",)),
    schema("execute_blender_code", "Execute ordinary persistent Python in the current read-only Blender. bpy, mathutils and ordinary Python geometry operations are available. Return captured stdout, stderr and any error. Do not move, edit or save the scene.", {"code": {"type": "string"}}, ("code",)),
    schema("scene_data", "Read current evaluated raw world vertices and source triangles in original object and triangle order, current source identity, and the six raw camera devices. selectors contains object names. Omit it to read all mesh objects. Source triangle indices are zero-based within each object's returned list.", {"selectors": {"type": ["array", "null"], "items": {"type": "string"}}}),
    schema("render_views", "Read or generate current full-frame images with the shared low-level triangle renderer. A source/camera-bound cached frame is reused unless fresh is true. Frame refs are stable. buffers[ref] contains color, depth, owners and triangle_ids. Pixel origin is top-left, indices are zero-based, background owner and triangle ID are -1. Metadata object_names and source_face_offsets map frame owners and global triangle IDs to object names and local source faces. include_images delivers PNG content. This tool returns raw buffers and images.", {
        "names": {"type": "array", "minItems": 1, "maxItems": 6, "items": {"enum": list(COMMON.VIEW_NAMES)}},
        "fresh": {"type": "boolean", "default": False}, "include_images": {"type": "boolean", "default": False}}, ("names",)),
    schema("read_images", "Deliver PNG content for current-session frame refs. It reuses existing images and does not construct a new raster.", {"refs": {"type": "array", "minItems": 1, "maxItems": 6, "items": {"type": "string"}}}, ("refs",)),
]
ACTIVE = schema("active_observation", "Call the current installed human_eye_scene_observe entry for the task's named target using active_observation and its default brief. include_images requests native image content. Existing current-source facts and frames may be reused. last_observation_json in execute_python contains the same most recently delivered public JSON text.", {"include_images": {"type": "boolean", "default": True}})


def public_tools(group):
    if group not in ("N", "P"):
        raise ValueError("registered_group")
    return copy.deepcopy(TOOLS + ([ACTIVE] if group == "P" else []))


def content_metrics(content):
    value = {"image_blocks": 0, "PNG_bytes": 0, "base64_chars": 0,
             "image_block_JSON_bytes": 0, "text_UTF8_bytes": 0, "PNG_sha256": []}
    for block in content:
        if block.get("type") == "text":
            value["text_UTF8_bytes"] += len(block["text"].encode("utf-8"))
        elif block.get("type") == "image" and block.get("mimeType") == "image/png":
            raw = base64.b64decode(block["data"], validate=True)
            value["image_blocks"] += 1
            value["PNG_bytes"] += len(raw)
            value["base64_chars"] += len(block["data"])
            value["image_block_JSON_bytes"] += len(encoded(block))
            value["PNG_sha256"].append(hashlib.sha256(raw).hexdigest())
        else:
            raise ValueError("public_text_or_PNG_content")
    return value


class Owner:
    def __init__(self, runtime, config, budget=None):
        self.runtime, self.config = runtime, config
        self.group, self.label, self.phase = config["group"], config["label"], config["phase"]
        self.deadline_ns = config["worker_deadline_ns"]
        self.budget = budget if budget is not None else runtime.budget
        self.output = Path(config["output"]).resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        self.session = COMMON.OrdinarySession(runtime, config)
        self.calls, self.tools, self.transports, self.constructions = 0, [], [], []
        self.protocol_errors = []
        self.listener = self.thread = None
        self.stop = threading.Event()
        self.serve_errors = []
        save(self.output / "TOOLS_SCHEMA.json", public_tools(self.group))
        self.save()

    def save(self):
        save(self.output / "TOOLS.json", {"calls": self.calls, "tools": self.tools})
        save(self.output / "METRICS.json", {"tool_attempts": self.calls,
            "public_content": [row["content_metrics"] for row in self.tools],
            "image_constructions": self.constructions, "transport": self.transports,
            "consumer_audit": self.session.audit, "protocol_errors": self.protocol_errors})
        save(self.output / "BRIDGE_RESULT.json", {"calls": self.tools,
            "protocol_errors": self.protocol_errors,
            "public_text_bytes": sum(row["content_metrics"]["text_UTF8_bytes"] for row in self.tools)})

    def images(self, refs):
        content = []
        for ref in refs:
            specification, directory = self.runtime.image_specification(ref)
            block, receipt = IMAGE.image_content(specification, directory, self.deadline_ns)
            self.constructions.append(receipt)
            content.extend([{"type": "text", "text": ref + " (512x512, image/png)"}, block])
        return content

    def call(self, request):
        params = request.get("params", {})
        name, arguments = params.get("name"), params.get("arguments", {})
        started = time.perf_counter_ns()
        self.calls += 1
        folder = self.output / ("tool_" + str(self.calls).zfill(2))
        folder.mkdir(exist_ok=False)
        save(folder / "REQUEST.json", request)
        error = None
        try:
            self.session.check()
            self.budget.reserve("business_tool", self.label, self.phase, 1)
            if self.calls > 12 or type(arguments) is not dict:
                raise ValueError("twelve_business_admissions_and_object_arguments")
            if self.group == "P" and self.calls == 1 and (
                    name != "active_observation" or arguments.get("include_images", True) is not True):
                self.protocol_errors.append({"reason": "P_first_business_active_with_images", "attempt": self.calls})
                raise ValueError("P_first_business_active_with_images")
            self.session.attached_refs = []
            if name in ("execute_python", "execute_blender_code"):
                if set(arguments) != {"code"} or type(arguments["code"]) is not str:
                    raise ValueError("code_string_required")
                value = (self.session.execute(arguments["code"]) if name == "execute_python"
                         else self.session.blender(arguments["code"]))
                result = {"content": [{"type": "text", "text": encoded(value).decode("utf-8")}],
                          "isError": value.get("error") is not None}
            elif name == "scene_data":
                if set(arguments) - {"selectors"}:
                    raise ValueError("scene_data_arguments")
                value = self.session.scene_data(arguments.get("selectors"))
                result = {"content": [{"type": "text", "text": encoded(value).decode("utf-8")}], "isError": False}
            elif name == "render_views":
                if set(arguments) - {"names", "fresh", "include_images"} or "names" not in arguments:
                    raise ValueError("render_views_arguments")
                value = self.session.render_views(arguments["names"], arguments.get("include_images", False), arguments.get("fresh", False))
                result = {"content": [{"type": "text", "text": encoded({"frames": value}).decode("utf-8")}], "isError": False}
            elif name == "read_images":
                if set(arguments) != {"refs"}:
                    raise ValueError("read_images_arguments")
                self.session.attach_images(arguments["refs"])
                result = {"content": [], "isError": False}
            elif name == "active_observation" and self.group == "P":
                if set(arguments) - {"include_images"} or type(arguments.get("include_images", True)) is not bool:
                    raise ValueError("active_observation_arguments")
                self.session.namespace["last_observation_json"] = None
                response = self.runtime.public_observe(include_images=arguments.get("include_images", True))
                result = response["result"] if "jsonrpc" in response else response
            else:
                raise ValueError("tool_unavailable")
            result["content"].extend(self.images(self.session.attached_refs))
            self.session.check()
        except BaseException as exception:
            error = {"type": type(exception).__name__, "message": str(exception), "traceback": traceback.format_exc()}
            result = {"content": [{"type": "text", "text": "Tool failed. " + type(exception).__name__ + " " + str(exception)}], "isError": True}
        response = {"jsonrpc": "2.0", "id": request["id"], "result": result}
        row = {"attempt": self.calls, "name": name, "started_ns": started,
               "closed_ns": time.perf_counter_ns(), "is_error": result.get("isError", False),
               "error": error, "response_bytes": len(encoded(response)),
               "content_metrics": content_metrics(result["content"])}
        row["elapsed_ns"] = row["closed_ns"] - started
        self.tools.append(row)
        save(folder / "RESPONSE.json", response)
        save(folder / "RECEIPT.json", row)
        self.save()
        return response

    def handle(self, request):
        if "id" not in request:
            return None
        method = request.get("method")
        if method == "tools/call":
            return self.call(request)
        self.session.check()
        if method == "initialize":
            result = {"protocolVersion": request.get("params", {}).get("protocolVersion", "2025-03-26"),
                      "capabilities": {"tools": {}}, "serverInfo": {"name": "live-target-task", "version": "1"}}
        elif method == "tools/list":
            result = {"tools": public_tools(self.group)}
        elif method == "ping":
            result = {}
        else:
            return {"jsonrpc": "2.0", "id": request["id"], "error": {"code": -32601, "message": "Method not found"}}
        return {"jsonrpc": "2.0", "id": request["id"], "result": result}

    def start(self, endpoint_path):
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(2)
        self.listener.settimeout(.2)
        self.thread = threading.Thread(target=self._serve, name="target-task-MCP", daemon=True)
        self.thread.start()
        save(endpoint_path, {"host": "127.0.0.1", "port": self.listener.getsockname()[1],
                             "chain_deadline_ns": self.deadline_ns})
        return str(Path(endpoint_path).resolve())

    def _serve(self):
        while not self.stop.is_set():
            try:
                connection, _ = self.listener.accept()
            except socket.timeout:
                if time.perf_counter_ns() >= self.deadline_ns:
                    break
                continue
            except OSError:
                break
            started, raw, outer, reply, sent = time.perf_counter_ns(), bytearray(), {}, None, False
            with connection:
                try:
                    while True:
                        self.session.check()
                        connection.settimeout(max(.001, min(30, (self.deadline_ns - time.perf_counter_ns()) / 1e9)))
                        block = connection.recv(65536)
                        if not block:
                            break
                        raw.extend(block)
                        if len(raw) > MAX_FRAME:
                            raise ValueError("MCP_frame_limit")
                    outer = json.loads(raw)
                    if outer["operation"] != "attached_mcp" or outer["args"]["kind"] != "native":
                        raise ValueError("attached_MCP_operation")
                    response = self.handle(outer["args"]["message"])
                    reply = {"request_id": outer["request_id"], "ok": True, "result": response}
                    payload = encoded(reply) + b"\n"
                    if len(payload) > MAX_FRAME:
                        raise ValueError("MCP_frame_limit")
                    self.session.check()
                    connection.sendall(payload)
                    sent = True
                    message = outer["args"]["message"]
                    if (message.get("method") == "tools/call" and message.get("params", {}).get("name") == "active_observation"
                            and response["result"].get("isError") is False):
                        content = response["result"].get("content", [])
                        if content and content[0].get("type") == "text":
                            self.session.namespace["last_observation_json"] = content[0]["text"]
                except BaseException as exception:
                    self.serve_errors.append({"type": type(exception).__name__, "message": str(exception)})
                    if not sent:
                        reply = {"request_id": outer.get("request_id"), "ok": False, "error": type(exception).__name__}
                        try:
                            connection.sendall(encoded(reply) + b"\n")
                        except OSError:
                            pass
            sequence = len(self.transports) + 1
            folder = self.output / ("rpc_" + str(sequence).zfill(3))
            folder.mkdir()
            (folder / "TCP_TX.bin").write_bytes(raw)
            if reply is not None:
                (folder / "TCP_RX.bin").write_bytes(encoded(reply) + b"\n")
            self.transports.append({"sequence": sequence, "started_ns": started,
                "closed_ns": time.perf_counter_ns(), "send_confirmed": sent,
                "request_bytes": len(raw), "response_bytes": None if reply is None else len(encoded(reply)) + 1})
            self.save()

    def close(self):
        self.stop.set()
        if self.listener is not None:
            self.listener.close()
        if self.thread is not None:
            self.thread.join(timeout=5)
        result = {"confirmed": self.thread is None or not self.thread.is_alive(),
                  "closed_ns": time.perf_counter_ns(), "errors": self.serve_errors,
                  "scope": "MCP listener and serving thread only. Owned runtime closure belongs to the root."}
        self.save()
        save(self.output / "CLOSE.json", result)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    options = parser.parse_args()
    config = json.loads(options.config.read_bytes())
    runtime_module = load("_target_task_owned_runtime", HERE / "owned_runtime.py")
    budget = runtime_module.Budget(Path(config["budget_root"]))
    runtime = owner = None
    errors = []
    try:
        runtime = runtime_module.RootRuntime.start(Path(config["runroot"]), config["phase"],
            config["label"], config["group"], deadline_ns=config["owned_deadline_ns"], budget=budget)
        runtime.set_consumer_deadline(config["worker_deadline_ns"])
        owner = Owner(runtime, config, budget)
        owner.start(config["endpoint"])
        save(config["ready"], {"actor_pid": os.getpid(), "actor_parent_pid": os.getppid(),
            "ready_ns": time.perf_counter_ns(), "worker_deadline_ns": config["worker_deadline_ns"],
            "owned_deadline_ns": config["owned_deadline_ns"], "endpoint": config["endpoint"],
            "runtime": runtime.snapshot()})
        sys.stdin.readline()
    except BaseException as exception:
        errors.append({"type": type(exception).__name__, "message": str(exception), "traceback": traceback.format_exc()})
        raise
    finally:
        bridge_close = None if owner is None else owner.close()
        runtime_close = None if runtime is None else runtime.close()
        save(Path(config["runroot"]) / "ACTOR_CLOSE.json", {"actor_pid": os.getpid(),
            "closed_ns": time.perf_counter_ns(), "bridge": bridge_close,
            "runtime": runtime_close, "errors": errors})


if __name__ == "__main__":
    main()
