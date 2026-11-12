"""Reviewable, project-local source-checkout configuration for agent hosts.

This writes host configuration only. It does not install packages, approve host
trust, contact Blender, or alter persisted spatial authority.
"""
from __future__ import annotations

import argparse
import base64
import copy
from dataclasses import dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import sys
import tempfile
import uuid

try:
    import tomllib
except ImportError:  # Python 3.10 can append or recognize our exact own section.
    tomllib = None


SERVER_NAME = "human_eye_live"
TRANSFORM_MATCHER = "^mcp__human_eye_live__human_eye_transform$"
CLEARANCE_SEGMENT_MATCHER = "^mcp__human_eye_live__human_eye_clearance_segment$"
MAX_CONFIG_BYTES = 8 * 1024 * 1024
MAX_STATE_BYTES = 32 * 1024 * 1024


class AgentSetupError(ValueError):
    """Configuration is incompatible, ambiguous, or changed during setup."""


def _path_text(value):
    text = os.fspath(value)
    if not isinstance(text, str) or not text or any(c in text for c in "\x00\r\n"):
        raise AgentSetupError("Paths must be nonempty and cannot contain NUL or line breaks")
    return text


def _json_object(raw, label):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise AgentSetupError("Duplicate JSON key in " + label + ": " + key)
            result[key] = value
        return result

    def invalid(value):
        raise AgentSetupError("Nonfinite JSON number in " + label)

    try:
        value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=pairs, parse_constant=invalid)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AgentSetupError("Invalid JSON in " + label) from exc
    if not isinstance(value, dict):
        raise AgentSetupError(label + " must contain a JSON object")
    return value


def _encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _read(path, limit=MAX_CONFIG_BYTES):
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > limit:
        raise AgentSetupError("Configuration is not a bounded regular file: " + str(path))
    return path.read_bytes()


def _project_path(project, relative):
    path = project / relative
    try:
        path.resolve().relative_to(project)
    except ValueError as exc:
        raise AgentSetupError("Configuration path escapes the target project: " + str(path)) from exc
    # Avoid changing a different checkout through a linked settings directory.
    for part in (path, *path.parents):
        if part == project:
            break
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise AgentSetupError("Linked configuration paths are not supported: " + str(part))
    return path


def _same_path(left, right):
    return isinstance(left, str) and os.path.normcase(str(Path(left).resolve())) == os.path.normcase(str(Path(right).resolve()))


def _fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _positive_number(value, label, *, integer=False):
    try:
        valid = type(value) in ((int,) if integer else (int, float)) and math.isfinite(value) and value > 0
    except OverflowError:
        valid = False
    if not valid:
        raise AgentSetupError(label + " must be a positive " + ("integer" if integer else "number"))


