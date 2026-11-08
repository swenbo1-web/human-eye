"""Bounded parent/child accounting inside the connector's atomic state.

All functions mutate only the supplied JSON value. The trusted service MUST
hold its connector lock, persist reservations before dispatch, and persist a
failed/frozen transition before returning. This is not an authorization API.
Clock domains and independent physical meters come from the trusted caller,
not tool arguments. A missing child after reservation is never proof of no write.
"""
from __future__ import annotations

import copy
from dataclasses import asdict
import hashlib
import json
import math
import re

from .goal_budget import (GoalBudget, GoalBudgetLimits, GoalBudgetError,
                          GoalBudgetStopped, _digest)

MAX_GOALS = 16
MAX_JOURNAL_BYTES = 16 * 1024 * 1024
_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$')
_ROOT_KEYS = {'schema_version', 'records'}
_RECORD_KEYS = {'session_id', 'limits', 'clock_domain', 'started_monotonic',
    'deadline_monotonic', 'last_seen_monotonic', 'status', 'reason', 'children'}
_CHILD_KEYS = {'request_id', 'request', 'reserved_monotonic',
    'dispatched_monotonic', 'confirmed_monotonic', 'receipt_digest',
    'child_record_digest', 'physical_meter', 'original_request_digest'}
_HEX = re.compile(r'^[a-f0-9]{64}$')
_METER_KEYS = {'complete', 'actual_setter_count', 'actual_cumulative_translation_m',
               'step_motions_m', 'rollback_count'}


class GoalJournalError(ValueError):
    pass


class GoalJournalStopped(GoalJournalError):
    pass


def _id(value, label):
    if type(value) is not str or not _ID.fullmatch(value):
        raise GoalJournalError(label + ' requires 1..128 simple identity characters')
    return value


def _time(value):
    try: valid = type(value) in (int, float) and math.isfinite(value) and value >= 0
    except OverflowError: valid = False
    if not valid:
        raise GoalJournalError('invalid monotonic timestamp')
    return float(value)


def _json(value):
    def plain(item):
        if type(item) is dict:
            if any(type(k) is not str for k in item):
                raise GoalJournalError('journal JSON keys must be strings')
            for v in item.values(): plain(v)
        elif type(item) is list:
            for v in item: plain(v)
        elif item is None or type(item) in (str, bool):
            return
        elif type(item) in (int, float):
            if not math.isfinite(item): raise GoalJournalError('nonfinite journal number')
        else:
            raise GoalJournalError('journal requires plain JSON')
    try:
        plain(value)
        encoded = json.dumps(value, sort_keys=True, separators=(',', ':'),
            ensure_ascii=True, allow_nan=False).encode('utf-8')
        if len(encoded) > MAX_JOURNAL_BYTES:
            raise GoalJournalError('goal journal size limit reached')
        return encoded
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        if isinstance(exc, GoalJournalError): raise
        raise GoalJournalError('invalid journal JSON') from exc


def _limits(value):
    try:
        limits = value if type(value) is GoalBudgetLimits else GoalBudgetLimits(**value)
        if type(limits) is not GoalBudgetLimits:
            raise GoalJournalError('invalid goal limits')
        return limits
    except (ValueError, TypeError, OverflowError) as exc:
        raise GoalJournalError('invalid goal limits') from exc


def _normalized_request(request):
    # The child executor owns normalization. Keeping its exact normalized JSON
    # here also makes the persisted request fingerprint byte-identical.
    from .goal_segment import validate_clearance_segment_request
    try:
        return validate_clearance_segment_request(request)
    except (ValueError, TypeError, OverflowError) as exc:
        raise GoalJournalError('invalid clearance request: ' + str(exc)) from exc


def _validate_physical_meter(meter):
    """A small accounting record, never a JSON proof of its own provenance."""
    if type(meter) is not dict or set(meter) != _METER_KEYS:
        raise GoalJournalError('physical meter requires exactly its five accounting fields')
    if meter['complete'] is not True:
        raise GoalJournalError('physical meter must be complete')
    for field in ('actual_setter_count', 'rollback_count'):
        if type(meter[field]) is not int or not 0 <= meter[field] <= 8:
            raise GoalJournalError('physical meter counter is outside its bound')
    motions = meter['step_motions_m']
    if type(motions) is not list or len(motions) > 8:
        raise GoalJournalError('physical meter has an invalid bounded step list')
    for amount in [meter['actual_cumulative_translation_m'], *motions]:
        try: valid = type(amount) in (int, float) and math.isfinite(amount) and 0 <= amount <= .008
        except OverflowError: valid = False
        if not valid: raise GoalJournalError('physical meter contains an invalid bounded amount')
    if len(_json(meter)) > 2048:
        raise GoalJournalError('physical meter exceeds its serialized bound')


