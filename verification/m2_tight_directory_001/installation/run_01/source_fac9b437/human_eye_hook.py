"""Lightweight hook entry. Skip decisions have no scene or execution authority.

The installed/source root is fixed by this file, never selected by event data or
connector.project_root. Standard-library leaf modules are reused directly from
that root. Spatial work imports the ordinary package and uses its normal gates.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import time

SPATIAL_TRANSFORM = 'mcp__human_eye_live__human_eye_transform'
SPATIAL_CLEARANCE_SEGMENT = 'mcp__human_eye_live__human_eye_clearance_segment'
SPATIAL_OBSERVE = 'mcp__human_eye_live__human_eye_scene_observe'
SPATIAL_STATUS = 'mcp__human_eye_live__human_eye_connection_status'
SPATIAL_WRITE_TOOLS = frozenset({SPATIAL_TRANSFORM, SPATIAL_CLEARANCE_SEGMENT})
SUPPORTED_TOOLS = SPATIAL_WRITE_TOOLS | frozenset({SPATIAL_OBSERVE, SPATIAL_STATUS})
HOOK_EVENTS = ('UserPromptSubmit', 'PreToolUse', 'PostToolUse')
ROOT = Path(__file__).resolve().parent
_REPLY_OPEN = '<send_user_message_question_reply>'
_REPLY_CLOSE = '</send_user_message_question_reply>'
_MAX_PROMPT_CHARS = 65536
_MAX_REPLY_ITEMS = 16


def _unique_prompt_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate structured reply key')
        result[key] = value
    return result


def _reject_prompt_constant(value):
    raise ValueError('Nonfinite structured reply value')


def host_prompt(event, *, agent='codex'):
    """Read only this host event's prompt, with a bounded Codex reply envelope.

    Only answer strings from a complete, strictly validated question-reply
    envelope become the instruction. Questions and IDs never supply intent.
    Answers remain plain text: quoted/code instructions are still rejected by
    the unchanged intent classifier. No history lookup or authority is added.
    Returned diagnostics describe the original event value without its text.
    """
    raw = event.get('prompt', '')
    metadata = {'present': 'prompt' in event, 'type': type(raw).__name__,
        'chars': None, 'bytes': None, 'sha256': None,
        'sha256_basis': 'utf8_surrogatepass_of_current_prompt_string',
        'format': 'plain', 'extraction': 'unchanged', 'reason': None,
        'item_count': None, 'scope': 'current_hook_event_prompt_only_no_history'}
    if isinstance(raw, str):
        encoded = raw.encode('utf-8', errors='surrogatepass')
        metadata.update(chars=len(raw), bytes=len(encoded), sha256=hashlib.sha256(encoded).hexdigest())
    else:
        metadata.update(format='non_text', extraction='not_applicable')
        return raw, metadata
    if agent != 'codex' or event.get('hook_event_name') != 'UserPromptSubmit':
        metadata['extraction'] = 'not_applicable'
        return raw, metadata
    if ('<send_user_message_question_reply' not in raw
            and '</send_user_message_question_reply' not in raw):
        return raw, metadata
    metadata.update(format='codex_question_reply', extraction='rejected')
    if len(raw) > _MAX_PROMPT_CHARS:
        metadata['reason'] = 'prompt_text_budget_exceeded'
        return '', metadata
    text = raw.strip()
    if not (text.startswith(_REPLY_OPEN) and text.endswith(_REPLY_CLOSE)):
        metadata['reason'] = 'reply_must_be_complete_unquoted_envelope'
        return '', metadata
    body = text[len(_REPLY_OPEN):-len(_REPLY_CLOSE)]
    try:
        items = json.loads(body, object_pairs_hook=_unique_prompt_object,
                           parse_constant=_reject_prompt_constant)
    except (ValueError, TypeError, RecursionError, OverflowError):
        metadata['reason'] = 'invalid_reply_json'
        return '', metadata
    if not isinstance(items, list):
        metadata['reason'] = 'reply_must_be_array'
        return '', metadata
    metadata['item_count'] = len(items)
    if not 1 <= len(items) <= _MAX_REPLY_ITEMS:
        metadata['reason'] = 'reply_item_budget_exceeded'
        return '', metadata
    answers, seen_ids = [], set()
    for item in items:
        if (not isinstance(item, dict) or set(item) != {'questionItemId', 'question', 'answer'}
                or any(not isinstance(item[key], str) for key in ('questionItemId', 'question', 'answer'))):
            metadata['reason'] = 'invalid_reply_item_schema'
            return '', metadata
        try:
            identity = json.loads(item['questionItemId'], object_pairs_hook=_unique_prompt_object,
                                  parse_constant=_reject_prompt_constant)
        except (ValueError, TypeError, RecursionError, OverflowError):
            metadata['reason'] = 'invalid_question_item_id'
            return '', metadata
        if (not isinstance(identity, list) or len(identity) != 3
                or identity[0] != 'request_user_input_async'
                or not isinstance(identity[1], str)
                or re.fullmatch(r'call_[A-Za-z0-9][A-Za-z0-9_-]{0,255}', identity[1]) is None
                or type(identity[2]) is not int or identity[2] < 0):
            metadata['reason'] = 'invalid_question_item_id'
            return '', metadata
        key = tuple(identity)
        if key in seen_ids:
            metadata['reason'] = 'duplicate_question_item_id'
            return '', metadata
        seen_ids.add(key)
        answers.append(item['answer'])
    metadata.update(extraction='answers_only', reason=None)
    return '\n'.join(answers), metadata


@lru_cache(maxsize=4)
def _leaf(name):
    if name not in {'agent_hooks', 'task_intent', 'telemetry', 'runtime_identity'}:
        raise ValueError('Only fixed standard-library hook support modules can be loaded')
    path = ROOT / 'human_eye_plugin' / (name + '.py')
    spec = importlib.util.spec_from_file_location('_human_eye_hook_leaf_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _host_id(value):
    return value if (isinstance(value, str) and 0 < len(value) <= 256
                     and not any(ord(char) < 32 for char in value)) else None


def _context(kind, text, *, deny=False):
    value = {'hookEventName': kind, 'additionalContext': text}
    if deny:
        value.update(permissionDecision='deny', permissionDecisionReason=text)
    return {'hookSpecificOutput': value}


def _record(service, event, **fields):
    try:
        return service.record_event(event, **fields)
    except Exception:
        return False


def write_audit_event(audit_path, event, *, lock_factory, **fields):
    """The shared bounded, locked operational log; never a state/session write."""
    item = {'time_unix': time.time(), 'pid': os.getpid(), 'event': event, **fields}
    try:
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_factory(audit_path, timeout_s=10):
            if audit_path.exists() and audit_path.stat().st_size > 2 * 1024 * 1024:
                lines = audit_path.read_bytes().splitlines()[-1000:]
                audit_path.write_bytes(b'\n'.join(lines) + b'\n')
            with audit_path.open('a', encoding='utf-8') as handle:
                handle.write(json.dumps(item, ensure_ascii=True, allow_nan=False) + '\n')
        return True
    except (OSError, ValueError):
        return False


def try_light_route(event, service, *, agent='codex', invocation_source='hook_command',
                    classifier=None, trace_factory=None, implementation_revision=None,
                    context_factory=None):
    """Return (handled, output, intent). False delegates to the ordinary engine.

    A handled result never calls observe/preview, changes state or allows an
    action. Both the package entry and lightweight entry share this policy.
    """
    if agent not in {'codex', 'claude'} or not isinstance(event, dict):
        raise ValueError('Invalid hook host or event')
    kind, tool = event.get('hook_event_name'), event.get('tool_name')
    if kind not in HOOK_EVENTS or kind != 'UserPromptSubmit' and tool not in SUPPORTED_TOOLS:
        return True, {}, None
    context_factory = context_factory or _context
    if not service.config.get('enabled', True):
        denied = kind == 'PreToolUse' and tool in SPATIAL_WRITE_TOOLS
        return True, context_factory(kind, 'Human-Eye live connector is disabled.', deny=True) if denied else {}, None
    if kind == 'UserPromptSubmit' and not service.config.get('observe_on_prompt', True):
        return True, {}, None
    sid = event.get('session_id')
    if not isinstance(sid, str) or not sid:
        denied = kind == 'PreToolUse' and tool in SPATIAL_WRITE_TOOLS
        return True, context_factory(kind, 'Human-Eye requires a host session identity.', deny=True) if denied else {}, None
    intent = None
    prompt_fields = {}
    if kind == 'UserPromptSubmit':
        instruction, prompt_input = host_prompt(event, agent=agent)
        prompt_fields = {'prompt_input': prompt_input}
        classifier = classifier or _leaf('task_intent').classify_task_intent
        intent = classifier(instruction, task_kind=event.get('task_kind'))
        if intent['kind'] == 'spatial_3d':
            return False, None, intent
    elif kind != 'PostToolUse':
        return False, None, None
    # Only the no-observation branch loads lightweight telemetry. Spatial
    # branches use the normal package telemetry and its one ContextVar tree.
    trace_factory = trace_factory or _leaf('telemetry').best_effort_trace
    revision = implementation_revision or _leaf('runtime_identity').IMPLEMENTATION_REVISION
    session_id = agent + ':' + sid
    actual_ids = {field: _host_id(event.get(field)) for field in ('turn_id', 'tool_use_id')}
    def write(record):
        return _record(service, 'request_trace', trace=record, hook_event=kind,
            session_id=session_id, **actual_ids, invocation_source=invocation_source, **prompt_fields)
    operation = 'hook.readback' if kind == 'PostToolUse' else 'hook.prompt'
    with trace_factory(operation, writer=write, implementation_revision=revision) as trace:
        if trace is not None:
            try:
                trace.set_image_request(False, source_name='host_hook')
            except Exception:
                pass
            trace.annotate(session_id=session_id, **actual_ids, include_image=False,
                request_origin=invocation_source, delivery='text_only_hook_no_native_image')
        if kind == 'PostToolUse':
            _record(service, 'host_hook_skip', hook_event=kind, session_id=session_id,
                **actual_ids, invocation_source=invocation_source, engine_invoked=False,
                scene_read=False, status='tool_result_delivery_retained')
            if trace is not None:
                trace.annotate(engine_invoked=False, route='native', status='duplicate_delivery_omitted')
                trace.set_outcome('duplicate_delivery_omitted')
        else:
            _record(service, 'host_hook_skip', hook_event=kind, session_id=session_id,
                **actual_ids, invocation_source=invocation_source, intent=intent,
                engine_invoked=False, scene_read=False, status='intent_' + intent['kind'], **prompt_fields)
            if trace is not None:
                trace.annotate(engine_invoked=False, route='native', status='intent_' + intent['kind'])
                trace.set_outcome('intent_' + intent['kind'])
    return True, {}, intent


class _LightService:
    def __init__(self, config_path, config):
        helpers = _leaf('agent_hooks')
        self.config_path = Path(config_path).resolve()
        self.config = config
        if config.get('schema_version') != '1.0':
            raise ValueError('Unsupported live connector configuration')
        for field in ('enabled', 'observe_on_prompt'):
            if field in config and not isinstance(config[field], bool):
                raise ValueError(field + ' must be a boolean')
        self.root = helpers._path(self.config_path.parent, config.get('project_root'), 'project_root')
        state = helpers._path(self.config_path.parent, config.get('state_file'), 'state_file')
        self.audit_path = helpers._path(self.config_path.parent, config.get('audit_file'), 'audit_file')
        paths = {self.config_path, state, self.audit_path,
                 state.with_name(state.name + '.lock'), self.audit_path.with_name(self.audit_path.name + '.lock')}
        if len(paths) != 5:
            raise ValueError('Configuration, state, audit and lock paths must be distinct')
        identity = _leaf('runtime_identity')
        self._identity = identity.runtime_identity(mode='live')
        self._identity_check = identity.validate_expected_identity(config.get('expected_identity'), self._identity)

    def record_event(self, event, **fields):
        # Pin failures are truthful operational facts, never geometry claims.
        fields.setdefault('runtime_identity', {k: self._identity[k]
            for k in ('implementation_revision', 'build_id', 'source_kind')})
        fields.setdefault('identity_check', self._identity_check)
        return write_audit_event(self.audit_path, event,
            lock_factory=_leaf('agent_hooks')._state_lock, **fields)


def _parse_event(raw, declared_event=None):
    if len(raw) > 1024 * 1024:
        raise ValueError('Hook input exceeds 1 MiB')
    event = json.loads(raw.decode('utf-8-sig'), parse_constant=_leaf('agent_hooks')._reject_constant)
    if not isinstance(event, dict):
        raise ValueError('Hook input must be an object')
    if declared_event is not None and event.get('hook_event_name') != declared_event:
        raise ValueError('Hook event does not match its trusted registration')
    if declared_event == 'PreToolUse' and event.get('tool_name') not in SPATIAL_WRITE_TOOLS:
        raise ValueError('The registered pre-action hook requires an exact supported structured spatial tool')
    return event


def _failure_output(event, declared_event=None):
    if declared_event == 'PreToolUse' or (isinstance(event, dict)
            and event.get('hook_event_name') == 'PreToolUse' and event.get('tool_name') in SPATIAL_WRITE_TOOLS):
        return _context('PreToolUse', 'Human-Eye live routing is unavailable; structured spatial action blocked.', deny=True)
    return {}


def _engine_entry():
    # Inspect existing modules before any package code can run, then put this
    # exact root first even when it was already later on sys.path.
    for name, relative in (('human_eye_plugin', 'human_eye_plugin/__init__.py'),
                           ('human_eye_plugin.live_hooks', 'human_eye_plugin/live_hooks.py')):
        loaded = sys.modules.get(name)
        if loaded is not None:
            filename = getattr(loaded, '__file__', None)
            if not isinstance(filename, str) or Path(filename).resolve() != ROOT / relative:
                raise ValueError('Heavy hook entry belongs to a different runtime root')
    sys.path[:] = [str(ROOT), *(value for value in sys.path if value != str(ROOT))]
    from human_eye_plugin.live_hooks import execute_command_event
    if Path(sys.modules['human_eye_plugin.live_hooks'].__file__).resolve() != ROOT / 'human_eye_plugin/live_hooks.py':
        raise ValueError('Heavy hook entry belongs to a different runtime root')
    return execute_command_event


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--agent', choices=('codex', 'claude'), default='codex')
    parser.add_argument('--probe', action='store_true')
    parser.add_argument('--event', choices=HOOK_EVENTS, help='Trusted registration event; malformed pre-action input fails closed')
    args = parser.parse_args(argv)
    event = {}
    try:
        event = _parse_event(sys.stdin.buffer.read(1024*1024+1), args.event)
        kind, tool = event.get('hook_event_name'), event.get('tool_name')
        if kind not in HOOK_EVENTS or kind != 'UserPromptSubmit' and tool not in SUPPORTED_TOOLS:
            output = {}
        else:
            config = _leaf('agent_hooks')._read_object(args.config.resolve())
            # Check the routing condition before loading the heavy package.
            needs_engine = kind == 'PreToolUse'
            if kind == 'UserPromptSubmit' and config.get('enabled', True) and config.get('observe_on_prompt', True):
                instruction, _ = host_prompt(event, agent=args.agent)
                needs_engine = _leaf('task_intent').classify_task_intent(
                    instruction, task_kind=event.get('task_kind'))['kind'] == 'spatial_3d'
            if needs_engine:
                output = _engine_entry()(event, args.config, agent=args.agent, probe=args.probe)
            else:
                service = _LightService(args.config, config)
                handled, output, _ = try_light_route(event, service, agent=args.agent,
                    invocation_source='manual_probe' if args.probe else 'hook_command')
                if not handled:
                    raise ValueError('Unexpected observation request in lightweight hook')
    except Exception:
        output = _failure_output(event, args.event)
    sys.stdout.write(json.dumps(output, ensure_ascii=True, allow_nan=False) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
