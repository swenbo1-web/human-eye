"""Command hook entry for current Blender scenes and checked spatial tools."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .agent_hooks import _context, _read_object, _reject_constant
from .live_service import LiveSpatialService, StateBindingError, RequestBudgetError
from .blender_process import HostTransportError
from .runtime_identity import IMPLEMENTATION_REVISION
from .task_intent import classify_task_intent
from .telemetry import best_effort_trace, set_image_request
from .hook_context import compact_hook_summary, denial_reason, encode_hook_summary
from human_eye_hook import (try_light_route, host_prompt, _parse_event, _failure_output,
                            SPATIAL_CLEARANCE_SEGMENT, SPATIAL_WRITE_TOOLS)


SPATIAL_TRANSFORM = "mcp__human_eye_live__human_eye_transform"
SPATIAL_OBSERVE = "mcp__human_eye_live__human_eye_scene_observe"
SPATIAL_STATUS = "mcp__human_eye_live__human_eye_connection_status"
SUPPORTED_TOOLS = {*SPATIAL_WRITE_TOOLS, SPATIAL_OBSERVE, SPATIAL_STATUS}


def _record_event(service, event, **fields):
    try:
        return service.record_event(event, **fields)
    except Exception:
        # Ancillary evidence cannot change a checked operation's disposition.
        return False


def _host_id(value):
    return value if (isinstance(value, str) and 0 < len(value) <= 256
                     and not any(ord(char) < 32 for char in value)) else None


def _reason_codes(result, routing):
    for value in (result.get("reason_codes"), routing.get("reason_codes")):
        if (isinstance(value, list) and value
                and all(isinstance(code, str) and code.strip() for code in value)):
            return value
    return []


def _runtime_summary(service):
    """Local descriptor only, never event-supplied identity or a host capture."""
    try:
        identity = service.describe_runtime()
        return {key: identity.get(key) for key in
                ('implementation_revision', 'build_id', 'source_kind', 'production_mode')}
    except Exception:
        return None


def _trace_failure(trace, outcome):
    """Ancillary failure reporting cannot replace the hook's disposition."""
    if trace is None:
        return
    try:
        trace.set_outcome(outcome)
    except Exception:
        pass
    try:
        trace.annotate(status=outcome)
    except Exception:
        pass


def _trace_id(trace, field):
    try:
        return _host_id(getattr(trace, field, None))
    except Exception:
        return None


def _unavailable_observation(session_id, intent, actual_ids, trace, identity,
                             invocation_source):
    """A failed current read supplies no historical scene or action authority."""
    reason = 'host_observation_unavailable'
    return {
        'human_eye_live': 'unavailable',
        'session_id': session_id,
        'observation_status': 'unavailable',
        'reason_codes': [reason],
        'message': ('The current spatial observation could not be completed. '
                    'No current geometry or clearance is certified; verify the '
                    'Blender connection before requesting a fresh observation.'),
        'requires_reobserve': True,
        'task_intent': intent,
        'scene_assessment': {'status': 'unknown', 'scope': 'all_scene_objects',
                             'reason_codes': [reason]},
        'action_eligibility': {'status': 'blocked', 'reason_codes': [reason],
                               'execution_authority': False},
        'allow_action': None,
        'execution_status': 'not_requested',
        'execution_authority': False,
        'retry_authorized': False,
        'inner_execution_gate_required': True,
        'delivery': 'text_only_hook_no_native_image',
        'runtime_identity': identity,
        'correlation': {**actual_ids, 'trace_id': _trace_id(trace, 'trace_id'),
                        'request_id': _trace_id(trace, 'request_id'),
                        'request_origin': invocation_source},
    }


