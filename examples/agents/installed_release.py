"""Review and activate one already installed Human-Eye release, without host IO.

Run with the target venv's Python -I -B. This independent administration tool
does not install dependencies, contact Blender, grant host trust, or reload an
existing agent process. doctor/plan perform no filesystem writes.
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
from importlib import util as importlib_util
import json
import math
import os
from pathlib import Path
import re
import sys
import uuid

import human_eye_hook
import human_eye_plugin
from human_eye_plugin import runtime_identity as identity_module
from human_eye_plugin.agent_hooks import _state_lock
from human_eye_plugin.agent_setup import (
    AgentSetupError, FileChange, SetupPlan, TRANSFORM_MATCHER,
    _atomic_bytes, _command_argv, _encode, _fingerprint, _hook_spec,
    _json_object as _setup_json_object, _merge_toml, _owned_hook, _project_path, _same_path,
)
from human_eye_plugin.host_runtime import GuardedHostRuntime

try:
    import tomllib
except ImportError:
    tomllib = None


EVENTS = ("UserPromptSubmit", "PreToolUse", "PostToolUse")
# This administration helper also runs under older installed runtimes whose
# agent_setup has no goal constant. The literal exact scope is a wire contract;
# whether to register it comes only from the target's explicit capability.
CLEARANCE_SEGMENT_MATCHER = "^mcp__human_eye_live__human_eye_clearance_segment$"
MAX_CONFIG = 8 * 1024 * 1024
MAX_STATE = 32 * 1024 * 1024
_PIN_FIELDS = ("base_version", "implementation_revision", "build_id", "source_kind",
               "protocol_version", "mode")
_SOURCE_ENTRY_SHA256 = "0e9bbc65b7a919353234a368f8b61a687e6746c6e6504d7e3add3d67eb9b49b5"
_TARGET_ENTRY_SHA256 = "0b63f86d1c98d5ecb259a55b7cce54860ecc1eec51bb9b67e48934b0b8215dd4"
_FIXED_TARGET_BOOTSTRAP = None


def _sha(raw):
    return hashlib.sha256(raw).hexdigest() if raw is not None else None


def _json_object(raw, label):
    value = _setup_json_object(raw, label)
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)
        elif isinstance(current, float) and not math.isfinite(current):
            # JSON's ordinary exponent syntax can overflow float without
            # invoking parse_constant (for example 1e999).
            raise AgentSetupError('Nonfinite JSON value in ' + label)
    return value


def _read(path, limit=MAX_CONFIG):
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > limit:
        raise AgentSetupError("Not a bounded regular file: " + str(path))
    raw = path.read_bytes()
    if len(raw) > limit:
        raise AgentSetupError("File grew beyond its limit: " + str(path))
    return raw


def _installed_runtime():
    """Pure local identity proof; never initialize a service or invoke a hook."""
    identity = identity_module.runtime_identity(mode="live")
    root = Path(identity_module.__file__).resolve().parents[1]
    prefix = Path(sys.prefix).resolve()
    launcher = None
    if _FIXED_TARGET_BOOTSTRAP is not None:
        entry = Path(getattr(_FIXED_TARGET_BOOTSTRAP, "__file__", "")).resolve()
        if _sha(_read(entry, 128 * 1024)) != _TARGET_ENTRY_SHA256:
            raise AgentSetupError("Unknown or modified fixed target bootstrap")
        try:
            launcher = _FIXED_TARGET_BOOTSTRAP.validate_binding(expected_python=sys.executable)
            _FIXED_TARGET_BOOTSTRAP.verify_imported_runtime(launcher)
        except (ValueError, OSError) as exc:
            raise AgentSetupError("Fixed target binding failed: " + str(exc)) from exc
        if (root != Path(launcher["module_root"]) or Path(__file__).resolve()
                != entry.with_name("installed_release.py")
                or _sha(_read(Path(__file__).resolve(), 1024 * 1024)) != launcher["admin_sha256"]):
            raise AgentSetupError("Administration helper is outside the bound installed target")
    if identity.get("source_kind") != "installed_distribution":
        raise AgentSetupError("Run this tool with the target installed venv; source imports are refused")
    root_modules = {Path(name).stem for name in identity_module._ROOT_MODULES}
    origins = {}
    for name, module in list(sys.modules.items()):
        if (name in root_modules or name == "human_eye_plugin" or name.startswith("human_eye_plugin.")
                or name == "human_eye_module1_operators" or name.startswith("human_eye_module1_operators.")):
            filename = getattr(module, "__file__", None)
            if filename is None:
                raise AgentSetupError("Engine module has no concrete origin: " + name)
            origin = Path(filename).resolve()
            if not origin.is_relative_to(root) or (launcher is None and not origin.is_relative_to(prefix)):
                raise AgentSetupError("Engine import escaped the target venv: " + name)
            origins[name] = str(origin)
    drift = identity_module.check_source_drift()
    if drift.get("compatible") is not True:
        raise AgentSetupError("Installed source changed after import; restart before planning")
    identity["source_file_count"] = len(identity.pop("source_files", []))
    fixed_names = ("human_eye_plugin", "human_eye_plugin.runtime_identity", "human_eye_plugin.agent_setup",
                   "human_eye_plugin.agent_hooks", "human_eye_plugin.host_runtime", "human_eye_hook")
    result = {"identity": identity, "python": str(Path(sys.executable).resolve()),
            "prefix": str(prefix), "module_root": str(root),
            "module_origins": {name: origins[name] for name in fixed_names}}
    if launcher is not None:
        result["launcher"] = launcher
    return result


def _target_entry_proof(entry, executable):
    """Inspect a byte-pinned fixed launcher without importing its engine."""
    if (not entry.is_absolute() or entry.name != "target_runtime_entry.py"
            or _sha(_read(entry, 128 * 1024)) != _TARGET_ENTRY_SHA256):
        raise AgentSetupError("Unknown or modified fixed target bootstrap")
    spec = importlib_util.spec_from_file_location("_human_eye_owned_target_entry", entry)
    module = importlib_util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        return module.validate_binding(expected_python=executable)
    except (ValueError, OSError) as exc:
        raise AgentSetupError("Owned fixed target binding failed: " + str(exc)) from exc


def _target(expected_build=None):
    target = _installed_runtime()
    if expected_build is not None and target["identity"].get("build_id") != expected_build:
        raise AgentSetupError("Target installed build does not match --expected-build")
    return target


def _relative_path(project, path):
    try:
        relative = path.relative_to(project)
    except ValueError as exc:
        raise AgentSetupError("Managed files must remain inside the target project") from exc
    if ".." in relative.parts or any(part.endswith((".", " ")) for part in relative.parts):
        raise AgentSetupError("Ambiguous managed path components are refused")
    devices = {"CON", "PRN", "AUX", "NUL", *("COM" + str(i) for i in range(1, 10)),
               *("LPT" + str(i) for i in range(1, 10))}
    if any(":" in part or part.split('.')[0].upper() in devices for part in relative.parts):
        raise AgentSetupError("Device/alternate-stream managed paths are refused")
    return _project_path(project, relative).resolve()


def _distinct_paths(paths):
    for index, path in enumerate(paths):
        for other in paths[:index]:
            if path == other or path.exists() and other.exists() and os.path.samefile(path, other):
                raise AgentSetupError("Managed paths alias the same file: " + str(path))


def _connector_paths(config, config_path, project):
    if config.get("schema_version") != "1.0":
        raise AgentSetupError("Unsupported connector schema")
    for key in ("enabled", "observe_on_prompt"):
        if key in config and type(config[key]) is not bool:
            raise AgentSetupError(key + " must be boolean")
    pin = config.get("expected_identity")
    if pin is not None and (not isinstance(pin, dict) or set(pin) - set(_PIN_FIELDS) - {"source_sha256"}
            or any(not isinstance(value, str) or not value for value in pin.values())):
        raise AgentSetupError("Invalid existing expected_identity contract")
    paths = {}
    for key in ("project_root", "state_file", "audit_file"):
        value = config.get(key)
        if not isinstance(value, str) or not value.strip() or any(c in value for c in "\x00\r\n"):
            raise AgentSetupError("Invalid connector path: " + key)
        candidate = config_path.parent / value
        paths[key] = (candidate.resolve() if key == "project_root" else _relative_path(project, candidate))
    for key in ("state_file", "audit_file"):
        path = _relative_path(project, paths[key])
        relative = path.relative_to(project)
        if (len(relative.parts) < 2 or relative.parts[0].casefold() != ".human-eye"
                or relative.parts[1].casefold() in {"setup-backups", "releases"}
                or relative.as_posix() in {".human-eye/setup.lock", ".human-eye/mcp-client.json",
                                          ".human-eye/installed-hooks.json"}):
            raise AgentSetupError("State/audit overlaps integration files or leaves .human-eye")
        _relative_path(project, path.with_name(path.name + ".lock"))
        if path.exists() and not path.is_file():
            raise AgentSetupError("State/audit must be regular files")
    state, audit = paths["state_file"], paths["audit_file"]
    reserved = {project / (".human-eye/" + name) for name in
                ("setup.lock", "mcp-client.json", "installed-hooks.json")}
    if {state, audit, state.with_name(state.name + ".lock"), audit.with_name(audit.name + ".lock")} & reserved:
        raise AgentSetupError("State/audit sidecar overlaps an integration reservation")
    if len({config_path, state, audit, state.with_name(state.name + ".lock"),
            audit.with_name(audit.name + ".lock")}) != 5:
        raise AgentSetupError("Connector, state, audit and locks must be distinct")
    _distinct_paths([config_path, state, audit, state.with_name(state.name + ".lock"),
                     audit.with_name(audit.name + ".lock")])
    connection = config.get("blender", {})
    if not isinstance(connection, dict) or connection.get("host", "127.0.0.1") not in {"127.0.0.1", "localhost", "::1"}:
        raise AgentSetupError("Only a loopback connector can be activated")
    port = connection.get("port", 9876)
    if type(port) is not int or not 1 <= port <= 65535:
        raise AgentSetupError("Invalid Blender port")
    for key, value in (("timeout_s", connection.get("timeout_s", 10)),
                       ("readback_atol_m", config.get("readback_atol_m", 1e-6))):
        try:
            valid = type(value) in (int, float) and math.isfinite(value) and value > 0
        except OverflowError:
            valid = False
        if not valid:
            raise AgentSetupError("Invalid positive connector option: " + key)
    for key, default, low, high in (("quad_size", 384, 64, 512), ("max_sessions", 16, 1, 256)):
        value = config.get(key, default)
        if type(value) is not int or not low <= value <= high:
            raise AgentSetupError("Invalid connector option: " + key)
    if config.get("readback_atol_m", 1e-6) > 1e-5:
        raise AgentSetupError("Readback tolerance exceeds the runtime contract")
    return paths


def _known_argv(argv, role, config_path=None, event=None, agent=None, *, launcher_proofs=None):
    """Recognize one literal owned invocation; never evaluate shell fragments."""
    if role not in {"mcp", "hook"}:
        raise AgentSetupError("Unknown Human-Eye launcher role")
    if not isinstance(argv, list) or len(argv) < 4 or any(not isinstance(x, str) for x in argv):
        raise AgentSetupError("Unknown Human-Eye launcher shape")
    executable = Path(argv[0])
    if (not executable.is_absolute()
            or re.fullmatch(r"python(?:\d+(?:\.\d+)*)?(?:\.exe)?", executable.name, re.I) is None):
        raise AgentSetupError("Human-Eye launcher is not a literal Python executable")
    args = list(argv[1:])
    seen_flags = set()
    while args and args[0] in {"-I", "-B"}:
        flag = args.pop(0)
        if flag in seen_flags:
            raise AgentSetupError("Duplicate Python launcher flags")
        seen_flags.add(flag)
    if args[:1] == ["-m"] and len(args) >= 2:
        module = args[1]
        expected = ({"human_eye_plugin.production_server", "human_eye_plugin.live_spatial_mcp"}
                    if role == "mcp" else {"human_eye_hook", "human_eye_plugin.live_hooks", "human_eye_plugin.agent_hooks"})
        if module not in expected:
            raise AgentSetupError("Unknown Human-Eye Python module")
        args = args[2:]
    else:
        if len(args) < 2:
            raise AgentSetupError("Unknown Human-Eye source launcher")
        entry = Path(args[0])
        if entry.name == "target_runtime_entry.py":
            proof = _target_entry_proof(entry, executable)
            if seen_flags != {"-I", "-B"} or argv[1:3] != ["-I", "-B"]:
                raise AgentSetupError("Fixed target requires the exact -I -B launcher flags")
            if args[1] != proof["roles"][role]:
                raise AgentSetupError("Fixed target launcher role disagrees with its registration")
            if launcher_proofs is not None and proof not in launcher_proofs:
                launcher_proofs.append(proof)
        else:
            raw = _read(entry, 64 * 1024) if entry.is_absolute() and entry.name == "live_entry.py" else None
            if _sha(raw) != _SOURCE_ENTRY_SHA256 or args[1] != ("serve" if role == "mcp" else "hook"):
                raise AgentSetupError("Unknown or modified Human-Eye source wrapper")
        args = args[2:]
    options = {}
    allowed = {"--config"} if role == "mcp" else {"--config", "--agent", "--event"}
    while args:
        if len(args) < 2 or args[0] not in allowed or args[0] in options:
            raise AgentSetupError("Unknown, duplicate or unsafe launcher arguments")
        options[args[0]] = args[1]
        args = args[2:]
    value = options.get("--config")
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise AgentSetupError("Owned launchers need an explicit absolute connector path")
    found = Path(value).absolute()
    if config_path is not None and found != config_path:
        raise AgentSetupError("Human-Eye launcher points at another connector; preserved")
    if role == "hook":
        if options.get("--agent") != agent or options.get("--event", event) != event:
            raise AgentSetupError("Human-Eye hook protocol/event disagrees with its registration")
    return found


def _load_server(raw, agent):
    if agent == "codex":
        if tomllib is None:
            raise AgentSetupError("This optional integration tool requires Python 3.11+ for TOML")
        try:
            data = tomllib.loads((raw or b"").decode("utf-8-sig"))
        except (ValueError, UnicodeError) as exc:
            raise AgentSetupError("Invalid Codex TOML") from exc
        servers = data.get("mcp_servers", {})
    else:
        data = _json_object(raw, "MCP configuration") if raw is not None else {}
        servers = data.get("mcpServers", {})
    if not isinstance(servers, dict):
        raise AgentSetupError("MCP server collection must be an object/table")
    server = servers.get("human_eye_live")
    if server is not None and (not isinstance(server, dict) or not isinstance(server.get("args"), list)):
        raise AgentSetupError("Invalid existing human_eye_live server")
    return data, server


def _replace_toml_server(raw, original, desired):
    """Patch only owned scalar/array assignments; leave other TOML bytes alone."""
    if original is None:
        return _merge_toml(raw, desired)[0]
    text = raw.decode("utf-8-sig")
    headers = list(re.finditer(r"(?m)^\s*\[.*\].*(?:\r?\n|$)", text))
    own = re.compile(r"^\s*\[\s*mcp_servers\s*\.\s*(?:human_eye_live|\"human_eye_live\"|'human_eye_live')\s*\]\s*(?:#.*)?(?:\r?\n)?$")
    matches = [i for i, header in enumerate(headers) if own.fullmatch(header.group())]
    if len(matches) != 1:
        raise AgentSetupError("Existing Human-Eye TOML uses a noncanonical table layout; preserved")
    index = matches[0]
    start, end = headers[index].end(), headers[index + 1].start() if index + 1 < len(headers) else len(text)
    body = text[start:end]
    newline = "\r\n" if "\r\n" in text else "\n"
    replacements = []
    additions = []
    for key, value in desired.items():
        if original.get(key) == value and key in original:
            continue
        assignments = list(re.finditer(r"(?m)^[ \t]*" + re.escape(key) + r"[ \t]*=", body))
        if key in original and len(assignments) != 1:
            raise AgentSetupError("Cannot safely locate owned TOML key: " + key)
        line = key + " = " + json.dumps(value, ensure_ascii=False, allow_nan=False) + newline
        if not assignments:
            additions.append(line)
            continue
        begin, value_start = assignments[0].start(), assignments[0].end()
        finish = value_start
        while True:
            next_line = body.find("\n", finish)
            finish = len(body) if next_line < 0 else next_line + 1
            try:
                parsed = tomllib.loads("value = " + body[value_start:finish])
            except ValueError:
                if finish == len(body):
                    raise AgentSetupError("Cannot safely delimit owned TOML value: " + key)
                continue
            if parsed != {"value": original[key]}:
                raise AgentSetupError("Owned TOML value has ambiguous boundaries: " + key)
            break
        replacements.append((begin, finish, line))
    for begin, finish, line in sorted(replacements, reverse=True):
        body = body[:begin] + line + body[finish:]
    if additions:
        body += (newline if body and not body.endswith("\n") else "") + "".join(additions)
    result = text[:start] + body + text[end:]
    expected = tomllib.loads(text)
    expected["mcp_servers"]["human_eye_live"] = desired
    if tomllib.loads(result) != expected:
        raise AgentSetupError("TOML patch changed unrelated settings; preserved")
    return (b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b"") + result.encode("utf-8")


def _merge_installed_hooks(document, argv_by_event, agent, platform, config_path, *,
                           bounded_clearance_segment=False, launcher_proofs=None):
    if type(bounded_clearance_segment) is not bool:
        raise AgentSetupError("Goal hook capability must be boolean")
    hooks = document.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise AgentSetupError("Hooks must be an object")
    for event in EVENTS:
        desired, _ = _hook_spec(argv_by_event[event], agent, platform)
        groups = hooks.setdefault(event, [])
        if not isinstance(groups, list):
            raise AgentSetupError("Hook groups must be arrays")
        owned_matchers = ((None,) if event == "UserPromptSubmit"
                          else (TRANSFORM_MATCHER, CLEARANCE_SEGMENT_MATCHER))
        required_matchers = (owned_matchers if bounded_clearance_segment or event == "UserPromptSubmit"
                             else (TRANSFORM_MATCHER,))
        counts = {matcher: 0 for matcher in owned_matchers}
        retained_groups = []
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                raise AgentSetupError("Invalid hook registration")
            retained_hooks = []
            removed_goal = False
            for hook in group["hooks"]:
                if not isinstance(hook, dict):
                    raise AgentSetupError("Invalid command hook")
                if "args" in hook and (not isinstance(hook['args'], list)
                        or any(not isinstance(value, str) for value in hook['args'])):
                    raise AgentSetupError('Hook args must be a literal string array')
                suspicious = _suspected_engine_hook(hook, platform, group.get('matcher'))
                if not suspicious:
                    retained_hooks.append(hook)
                    continue
                if hook.get("type") != "command":
                    raise AgentSetupError("Unknown Human-Eye hook type; preserved")
                _known_argv(_strict_hook_argv(hook, platform, agent), "hook", config_path, event, agent,
                            launcher_proofs=launcher_proofs)
                matcher = group.get("matcher")
                if matcher not in owned_matchers:
                    raise AgentSetupError("Human-Eye hook matcher differs from the exact owned tool scope")
                counts[matcher] += 1
                if counts[matcher] > 1:
                    raise AgentSetupError("Duplicate Human-Eye hooks need review")
                if matcher == CLEARANCE_SEGMENT_MATCHER and not bounded_clearance_segment:
                    # The invocation and exact scope have both been proved
                    # above. Remove only our obsolete goal hook on downgrade;
                    # independent commands sharing that group remain intact.
                    removed_goal = True
                    continue
                updated = {key: value for key, value in hook.items() if key not in {"command", "args", "type"}}
                updated.update({key: value for key, value in desired.items()
                                if key != "timeout" or key not in updated})
                retained_hooks.append(updated)
            group["hooks"] = retained_hooks
            if retained_hooks or not removed_goal:
                retained_groups.append(group)
        for matcher in required_matchers:
            if counts[matcher]:
                continue
            group = {"hooks": [copy.deepcopy(desired)]}
            if matcher is not None:
                group["matcher"] = matcher
            retained_groups.append(group)
        groups[:] = retained_groups
    return document


def _suspected_engine_hook(hook, platform, matcher):
    """Inspect encoded data in command and args, without running shell code."""
    args = hook.get('args', [])
    fragments = [hook.get('command', '')] + (args if isinstance(args, list) else [])
    fragments = [value for value in fragments if isinstance(value, str)]
    combined = ' '.join(fragments)
    # PowerShell accepts unique prefixes, not a fixed short list such as
    # -enc. Ownership detection must not depend on which prefix was used.
    switches = re.finditer(r"(?i)(?:^|\s)[-/]([a-z]+)(?::|\s+)[\"']?([A-Za-z0-9+/=]+)", combined)
    encoded = [match.group(2) for match in switches if _encoded_switch(match.group(1))]
    # Also inspect independent base64 tokens. A future flag spelling or an
    # outer wrapper cannot hide a literal engine call solely by changing the
    # token preceding its payload. Decoding is data inspection, never eval.
    candidates = {match.group() for match in re.finditer(
        r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{8,}={0,2}(?![A-Za-z0-9+/=])", combined)}
    for payload in candidates | set(encoded):
        try:
            fragments.append(base64.b64decode(payload, validate=True).decode('utf-16-le'))
        except (ValueError, UnicodeError):
            pass
    needles = ('human_eye', 'human-eye', 'live_entry.py', 'target_runtime_entry.py')
    if _owned_hook(hook, platform) or any(needle in value.lower() for value in fragments for needle in needles):
        return True
    # A damaged encoded command attached specifically to an owned tool cannot
    # be certified as an unrelated command. Preserve it and require review.
    return bool(encoded and any(not _can_decode_payload(payload) for payload in encoded))


def _encoded_switch(value):
    value = value.casefold()
    return value in {'ec', 'ea'} or bool(value) and any(
        full.startswith(value) for full in ('encodedcommand', 'encodedarguments'))


def _can_decode_payload(value):
    try:
        base64.b64decode(value, validate=True).decode('utf-16-le')
        return True
    except (ValueError, UnicodeError):
        return False


def _strict_hook_argv(hook, platform, agent):
    """Verify the complete encoded launcher, not merely its inner invocation."""
    argv = _command_argv(hook, platform)
    command = hook.get("command", "")
    if "args" not in hook and isinstance(command, str):
        if re.search(r"(?i)-EncodedCommand\b", command):
            if argv is None:
                raise AgentSetupError("Unrecognized encoded Human-Eye launcher")
            # The known PowerShell outer dialect is independent of the event
            # wire protocol carried by --agent inside the literal argv.
            canonical, _ = _hook_spec(argv, 'codex', platform)
            if command != canonical.get("command") or "args" in canonical:
                raise AgentSetupError("Unknown outer shell wrapper/flags around Human-Eye; preserved")
        elif any(character in command for character in "%!^"):
            raise AgentSetupError("Unknown shell expansion in a legacy Human-Eye launcher")
    return argv


class _NoHost:
    def capture_scene(self):
        raise AssertionError("Integration compatibility checks must not capture a host")

    def apply_transform(self, *args, **kwargs):
        raise AssertionError("Integration must never mutate a host")


def _check_state(raw, config):
    if raw is None:
        return None
    state = _json_object(raw, "persisted live state")
    if (state.get("schema_version") != "1.0" or state.get("config_fingerprint") != _fingerprint(config)
            or "inflight" not in state or not isinstance(state.get("runtime"), dict)):
        raise AgentSetupError("Persisted state schema/binding is invalid; cannot reset it")
    if state["inflight"] is not None:
        raise AgentSetupError("Pending inflight operation blocks activation")
    runtime = state["runtime"]
    if "quarantine" not in runtime or runtime["quarantine"] is not None:
        raise AgentSetupError("Quarantined or incomplete runtime blocks activation")
    router = runtime.get("router")
    if not isinstance(router, dict) or not isinstance(router.get("sessions"), list):
        raise AgentSetupError("Missing router state")
    for pair in router["sessions"]:
        if (not isinstance(pair, list) or len(pair) != 2 or not isinstance(pair[1], dict)
                or "pending" not in pair[1] or pair[1]["pending"] is not None):
            raise AgentSetupError("Pending or malformed router journal blocks activation")
    # A complete single-step router does not prove that its owning goal has
    # finished. In particular, a process can die after clearing inflight but
    # before accounting the actual motion or acknowledging the parent.
    # Legacy states without these fields need no new-runtime imports. A target
    # which cannot validate a present ledger must refuse rather than preserve
    # an opaque execution journal while claiming activation is safe.
    try:
        if 'goal_authorizations' in state or any(identity.startswith('auth-goal:') for identity in
                state.get('goal_supervision', {}).get('records', {})):
            from human_eye_plugin.task_authority import validate_authorizations, blocking_authorization
            validate_authorizations(state)
            if blocking_authorization(state) is not None:
                raise AgentSetupError('Unresolved trusted task authorization blocks activation')
        if "goal_segments" in state:
            from human_eye_plugin.goal_execution import validate_segment_ledger, unfinished_segment
            validate_segment_ledger(state)
            records = state["goal_segments"]["records"]
            if (unfinished_segment(state) or any(entry["status"] in
                    {"execution_uncertain", "segment_interrupted"} for entry in records.values())):
                raise AgentSetupError("Unresolved goal segment blocks activation")
        if "goal_supervision" in state or any(
                "parent_goal_id" in entry for entry in
                state.get("goal_segments", {}).get("records", {}).values()):
            from human_eye_plugin.goal_journal import validate_goal_journal, blocking_goal
            validate_goal_journal(state)
            if blocking_goal(state) is not None:
                raise AgentSetupError("Unresolved parent goal blocks activation")
    except AgentSetupError:
        raise
    except Exception as exc:
        raise AgentSetupError("Target cannot validate existing goal ledgers: " + type(exc).__name__) from exc
    try:
        verifier = GuardedHostRuntime(_NoHost(), quad_size=config.get("quad_size", 384),
            max_sessions=config.get("max_sessions", 16), readback_atol_m=config.get("readback_atol_m", 1e-6),
            require_execution_capability=True)
        verifier.import_state(copy.deepcopy(runtime))
    except Exception as exc:
        raise AgentSetupError("Target runtime cannot import the existing state: " + type(exc).__name__) from exc
    # Never export this verifier: TTL/old observation invalidation is its own
    # read-side policy, not permission to rewrite persisted runtime or journals.
    return state


def _state_binding_bytes(raw, old_fingerprint, new_fingerprint):
    """Replace exactly one top-level JSON string token, preserving other bytes."""
    bom = b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b""
    text = raw.decode("utf-8-sig")
    decoder = json.JSONDecoder()
    position = len(text) - len(text.lstrip())
    if text[position:position + 1] != "{":
        raise AgentSetupError("State must be a JSON object")
    position += 1
    span = None
    while True:
        while position < len(text) and text[position] in " \r\n\t,":
            position += 1
        if text[position:position + 1] == "}":
            break
        key, position = decoder.raw_decode(text, position)
        while position < len(text) and text[position].isspace():
            position += 1
        if text[position:position + 1] != ":":
            raise AgentSetupError("Malformed state property")
        position += 1
        while position < len(text) and text[position].isspace():
            position += 1
        start = position
        value, position = decoder.raw_decode(text, position)
        if key == "config_fingerprint":
            if span is not None or value != old_fingerprint:
                raise AgentSetupError("State fingerprint changed or is duplicated")
            span = start, position
    if span is None:
        raise AgentSetupError("No top-level state fingerprint to migrate")
    changed = bom + (text[:span[0]] + json.dumps(new_fingerprint) + text[span[1]:]).encode("utf-8")
    before, after = _json_object(raw, "state"), _json_object(changed, "state")
    before["config_fingerprint"] = new_fingerprint
    if before != after:
        raise AgentSetupError("State migration would change another field")
    return changed


def _current_status(path):
    if path is None:
        return {"status": "unknown", "source": "not_probed", "live_probe_performed": False,
                "restart_required_after_apply": True}
    path = Path(path).resolve()
    raw = _read(path)
    if raw is None:
        raise AgentSetupError("Saved current status does not exist")
    value = _json_object(raw, "operator-saved current status")
    for block in value.get("content", []):
        if isinstance(block, dict) and block.get("type") == "text":
            try:
                candidate = _json_object(block["text"].encode("utf-8"), "saved MCP status text")
            except (AgentSetupError, AttributeError):
                continue
            if "runtime_identity" in candidate:
                value = candidate
                break
    return {"status": "operator_saved_snapshot", "source": "operator_saved_file", "path": str(path),
            "sha256": _sha(raw), "runtime_identity": value.get("runtime_identity"),
            "inflight_operation": value.get("inflight_operation"), "quarantined": value.get("quarantined"),
            "freshness": "not_verified", "live_probe_performed": False,
            "restart_required_after_apply": True}


class InstalledReleasePlan(SetupPlan):
    """Use FileChange/preview with a state-aware, bounded CAS transaction."""
    def __init__(self, *, agent, project, target, config_path, config, state_path,
                 changes, preconditions, hooks, current_connection, expected_build, launcher_proofs=()):
        super().__init__(agent, project, Path(target["module_root"]), Path(target["python"]),
                         changes, preconditions=preconditions, hook_argv_by_event=hooks["argv_by_event"])
        self.target = target
        self.config_path, self.config, self.state_path = config_path, config, state_path
        self.hooks, self.current_connection = hooks, current_connection
        self.expected_build = expected_build
        self.launcher_proofs = copy.deepcopy(list(launcher_proofs))

    def preview(self):
        result = super().preview()
        old_fingerprint = _fingerprint(self.config)
        config_change = next((change for change in self.changes if change.path == self.config_path), None)
        new_config = _json_object(config_change.after, "new connector") if config_change else self.config
        result.update(operation="plan", target_runtime=self.target,
            input_sha256={path.relative_to(self.project).as_posix(): _sha(raw)
                          for path, raw in self.preconditions.items()},
            current_connection=self.current_connection, connector_path=str(self.config_path),
            hooks=self.hooks, restart_required=True, hot_reload=False,
            state_migration={"state_file": str(self.state_path),
                "state_exists": self.preconditions[self.state_path] is not None,
                "old_config_fingerprint": old_fingerprint,
                "new_config_fingerprint": _fingerprint(new_config),
                "changed_fields": ["config_fingerprint"] if old_fingerprint != _fingerprint(new_config)
                    and self.preconditions[self.state_path] is not None else [],
                "runtime_and_journal_bytes_preserved": True,
                "old_worker_after_commit": "config_fingerprint_mismatch_fail_closed",
                "during_activation": "random_fingerprint_fence_blocks_old_and_new_workers",
                "state_commit_order": "transaction_fence_first_final_binding_last",
                "incomplete_rollback": "retain_fence_and_require_operator_recovery",
                "new_observation_required": True},
            consistency="unlocked_snapshot_revalidated_under_locks_on_apply",
            transaction_scope="per_file_atomic_replace_with_backups_not_power_loss_atomic")
        if self.launcher_proofs:
            result["owned_launcher_proofs"] = self.launcher_proofs
        result["plan_sha256"] = _fingerprint(result)
        return result

    def _check_runtime_proofs(self):
        current = _target(self.expected_build)
        if current != self.target:
            raise AgentSetupError("Target runtime identity/origin changed after planning")
        for expected in self.launcher_proofs:
            if _target_entry_proof(Path(expected["entry"]), Path(expected["dependency_python"])) != expected:
                raise AgentSetupError("Owned launcher binding/source changed after planning")

    def _check_preconditions(self):
        self._check_runtime_proofs()
        for path, expected in self.preconditions.items():
            _relative_path(self.project, path)
            if _read(path, MAX_STATE if path == self.state_path else MAX_CONFIG) != expected:
                raise AgentSetupError("Configuration/state changed after planning: " + str(path))
        paths = _connector_paths(self.config, self.config_path, self.project)
        _distinct_paths([*self.preconditions, paths['audit_file'],
            self.state_path.with_name(self.state_path.name+'.lock'),
            paths['audit_file'].with_name(paths['audit_file'].name+'.lock'),
            self.project/'.human-eye/setup.lock'])
        _check_state(self.preconditions[self.state_path], self.config)

    def apply(self, *, plan_sha256=None):
        result = self.preview()
        if plan_sha256 is not None and plan_sha256 != result["plan_sha256"]:
            raise AgentSetupError("Plan SHA differs from the reviewed preview")
        self._check_preconditions()
        if not self.changes:
            return {**result, "applied": True, "backup_manifest": None}
        setup_path = _relative_path(self.project, self.project / ".human-eye/setup.lock")
        setup_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(setup_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise AgentSetupError("Existing setup lock was preserved; review its prior transaction") from exc
        lock_token = (uuid.uuid4().hex + ":" + str(os.getpid())).encode("ascii")
        try:
            os.write(descriptor, lock_token)
        finally:
            os.close(descriptor)
        try:
            # The stable state sidecar is shared with running MCP/hooks and is
            # never deleted, renamed, or substituted by this transaction.
            with _state_lock(self.state_path, timeout_s=20):
                self._check_preconditions()
                return self._apply_locked(result)
        finally:
            if _read(setup_path) == lock_token:
                setup_path.unlink()

    def _apply_locked(self, result):
        backup = _relative_path(self.project, self.project / (".human-eye/setup-backups/" + uuid.uuid4().hex))
        manifest_path = backup / "manifest.json"
        original_state = self.preconditions[self.state_path]
        old_fingerprint = _fingerprint(self.config)
        new_fingerprint = result['state_migration']['new_config_fingerprint']
        fence = os.urandom(32).hex()
        while fence in {old_fingerprint, new_fingerprint}:
            fence = os.urandom(32).hex()
        fenced_state = _state_binding_bytes(original_state, old_fingerprint, fence)
        final_state = _state_binding_bytes(original_state, old_fingerprint, new_fingerprint)
        configurations = [change for change in self.changes if change.path != self.state_path]
        backup_changes = configurations + [FileChange(self.state_path, original_state, final_state,
                                                       {'changed_fields': ['config_fingerprint']})]
        manifest = {"schema_version": "1.0", "agent": self.agent, "status": "prepared",
                    "plan_sha256": result["plan_sha256"], "target_identity": self.target["identity"],
                    "phase": "backups_prepared", "state_commit_order": "fence_first_final_binding_last",
                    "transaction_fence_fingerprint": fence, "fenced_state_sha256": _sha(fenced_state),
                    "old_state_sha256": _sha(original_state), "new_state_sha256": _sha(final_state),
                    "recovery_required": True, "files": []}
        fence_attempted = False
        try:
            for change in backup_changes:
                relative = change.path.relative_to(self.project)
                manifest["files"].append({"path": relative.as_posix(), "existed": change.before is not None,
                    "before_sha256": _sha(change.before), "after_sha256": _sha(change.after)})
                if change.before is not None:
                    _atomic_bytes(backup / "files" / relative, change.before)
            _atomic_bytes(manifest_path, _encode(manifest))
            if _read(self.state_path, MAX_STATE) != original_state:
                raise AgentSetupError("State changed before transaction fence")
            fence_attempted = True
            _atomic_bytes(self.state_path, fenced_state)
            manifest.update(status="in_progress", phase="fenced", recovery_required=True)
            _atomic_bytes(manifest_path, _encode(manifest))
            for change in configurations:
                _relative_path(self.project, change.path)
                if _read(change.path, MAX_STATE if change.path == self.state_path else MAX_CONFIG) != change.before:
                    raise AgentSetupError("Concurrent edit during activation: " + str(change.path))
                _atomic_bytes(change.path, change.after)
            for path, expected in self.preconditions.items():
                if path == self.state_path:
                    continue
                changed = next((change for change in configurations if change.path == path), None)
                if _read(path) != (changed.after if changed is not None else expected):
                    raise AgentSetupError('Concurrent edit before state commit: ' + str(path))
            manifest['phase'] = 'configuration_written'
            _atomic_bytes(manifest_path, _encode(manifest))
            self._check_runtime_proofs()
            if _read(self.state_path, MAX_STATE) != fenced_state:
                raise AgentSetupError("State changed while transaction was fenced")
            _atomic_bytes(self.state_path, final_state)
            manifest.update(status="applied", phase="committed", recovery_required=False)
            _atomic_bytes(manifest_path, _encode(manifest))
            return {**result, "applied": True, "backup_manifest": str(manifest_path)}
        except Exception as exc:
            errors = []
            for change in reversed(configurations):
                try:
                    _relative_path(self.project, change.path)
                    current = _read(change.path)
                    if current == change.before:
                        continue
                    if current != change.after:
                        raise AgentSetupError("Concurrent edit prevents rollback: " + str(change.path))
                    if change.before is None:
                        change.path.unlink()
                    else:
                        _atomic_bytes(change.path, change.before)
                except Exception as rollback_exc:
                    errors.append(str(rollback_exc))
            for path, expected in self.preconditions.items():
                if path == self.state_path:
                    continue
                try:
                    _relative_path(self.project, path)
                    if _read(path) != expected:
                        raise AgentSetupError('Configuration changed during rollback: ' + str(path))
                except Exception as rollback_exc:
                    errors.append(str(rollback_exc))
            if fence_attempted:
                try:
                    current_state = _read(self.state_path, MAX_STATE)
                    if errors:
                        # A completed commit followed by a failed manifest or
                        # config rollback must be fenced again before unlock.
                        if current_state in (original_state, final_state):
                            _atomic_bytes(self.state_path, fenced_state)
                        elif current_state != fenced_state:
                            raise AgentSetupError("Concurrent state edit prevented retaining the fence")
                    else:
                        if any(_read(change.path) != change.before for change in configurations):
                            raise AgentSetupError("Configuration rollback is incomplete")
                        if current_state not in (original_state, fenced_state, final_state):
                            raise AgentSetupError("Concurrent state edit prevents restoring the old binding")
                        if current_state != original_state:
                            _atomic_bytes(self.state_path, original_state)
                except Exception as rollback_exc:
                    errors.append(str(rollback_exc))
            manifest.update(status="rollback_incomplete" if errors else "rolled_back",
                            phase="recovery_required" if errors else "rolled_back",
                            recovery_required=bool(errors), error_type=type(exc).__name__, rollback_errors=errors)
            try:
                _atomic_bytes(manifest_path, _encode(manifest))
            except OSError:
                pass
            raise AgentSetupError("Activation failed; " + manifest["status"] + "; " + str(manifest_path)) from exc


def build_plan(agent, project, *, config_path=None, expected_build=None, current_status=None, platform=None):
    agent = "mcp" if agent == "genericmcp" else agent
    if agent not in {"codex", "claude", "mcp"}:
        raise AgentSetupError("Unsupported agent")
    project = Path(project).resolve()
    if not project.is_dir():
        raise AgentSetupError("Target project must already exist")
    target = _target(expected_build)
    platform = platform or ("windows" if os.name == "nt" else "posix")
    if platform not in {"windows", "posix"}:
        raise AgentSetupError("Unsupported platform")
    server_path = _relative_path(project, project / ({"codex": ".codex/config.toml", "claude": ".mcp.json",
                                                    "mcp": ".human-eye/mcp-client.json"}[agent]))
    server_raw = _read(server_path)
    document, old_server = _load_server(server_raw, agent)
    found = None
    launcher_proofs = []
    if old_server is not None:
        found = _relative_path(project, _known_argv([old_server.get("command"), *old_server["args"]], "mcp",
                                                   launcher_proofs=launcher_proofs))
    if config_path is None:
        if found is None:
            raise AgentSetupError("Pass --config or register one recognized Human-Eye MCP connector first")
        config_path = found
    else:
        config_path = Path(config_path)
        config_path = project / config_path if not config_path.is_absolute() else config_path
    config_path = _relative_path(project, config_path)
    if config_path.relative_to(project).parts[0].casefold() != ".human-eye":
        raise AgentSetupError("Connector must remain inside project/.human-eye")
    config_relative = config_path.relative_to(project)
    if (len(config_relative.parts) < 2 or config_relative.parts[1].casefold() in {"setup-backups", "releases"}
            or config_relative.as_posix() in {".human-eye/setup.lock", ".human-eye/mcp-client.json",
                                              ".human-eye/installed-hooks.json"}):
        raise AgentSetupError("Connector overlaps integration/backup files")
    if found is not None and found != config_path:
        raise AgentSetupError("Explicit connector differs from the registered owned connection")
    config_raw = _read(config_path)
    if config_raw is None:
        raise AgentSetupError("Connector must exist; this tool does not invent/reset a connection")
    config = _json_object(config_raw, "existing connector")
    paths = _connector_paths(config, config_path, project)
    state_path = paths["state_file"]
    state_raw = _read(state_path, MAX_STATE)
    if state_raw is None:
        raise AgentSetupError("state_initialization_required: this narrow upgrade preserves an existing runtime; no state is invented")
    _check_state(state_raw, config)
    updated_config = copy.deepcopy(config)
    updated_config["project_root"] = target["module_root"]
    updated_config["expected_identity"] = {key: target["identity"][key] for key in _PIN_FIELDS}
    if not (Path(target["module_root"]) / "human_eye_plugin/blender_host.py").is_file():
        raise AgentSetupError("Installed target has no fixed Blender host source")
    changes = []
    preconditions = {server_path: server_raw, config_path: config_raw, state_path: state_raw}
    def add(path, before, after, owned):
        if len(after) > (MAX_STATE if path == state_path else MAX_CONFIG):
            raise AgentSetupError('Planned output exceeds its file-size limit: ' + str(path))
        if before != after:
            changes.append(FileChange(path, before, after, owned))
    python = target["python"]
    launcher = target.get("launcher")
    server_prefix = (launcher["invocation_prefix"] + [launcher["roles"]["mcp"]] if launcher
                     else [python, "-I", "-B", "-m", "human_eye_plugin.production_server"])
    desired_server = copy.deepcopy(old_server) if old_server is not None else {}
    desired_server.update(command=server_prefix[0], args=server_prefix[1:] + ["--config", str(config_path)])
    if agent == "codex":
        desired_server["cwd"] = str(project)
        for key, default in (("enabled", True), ("startup_timeout_sec", 30), ("tool_timeout_sec", 30)):
            desired_server.setdefault(key, default)
        after = _replace_toml_server(server_raw, old_server, desired_server)
    else:
        document.setdefault("mcpServers", {})["human_eye_live"] = desired_server
        after = _encode(document)
    add(server_path, server_raw, after, {"mcp_server": "human_eye_live", "managed_keys": ["command", "args", "cwd"]})
    hook_agent = agent if agent != "mcp" else "codex"
    hook_prefix = (launcher["invocation_prefix"] + [launcher["roles"]["hook"]] if launcher
                   else [python, "-I", "-B", "-m", "human_eye_hook"])
    argv_by_event = {event: hook_prefix + ["--agent", hook_agent,
                            "--event", event, "--config", str(config_path)] for event in EVENTS}
    hooks = {"argv_by_event": argv_by_event, "wire_protocol": hook_agent,
             "registration": "host_integration_required" if agent == "mcp" else "project_configuration_only",
             "actual_host_dispatch_verified": False}
    capabilities = target["identity"].get("capabilities")
    goal_hooks = isinstance(capabilities, dict) and capabilities.get("bounded_clearance_segment") is True
    hooks["tool_matchers"] = [TRANSFORM_MATCHER] + ([CLEARANCE_SEGMENT_MATCHER] if goal_hooks else [])
    if agent != "mcp":
        hook_path = _relative_path(project, project / (".codex/hooks.json" if agent == "codex" else ".claude/settings.json"))
        hook_raw = _read(hook_path)
        preconditions[hook_path] = hook_raw
        hook_document = _json_object(hook_raw, "hook configuration") if hook_raw is not None else {}
        original_hooks = copy.deepcopy(hook_document)
        merged = _merge_installed_hooks(hook_document, argv_by_event, agent, platform, config_path,
                                        bounded_clearance_segment=goal_hooks, launcher_proofs=launcher_proofs)
        hook_after = hook_raw if hook_raw is not None and merged == original_hooks else _encode(merged)
        add(hook_path, hook_raw, hook_after, {"events": list(EVENTS), "managed_hook": "human_eye_hook"})
    else:
        hook_path = _relative_path(project, project / ".human-eye/installed-hooks.json")
        hook_raw = _read(hook_path)
        preconditions[hook_path] = hook_raw
        previous = {}
        if hook_raw is not None:
            previous = _json_object(hook_raw, "portable hook manifest")
            if previous.get("kind") != "human_eye_installed_hook_manifest":
                raise AgentSetupError("Unknown portable hook manifest was preserved")
        add(hook_path, hook_raw, _encode({**previous, "schema_version": "1.0", "kind": "human_eye_installed_hook_manifest",
            "expected_identity": updated_config["expected_identity"], "connector_path": str(config_path), **hooks}),
            {"kind": "portable_hook_commands_not_host_registration"})
    config_after = config_raw if updated_config == config else _encode(updated_config)
    add(config_path, config_raw, config_after, {"changed_keys": ["project_root", "expected_identity"],
                                              "expected_identity": updated_config["expected_identity"]})
    if state_raw is not None and _fingerprint(config) != _fingerprint(updated_config):
        state_after = _state_binding_bytes(state_raw, _fingerprint(config), _fingerprint(updated_config))
        # State must be the last changed file: its binding is the commit fence.
        add(state_path, state_raw, state_after, {"changed_fields": ["config_fingerprint"],
                                               "runtime_and_journal_bytes_preserved": True})
    _distinct_paths([*preconditions, paths['audit_file'], state_path.with_name(state_path.name+'.lock'),
        paths['audit_file'].with_name(paths['audit_file'].name+'.lock'), project/'.human-eye/setup.lock'])
    return InstalledReleasePlan(agent=agent, project=project, target=target, config_path=config_path,
        config=config, state_path=state_path, changes=changes, preconditions=preconditions,
        hooks=hooks, current_connection=_current_status(current_status), expected_build=expected_build,
        launcher_proofs=launcher_proofs)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("doctor", "plan"))
    parser.add_argument("--agent", choices=("codex", "claude", "mcp", "genericmcp"), required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--config", dest="config_path", type=Path)
    parser.add_argument("--expected-build")
    parser.add_argument("--current-status", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--plan-sha256")
    args = parser.parse_args(argv)
    try:
        if not sys.flags.isolated or not sys.dont_write_bytecode:
            raise AgentSetupError("Invoke the target installed Python with -I -B")
        if args.operation == "doctor" and args.apply:
            raise AgentSetupError("doctor is read-only; --apply belongs to plan")
        if args.apply and not args.expected_build:
            raise AgentSetupError("--apply requires an explicit --expected-build")
        plan = build_plan(args.agent, args.project, config_path=args.config_path,
            expected_build=args.expected_build, current_status=args.current_status)
        result = plan.apply(plan_sha256=args.plan_sha256) if args.apply else plan.preview()
        if args.operation == "doctor":
            result.update(operation="doctor", ready_to_apply=True, applied=False,
                          diagnostic_scope="configuration_identity_and_saved_state_no_host_probe")
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (AgentSetupError, OSError, ValueError, OverflowError, RecursionError) as exc:
        print(json.dumps({"operation": args.operation, "applied": False, "ready_to_apply": False,
                          "error_type": type(exc).__name__, "error": str(exc),
                          "live_probe_performed": False}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