def _child_entry(value, record, child):
    entry = value.get('goal_segments', {}).get('records', {}).get(child['request_id'])
    if type(entry) is not dict:
        raise GoalJournalStopped('reserved_child_has_no_durable_outcome')
    receipt = entry.get('result')
    if entry.get('status') not in {'satisfied', 'review_required', 'blocked'} or type(receipt) is not dict:
        raise GoalJournalStopped('child_outcome_is_unconfirmed_or_unknown')
    expected = {'session_id': record['session_id'], 'request': child['request']}
    fingerprint = hashlib.sha256(json.dumps(expected, sort_keys=True, ensure_ascii=True,
        allow_nan=False, separators=(',', ':')).encode()).hexdigest()
    parent_id = next((identity for identity, candidate in
        value.get('goal_supervision', {}).get('records', {}).items() if candidate is record), None)
    if (parent_id is None or entry.get('parent_goal_id') != parent_id
            or entry.get('session_id') != record['session_id']
            or entry.get('request') != child['request']
            or entry.get('request_fingerprint') != fingerprint
            or receipt.get('request_id') != child['request_id']
            or receipt.get('request') != child['request']
            or any(receipt.get(k) != entry.get(k) for k in
                ('segment_id', 'status', 'steps', 'base_revision', 'end_revision'))
            or receipt.get('replayed', False) is not False
            or receipt.get('historical_receipt', False) is not False):
        raise GoalJournalStopped('durable_child_parent_binding_mismatch')
    return entry, receipt


def _validate_existing_child_binding(value, goal_id, record, child):
    entry = value.get('goal_segments', {}).get('records', {}).get(child['request_id'])
    if entry is None: return
    fingerprint = hashlib.sha256(json.dumps({'session_id': record['session_id'],
        'request': child['request']}, sort_keys=True, ensure_ascii=True,
        allow_nan=False, separators=(',', ':')).encode()).hexdigest()
    if (type(entry) is not dict or child['dispatched_monotonic'] is None
            or entry.get('parent_goal_id') != goal_id
            or entry.get('session_id') != record['session_id']
            or entry.get('request') != child['request']
            or entry.get('request_fingerprint') != fingerprint):
        raise GoalJournalError('existing child parent binding mismatch')


def _rebuild(value, record, current=None):
    """Replay original event times; current time never rewrites reservations."""
    replay_clock = [record['started_monotonic']]
    budget = GoalBudget(_limits(record['limits']), clock=lambda: replay_clock[0],
                        started=record['started_monotonic'])
    original_triangle = None
    for child in record['children']:
        if _json(_normalized_request(child['request'])) != _json(child['request']):
            raise GoalJournalError('persisted child request is not normalized')
        replay_clock[0] = child['reserved_monotonic']
        reserved = budget.reserve_segment(child['request_id'], child['request'])
        if reserved['request'] != child['request']:
            raise GoalJournalError('persisted reservation expands its original deadline')
        triangle = child['request'].get('reference_triangle_index')
        if original_triangle is None: original_triangle = triangle
        elif triangle != original_triangle:
            raise GoalJournalError('original reference triangle changed')
        if child['confirmed_monotonic'] is not None:
            _validate_physical_meter(child['physical_meter'])
            entry, receipt = _child_entry(value, record, child)
            if (_digest(entry, MAX_JOURNAL_BYTES) != child['child_record_digest']
                    or _digest(receipt, MAX_JOURNAL_BYTES) != child['receipt_digest']):
                raise GoalJournalError('confirmed durable child changed')
            replay_clock[0] = child['confirmed_monotonic']
            budget.confirm_segment(receipt, physical_meter=child['physical_meter'])
    replay_clock[0] = record['last_seen_monotonic'] if current is None else current
    return budget, replay_clock


