"""One resident MCP connection for a host-bound local Blender task."""

import base64
from collections.abc import Callable
from dataclasses import dataclass
import json
from math import isfinite


PROTOCOL_VERSION = "2025-06-18"


@dataclass(slots=True)
class Binding:
    """Host-owned task factory and optional connection-owned render/close factory."""

    moving_id: str
    reference_id: str
    open_task: Callable
    open_renderer: Callable | None = None
    labels: tuple[str, str] | None = None
    default_image_mode: str = "NATURAL"


def _schema(properties, required):
    return {"type": "object", "properties": properties, "required": list(required),
            "additionalProperties": False}


_MODES = ("NATURAL", "SECTION")
_IMAGE_MODE = {"type": "string", "enum": list(_MODES)}
_RUN = {
    "task": {"type": "string", "enum": ["close_gap"]},
    "target_gap_m": {"type": "number", "minimum": 0},
    "tolerance_m": {"type": "number", "minimum": 0},
    "image_mode": _IMAGE_MODE,
}
_INSPECT = {
    "task_id": {"type": "string"},
    "evidence": {"type": "string", "enum": ["directory", "result", "witness", "image", "camera"]},
    "image_mode": _IMAGE_MODE,
}
_TOOLS = [
    {"name": "eye_run", "description": "Move the bound rigid surface toward the bound reference to reach a target gap in meters. Execute at most one translation and verify the actual gap.",
     "inputSchema": _schema(_RUN, ("task", "target_gap_m", "tolerance_m"))},
    {"name": "eye_inspect", "description": "Read the bound object directory, or pass the latest task_id to recover its result, witness, PNG or current image camera metadata.",
     "inputSchema": _schema(_INSPECT, ("evidence",)), "annotations": {"readOnlyHint": True}},
]