def _validate_connector(config, config_path, project, engine_root):
    if config.get("schema_version") != "1.0":
        raise AgentSetupError("Unsupported live connector schema")
    for key in ("enabled", "observe_on_prompt"):
        if key in config and type(config[key]) is not bool:
            raise AgentSetupError(key + " must be boolean")
    base = config_path.parent

    def configured_path(key):
        value = config.get(key)
        if not isinstance(value, str):
            raise AgentSetupError("Missing connector path: " + key)
        return (base / _path_text(value)).resolve()

    if configured_path("project_root") != engine_root:
        raise AgentSetupError("Existing connector project_root must resolve to the selected engine source checkout")
    state_path = configured_path("state_file")
    audit_path = configured_path("audit_file")
    sidecars = [path.with_name(path.name + ".lock") for path in (state_path, audit_path)]
    if len({state_path, audit_path, config_path, *sidecars}) != 5:
        raise AgentSetupError("Connector configuration, state, audit and lock paths must be distinct")
    reserved = {project / ".human-eye/mcp-client.json", project / ".human-eye/setup.lock"}
    for target in (state_path, audit_path):
        try:
            relative = target.relative_to(project)
        except ValueError as exc:
            raise AgentSetupError("Connector state/audit must stay inside the target project") from exc
        _project_path(project, relative)
        if len(relative.parts) < 2 or relative.parts[0] != ".human-eye":
            raise AgentSetupError("Connector state/audit must stay inside the project's .human-eye directory")
        if relative.parts[1:2] == ("setup-backups",) or target in reserved or target.with_name(target.name + ".lock") in reserved:
            raise AgentSetupError("Connector state/audit overlaps setup files")
        if target.exists() and not target.is_file():
            raise AgentSetupError("Connector state/audit must be regular files")
    connection = config.get("blender", {})
    if not isinstance(connection, dict) or connection.get("host", "127.0.0.1") not in {"127.0.0.1", "localhost", "::1"}:
        raise AgentSetupError("The source connector must use a loopback Blender host")
    port = connection.get("port", 9876)
    if type(port) is not int or not 1 <= port <= 65535:
        raise AgentSetupError("Blender port must be an integer between 1 and 65535")
    _positive_number(connection.get("timeout_s", 10), "timeout_s")
    for key, default in (("quad_size", 384), ("max_sessions", 16)):
        _positive_number(config.get(key, default), key, integer=True)
    _positive_number(config.get("readback_atol_m", 1e-6), "readback_atol_m")
    state_raw = _read(state_path, MAX_STATE_BYTES)
    if state_raw is not None:
        state = _json_object(state_raw, "live connector state")
        if state.get("schema_version") != "1.0" or state.get("config_fingerprint") != _fingerprint(config):
            raise AgentSetupError("Persisted live state does not match this connector; review it separately")
        if not isinstance(state.get("runtime"), dict) or "inflight" not in state:
            raise AgentSetupError("Persisted live state is incomplete; setup cannot reset host authority")
        if state["inflight"] is not None:
            raise AgentSetupError("A host operation is pending; resolve it before changing agent configuration")


def _powershell_literal(value):
    return "'" + _path_text(value).replace("'", "''") + "'"


def _hook_spec(argv, agent, platform):
    """Return native host hook fields and a readable launch explanation."""
    if agent == "claude":
        # Current Claude Code supports direct spawn when args is present.
        return {"type": "command", "command": argv[0], "args": argv[1:], "timeout": 30}, None
    if platform == "windows":
        script = "& " + " ".join(_powershell_literal(value) for value in argv) + "; exit $LASTEXITCODE"
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        shell = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        executable = str(shell) if shell.is_file() else "powershell.exe"
        # The shell path is OS-controlled, never a project-supplied fragment.
        command = '"' + executable + '" -NoProfile -NonInteractive -EncodedCommand ' + encoded
        # A bare executable path works in both cmd.exe and PowerShell. Quoting
        # is needed only for custom SystemRoot paths containing spaces.
        if not any(char.isspace() for char in executable):
            command = executable + " -NoProfile -NonInteractive -EncodedCommand " + encoded
        return {"type": "command", "command": command, "timeout": 30}, script
    return {"type": "command", "command": shlex.join(argv), "timeout": 30}, None


def _command_argv(hook, platform):
    """Recognize direct spawn, our encoded launcher, and simple legacy hooks.

    This only compares configuration. It never evaluates shell source.
    """
    command = hook.get("command")
    if not isinstance(command, str):
        return None
    if "args" in hook:
        args = hook["args"]
        return [command, *args] if isinstance(args, list) and all(isinstance(x, str) for x in args) else None
    marker = re.search(r"(?i)\s-EncodedCommand\s+([A-Za-z0-9+/=]+)\s*$", command)
    if marker:
        try:
            source = base64.b64decode(marker.group(1), validate=True).decode("utf-16-le")
        except (ValueError, UnicodeError):
            return None
        literal = r"'(?:[^']|'')*'"
        if re.fullmatch(r"&\s+" + literal + r"(?:\s+" + literal + r")*(?:;\s*exit\s+\$LASTEXITCODE)?", source):
            return [token[1:-1].replace("''", "'") for token in re.findall(literal, source)]
        return None
    # Legacy hooks are accepted only as a single literal invocation. A shell
    # pipeline or expression cannot be considered equivalent to direct spawn.
    if any(char in command for char in ";&|<>`$\r\n"):
        return None
    try:
        args = shlex.split(command, posix=platform != "windows")
    except ValueError:
        return None
    return [x[1:-1] if len(x) >= 2 and x[0] == x[-1] and x[0] in "\"'" else x for x in args]


