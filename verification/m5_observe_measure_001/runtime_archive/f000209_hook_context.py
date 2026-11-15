"""Model-facing hook projection; never an execution or measurement policy.

Repeated dictionaries use local JSON Pointers, preserving their exact JSON
values. Only explicitly named cache statistics are omitted. Full service/MCP
results, action decisions and state are not mutated.
"""
from __future__ import annotations

import copy
import json


CONTEXT_REVISION = 'hook-context-v2-20261024'
_SCOPED_FIELDS = ('observation_status', 'scene_assessment', 'action_eligibility',
    'pair_goal', 'execution_status', 'task_succeeded_scope', 'host_execution', 'scene_capabilities')
_GATE_FIELDS = ('geometry_work_budget', 'rigid_frame_valid', 'rigid_frame',
    'requires_reobserve', 'source_check')


def _encode(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(',', ':'))


def _reject_constant(value):
    raise ValueError('Non-finite JSON value: ' + value)


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('Ambiguous duplicate JSON key')
        value[key] = item
    return value


def _observation(value):
    if not isinstance(value, str):
        return '', 'unavailable'
    try:
        parsed = json.loads(value, parse_constant=_reject_constant, object_pairs_hook=_unique_object)
        _encode(parsed)  # Exponent overflow must not become a new numeric fact.
    except (ValueError, TypeError, RecursionError):
        return value, 'verbatim_unparsed'
    return (parsed, 'structured') if isinstance(parsed, dict) else (value, 'verbatim_unparsed')


def _deduplicate(value, path='#', seen=None):
    """Replace only identical dictionaries of substantial size, never lists.

    First occurrences stay in place. References point backward into this same
    document and preserve distinction between missing, null, false and zero.
    """
    if seen is None:
        seen = {}
    if isinstance(value, dict):
        key = _encode(value)
        if len(key) >= 256:
            if key in seen:
                return {'$ref': seen[key]}
            if 'object_id' in value:
                body = {k: v for k, v in value.items() if k != 'object_id'}
                base = _encode(body)
                if len(base) >= 256 and base in seen:
                    return {'$ref': seen[base], 'object_id': value['object_id']}
            seen[key] = path
        return {k: _deduplicate(v, path + '/' + k.replace('~', '~0').replace('/', '~1'), seen)
                for k, v in value.items()}
    if isinstance(value, list):
        return [_deduplicate(v, path + '/' + str(i), seen) for i, v in enumerate(value)]
    return value


def _contains_reference_key(value):
    if isinstance(value, dict):
        return '$ref' in value or any(_contains_reference_key(v) for v in value.values())
    if isinstance(value, list):
        return any(_contains_reference_key(v) for v in value)
    return False


def compact_hook_summary(summary, result, route, *, correlation, identity):
    """Build a detached display projection, keeping original decisions intact."""
    value = copy.deepcopy(summary)
    observation, status = _observation(value.get('observation'))
    omitted = []
    if isinstance(observation, dict):
        for field in ('scene_memory', 'measurement_cache'):
            diagnostic = observation.get(field)
            if isinstance(diagnostic, dict) and 'stats' in diagnostic:
                diagnostic.pop('stats')
                omitted.append('observation.' + field + '.stats')
    value['observation'] = observation
    for field in (*_SCOPED_FIELDS, *_GATE_FIELDS):
        if field in result:
            value[field] = copy.deepcopy(result[field])
        elif field in _GATE_FIELDS and field in route:
            value[field] = copy.deepcopy(route[field])
    value['scene_revision'] = route.get('scene_revision')
    value['observation_id'] = route.get('observation_id')
    value['correlation'] = copy.deepcopy(correlation)
    value['runtime_identity'] = copy.deepcopy(identity)
    reserved = _contains_reference_key(value)
    value['context_projection'] = {'revision': CONTEXT_REVISION, 'observation_format': status,
        'reference_encoding': 'disabled_reserved_key' if reserved else 'local_pointer_with_object_id',
        'references': 'none' if reserved else
            'Local JSON Pointer $ref copies an earlier dictionary; any object_id sibling is added without overriding its keys.',
        'omitted_diagnostics': omitted, 'execution_authority': False}
    # Host context limits can still apply. Put the actual decisions, scope,
    # provenance and codec header before the potentially large observation.
    # This is presentation ordering, never truncation or a new permission.
    value['observation'] = value.pop('observation')
    return value if reserved else _deduplicate(value)


def denial_reason(summary, *, result=None, route=None):
    """Avoid repeating the entire observation in the host's denial message."""
    original = result if isinstance(result, dict) else {}
    routing = route if isinstance(route, dict) else {}
    brief = {key: (original.get(key, summary.get(key)) if key in _SCOPED_FIELDS
                   else summary.get(key)) for key in
             ('human_eye_live', 'reason_codes', 'execution_scope', 'allow_action',
              'inner_execution_gate_required', 'scene_revision', *_SCOPED_FIELDS)}
    brief = _expand_local(summary, brief)
    observation = (_observation(routing['context_text'])[0] if 'context_text' in routing
                   else summary.get('observation'))
    if isinstance(observation, dict):
        for field in ('reason', 'detail'):
            if field in observation:
                brief[field] = observation[field]
    # Some hosts may expose only the denial reason when a tool is blocked.
    # Repeat actionable failure evidence here, never the full observation.
    for field in ('geometry_work_budget', 'rigid_frame'):
        detail = original.get(field, routing.get(field, summary.get(field)))
        if isinstance(detail, dict):
            if field not in original and field not in routing:
                detail = _expand_local(summary, detail)
            marker = 'within_budget' if field == 'geometry_work_budget' else 'valid'
            if isinstance(detail, dict) and detail.get(marker) is not True:
                brief[field] = detail
    if 'requires_reobserve' in summary:
        brief['requires_reobserve'] = summary['requires_reobserve']
    return 'Human-Eye structured transform blocked: ' + _encode(brief)


def _expand_local(document, value, active=()):
    """Make standalone denial evidence; never leave local pointers dangling."""
    if document.get('context_projection', {}).get('reference_encoding') != 'local_pointer_with_object_id':
        return copy.deepcopy(value)
    if isinstance(value, dict):
        if '$ref' in value:
            pointer = value['$ref']
            if not isinstance(pointer, str) or not pointer.startswith('#/') or pointer in active:
                raise ValueError('Invalid local reference')
            target = document
            for token in pointer[2:].split('/'):
                token = token.replace('~1', '/').replace('~0', '~')
                target = target[int(token)] if isinstance(target, list) else target[token]
            expanded = _expand_local(document, target, (*active, pointer))
            if 'object_id' in value:
                expanded['object_id'] = copy.deepcopy(value['object_id'])
            return expanded
        return {k: _expand_local(document, v, active) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_local(document, v, active) for v in value]
    return value


def encode_hook_summary(summary):
    return _encode(summary)