def _stop(record, reason, *, value=None):
    previous = record['status'], record['reason']
    record['status'] = 'frozen'
    record['reason'] = str(reason)[:256]
    if value is not None:
        try: _json(value['goal_supervision'])
        except GoalJournalError:
            # A failure marker must not make an otherwise loadable pending
            # journal exceed its hard bound. "!" means reconciliation failed;
            # the raised exception retains the precise diagnosis. Its JSON is
            # smaller than null; "frozen" is no longer than "pending".
            record['reason'] = '!'
            try: _json(value['goal_supervision'])
            except GoalJournalError:
                record['status'], record['reason'] = previous
    raise GoalJournalStopped(str(reason)[:256])


def _validate_goal_journal(value):
    """Strict bounded shape, ownership, event chronology and budget replay."""
    if 'goal_supervision' not in value:
        for entry in value.get('goal_segments', {}).get('records', {}).values():
            if type(entry) is dict and 'parent_goal_id' in entry:
                raise GoalJournalError('supervised child has no parent journal')
        return
    ledger = value['goal_supervision']
    _json(ledger)
    if (type(ledger) is not dict or set(ledger) != _ROOT_KEYS
            or ledger['schema_version'] != 'goal-supervision-v1'
            or type(ledger['records']) is not dict or len(ledger['records']) > MAX_GOALS):
        raise GoalJournalError('invalid goal supervision ledger')
    owned = set()
    blockers = []
    for goal_id, record in ledger['records'].items():
        _id(goal_id, 'goal_id')
        if type(record) is not dict or set(record) != _RECORD_KEYS:
            raise GoalJournalError('invalid parent goal record')
        _id(record['session_id'], 'session_id'); _id(record['clock_domain'], 'clock_domain')
        limits = _limits(record['limits'])
        if record['limits'] != asdict(limits): raise GoalJournalError('goal limits not normalized')
        started = _time(record['started_monotonic'])
        if record['deadline_monotonic'] != started + limits.max_duration_s:
            raise GoalJournalError('persisted parent deadline changed')
        last = _time(record['last_seen_monotonic'])
        if last < started: raise GoalJournalError('persisted clock moved backwards')
        if record['status'] not in {'active', 'pending', 'completed', 'stopped', 'frozen'}:
            raise GoalJournalError('invalid parent status')
        if record['reason'] is not None and (type(record['reason']) is not str
                or not record['reason'] or len(record['reason']) > 256):
            raise GoalJournalError('invalid parent stop reason')
        if type(record['children']) is not list or len(record['children']) > limits.max_segments:
            raise GoalJournalError('invalid bounded child list')
        event_time = started
        pending = False
        for child in record['children']:
            if type(child) is not dict or set(child) != _CHILD_KEYS:
                raise GoalJournalError('invalid child journal entry')
            identity = _id(child['request_id'], 'request_id')
            if identity in owned: raise GoalJournalError('child request owned by multiple parents')
            owned.add(identity)
            if (type(child['original_request_digest']) is not str
                    or not _HEX.fullmatch(child['original_request_digest'])):
                raise GoalJournalError('invalid original request digest')
            if pending: raise GoalJournalError('child reservation follows an unconfirmed child')
            reserved = _time(child['reserved_monotonic'])
            if not event_time <= reserved < record['deadline_monotonic']:
                raise GoalJournalError('invalid reserve chronology')
            dispatch = child['dispatched_monotonic']; confirm = child['confirmed_monotonic']
            if dispatch is not None:
                if not reserved <= _time(dispatch) < record['deadline_monotonic']:
                    raise GoalJournalError('invalid dispatch chronology')
            if confirm is None:
                if any(child[k] is not None for k in ('physical_meter', 'receipt_digest', 'child_record_digest')):
                    raise GoalJournalError('unconfirmed child has confirmed accounting')
                pending = True; event_time = dispatch if dispatch is not None else reserved
            else:
                if dispatch is None or _time(confirm) < dispatch:
                    raise GoalJournalError('confirmation precedes dispatch')
                for key in ('receipt_digest', 'child_record_digest'):
                    if type(child[key]) is not str or not _HEX.fullmatch(child[key]):
                        raise GoalJournalError('invalid child digest')
                event_time = confirm
            _validate_existing_child_binding(value, goal_id, record, child)
        if event_time > last: raise GoalJournalError('events exceed last observed clock')
        try:
            budget, _ = _rebuild(value, record)
            snapshot = budget.snapshot()
        except (GoalBudgetError, GoalJournalError, ValueError, TypeError, KeyError, OverflowError) as exc:
            raise GoalJournalError('invalid parent budget replay: ' + str(exc)) from exc
        status = record['status']; reason = record['reason']
        if status == 'frozen':
            if reason is None: raise GoalJournalError('frozen parent needs a reason')
        elif pending:
            if status != 'pending' or reason is not None:
                raise GoalJournalError('pending child cannot release its parent')
        elif status == 'completed':
            if snapshot['stopped_reason'] != 'goal_satisfied' or reason != 'goal_satisfied':
                raise GoalJournalError('parent completion lacks an on-time satisfied child')
        elif status == 'stopped':
            derived = snapshot['stopped_reason']
            if derived is None:
                try: budget.next_request_caps()
                except GoalBudgetStopped as exc: derived = str(exc)
            if reason is None or reason != derived:
                raise GoalJournalError('parent stop is not derived from its history')
        elif status != 'active' or reason is not None or snapshot['stopped_reason'] is not None:
            raise GoalJournalError('parent active status contradicts its history')
        if pending or status in {'active', 'pending', 'frozen'}: blockers.append(goal_id)
    if len(blockers) > 1:
        raise GoalJournalError('multiple unresolved parent goals')
    for identity, entry in value.get('goal_segments', {}).get('records', {}).items():
        if type(entry) is dict and 'parent_goal_id' in entry:
            if identity not in owned or entry['parent_goal_id'] not in ledger['records']:
                raise GoalJournalError('orphan supervised child has no parent reservation')