def _same_hook(hook, spec, platform):
    if hook == spec:
        return True
    if hook.get("type") != "command" or hook.get("timeout") != spec["timeout"]:
        return False
    if set(hook) - {"type", "command", "args", "timeout"}:
        return False
    left, right = _command_argv(hook, platform), _command_argv(spec, platform)
    if left is None or right is None or len(left) != len(right):
        return False
    return all(_same_path(a, b) if i in {0, 2, 7} else a == b for i, (a, b) in enumerate(zip(left, right)))


def _owned_hook(hook, platform):
    command = hook.get("command", "")
    fragments = [command] if isinstance(command, str) else []
    args = _command_argv(hook, platform) or hook.get("args", [])
    if isinstance(args, list):
        fragments.extend(str(arg) for arg in args)
    # Even an unrecognized shell wrapper must not hide a conflicting engine
    # command merely by encoding its source. Decoding is never evaluation.
    marker = re.search(r"(?i)\s-EncodedCommand\s+([A-Za-z0-9+/=]+)\s*$", command) if isinstance(command, str) else None
    if marker:
        try:
            fragments.append(base64.b64decode(marker.group(1), validate=True).decode("utf-16-le"))
        except (ValueError, UnicodeError):
            pass
    return any(needle in fragment for fragment in fragments for needle in (
        "live_entry.py", "human_eye_plugin.live_hooks", "human_eye_plugin.agent_hooks",
        "human_eye_hook.py", "human_eye_hook", "human-eye-hook"))


def _merge_hooks(document, spec, entry_path, platform, *, event_specs=None):
    hooks = document.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise AgentSetupError("Existing hooks must be an object")
    changed = False
    for event in ("UserPromptSubmit", "PreToolUse", "PostToolUse"):
        desired = (event_specs or {}).get(event, spec)
        # A working pre-bootstrap registration has no trusted --event flag.
        # Retain it exactly; setup must not silently upgrade or duplicate it.
        def compatible(hook):
            return _same_hook(hook, desired, platform) or _same_hook(hook, spec, platform)
        matchers = (None,) if event == "UserPromptSubmit" else (TRANSFORM_MATCHER, CLEARANCE_SEGMENT_MATCHER)
        groups = hooks.setdefault(event, [])
        if not isinstance(groups, list):
            raise AgentSetupError("Existing " + event + " hooks must be an array")
        counts = {matcher: 0 for matcher in matchers}
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                raise AgentSetupError("Invalid existing hook group in " + event)
            matcher = group.get("matcher")
            matching_hooks = [hook for hook in group["hooks"] if isinstance(hook, dict) and compatible(hook)]
            if matcher in matchers and matching_hooks:
                if len(matching_hooks) > 1:
                    raise AgentSetupError("Duplicate Human-Eye hooks need review before setup")
                counts[matcher] += 1
            for hook in group["hooks"]:
                if not isinstance(hook, dict):
                    raise AgentSetupError("Invalid existing command hook")
                if matcher in matchers and compatible(hook):
                    continue
                # Existing same-server or source launchers must not silently
                # coexist with another engine/configuration for this event.
                if _owned_hook(hook, platform):
                    raise AgentSetupError("Conflicting Human-Eye " + event + " hook; review the existing entry")
        if any(count > 1 for count in counts.values()):
            raise AgentSetupError("Duplicate Human-Eye hooks need review before setup")
        for matcher, count in counts.items():
            if not count:
                expected = {"hooks": [dict(desired)]}
                if matcher is not None:
                    expected = {"matcher": matcher, **expected}
                groups.append(expected)
                changed = True
    return changed