def route_live_hook(event, service, *, agent="codex", invocation_source="hook_command"):
    if agent not in {"codex", "claude"} or not isinstance(event, dict):
        raise ValueError("Invalid hook host or event")
    handled, output, intent = try_light_route(event, service, agent=agent,
        invocation_source=invocation_source, classifier=classify_task_intent,
        trace_factory=best_effort_trace, implementation_revision=IMPLEMENTATION_REVISION,
        context_factory=_context)
    if handled:
        return output
    kind = event.get("hook_event_name")
    tool = event.get("tool_name")
    sid = event.get("session_id")
    session_id = agent + ":" + sid
    actual_ids = {field: _host_id(event.get(field)) for field in ("turn_id", "tool_use_id")}
    instruction, prompt_input = host_prompt(event, agent=agent)
    prompt_fields = {'prompt_input': prompt_input} if kind == 'UserPromptSubmit' else {}
    identity = _runtime_summary(service)
    def write(record):
        return _record_event(service, "request_trace", trace=record, hook_event=kind,
                             session_id=session_id, **actual_ids, invocation_source=invocation_source, **prompt_fields)
    operations = {"UserPromptSubmit": "hook.prompt", "PreToolUse": "hook.preview", "PostToolUse": "hook.readback"}
    with best_effort_trace(operations[kind], writer=write,
            implementation_revision=IMPLEMENTATION_REVISION) as trace:
        if trace is not None:
            try:
                set_image_request(False, source_name='host_hook')
                trace.annotate(session_id=session_id, **actual_ids, include_image=False,
                               request_origin=invocation_source, delivery="text_only_hook_no_native_image")
                if identity is not None:
                    trace.annotate(build_id=identity.get('build_id'))
            except Exception:
                pass
        deny = False
        try:
            if kind == "PreToolUse":
                if tool == SPATIAL_CLEARANCE_SEGMENT:
                    # A request may replay a durable receipt. Capturing a new
                    # scene here would incorrectly make replay depend on the
                    # current host. The real service still owns all write gates.
                    from .live_spatial_mcp import _validate_arguments
                    arguments = event.get('tool_input')
                    _validate_arguments('human_eye_clearance_segment', arguments)
                    summary = {'human_eye_live': 'goal_request_structure_valid',
                        'session_id': session_id, 'validation_scope': 'request_shape_only',
                        'execute_requested': arguments.get('execute', False),
                        'execution_authority': False, 'inner_execution_gate_required': True,
                        'scene_read': False, 'engine_invoked': False,
                        'execution_status': 'not_requested_by_hook', 'retry_authorized': False,
                        'delivery': 'text_only_hook_no_native_image',
                        'runtime_identity': identity,
                        'correlation': {**actual_ids, 'request_origin': invocation_source}}
                    _record_event(service, 'host_hook', hook_event=kind,
                        session_id=session_id, **actual_ids, tool_name=tool,
                        invocation_source=invocation_source, engine_invoked=False,
                        scene_read=False, denied=False, status='goal_request_structure_valid')
                    if trace is not None:
                        trace.set_outcome('goal_request_structure_valid')
                    return _context(kind, json.dumps(summary, ensure_ascii=True, allow_nan=False))
                if tool != SPATIAL_TRANSFORM:
                    return {}
                arguments = event.get("tool_input")
                if not isinstance(arguments, dict) or not isinstance(arguments.get("action"), dict):
                    raise ValueError("Structured transform input is required")
                result = service.preview_action(session_id, arguments["action"], include_image=False)
                deny = result.get("allow_action") is not True
            else:
                result = service.observe(session_id,
                    task_instruction=instruction if isinstance(instruction, str) else "", include_image=False)
            route = result.get("routing") or {}
            _record_event(service, "host_hook", hook_event=kind, session_id=session_id,
                **actual_ids, invocation_source=invocation_source, route=route.get("route"),
                scene_revision=route.get("scene_revision"), engine_invoked=route.get("engine_invoked", False),
                denied=deny, status=result.get("status"), intent=intent, **prompt_fields)
            summary = {"human_eye_live": result.get("status"),
                       "session_id": session_id, "observation": route.get("context_text", ""),
                       "reason_codes": _reason_codes(result, route),
                       "task_intent": intent, "allow_action": result.get("allow_action"),
                       "delivery": "text_only_hook_no_native_image",
                       "execution_scope": route.get("execution_scope", "terminal_geometry_only"),
                       "inner_execution_gate_required": True}
            # Keep pair goals, observation availability and execution separate.
            # Only service-defined range/capability fields are forwarded; no
            # arbitrary prompt, mesh or model-selected instruction is promoted.
            for field in ("observation_status", "scene_assessment", "action_eligibility",
                          "pair_goal", "execution_status", "task_succeeded_scope", "host_execution", "visual_delivery"):
                if field in result:
                    summary[field] = result[field]
            summary = compact_hook_summary(summary, result, route,
                correlation={**actual_ids, 'trace_id': trace.trace_id if trace is not None else None,
                    'request_id': trace.request_id if trace is not None else None,
                    'request_origin': invocation_source}, identity=identity)
            text = encode_hook_summary(summary)
            output = _context(kind, text, deny=deny)
            if deny:
                output['hookSpecificOutput']['permissionDecisionReason'] = denial_reason(summary,
                    result=result, route=route)
            return output
        except Exception as exc:
            if isinstance(exc, HostTransportError) and kind == 'UserPromptSubmit':
                outcome = 'host_observation_unavailable'
            elif isinstance(exc, StateBindingError):
                outcome = 'hook_state_binding_refused'
            elif isinstance(exc, RequestBudgetError):
                outcome = 'hook_request_budget_exhausted'
            else:
                outcome = 'hook_error'
            _trace_failure(trace, outcome)
            _record_event(service, "host_hook_error", hook_event=kind, session_id=session_id,
                **actual_ids, invocation_source=invocation_source, error_type=type(exc).__name__,
                status=outcome, **prompt_fields)
            if isinstance(exc, HostTransportError) and kind == 'UserPromptSubmit':
                failure = _unavailable_observation(session_id, intent, actual_ids,
                                                   trace, identity, invocation_source)
                return _context(kind, encode_hook_summary(failure))
            if isinstance(exc, (StateBindingError, RequestBudgetError)):
                failure = {'human_eye_live': 'blocked', 'error': str(exc),
                    'allow_action': False if kind == 'PreToolUse' else None,
                    'execution_status': 'not_executed', 'inner_execution_gate_required': True,
                    'delivery': 'text_only_hook_no_native_image', **exc.to_error_fields()}
                return _context(kind, encode_hook_summary(failure),
                                 deny=kind == 'PreToolUse' and tool in SPATIAL_WRITE_TOOLS)
            if kind == "PreToolUse" and tool in SPATIAL_WRITE_TOOLS:
                return _context(kind, "Human-Eye could not validate this structured spatial action; refresh the Blender connection.", deny=True)
            # A closed Blender must not block ordinary project work.
            return {}


def execute_command_event(event, config_path, *, agent="codex", probe=False):
    """Normal production path shared with the lightweight command dispatcher."""
    if (event.get("hook_event_name") not in {"UserPromptSubmit", "PreToolUse", "PostToolUse"}
            or event.get("hook_event_name") != "UserPromptSubmit" and event.get("tool_name") not in SUPPORTED_TOOLS):
        return {}
    service = LiveSpatialService(config_path, production_mode=True)
    return route_live_hook(event, service, agent=agent,
        invocation_source="manual_probe" if probe else "hook_command")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--agent", choices=("codex", "claude"), default="codex")
    parser.add_argument("--probe", action="store_true", help="Label manual protocol tests; does not prove a host hook fired")
    parser.add_argument("--event", choices=("UserPromptSubmit", "PreToolUse", "PostToolUse"))
    args = parser.parse_args(argv)
    event = {}
    try:
        event = _parse_event(sys.stdin.buffer.read(1024*1024+1), args.event)
        output = execute_command_event(event, args.config, agent=args.agent, probe=args.probe)
    except Exception:
        output = _failure_output(event, args.event)
    sys.stdout.write(json.dumps(output, ensure_ascii=True, allow_nan=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