def validate_goal_journal(value):
    try:
        if type(value) is not dict: raise GoalJournalError('connector state must be an object')
        _validate_goal_journal(value)
    except GoalJournalError:
        raise
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, OverflowError, RecursionError) as exc:
        raise GoalJournalError('invalid goal supervision state: ' + str(exc)) from exc


def blocking_goal(value):
    validate_goal_journal(value)
    for identity, record in value.get('goal_supervision', {}).get('records', {}).items():
        if (record['status'] in {'active', 'pending', 'frozen'}
                or any(c['confirmed_monotonic'] is None for c in record['children'])):
            return identity
    return None


def child_owner(value, request_id):
    validate_goal_journal(value)
    for identity, record in value.get('goal_supervision', {}).get('records', {}).items():
        if any(c['request_id'] == request_id for c in record['children']): return identity
    return None


def _record(value, goal_id, *, clock_domain, now):
    validate_goal_journal(value)
    _id(goal_id, 'goal_id')
    try: record = value['goal_supervision']['records'][goal_id]
    except KeyError as exc: raise GoalJournalError('unknown parent goal') from exc
    try:
        _id(clock_domain, 'trusted clock_domain'); instant = _time(now)
        if clock_domain != record['clock_domain']: _stop(record, 'trusted_clock_domain_changed')
        if instant < record['last_seen_monotonic']: _stop(record, 'trusted_monotonic_clock_moved_backwards')
    except GoalJournalError as exc:
        if isinstance(exc, GoalJournalStopped): raise
        _stop(record, 'trusted_monotonic_clock_unavailable')
    record['last_seen_monotonic'] = instant
    return record, instant


def _derived_status(record, budget):
    snap = budget.snapshot()
    if record['status'] != 'frozen' and snap['pending_request_id'] is None:
        reason = snap['stopped_reason']
        if reason is not None:
            record['status'] = 'completed' if reason == 'goal_satisfied' else 'stopped'
            record['reason'] = reason
    return snap


def _view(record, budget):
    snap = _derived_status(record, budget)
    return {**snap, 'schema_version': 'goal-journal-v1',
        'scope': 'connector_locked_durable_parent_children',
        'cross_process_or_crash_recovery': 'reconcile_known_children_only',
        'journal_status': record['status'], 'journal_reason': record['reason'],
        'clock_domain': record['clock_domain'], 'retry_authorized': False}