def _append_hook_json(raw, before, after):
    """Apply append-only hook additions without reformatting existing bytes.

    This is not a general JSON editor: existing values cannot be changed or
    removed. Input has already passed strict duplicate-key/finite validation.
    Insertions are checked again against the exact planned document.
    """
    if raw is None:
        return _encode(after)
    text = raw.decode('utf-8')
    decoder = json.JSONDecoder()
    insertions = []

    def skip(position):
        while position < len(text) and text[position] in ' \t\r\n':
            position += 1
        return position

    def closing_insertion(start, end):
        position = end - 1
        while position > start + 1 and text[position - 1] in ' \t\r\n':
            position -= 1
        return position

    def encoded(value):
        return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))

    def same(left, right):
        if type(left) is not type(right):
            return False
        if isinstance(left, dict):
            return set(left) == set(right) and all(same(left[key], right[key]) for key in left)
        if isinstance(left, list):
            return len(left) == len(right) and all(same(a, b) for a, b in zip(left, right))
        return left == right

    def visit(old, new, start, end):
        if same(old, new):
            return
        if isinstance(old, list) and isinstance(new, list):
            if len(new) < len(old) or not same(new[:len(old)], old):
                raise AgentSetupError('Hook upgrade must not alter existing array entries')
            additions = new[len(old):]
            insertions.append((closing_insertion(start, end),
                               (',' if old else '') + ','.join(encoded(value) for value in additions)))
            return
        if isinstance(old, dict) and isinstance(new, dict):
            if set(old) - set(new):
                raise AgentSetupError('Hook upgrade must not remove existing keys')
            spans = {}
            position = skip(start + 1)
            while position < end - 1 and text[position] != '}':
                key, key_end = decoder.raw_decode(text, position)
                colon = skip(key_end)
                if text[colon] != ':':
                    raise AgentSetupError('Invalid hook JSON member')
                value_start = skip(colon + 1)
                _, value_end = decoder.raw_decode(text, value_start)
                spans[key] = (value_start, value_end)
                position = skip(value_end)
                if text[position] == ',':
                    position = skip(position + 1)
                elif text[position] != '}':
                    raise AgentSetupError('Invalid hook JSON object delimiter')
            for key in old:
                visit(old[key], new[key], *spans[key])
            additions = [(key, new[key]) for key in new if key not in old]
            if additions:
                insertions.append((closing_insertion(start, end), (',' if old else '') +
                    ','.join(encoded(key) + ':' + encoded(value) for key, value in additions)))
            return
        raise AgentSetupError('Hook upgrade must not replace existing values')

    start = skip(1 if text.startswith('\ufeff') else 0)
    parsed, end = decoder.raw_decode(text, start)
    if not same(parsed, before):
        raise AgentSetupError('Hook JSON changed while preparing additions')
    visit(before, after, start, end)
    for position, addition in sorted(insertions, reverse=True):
        text = text[:position] + addition + text[position:]
    result = text.encode('utf-8')
    if len(result) > MAX_CONFIG_BYTES or not same(_json_object(result, 'updated hooks'), after):
        raise AgentSetupError('Append-only hook plan failed verification')
    return result


def _server_matches(existing, expected):
    if not isinstance(existing, dict) or set(existing) != set(expected):
        return False
    for key, value in expected.items():
        actual = existing[key]
        if key in {"command", "cwd"}:
            if not _same_path(actual, value):
                return False
        elif key == "args":
            if not isinstance(actual, list) or len(actual) != len(value):
                return False
            for index, (left, right) in enumerate(zip(actual, value)):
                if index in {1, 4}:
                    if not _same_path(left, right):
                        return False
                elif left != right:
                    return False
        elif type(actual) is not type(value) or actual != value:
            return False
    return True


def _toml_section(server):
    lines = ["[mcp_servers.human_eye_live]"]
    for key, value in server.items():
        # JSON strings/arrays and booleans are valid basic TOML values here.
        lines.append(key + " = " + json.dumps(value, ensure_ascii=False, allow_nan=False))
    return "\n".join(lines) + "\n"


