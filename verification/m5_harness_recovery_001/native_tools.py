"""Ordinary persistent consumer Python over a live owned runtime.

This adapter contains no region, coverage, visibility or task-answer algorithm.
The runtime owns current Blender reads and the shared raw-frame constructor.
"""

import contextlib
import ast
import builtins
import copy
from fractions import Fraction
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import threading
import time
from types import MappingProxyType


HERE = Path(__file__).resolve().parent
VIEW_NAMES = ("SCENE", "TOP", "LEFT", "RIGHT", "FRONT", "BACK")
PUBLIC_IMPORT_ROOTS = frozenset({"numpy", "PIL", "fractions", "shapely", "math", "cmath",
    "collections", "itertools", "functools", "operator", "json", "pathlib", "statistics",
    "decimal", "random", "re", "heapq", "bisect", "array", "copy", "dataclasses",
    "typing", "enum", "time", "hashlib", "struct", "zlib", "base64", "io", "csv",
    "bpy", "mathutils", "bmesh"})
PRIVATE_BUILTINS = frozenset({"globals", "locals", "vars", "eval", "exec", "compile",
                             "breakpoint", "input", "help"})


def validate_code(code):
    """Apply this experiment's common public-input and reflection boundary."""
    tree = ast.parse(code, filename="<consumer-python>", mode="exec")
    for node in ast.walk(tree):
        type_name = (isinstance(node, ast.Attribute) and node.attr == "__name__"
            and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "type" and len(node.value.args) == 1 and not node.value.keywords)
        if isinstance(node, ast.Attribute) and node.attr.startswith("_") and not type_name:
            raise PermissionError("consumer_private_attribute:" + node.attr)
        if isinstance(node, ast.Name) and (node.id in PRIVATE_BUILTINS or node.id == "__builtins__"):
            raise PermissionError("consumer_private_reflection:" + node.id)
        if isinstance(node, ast.Import):
            roots = [alias.name.split(".", 1)[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            roots = [node.module.split(".", 1)[0]] if node.module and not node.level else [""]
            if any(alias.name.startswith("_") for alias in node.names):
                raise PermissionError("consumer_private_import_attribute")
        else:
            roots = []
        if any(root not in PUBLIC_IMPORT_ROOTS for root in roots):
            raise PermissionError("consumer_module_outside_public_input_scope")
    return tree


def public_getattr(value, name, *default):
    if type(name) is not str or (name.startswith("_") and not (name == "__name__" and isinstance(value, type))):
        raise PermissionError("consumer_private_dynamic_attribute")
    return builtins.getattr(value, name, *default)


def public_hasattr(value, name):
    try:
        public_getattr(value, name)
    except AttributeError:
        return False
    return True


def public_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level or name.split(".", 1)[0] not in PUBLIC_IMPORT_ROOTS:
        raise PermissionError("consumer_module_outside_public_input_scope")
    fromlist = () if fromlist is None else fromlist
    if any(type(item) is not str or item.startswith("_") for item in fromlist):
        raise PermissionError("consumer_private_import_attribute")
    return builtins.__import__(name, globals, locals, fromlist, level)


def public_builtins():
    values = dict(builtins.__dict__)
    for name in PRIVATE_BUILTINS:
        values.pop(name, None)
    values.update(getattr=public_getattr, hasattr=public_hasattr, __import__=public_import)
    return values


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def save(path, value):
    Path(path).write_bytes(encoded(value) + b"\n")


class OrdinarySession:
    """Expose public data and retain Python variables between business calls."""

    def __init__(self, runtime, config):
        import numpy as np
        import PIL
        from PIL import Image
        import shapely

        self.runtime = runtime
        self.config = config
        self.deadline_ns = config["worker_deadline_ns"]
        self.scratch = Path(config["output"]).resolve() / "scratch"
        self.scratch.mkdir(exist_ok=True)
        self.attached_refs = []
        self.product_images = []
        self.product_calls = []
        self.audit = []
        self._scope = threading.local()
        self._scope.active = False
        dependency = json.loads((HERE / "SHARED_DEPENDENCY.json").read_bytes())
        self.read_roots = tuple(Path(path).resolve() for path in (
            sys.base_prefix, dependency["dependency_root"],
            "D:/he_anchor_001/venv/Lib/site-packages"))
        self.namespace = {
            "__name__": "__consumer_python__", "__builtins__": public_builtins(),
            "np": np, "Fraction": Fraction,
            "PIL": PIL, "Image": Image, "shapely": shapely,
            "cameras": {"views": [{key: copy.deepcopy(value) for key, value in pose.items()
                                      if key in ("name", "view_matrix", "projection_matrix", "size_px", "direction", "direction_rational")}
                                     for pose in runtime.cameras["views"]]},
            "buffers": MappingProxyType(runtime.buffers), "scratch": self.scratch,
            "blender": self.blender, "scene_data": self.scene_data,
            "render_views": self.render_views, "read_images": self.attach_images,
            "attach_images": self.attach_images, "last_observation_json": None,
            "observe": self.observe, "task": self.task, "last_task_json": None,
            "last_product_is_error": None,
        }
        sys.addaudithook(self._audit)

    def check(self):
        if time.perf_counter_ns() >= self.deadline_ns:
            raise TimeoutError("original_consumer_deadline")

    def _audit(self, event, arguments):
        if not getattr(self._scope, "active", False):
            return
        reason = None
        if event == "exec":
            filename = arguments[0].co_filename
            if filename.startswith("<"):
                return
            path = Path(filename).resolve()
            if not any(path.is_relative_to(root) for root in self.read_roots):
                reason = "consumer_private_code"
        elif event == "open" and isinstance(arguments[0], (str, bytes, os.PathLike)):
            path = Path(os.fsdecode(arguments[0])).resolve()
            mode, flags = arguments[1], arguments[2]
            writing = isinstance(mode, str) and any(char in mode for char in "wax+")
            writing = writing or bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            if not path.is_relative_to(self.scratch) and (
                    writing or not any(path.is_relative_to(root) for root in self.read_roots)):
                reason = "consumer_private_file"
        elif event in ("subprocess.Popen", "os.system", "os.startfile", "socket.connect", "ctypes.dlopen"):
            reason = "consumer_external_process_or_connection"
        if reason:
            self.audit.append({"event": event, "reason": reason, "at_ns": time.perf_counter_ns()})
            raise PermissionError(reason)

    @contextlib.contextmanager
    def trusted(self):
        active = getattr(self._scope, "active", False)
        self._scope.active = False
        try:
            self.check()
            yield
            self.check()
        finally:
            self._scope.active = active

    def blender(self, code, timeout=30):
        if type(code) is not str or type(timeout) not in (int, float) or not 0 < timeout <= 30:
            raise ValueError("ordinary_Blender_code_and_timeout")
        with self.trusted():
            validate_code(code)
            return self.runtime.native_run(code, timeout_s=timeout)

    def scene_data(self, selectors=None):
        if selectors is not None and (type(selectors) is not list or any(type(item) is not str for item in selectors)):
            raise ValueError("object_names_or_null")
        with self.trusted():
            return self.runtime.scene_data(selectors=selectors)

    def render_views(self, names, include_images=False, fresh=False):
        if (type(names) not in (list, tuple) or not names or len(names) > 6
                or any(name not in VIEW_NAMES for name in names)
                or type(include_images) is not bool or type(fresh) is not bool):
            raise ValueError("registered_views_and_boolean_options")
        with self.trusted():
            frames = self.runtime.render_views(list(names), fresh=fresh)
        if include_images:
            self.attach_images([frame["ref"] for frame in frames])
        return frames

    def attach_images(self, refs):
        if type(refs) not in (list, tuple) or not refs or len(refs) > 6 or any(type(ref) is not str for ref in refs):
            raise ValueError("current_image_references")
        with self.trusted():
            for ref in refs:
                self.runtime.image_specification(ref)
        self.attached_refs.extend(refs)
        return list(refs)

    def public_request(self, arguments, *, queue_images=False):
        """Execute one installed public request and retain its original result."""
        if type(arguments) is not dict:
            raise ValueError("public_observe_arguments_object")
        with self.trusted():
            started = time.perf_counter_ns()
            response = self.runtime.public_request(copy.deepcopy(arguments))
            result = response["result"] if "jsonrpc" in response else response
            text = [block["text"] for block in result.get("content", []) if block.get("type") == "text"]
            if len(text) != 1:
                raise ValueError("one_original_product_JSON_text_required")
            value = json.loads(text[0])
            self.namespace["last_product_is_error"] = result.get("isError", False)
            if arguments.get("query", {}).get("mode") == "task":
                self.namespace["last_task_json"] = text[0]
            else:
                self.namespace["last_observation_json"] = text[0]
            images = [block for block in result.get("content", []) if block.get("type") == "image"]
            if queue_images:
                self.product_images.extend(copy.deepcopy(images))
            self.product_calls.append({"sequence": len(self.product_calls) + 1,
                "public_response_id": response.get("id"), "arguments": copy.deepcopy(arguments),
                "started_ns": started, "closed_ns": time.perf_counter_ns(),
                "is_error": result.get("isError", False), "text_UTF8_bytes": len(text[0].encode("utf-8")),
                "public_JSON_sha256": hashlib.sha256(text[0].encode('utf-8')).hexdigest(),
                "image_blocks": len(images)})
        return result, value

    def observe(self, query=None, include_image=True):
        if (query is not None and type(query) is not dict) or type(include_image) is not bool:
            raise ValueError("public_query_object_and_image_boolean")
        arguments = {"session_id": "m5-harness-recovery-001", "include_image": include_image}
        arguments["query"] = copy.deepcopy(query) if query is not None else {
            'mode': 'active_observation', 'objects': [{'name': 'M4_Far_00'}]}
        _, value = self.public_request(arguments, queue_images=True)
        return value

    def task(self, query):
        if type(query) is not dict or query.get("mode") != "task":
            raise ValueError("original_task_query_required")
        return self.observe(query, include_image=False)

    def execute(self, code):
        if type(code) is not str:
            raise ValueError("python_code_string")
        self.check()
        stdout, stderr = io.StringIO(), io.StringIO()
        error = None
        self.attached_refs = []
        self.product_images = []
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            self._scope.active = True
            try:
                validate_code(code)
                exec(compile(code, "<consumer-python>", "exec"), self.namespace, self.namespace)
            except BaseException as exception:
                error = {"type": type(exception).__name__, "message": str(exception)}
                if isinstance(exception, PermissionError):
                    self.audit.append({"event": "consumer_code_boundary", "reason": str(exception),
                                       "at_ns": time.perf_counter_ns()})
            finally:
                self._scope.active = False
        self.check()
        return {"stdout": stdout.getvalue(), "stderr": stderr.getvalue(), "error": error}