def _rpc(request_id, result=None, *, code=None, message=None):
    envelope = {"jsonrpc": "2.0", "id": request_id}
    if code is None:
        envelope["result"] = result
    else:
        envelope["error"] = {"code": code, "message": message}
    return json.dumps(envelope, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("ascii") + b"\n"


def _invalid_constant(value):
    raise ValueError(value)


def _nonnegative(value):
    if type(value) not in (int, float):
        raise ValueError("Gap and tolerance must be finite nonnegative numbers in meters")
    try:
        value = float(value)
    except OverflowError:
        raise ValueError("Gap and tolerance must be finite nonnegative numbers in meters") from None
    if not isfinite(value) or value < 0:
        raise ValueError("Gap and tolerance must be finite nonnegative numbers in meters")
    return value


def _gap(readback):
    return readback.surface.distance_m if readback is not None and isfinite(readback.surface.distance_m) else None


def _result(fields, *, error=False, image=None):
    text = json.dumps(fields, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    content = [{"type": "text", "text": text}]
    if image is not None:
        content.append(image)
    return {"content": content, "isError": error}


def _observation(readback):
    return {"observation_id": readback.observation_id, "frame_id": readback.frame_id}


def _witness(readback):
    surface = readback.surface
    return {"gap_m": surface.distance_m, "moving_point_m": surface.point_a,
            "reference_point_m": surface.point_b, "moving_triangle": surface.triangle_a,
            "reference_triangle": surface.triangle_b}


class LLMEntry:
    """Serialize task execution and retain evidence for only the latest task."""

    def __init__(self, binding):
        self._binding = binding
        self._initializing = self._ready = self._closed = False
        self._session = self._parameters = None
        self._task_id = self._receipt = self._readback = self._image = self._renderer = None
        self._count = self._image_count = 0

    def close(self):
        self._closed = True
        session, self._session = self._session, None
        renderer, self._renderer = self._renderer, None
        self._task_id = self._receipt = self._readback = self._image = None
        try:
            if renderer is not None:
                renderer.close()
        finally:
            if session is not None:
                session.close()

    def _task_session(self, parameters):
        if self._session is None or self._parameters != parameters:
            old, self._session = self._session, None
            if old is not None:
                old.close()
            self._session = self._binding.open_task(*parameters)
            self._parameters = parameters
        return self._session

    def _run(self, arguments):
        if arguments["task"] != "close_gap":
            raise ValueError("Unknown local task")
        target = _nonnegative(arguments["target_gap_m"])
        tolerance = _nonnegative(arguments["tolerance_m"])
        mode = arguments.get("image_mode")
        if "image_mode" in arguments and mode not in _MODES:
            raise ValueError("Choose NATURAL or SECTION for image_mode")
        if mode is not None and self._binding.open_renderer is None:
            return _result({"status": "rejected", "reason": "image_disabled", "write_status": "not_written"},
                           error=True)
        self._count += 1
        self._task_id = task_id = f"gap-{self._count}"
        self._receipt = self._readback = self._image = None
        fields = {"task_id": task_id, "task": "close_gap", "moving_id": self._binding.moving_id,
                  "reference_id": self._binding.reference_id, "unit": "m", "target_gap_m": target,
                  "tolerance_m": tolerance}
        try:
            session = self._task_session((target, tolerance))
        except Exception:
            return self._publish({**fields, "status": "error", "reason": "task_setup_failed",
                                  "write_status": "not_written"}, error=True)
        try:
            result = session.run(before_id=f"{task_id}-before", after_id=f"{task_id}-after")
        except Exception:
            return self._publish({**fields, "status": "error", "reason": "task_failed",
                                  "write_status": "unknown"}, error=True)

        before, outcome = result.before, result.outcome
        after = None if outcome is None else outcome.after
        known = after if after is not None else before if result.write_status == "not_written" else None
        initial, final = _gap(before), _gap(after)
        observed = _gap(known)
        if observed is not None and result.status != "error":
            self._readback = known
        measured_delta = None if outcome is None else tuple(
            value_after - value_before
            for value_before, value_after in zip(outcome.control_before, outcome.control_after)
        )
        fields.update({
            "status": result.status, "write_status": result.write_status,
            "goal_reached": observed is not None and abs(observed - target) <= tolerance,
            "before_gap_m": initial, "after_gap_m": final,
            "error_m": None if observed is None else abs(observed - target),
            "delta_world_m": None if result.command is None else result.command.delta_world_m,
            "actual_delta_world_m": measured_delta,
        })
        if result.reason is not None:
            fields["reason"] = result.reason
        if result.stage is not None:
            fields["stage"] = result.stage
        if known is not None:
            fields.update(_observation(known))
            if final is not None and result.status in {"error", "not_reached"}:
                fields["witness"] = _witness(known)
        error = result.status in {"rejected", "error"}
        image = None
        if mode is not None:
            info, image = self._render(mode)
            fields["image"] = info
            error |= image is None
        return self._publish(fields, error=error, image=image)

    def _publish(self, fields, *, error, image=None):
        response = _result(fields, error=error, image=image)
        self._receipt = fields, error
        return response

    def _render(self, mode):
        if self._image is not None and mode == self._image[0]:
            return self._image[1:3]
        block = camera = None
        if _gap(self._readback) is None:
            info = {"status": "unavailable", "reason": "no_measured_surface"}
        elif self._binding.open_renderer is None:
            info = {"status": "unavailable", "reason": "image_disabled"}
        else:
            try:
                if self._renderer is None:
                    self._renderer = self._binding.open_renderer()
                rendered = self._renderer.render(self._session, self._readback, mode)
                if rendered is None:
                    info = {"status": "unavailable", "reason": "image_unavailable"}
                else:
                    png, metadata = rendered
                    self._image_count += 1
                    info = {"status": "available", "mode": metadata["mode"],
                            "image_id": f"{self._task_id}-image-{self._image_count}",
                            "scene_object_ids": metadata["mesh_ids"], "section": metadata["section"],
                            "panels": ["scene_context", "witness"]}
                    camera = {"meters_per_blender_unit": metadata["meters_per_blender_unit"],
                              "views": metadata["views"]}
                    block = {"type": "image", "mimeType": "image/png", "data": base64.b64encode(png).decode("ascii")}
            except Exception:
                info = {"status": "unavailable", "reason": "image_capture_failed"}
                block = camera = None
        self._image = mode, info, block, camera
        return info, block

    def _inspect(self, arguments):
        evidence = arguments["evidence"]
        if evidence == "directory" and arguments.keys() == {"evidence"}:
            ids = (self._binding.moving_id, self._binding.reference_id)
            labels = self._binding.labels or ids
            return _result({"status": "available", "evidence": evidence, "unit": "m",
                            "tasks": ["close_gap"], "objects": [
                                {"id": key, "name": label, "role": role}
                                for key, label, role in zip(ids, labels, ("moving", "reference"))]})
        task_id = arguments.get("task_id")
        if not isinstance(task_id, str) or task_id != self._task_id:
            raise ValueError("Evidence is retained only for the latest task")
        if evidence not in ("result", "witness", "image", "camera"):
            raise ValueError("Unknown evidence kind")
        if "image_mode" in arguments and (evidence != "image" or arguments["image_mode"] not in _MODES):
            raise ValueError("Choose NATURAL or SECTION for image evidence")
        if evidence == "result":
            if self._receipt is None:
                return _result({"status": "unavailable", "task_id": task_id, "reason": "no_current_result"})
            fields, error = self._receipt
            return _result(fields, error=error)
        readback = self._readback
        header = {"task_id": task_id, "evidence": evidence, "unit": "m",
                  "moving_id": self._binding.moving_id, "reference_id": self._binding.reference_id}
        if _gap(readback) is None:
            return _result({"status": "unavailable", **header, "reason": "no_measured_surface"})
        header.update(_observation(readback))
        if evidence == "witness":
            return _result({"status": "available", **header, **_witness(readback)})
        if evidence == "camera":
            if self._image is None or self._image[3] is None:
                return _result({"status": "unavailable", **header, "reason": "no_current_image"})
            _, info, _, camera = self._image
            return _result({**header, **info, **camera})
        preferred = self._binding.default_image_mode if self._image is None else self._image[0]
        info, image = self._render(arguments.get("image_mode", preferred))
        return _result({**header, **info}, image=image)

    def handle_line(self, line):
        """Parse one UTF-8 JSON-RPC frame and return at most one framed response."""
        try:
            request = json.loads(line.decode("utf-8"), parse_constant=_invalid_constant)
        except (ValueError, RecursionError):
            return _rpc(None, code=-32700, message="Invalid UTF-8 JSON")
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0" or not isinstance(request.get("method"), str):
            return _rpc(None, code=-32600, message="Invalid JSON-RPC request")
        method = request["method"]
        if "id" not in request:
            if method == "notifications/initialized" and self._initializing:
                self._ready = True
            return None
        request_id = request["id"]
        if type(request_id) not in (int, str):
            return _rpc(None, code=-32600, message="Invalid JSON-RPC request ID")
        params = request.get("params", {})
        if not isinstance(params, dict):
            return _rpc(request_id, code=-32602, message="Parameters must be an object")
        if self._closed:
            return _rpc(request_id, code=-32002, message="MCP connection closed")
        if method == "initialize":
            if self._initializing or not isinstance(params.get("protocolVersion"), str):
                return _rpc(request_id, code=-32602, message="Invalid initialize request")
            self._initializing = True
            return _rpc(request_id, {"protocolVersion": PROTOCOL_VERSION, "capabilities": {"tools": {}},
                                     "serverInfo": {"name": "human-eye-entry", "version": "1.0"}})
        if method == "ping":
            return _rpc(request_id, {})
        if not self._ready:
            return _rpc(request_id, code=-32002, message="Initialize the MCP connection first")
        if method == "tools/list":
            if "cursor" in params:
                return _rpc(request_id, code=-32602, message="There is no next tool page")
            return _rpc(request_id, {"tools": _TOOLS})
        if method != "tools/call":
            return _rpc(request_id, code=-32601, message="Unknown method")
        name, arguments = params.get("name"), params.get("arguments", {})
        if name == "eye_run":
            schema, call = _RUN, self._run
        elif name == "eye_inspect":
            schema, call = _INSPECT, self._inspect
        else:
            return _rpc(request_id, code=-32602, message="Unknown tool")
        required = {"task", "target_gap_m", "tolerance_m"} if name == "eye_run" else {"evidence"}
        if (not isinstance(arguments, dict) or not required <= arguments.keys()
                or not arguments.keys() <= schema.keys()):
            result = _result({"status": "error", "reason": "invalid_tool_arguments"}, error=True)
        else:
            try:
                result = call(arguments)
            except ValueError as error:
                result = _result({"status": "error", "reason": str(error)}, error=True)
            except Exception:
                result = _result({"status": "error", "reason": "tool_failed"}, error=True)
        return _rpc(request_id, result)
