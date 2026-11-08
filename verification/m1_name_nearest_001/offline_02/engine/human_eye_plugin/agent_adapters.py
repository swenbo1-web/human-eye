"""Convert automatic-router observations to SDK-independent agent input data.

These adapters prepare messages; they neither call a model nor install a hook.
The host must invoke ``before_model`` before every relevant model invocation,
and separately enforce the router's action decision at its execution boundary.
"""
from __future__ import annotations

import base64
import binascii
import copy
import io
import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol, Union


SUPPORTED_FORMATS = (
    "openai_responses", "openai_chat", "anthropic", "gemini", "mcp",
)
_SUPPORTED_MIME_FORMATS = {
    "image/png": "PNG",
    "image/jpeg": "JPEG",
    "image/webp": "WEBP",
    "image/gif": "GIF",
}
_OBSERVATION_FIELDS = (
    "schema_version", "event", "session_id", "route", "reason_codes",
    "scene_revision", "scene_fingerprint", "observation_id", "cache_hit",
    "engine_invoked", "allow_action", "measurement_valid", "axes_valid",
    "rigid_frame_valid", "rigid_frame", "legacy_axes_validation_scope",
    "requires_reobserve", "execution_scope",
)


class RouterProtocol(Protocol):
    def handle_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """Return the versioned automatic-routing result."""
        ...


def _validate_format(format: str) -> None:
    if not isinstance(format, str) or format not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported agent format {format!r}; expected {SUPPORTED_FORMATS}")


def _validated_image(image: Any) -> tuple[str, str] | None:
    if image is None:
        return None
    if not isinstance(image, Mapping) or image.get("type") != "image":
        raise ValueError("image must be an image content block or None")
    mime_type = image.get("mimeType")
    data = image.get("data")
    if not isinstance(mime_type, str) or mime_type not in _SUPPORTED_MIME_FORMATS:
        raise ValueError("image.mimeType must be PNG, JPEG, WebP, or GIF")
    if not isinstance(data, str) or not data:
        raise ValueError("image.data must be a nonempty base64 string")
    try:
        decoded = base64.b64decode(data, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("image.data is not valid base64") from exc
    if not decoded:
        raise ValueError("image.data decodes to empty bytes")

    # Pillow is already an engine dependency. Verify the actual file so valid
    # base64 text or a mislabeled MIME type is never reported as a sent image.
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(decoded)) as parsed:
            if parsed.format != _SUPPORTED_MIME_FORMATS[mime_type]:
                raise ValueError("image MIME type does not match its file contents")
            if getattr(parsed, "is_animated", False):
                raise ValueError("animated images are not supported by this adapter")
            parsed.verify()
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise ValueError("image.data is not a valid image file") from exc
    return mime_type, data


def _image_block(format: str, mime_type: str, data: str) -> dict[str, Any]:
    data_url = f"data:{mime_type};base64,{data}"
    if format == "openai_responses":
        return {"type": "input_image", "image_url": data_url}
    if format == "openai_chat":
        return {"type": "image_url", "image_url": {"url": data_url}}
    if format == "anthropic":
        return {"type": "image", "source": {
            "type": "base64", "media_type": mime_type, "data": data,
        }}
    if format == "gemini":
        return {"inline_data": {"mime_type": mime_type, "data": data}}
    return {"type": "image", "mimeType": mime_type, "data": data}


