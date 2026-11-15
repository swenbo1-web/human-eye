"""Bounded, request-driven recovery of optional annotation budget holds.

This observational record cannot grant action authority. A cache hit does not
spend an attempt or extend the episode. Regenerating a complete observation is
outside the refill-only cost account and must be measured separately.
"""
from __future__ import annotations

import copy
import math


RETRY_SCHEMA = 'visible_refill_retry_v1'
RETRY_DELAYS_S = (1.0, 2.0)
MAX_RETRY_COST_MS = 10.0
EPISODE_TTL_S = 30.0
BUDGET_REASONS = frozenset({
    'shared_refill_budget_unavailable',
    'refill_budget_exhausted_before_qualification',
    'refill_budget_exceeded_during_qualification',
    'refill_budget_exceeded_before_annotation',
    'refill_budget_exceeded_after_annotation',
    'refill_budget_exceeded_before_commit',
    'refill_budget_exceeded_during_release',
    'refill_budget_exceeded_before_proposal_commit',
    'visible_refill_integration_budget_exceeded',
    'refill_setup_budget_exceeded',
    'refill_capture_budget_exceeded',
})


def _number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _next_deadline(record):
    attempts = record['attempts']
    if attempts > len(RETRY_DELAYS_S) or record['retry_cost_ms'] >= MAX_RETRY_COST_MS:
        return None
    deadline = record['last_attempt_s'] + RETRY_DELAYS_S[attempts - 1]
    return deadline if deadline <= record['started_s'] + EPISODE_TTL_S else None


def retry_state(value, now, *, key):
    """Validate persisted bounds and exact observation identity before reuse."""
    fields = {'schema_version', 'key', 'started_s', 'last_attempt_s',
              'attempts', 'retry_cost_ms', 'retry_at_s'}
    if (type(value) is not dict or set(value) != fields or not _number(now)
            or value['schema_version'] != RETRY_SCHEMA
            or type(value['key']) is not str or value['key'] != key
            or len(value['key']) != 64
            or any(c not in '0123456789abcdef' for c in value['key'])
            or type(value['attempts']) is not int or not 1 <= value['attempts'] <= 3
            or not all(_number(value[name]) for name in
                       ('started_s', 'last_attempt_s', 'retry_cost_ms'))):
        return None
    started, last, cost = value['started_s'], value['last_attempt_s'], value['retry_cost_ms']
    if (not 0 <= now - started <= EPISODE_TTL_S or not started <= last <= now
            or cost < 0 or value['attempts'] == 1 and (cost != 0 or last != started)):
        return None
    expected = _next_deadline(value)
    actual = value['retry_at_s']
    if (actual is None) != (expected is None):
        return None
    if actual is not None and (not _number(actual) or actual != expected):
        return None
    return copy.deepcopy(value)


def retry_blocked(record, now):
    return record is not None and (record['retry_at_s'] is None or now < record['retry_at_s'])


def record_budget_failure(previous, *, key, now, cost_ms):
    """Record a real attempt, charging actual retry overruns without clipping."""
    if not _number(cost_ms) or cost_ms < 0 or not _number(now):
        raise ValueError('Refill recovery needs finite nonnegative actual cost')
    if previous is not None:
        previous = retry_state(previous, now, key=key)
        if previous is None or retry_blocked(previous, now):
            raise ValueError('Refill recovery attempt was not due')
    record = {'schema_version': RETRY_SCHEMA, 'key': key,
              'started_s': previous['started_s'] if previous else now,
              'last_attempt_s': now, 'attempts': previous['attempts'] + 1 if previous else 1,
              'retry_cost_ms': previous['retry_cost_ms'] + cost_ms if previous else 0.0,
              'retry_at_s': None}
    record['retry_at_s'] = _next_deadline(record)
    return record


def retry_evidence(record, *, attempted=False, reused=False):
    return {'schema_version': RETRY_SCHEMA, 'attempted': attempted,
            'evidence_reused': reused, 'attempts': record['attempts'] if record else 0,
            'additional_attempts_used': record['attempts'] - 1 if record else 0,
            'max_additional_attempts': len(RETRY_DELAYS_S),
            'retry_cost_ms': record['retry_cost_ms'] if record else 0.0,
            'retry_cost_limit_ms': MAX_RETRY_COST_MS,
            'retry_at_s': record['retry_at_s'] if record else None,
            'exhausted': record is not None and record['retry_at_s'] is None,
            'episode_expires_at_s': record['started_s'] + EPISODE_TTL_S if record else None,
            'cost_scope': 'additional_refill_only_excludes_complete_observation_regeneration',
            'budget_cap_is_cooperative': True, 'execution_authority': False}
