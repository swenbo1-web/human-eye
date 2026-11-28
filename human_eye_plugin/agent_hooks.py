"""Text-only lifecycle hook bridge for structured 3D tools.

The agent host, not a model tool choice, invokes this command. Configuration
selects exact tool names; arbitrary shell/Python programs are never interpreted.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import copy
import errno
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any, Callable, Iterator


SUPPORTED_EVENTS = {"UserPromptSubmit", "PreToolUse", "PostToolUse", "PostToolUseFailure"}
MAX_JSON_BYTES = 32 * 1024 * 1024
MAX_SESSIONS = 32


class HookBridgeError(ValueError):
    """A hook input or configured connector does not satisfy its contract."""


class StateLockTimeoutError(HookBridgeError):
    """Only confirmed nonblocking state-lock contention exhausted its wait."""


def _read_object(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        raw = handle.read(MAX_JSON_BYTES + 1)
    if len(raw) > MAX_JSON_BYTES:
        raise HookBridgeError("JSON file exceeds the hook input limit")
    data = json.loads(raw.decode("utf-8-sig"), parse_constant=_reject_constant)
    if not isinstance(data, dict):
        raise HookBridgeError("JSON document must be an object")
    return data


def _reject_constant(value: str) -> None:
    raise HookBridgeError("Non-finite JSON numbers are not supported")


def _atomic_write(path: Path, data: dict[str, Any], *, _buffered: bool = False,
                  _commit_receipt: dict | None = None) -> None:
    if _commit_receipt is not None:
        _commit_receipt['status'] = 'not_committed'
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            if _buffered:
                # Callers opt in only after bounding the serialized state size.
                handle.write(json.dumps(data, ensure_ascii=False, allow_nan=False,
                                        separators=(",", ":")))
            else:
                json.dump(data, handle, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        if _commit_receipt is not None:
            _commit_receipt['status'] = 'unknown'
        os.replace(name, path)
        if _commit_receipt is not None:
            _commit_receipt['status'] = 'committed'
    finally:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass


@contextmanager
def _state_lock(state_path: Path, timeout_s: float = 10.0) -> Iterator[None]:
    """Lock a stable sidecar inode; never delete it while writers can exist."""
    lock_path = state_path.with_name(state_path.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        deadline = time.monotonic() + timeout_s
        while True:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                # Non-contention I/O failures retain their original identity.
                # A bad descriptor or device failure is not a busy connector.
                if exc.errno not in {errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK}:
                    raise
                if time.monotonic() >= deadline:
                    raise StateLockTimeoutError("Timed out waiting for the router state lock") from exc
                time.sleep(min(0.025, max(0., deadline - time.monotonic())))
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _path(base: Path, value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise HookBridgeError(field + " must be an explicit path in the local configuration")
    candidate = Path(value)
    return (candidate if candidate.is_absolute() else base / candidate).resolve()


def _context(event_name: str, text: str, *, deny: bool = False) -> dict[str, Any]:
    output: dict[str, Any] = {"hookEventName": event_name, "additionalContext": text}
    if deny:
        output.update(permissionDecision="deny", permissionDecisionReason=text)
    return {"hookSpecificOutput": output}


def _error_output(event: dict[str, Any], registered: bool, error: Exception) -> dict[str, Any]:
    # Do not echo arbitrary host arguments, file contents, or credentials.
    message = "Human-Eye routing unavailable (" + type(error).__name__ + ")."
    name = event.get("hook_event_name")
    if name == "PreToolUse" and registered:
        return _context("PreToolUse", message + " Registered spatial action was blocked; repair the connector and reobserve.", deny=True)
    if name in SUPPORTED_EVENTS and (registered or name == "UserPromptSubmit"):
        return _context(name, message + " No current spatial observation is certified.")
    return {}


def _get_dotted(data: Any, path: str) -> Any:
    for key in path.split("."):
        if not isinstance(data, dict) or key not in data:
            raise HookBridgeError("Configured action path is absent from structured tool input")
        data = data[key]
    return data


def _quarantine(envelope: dict[str, Any], reason: str, pending: dict[str, Any] | None = None) -> None:
    previous = envelope.get("last_snapshot") or {}
    revision = (pending or {}).get("scene_revision", previous.get("revision"))
    envelope["quarantine"] = {"revision": revision, "reason": reason}
    for saved in envelope["sessions"].values():
        if isinstance(saved, dict):
            saved.pop("observation_id", None)


def _snapshot_fingerprint(scene: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(scene, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def _action(tool_input: Any, mapping: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(tool_input, dict):
        raise HookBridgeError("Registered tool input must be a structured object")
    path = mapping.get("action_path")
    candidate = _get_dotted(tool_input, path) if path else tool_input
    if not isinstance(candidate, dict):
        raise HookBridgeError("Spatial action must be an object")
    if set(candidate) - {"focal_id", "reference_id", "translation", "rotation_euler_deg"}:
        raise HookBridgeError("Spatial action contains unsupported operation fields")
    # Require a pose delta instead of silently approving unrelated tool fields.
    if not any(key in candidate for key in ("translation", "rotation_euler_deg")):
        raise HookBridgeError("Spatial action requires a translation or rotation_euler_deg vector")
    action: dict[str, Any] = {}
    for key in ("translation", "rotation_euler_deg"):
        value = candidate.get(key, [0.0, 0.0, 0.0])
        if not isinstance(value, list) or len(value) != 3 or any(
            isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item)
            for item in value
        ):
            raise HookBridgeError(key + " must contain three finite numbers")
        action[key] = list(value)
    for key in ("focal_id", "reference_id"):
        value = candidate.get(key, mapping.get(key, config.get(key)))
        if value is not None:
            if not isinstance(value, str) or not value:
                raise HookBridgeError(key + " must be an object ID string")
            action[key] = value
    return action


def _default_router_factory(**kwargs: Any) -> Any:
    from .auto_router import HumanEyeAutoRouter
    return HumanEyeAutoRouter(**kwargs)


def route_hook_event(
    event: dict[str, Any],
    config: dict[str, Any],
    *,
    agent: str,
    config_dir: str | Path,
    router_factory: Callable[..., Any] | None = None,
    declared_spatial_tools: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Return host-compatible JSON; persist observations across hook processes.

    Paths come only from local configuration, never from the model's tool input.
    ``router_factory`` supports deterministic tests without an external model.
    """
    if agent not in {"codex", "claude"}:
        raise HookBridgeError("Unsupported hook host")
    if not isinstance(event, dict) or not isinstance(config, dict):
        raise HookBridgeError("Hook event and configuration must be objects")
    event_name = event.get("hook_event_name")
    if event_name not in SUPPORTED_EVENTS:
        return {}
    tools = config.get("spatial_tools", {})
    tool_name = event.get("tool_name")
    registered = isinstance(tools, dict) and isinstance(tool_name, str) and tool_name in tools
    declared = tool_name in declared_spatial_tools
    if event_name != "UserPromptSubmit" and not (registered or declared):
        return {}
    try:
        if not isinstance(tools, dict) or any(not isinstance(k, str) or not isinstance(v, dict) for k, v in tools.items()):
            raise HookBridgeError("spatial_tools must map exact tool names to mapping objects")
        if declared and not registered:
            raise HookBridgeError("Declared spatial tool has no configured mapping")
        session_id = event.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            raise HookBridgeError("A nonempty host session_id is required")
        session_key = agent + ":" + session_id
        base = Path(config_dir).resolve()
        scene_path = _path(base, config.get("scene_file"), "scene_file")
        state_path = _path(base, config.get("state_file"), "state_file")
        if scene_path == state_path:
            raise HookBridgeError("scene_file and state_file must be different files")
        with _state_lock(state_path):
            envelope = _read_object(state_path) if state_path.exists() else {"schema_version": "1.0", "sessions": {}, "router_state": None}
            if envelope.get("schema_version") != "1.0" or not isinstance(envelope.get("sessions"), dict):
                raise HookBridgeError("Router state envelope is incompatible")
            sessions = envelope["sessions"]
            saved = sessions.get(session_key, {})
            if not isinstance(saved, dict):
                raise HookBridgeError("Session state is malformed")
            saved = copy.deepcopy(saved)
            factory = router_factory or _default_router_factory
            router = factory(mode=config.get("mode", "auto"), quad_size=config.get("quad_size", 128), observation_ttl_s=config.get("observation_ttl_s", 120), max_sessions=MAX_SESSIONS)
            if envelope.get("router_state") is not None:
                router.import_state(envelope["router_state"])
            try:
                scene = _read_object(scene_path)
            except Exception:
                _quarantine(envelope, "scene_snapshot_unavailable")
                _atomic_write(state_path, envelope)
                raise
            quarantine = envelope.get("quarantine")
            pending_calls = [item["pending"] for item in sessions.values() if isinstance(item, dict) and item.get("pending")]
            recovery_needed = bool(quarantine or pending_calls)
            recovery_revision = (quarantine or {}).get("revision")
            if recovery_revision is None and pending_calls:
                recovery_revision = pending_calls[0].get("scene_revision")
            if event_name == "PreToolUse" and quarantine:
                return _context("PreToolUse", "Human-Eye: connector is awaiting a fresh host scene revision and a new observation after an unverified operation or snapshot failure.", deny=True)
            if event_name == "UserPromptSubmit" and recovery_needed and scene.get("revision") == recovery_revision:
                return _context("UserPromptSubmit", "Human-Eye: the prior spatial action or snapshot is unverified. Publish a fresh host scene revision before reobserving; no current observation is certified.")
            routed_event: dict[str, Any] = {"session_id": session_key, "event": "before_model", "task_instruction": event.get("prompt", saved.get("task_instruction", ""))}
            for key in ("focal_id", "reference_id", "task_kind"):
                if key in config:
                    routed_event[key] = config[key]
            routed_event["scene"] = scene
            observation_id = saved.get("observation_id")
            if observation_id:
                routed_event["observation_id"] = observation_id
            if event_name == "UserPromptSubmit":
                saved["task_instruction"] = event.get("prompt", "")
                saved.pop("observation_id", None)
                routed_event.pop("observation_id", None)
            elif event_name == "PreToolUse":
                if any(isinstance(item, dict) and item.get("pending") for item in sessions.values()):
                    return _context("PreToolUse", "Human-Eye: another spatial tool call is awaiting host scene readback for this connector.", deny=True)
                tool_use_id = event.get("tool_use_id")
                if not isinstance(tool_use_id, str) or not tool_use_id:
                    raise HookBridgeError("tool_use_id is required for a registered spatial action")
                routed_event["event"] = "before_action"
                routed_event["task_kind"] = "spatial_3d"
                routed_event["action"] = _action(event.get("tool_input"), tools[tool_name], config)
                for key in ("focal_id", "reference_id"):
                    if key in routed_event["action"]:
                        routed_event[key] = routed_event["action"][key]
            else:
                routed_event["event"] = "after_action"
                routed_event["task_kind"] = "spatial_3d"
                pending = saved.get("pending")
                # A post hook cannot prove a scene readback unless it matches a
                # previously checked tool call and the connector published anew.
                if not isinstance(pending, dict) or pending.get("tool_use_id") != event.get("tool_use_id") or pending.get("tool_name") != tool_name:
                    saved.pop("observation_id", None)
                    saved["updated_at"] = time.time()
                    sessions[session_key] = saved
                    _quarantine(envelope, "unmatched_host_readback", pending if isinstance(pending, dict) else None)
                    envelope["router_state"] = router.export_state()
                    _atomic_write(state_path, envelope)
                    return _context(event_name, "Human-Eye: tool completed without a matching checked action receipt; host scene verification is unavailable. Publish a fresh scene snapshot and reobserve.")
                if event_name == "PostToolUseFailure" or scene is None or scene.get("revision") == pending.get("scene_revision"):
                    # Retain no receipt that could be reused to certify an
                    # unchanged snapshot after an actual host mutation.
                    saved.pop("observation_id", None)
                    saved.pop("pending", None)
                    saved["updated_at"] = time.time()
                    sessions[session_key] = saved
                    _quarantine(envelope, "host_readback_required", pending)
                    envelope["router_state"] = router.export_state()
                    _atomic_write(state_path, envelope)
                    return _context(event_name, "Human-Eye: host scene readback is missing, unchanged, or the tool failed. The completed operation is not certified. Publish a new scene revision and reobserve before another spatial action.")
                for key in ("focal_id", "reference_id"):
                    if key in pending:
                        routed_event[key] = pending[key]
            result = router.handle_event(routed_event)
            if not isinstance(result, dict):
                raise HookBridgeError("Router returned an invalid result")
            if result.get("route") == "blocked" and event_name == "PostToolUse":
                _quarantine(envelope, "host_readback_rejected", pending)
            if result.get("route") == "blocked" and "invalid_scene" in result.get("reason_codes", []):
                _quarantine(envelope, "invalid_scene")
            if event_name == "PreToolUse" and (result.get("allow_action") is not True or result.get("route") != "engine"):
                deny = True
            else:
                deny = False
            if result.get("requires_reobserve"):
                saved.pop("observation_id", None)
            if (result.get("observation_id") and result.get("route") == "engine"
                    and result.get("requires_reobserve") is not True):
                if event_name in {"UserPromptSubmit", "PostToolUse"} and recovery_needed:
                    for old_saved in sessions.values():
                        old_saved.pop("pending", None)
                        old_saved.pop("observation_id", None)
                    saved.pop("pending", None)
                    envelope.pop("quarantine", None)
                saved["observation_id"] = result["observation_id"]
                saved["scene_revision"] = result.get("scene_revision")
                envelope["last_snapshot"] = {"revision": scene.get("revision"), "fingerprint": _snapshot_fingerprint(scene)}
            if event_name == "PreToolUse" and not deny:
                tool_use_id = event.get("tool_use_id")
                saved["pending"] = {"tool_use_id": tool_use_id, "tool_name": tool_name, "scene_revision": result.get("scene_revision")}
                for key in ("focal_id", "reference_id"):
                    if key in routed_event["action"]:
                        saved["pending"][key] = routed_event["action"][key]
            elif event_name in {"PostToolUse", "PostToolUseFailure"}:
                saved.pop("pending", None)
            saved["updated_at"] = time.time()
            sessions[session_key] = saved
            # Bounding bridge metadata also prevents a long-lived state file
            # from retaining a session history beyond the runtime's own bound.
            if len(sessions) > MAX_SESSIONS:
                oldest = sorted((key for key in sessions if not sessions[key].get("pending")), key=lambda key: sessions[key].get("updated_at", 0))
                for key in oldest[:len(sessions) - MAX_SESSIONS]:
                    del sessions[key]
            envelope["router_state"] = router.export_state()
            _atomic_write(state_path, envelope)
            if result.get("route") == "native" and not deny:
                return {}
            text = str(result.get("context_text") or "Human-Eye returned no current spatial observation.")
            # Native images cannot be conveyed by the documented additional-
            # context string; make this explicit instead of calling it vision.
            text += "\n[Hook delivery: text only; no engine image was delivered. Validation scope: supplied scene snapshot / terminal geometry; no swept-path or physical-host guarantee.]"
            return _context(event_name, text, deny=deny)
    except Exception as error:
        return _error_output(event, registered or declared, error)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", choices=("codex", "claude"), required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--spatial-tool", action="append", default=[], help="Exact registered tool name, also used if config cannot be loaded")
    args = parser.parse_args(argv)
    event: dict[str, Any] = {}
    try:
        raw = sys.stdin.buffer.read(MAX_JSON_BYTES + 1)
        if len(raw) > MAX_JSON_BYTES:
            raise HookBridgeError("Hook input exceeds the input limit")
        event = json.loads(raw.decode("utf-8-sig"), parse_constant=_reject_constant)
        if not isinstance(event, dict):
            raise HookBridgeError("Hook event must be an object")
        config_path = args.config.resolve()
        config = _read_object(config_path)
        if any(_path(config_path.parent, config.get(key), key) == config_path for key in ("scene_file", "state_file")):
            raise HookBridgeError("State and scene paths must not overwrite the configuration")
        output = route_hook_event(event, config, agent=args.agent, config_dir=config_path.parent, declared_spatial_tools=tuple(args.spatial_tool))
    except Exception as error:
        registered = isinstance(event, dict) and event.get("tool_name") in args.spatial_tool
        output = _error_output(event if isinstance(event, dict) else {}, registered, error)
    sys.stdout.write(json.dumps(output, ensure_ascii=False, allow_nan=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
