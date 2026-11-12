"""Optional task correlation labels, never host identity or action authority."""
from __future__ import annotations

import copy

TASK_CONTEXT_SCHEMA = {'type': 'object', 'additionalProperties': False,
    'required': ['task_id', 'task_run_id'], 'properties': {
        key: {'type': 'string', 'minLength': 1, 'maxLength': 128}
        for key in ('task_id', 'task_run_id')}}


def validate_task_context(value):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {'task_id', 'task_run_id'}:
        raise ValueError('task_context requires only task_id and task_run_id')
    if any(not isinstance(text, str) or not text.strip() or not 1 <= len(text) <= 128
           or any(ord(char) < 32 for char in text) for text in value.values()):
        raise ValueError('task correlation IDs must be bounded nonempty text')
    try:
        for text in value.values():
            text.encode('utf-8')
    except UnicodeEncodeError as exc:
        raise ValueError('task correlation IDs must be valid UTF-8 text') from exc
    return dict(value)


def _trace_labels(trace):
    if trace is None:
        return None
    try:
        correlation = getattr(trace, 'task_correlation', None)
        if correlation is None:
            correlation = trace.record['correlation']
        if not any(correlation.get(key) is not None for key in ('task_id', 'task_run_id')):
            return None
        return {key: correlation.get(key) for key in ('task_id', 'task_run_id')}
    except Exception:
        return None


def trace_task_context(trace):
    try:
        return validate_task_context(_trace_labels(trace))
    except ValueError:
        return None


def bind_task_context(trace, value):
    """Refuse conflicting explicit labels before work rather than overwrite them."""
    value = validate_task_context(value)
    labels = _trace_labels(trace)
    try:
        existing = validate_task_context(labels)
    except ValueError:
        if value is not None:
            raise ValueError('Explicit task_context cannot replace incomplete enclosing labels')
        existing = None
    if value is not None and existing is not None and value != existing:
        raise ValueError('task_context conflicts with the enclosing request trace')
    if trace is not None and value is not None:
        # Instrumentation can fail without changing completed scene work.
        try:
            trace.annotate(**value)
        except Exception:
            return None
    return copy.deepcopy(existing if value is None else value)


SCENE_DELTA_REQUEST_SCHEMA = {'type': 'object', 'additionalProperties': False,
    'description': 'Optional observation-only snapshot transport. Empty object asks for full resync; a complete base revision and SHA256 enables a delta when worthwhile.',
    'properties': {'base_revision': {'type': 'string', 'minLength': 1, 'maxLength': 256},
                   'base_fingerprint': {'type': 'string', 'pattern': '^[a-f0-9]{64}$'}},
    'dependentRequired': {'base_revision': ['base_fingerprint'], 'base_fingerprint': ['base_revision']}}


def validate_scene_delta_request(value):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) not in (set(), {'base_revision', 'base_fingerprint'}):
        raise ValueError('scene_delta requires both base_revision and base_fingerprint, or an empty object')
    if value:
        revision, fingerprint = value['base_revision'], value['base_fingerprint']
        if (not isinstance(revision, str) or not revision.strip() or len(revision) > 256
                or not isinstance(fingerprint, str) or len(fingerprint) != 64
                or any(character not in '0123456789abcdef' for character in fingerprint)):
            raise ValueError('Invalid scene delta base reference')
        try:
            revision.encode('utf-8')
        except UnicodeEncodeError as exc:
            raise ValueError('Scene base revision must be valid UTF-8 text') from exc
    return dict(value)


__all__ = ['TASK_CONTEXT_SCHEMA', 'validate_task_context', 'trace_task_context', 'bind_task_context',
           'SCENE_DELTA_REQUEST_SCHEMA', 'validate_scene_delta_request']