def build_agent_observation(
    route_result: Mapping[str, Any],
    format: str = "openai_responses",
    supports_images: bool = True,
) -> dict[str, Any]:
    """Build additional observation messages and explicit delivery metadata.

    ``native`` returns empty additions. Other routes contain a JSON data
    document in a user message, never a system or assistant instruction. Only
    the routing metadata and ``context_text`` are included: arbitrary action,
    answer, or evaluation fields from callers are not forwarded.

    Gemini uses generateContent REST ``parts`` / ``inline_data``. MCP's
    ``content`` is a ToolResult content list; its ``messages`` member is only a
    host-neutral user envelope, not a complete MCP wire message.
    """
    _validate_format(format)
    if not isinstance(supports_images, bool):
        raise TypeError("supports_images must be a boolean")
    if not isinstance(route_result, Mapping):
        raise TypeError("route_result must be a mapping")
    if route_result.get("schema_version") != "1.0":
        raise ValueError("Unsupported router schema_version; expected '1.0'")
    route = route_result.get("route")
    if route not in ("native", "engine", "blocked"):
        raise ValueError("route must be 'native', 'engine', or 'blocked'")
    delivery = {
        "format": format,
        "route": route,
        "image_available": False,
        "image_delivered": False,
        "degraded_to_text": False,
    }
    if route == "native":
        return {"messages": [], "content": [], "delivery": delivery}

    context_text = route_result.get("context_text", "")
    if not isinstance(context_text, str):
        raise ValueError("context_text must be a string")
    reason_codes = route_result.get("reason_codes", [])
    if not isinstance(reason_codes, list) or any(not isinstance(v, str) for v in reason_codes):
        raise ValueError("reason_codes must be a list of strings")
    image = _validated_image(route_result.get("image"))
    delivery["image_available"] = image is not None
    delivery["image_delivered"] = image is not None and supports_images
    delivery["degraded_to_text"] = image is not None and not supports_images

    observation = {
        "kind": "human_eye_3d_observation",
        "routing": {key: copy.deepcopy(route_result[key]) for key in _OBSERVATION_FIELDS
                    if key in route_result},
        "observation_text": context_text,
        "image_delivery": (
            "included" if delivery["image_delivered"] else
            "omitted_host_does_not_support_images" if delivery["degraded_to_text"] else
            "not_available"
        ),
    }
    # JSON containment preserves scene strings as data. No target action or
    # benchmark answer is synthesized here, and no original task is replaced.
    text = json.dumps(observation, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    if format == "gemini":
        content = [{"text": text}]
    else:
        content = [{"type": "input_text" if format == "openai_responses" else "text", "text": text}]
    if delivery["image_delivered"]:
        content.append(_image_block(format, *image))
    message = {"role": "user", "parts" if format == "gemini" else "content": content}
    return {"messages": [message], "content": copy.deepcopy(content), "delivery": delivery}


class AgentRuntimeAdapter:
    """A synchronous boundary usable by custom loops and framework callbacks.

    The router can expose ``handle_event`` or be a callable. The host owns the
    model invocation, credentials, request limits, asynchronous scheduling, and
    actual tool execution. Preparing a blocked observation does not enforce a
    block in a tool executor; the executor must separately inspect routing.
    """

    def __init__(
        self,
        router: Union[RouterProtocol, Callable[[dict[str, Any]], Mapping[str, Any]]],
        format: str = "openai_responses",
        supports_images: bool = True,
    ) -> None:
        _validate_format(format)
        if not isinstance(supports_images, bool):
            raise TypeError("supports_images must be a boolean")
        handle_event = getattr(router, "handle_event", None)
        if callable(handle_event):
            self._route_event = handle_event
        elif callable(router):
            self._route_event = router
        else:
            raise TypeError("router must expose handle_event(event) or be a callable")
        self.format = format
        self.supports_images = supports_images

    def before_model(
        self,
        event: Mapping[str, Any],
        messages: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Route once and append observations without mutating caller inputs."""
        if not isinstance(event, Mapping):
            raise TypeError("event must be a mapping")
        if event.get("event") != "before_model":
            raise ValueError("before_model requires event='before_model'; route action events separately")
        if not isinstance(messages, Sequence) or isinstance(messages, (str, bytes)):
            raise TypeError("messages must be a sequence of message mappings")
        if any(not isinstance(message, Mapping) for message in messages):
            raise TypeError("messages must contain only message mappings")
        original = copy.deepcopy(list(messages))
        routing = copy.deepcopy(self._route_event(copy.deepcopy(dict(event))))
        observation = build_agent_observation(routing, self.format, self.supports_images)
        return {
            "routing": routing,
            "messages": original + observation["messages"],
            "delivery": observation["delivery"],
        }


__all__ = ["SUPPORTED_FORMATS", "RouterProtocol", "build_agent_observation", "AgentRuntimeAdapter"]