def create_goal(value, goal_id, session_id, *, limits=None, clock_domain, now):
    validate_goal_journal(value)
    _id(goal_id, 'goal_id'); _id(session_id, 'session_id'); _id(clock_domain, 'trusted clock_domain')
    instant = _time(now); normalized = asdict(_limits(GoalBudgetLimits() if limits is None else limits))
    records = value.get('goal_supervision', {}).get('records', {})
    if goal_id in records:
        existing = records[goal_id]
        if existing['session_id'] != session_id or existing['limits'] != normalized:
            _stop(existing, 'parent_identity_payload_conflict')
        return snapshot(value, goal_id, clock_domain=clock_domain, now=instant)
    if blocking_goal(value) is not None:
        raise GoalJournalStopped('another_parent_goal_requires_reconciliation')
    if value.get('inflight') is not None:
        raise GoalJournalStopped('unresolved_host_write_requires_review')
    if len(records) >= MAX_GOALS: raise GoalJournalStopped('parent_receipt_capacity_exhausted')
    record = {'session_id': session_id, 'limits': normalized, 'clock_domain': clock_domain,
        'started_monotonic': instant, 'deadline_monotonic': instant + normalized['max_duration_s'],
        'last_seen_monotonic': instant, 'status': 'active', 'reason': None, 'children': []}
    budget = GoalBudget(_limits(normalized), clock=lambda: instant, started=instant)
    result = _view(record, budget)
    value.setdefault('goal_supervision', {'schema_version': 'goal-supervision-v1', 'records': {}})['records'][goal_id] = record
    validate_goal_journal(value)
    return result


def snapshot(value, goal_id, *, clock_domain, now):
    record, instant = _record(value, goal_id, clock_domain=clock_domain, now=now)
    budget, _ = _rebuild(value, record, instant)
    return _view(record, budget)


def next_caps(value, goal_id, *, clock_domain, now):
    record, instant = _record(value, goal_id, clock_domain=clock_domain, now=now)
    budget, _ = _rebuild(value, record, instant)
    if record['status'] == 'frozen': raise GoalJournalStopped(record['reason'])
    try: return budget.next_request_caps()
    except GoalBudgetStopped as exc:
        if not any(c['confirmed_monotonic'] is None for c in record['children']):
            record.update(status='completed' if str(exc) == 'goal_satisfied' else 'stopped', reason=str(exc))
        raise GoalJournalStopped(str(exc)) from exc


def reserve_segment(value, goal_id, request_id, request, *, clock_domain, now):
    record, instant = _record(value, goal_id, clock_domain=clock_domain, now=now)
    _id(request_id, 'request_id')
    if type(request) is not dict: raise GoalJournalError('request must be a JSON object')
    raw_digest = _digest(request, 65536)
    request = _normalized_request(request)
    if record['status'] in {'frozen', 'stopped', 'completed'}:
        raise GoalJournalStopped(record['reason'] or 'parent_is_terminal')
    existing = next((c for c in record['children'] if c['request_id'] == request_id), None)
    if existing is not None:
        if raw_digest not in (existing['original_request_digest'], _digest(existing['request'], 65536)):
            _stop(record, 'request_id_payload_conflict')
        return {'fresh_reservation': False, 'request_id': request_id,
            'request': copy.deepcopy(existing['request']), 'execution_authority': False}
    if child_owner(value, request_id) is not None or request_id in value.get('goal_segments', {}).get('records', {}):
        _stop(record, 'child_request_identity_already_used')
    if record['children'] and request.get('reference_triangle_index') != record['children'][0]['request'].get('reference_triangle_index'):
        raise GoalJournalError('original reference triangle changed')
    budget, _ = _rebuild(value, record, instant)
    try: result = budget.reserve_segment(request_id, request)
    except GoalBudgetStopped as exc:
        if not any(c['confirmed_monotonic'] is None for c in record['children']):
            record.update(status='stopped', reason=str(exc))
        raise GoalJournalStopped(str(exc)) from exc
    except GoalBudgetError as exc: raise GoalJournalError(str(exc)) from exc
    child = {'request_id': request_id, 'request': copy.deepcopy(result['request']),
        'original_request_digest': raw_digest,
        'reserved_monotonic': instant, 'dispatched_monotonic': None,
        'confirmed_monotonic': None, 'receipt_digest': None, 'child_record_digest': None,
        'physical_meter': None}
    record['children'].append(child); record.update(status='pending', reason=None)
    validate_goal_journal(value)
    return result