def _merge_toml(raw, server):
    try:
        text = raw.decode("utf-8-sig") if raw is not None else ""
    except UnicodeError as exc:
        raise AgentSetupError("Codex config.toml must be UTF-8") from exc
    section = _toml_section(server)
    if tomllib is not None:
        try:
            data = tomllib.loads(text)
        except ValueError as exc:
            raise AgentSetupError("Invalid Codex TOML configuration") from exc
        servers = data.get("mcp_servers", {})
        if not isinstance(servers, dict):
            raise AgentSetupError("mcp_servers must be a TOML table")
        if SERVER_NAME in servers:
            if not _server_matches(servers[SERVER_NAME], server):
                raise AgentSetupError("Conflicting mcp_servers.human_eye_live; existing configuration was preserved")
            return raw, False
    else:
        # Do not implement a partial general TOML parser on Python 3.10.
        own = re.search(r"(?m)^\s*\[\s*mcp_servers\s*\.\s*(?:human_eye_live|\"human_eye_live\"|'human_eye_live')\s*\]\s*(?:#.*)?$", text)
        if own:
            tail = text[own.end():]
            next_header = re.search(r"(?m)^\s*\[", tail)
            body = text[own.start():own.end()] + tail[:next_header.start() if next_header else len(tail)]
            if body.strip() != section.strip():
                raise AgentSetupError("Use Python 3.11+ to verify an existing noncanonical Human-Eye TOML section")
            return raw, False
        if text.strip():
            raise AgentSetupError("Use Python 3.11+ to verify an existing nonempty TOML configuration")
    # Appending preserves every original byte, including comments and CRLF.
    original = raw or b""
    addition = ("\n" if original and not original.endswith(b"\n") else "") + "\n" + section
    merged = original + addition.encode("utf-8")
    if tomllib is not None:
        try:
            tomllib.loads(merged.decode("utf-8-sig"))
        except ValueError as exc:
            raise AgentSetupError("Cannot safely append a server to this TOML layout") from exc
    return merged, True


def _atomic_bytes(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


@dataclass(frozen=True)
class FileChange:
    path: Path
    before: bytes | None
    after: bytes
    owned_configuration: dict = field(repr=False)


@dataclass
class SetupPlan:
    agent: str
    project: Path
    engine_root: Path
    python_path: Path
    changes: list[FileChange]
    hook_argv: list[str] | None = None
    hook_script: str | None = None
    preconditions: dict[Path, bytes | None] = field(default_factory=dict, repr=False)
    hook_argv_by_event: dict[str, list[str]] = field(default_factory=dict)
    hook_scripts_by_event: dict[str, str | None] = field(default_factory=dict)

    def _check_preconditions(self):
        for path, before in self.preconditions.items():
            _project_path(self.project, path.relative_to(self.project))
            if _read(path) != before:
                raise AgentSetupError("Configuration changed after planning: " + str(path))
        config_path = self.project / ".human-eye/live-connector.json"
        raw = _read(config_path)
        if raw is not None:
            _validate_connector(_json_object(raw, "live connector"), config_path, self.project, self.engine_root)

    def preview(self):
        return {"agent": self.agent, "project": str(self.project), "engine_root": str(self.engine_root),
                "python": str(self.python_path), "applied": False,
                "activation": "passive_mcp_only" if self.agent == "mcp" else "host_trust_review_required",
                "hook_argv": self.hook_argv, "hook_script": self.hook_script,
                "hook_argv_by_event": self.hook_argv_by_event,
                "hook_scripts_by_event": self.hook_scripts_by_event,
                "changes": [{"path": str(change.path), "operation": "create" if change.before is None else "update",
                             "before_sha256": hashlib.sha256(change.before).hexdigest() if change.before is not None else None,
                             "after_sha256": hashlib.sha256(change.after).hexdigest(),
                             "human_eye_configuration": change.owned_configuration} for change in self.changes]}

    def apply(self):
        """Apply the exact reviewed plan with local backups and rollback."""
        result = self.preview()
        self._check_preconditions()
        if not self.changes:
            return {**result, "applied": True, "backup_manifest": None}
        for change in self.changes:
            _project_path(self.project, change.path.relative_to(self.project))
            if _read(change.path) != change.before:
                raise AgentSetupError("Configuration changed after planning: " + str(change.path))
        backup_dir = _project_path(self.project, ".human-eye/setup-backups/" + uuid.uuid4().hex)
        lock_path = _project_path(self.project, ".human-eye/setup.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._check_preconditions()
            lock = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise AgentSetupError("Another project setup is active; review .human-eye/setup.lock") from exc
        os.close(lock)
        manifest_path = backup_dir / "manifest.json"
        manifest = {"schema_version": "1.0", "agent": self.agent, "status": "prepared", "files": []}
        written = []
        try:
            self._check_preconditions()
            for change in self.changes:
                relative = change.path.relative_to(self.project)
                record = {"path": relative.as_posix(), "existed": change.before is not None,
                          "before_sha256": hashlib.sha256(change.before).hexdigest() if change.before is not None else None,
                          "after_sha256": hashlib.sha256(change.after).hexdigest()}
                if change.before is not None:
                    _atomic_bytes(backup_dir / "files" / relative, change.before)
                manifest["files"].append(record)
            _atomic_bytes(manifest_path, _encode(manifest))
            for change in self.changes:
                _project_path(self.project, change.path.relative_to(self.project))
                if _read(change.path) != change.before:
                    raise AgentSetupError("Configuration changed while applying: " + str(change.path))
                _atomic_bytes(change.path, change.after)
                written.append(change)
            manifest["status"] = "applied"
            _atomic_bytes(manifest_path, _encode(manifest))
            return {**result, "applied": True, "backup_manifest": str(manifest_path)}
        except Exception as exc:
            rollback_errors = []
            for change in reversed(written):
                try:
                    _project_path(self.project, change.path.relative_to(self.project))
                    if _read(change.path) != change.after:
                        raise AgentSetupError("A concurrent edit prevents rollback: " + str(change.path))
                    if change.before is None:
                        change.path.unlink()
                    else:
                        _atomic_bytes(change.path, change.before)
                except Exception as rollback_exc:
                    rollback_errors.append(str(rollback_exc))
            manifest["status"] = "rollback_incomplete" if rollback_errors else "rolled_back"
            manifest["error_type"] = type(exc).__name__
            manifest["rollback_errors"] = rollback_errors
            try:
                _atomic_bytes(manifest_path, _encode(manifest))
            except OSError:
                pass
            raise AgentSetupError("Setup failed; " + manifest["status"] + ". Backup manifest: " + str(manifest_path)) from exc
        finally:
            lock_path.unlink(missing_ok=True)


def build_setup_plan(agent, project, *, python_path=None, engine_root=None, platform=None):
    """Prepare deterministic source integration without touching any files."""
    if agent not in {"codex", "claude", "mcp"}:
        raise AgentSetupError("Agent must be codex, claude or mcp")
    project = Path(_path_text(project)).resolve()
    engine_root = Path(_path_text(engine_root or Path(__file__).resolve().parents[1])).resolve()
    python_path = Path(_path_text(python_path or sys.executable)).resolve()
    if not project.is_dir():
        raise AgentSetupError("Target project directory must already exist")
    if not python_path.is_file():
        raise AgentSetupError("Selected Python executable does not exist")
    entry = engine_root / "examples/agents/live_entry.py"
    if not entry.is_file() or not (engine_root / "human_eye_plugin/live_service.py").is_file():
        raise AgentSetupError("Engine root must be a Human-Eye source checkout containing live_entry.py and live_service.py")
    platform = platform or ("windows" if os.name == "nt" else "posix")
    if platform not in {"windows", "posix"}:
        raise AgentSetupError("Platform must be windows or posix")
    changes = []
    preconditions = {}

    def read_configuration(path):
        raw = _read(path)
        preconditions[path] = raw
        return raw

    def add(path, before, after, owned):
        if before != after:
            changes.append(FileChange(path, before, after, owned))

    config_path = _project_path(project, ".human-eye/live-connector.json")
    raw = read_configuration(config_path)
    config = _json_object(raw, "live connector") if raw is not None else {
        "schema_version": "1.0", "enabled": True, "observe_on_prompt": True,
        "project_root": engine_root.as_posix(), "state_file": "live-state.json", "audit_file": "live-events.jsonl",
        "quad_size": 384, "max_sessions": 16, "readback_atol_m": 1e-6,
        "blender": {"host": "127.0.0.1", "port": 9876, "timeout_s": 10}}
    _validate_connector(config, config_path, project, engine_root)
    if raw is None:
        add(config_path, None, _encode(config), config)
    server = {"command": str(python_path), "args": ["-B", entry.as_posix(), "serve", "--config", config_path.as_posix()]}
    hook_argv = hook_script = None
    hook_argv_by_event, hook_scripts_by_event = {}, {}
    if agent == "codex":
        server = {"enabled": True, **server, "cwd": str(project), "startup_timeout_sec": 30, "tool_timeout_sec": 30}
        path = _project_path(project, ".codex/config.toml")
        before = read_configuration(path)
        after, _ = _merge_toml(before, server)
        add(path, before, after, {"mcp_servers": {SERVER_NAME: server}})
    else:
        path = _project_path(project, ".mcp.json" if agent == "claude" else ".human-eye/mcp-client.json")
        before = read_configuration(path)
        value = _json_object(before, path.name) if before is not None else {}
        servers = value.setdefault("mcpServers", {})
        if not isinstance(servers, dict):
            raise AgentSetupError("mcpServers must be an object")
        if SERVER_NAME in servers:
            if not _server_matches(servers[SERVER_NAME], server):
                raise AgentSetupError("Conflicting mcpServers.human_eye_live; existing configuration was preserved")
        else:
            servers[SERVER_NAME] = server
            add(path, before, _encode(value), {"mcpServers": {SERVER_NAME: server}})
    if agent != "mcp":
        hook_argv = [str(python_path), "-B", entry.as_posix(), "hook", "--agent", agent, "--config", config_path.as_posix()]
        spec, hook_script = _hook_spec(hook_argv, agent, platform)
        event_specs = {}
        for event in ("UserPromptSubmit", "PreToolUse", "PostToolUse"):
            # Keep --config last for old setup consumers; the event value is a
            # trusted command argument, never inferred from damaged stdin.
            argv = hook_argv[:-2] + ["--event", event] + hook_argv[-2:]
            event_specs[event], hook_scripts_by_event[event] = _hook_spec(argv, agent, platform)
            hook_argv_by_event[event] = argv
        path = _project_path(project, ".codex/hooks.json" if agent == "codex" else ".claude/settings.json")
        before = read_configuration(path)
        value = _json_object(before, path.name) if before is not None else {}
        previous = copy.deepcopy(value)
        if _merge_hooks(value, spec, entry, platform, event_specs=event_specs):
            add(path, before, _append_hook_json(before, previous, value), {"hooks": {event: [group for group in value["hooks"][event]
                if group.get("hooks") in ([event_specs[event]], [spec])]
                for event in ("UserPromptSubmit", "PreToolUse", "PostToolUse")}})
    return SetupPlan(agent, project, engine_root, python_path, changes, hook_argv, hook_script, preconditions,
                     hook_argv_by_event=hook_argv_by_event, hook_scripts_by_event=hook_scripts_by_event)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", choices=("codex", "claude", "mcp"), required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--python", dest="python_path", type=Path)
    parser.add_argument("--engine-root", type=Path)
    parser.add_argument("--apply", action="store_true", help="Write project-only settings after reviewing the dry run")
    args = parser.parse_args(argv)
    try:
        plan = build_setup_plan(args.agent, args.project, python_path=args.python_path, engine_root=args.engine_root)
        result = plan.apply() if args.apply else plan.preview()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (AgentSetupError, OSError) as exc:
        print(json.dumps({"applied": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