def mark_dispatched(value, goal_id, request_id, session_id, request, *, clock_domain, now):
    record, instant = _record(value, goal_id, clock_domain=clock_domain, now=now)
    if record['status'] == 'frozen': raise GoalJournalStopped(record['reason'])
    if value.get('inflight') is not None: _stop(record, 'unresolved_host_write_requires_review')
    child = next((c for c in record['children'] if c['request_id'] == request_id), None)
    if (child is None or child['confirmed_monotonic'] is not None
            or child['dispatched_monotonic'] is not None):
        _stop(record, 'child_dispatch_is_not_a_fresh_reserved_transition')
    if record['session_id'] != session_id or _json(child['request']) != _json(request):
        _stop(record, 'child_dispatch_parent_binding_mismatch')
    if instant >= record['deadline_monotonic']:
        _stop(record, 'parent_deadline_reached_before_dispatch')
    if request_id in value.get('goal_segments', {}).get('records', {}):
        _stop(record, 'child_already_present_before_dispatch')
    child['dispatched_monotonic'] = instant
    return {'request_id': request_id, 'deadline_monotonic': record['deadline_monotonic'],
        'execution_authority': False, 'retry_authorized': False}


def confirm_segment(value, goal_id, request_id, *, physical_meter, clock_domain, now):
    record, instant = _record(value, goal_id, clock_domain=clock_domain, now=now)
    child = next((c for c in record['children'] if c['request_id'] == request_id), None)
    if child is None: _stop(record, 'unreserved_child_cannot_be_reconciled')
    # Freeze is deliberately absorbing. Recovering an uncertain goal requires
    # a separate explicit operator procedure; no new meter clears that stop.
    if record['status'] == 'frozen': raise GoalJournalStopped(record['reason'])
    if value.get('inflight') is not None: _stop(record, 'unresolved_host_write_requires_review')
    if child['dispatched_monotonic'] is None:
        _stop(record, 'child_was_not_marked_dispatched')
    try:
        _validate_physical_meter(physical_meter)
        entry, receipt = _child_entry(value, record, child)
        budget, _ = _rebuild(value, record, instant)
        if child['confirmed_monotonic'] is not None:
            budget.confirm_segment(receipt, physical_meter=physical_meter)
            result = _view(record, budget); result['deduplicated'] = True
            return result
        budget.confirm_segment(receipt, physical_meter=physical_meter)
        candidate = copy.deepcopy(child)
        candidate.update(confirmed_monotonic=instant,
            receipt_digest=_digest(receipt, MAX_JOURNAL_BYTES),
            child_record_digest=_digest(entry, MAX_JOURNAL_BYTES),
            physical_meter=copy.deepcopy(physical_meter))
        _json(candidate)
        # Validate the *whole* prospective journal before changing the live
        # child. A valid per-child packet can exceed the aggregate bound.
        candidate_value = dict(value)
        candidate_value['goal_supervision'] = copy.deepcopy(value['goal_supervision'])
        candidate_record = candidate_value['goal_supervision']['records'][goal_id]
        candidate_child = next(c for c in candidate_record['children'] if c['request_id'] == request_id)
        candidate_child.update(candidate)
        candidate_record.update(status='active', reason=None)
        result = _view(candidate_record, budget)
        validate_goal_journal(candidate_value)
        record.clear(); record.update(candidate_record)
        return result
    except (GoalBudgetError, GoalJournalError, ValueError, TypeError, KeyError, OverflowError) as exc:
        _stop(record, str(exc) or 'invalid_child_reconciliation', value=value)


def reconcile_child(value, goal_id, request_id, *, physical_meter, clock_domain, now):
    """Read the raw committed child ledger and account it, never resubmit it."""
    return confirm_segment(value, goal_id, request_id, physical_meter=physical_meter,
        clock_domain=clock_domain, now=now)


__all__ = ['GoalJournalError', 'GoalJournalStopped', 'validate_goal_journal',
    'create_goal', 'snapshot', 'next_caps', 'reserve_segment', 'mark_dispatched',
    'confirm_segment', 'reconcile_child', 'blocking_goal', 'child_owner']
