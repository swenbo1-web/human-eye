"""Task-scoped capabilities issued by a trusted embedding, not model JSON.

The issuer callback authenticates a stable task event. Python capabilities are
an in-process trust boundary, not a sandbox against arbitrary Python execution
or a remote attestation. Persisted JSON is an accounting/index record only.
All state helpers require the caller's connector lock and atomic persistence.
"""
from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
import hashlib
import hmac
import json
import math
import re
import secrets
import time

from .goal_budget import GoalBudgetLimits

MAX_AUTHORIZATIONS = 16
MAX_BYTES = 4 * 1024 * 1024
MAX_RESULT_BYTES = 8192
_HEX = re.compile(r'^[a-f0-9]{64}$')
_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$')
_SCOPE_FIELDS = {'engine_build_id', 'process_id', 'host_identity',
    'reference_triangle_index', 'initial_capture_sha256', 'initial_native_sha256', 'clock_domain'}
_PAYLOAD_FIELDS = {'schema_version', 'issuer_id', 'event_id', 'authorization_id',
    'key', 'goal_id', 'session_id', 'spec', 'spec_hash', 'scope',
    'issued_monotonic', 'deadline_monotonic'}
_RECORD_FIELDS = {'grant', 'grant_sha256', 'status', 'reason', 'result'}
_STATUSES = {'reserved', 'active', 'completed', 'stopped', 'frozen'}


class TaskAuthorityError(ValueError):
    pass


class TaskAuthorizationDenied(TaskAuthorityError):
    pass


def _require(condition, message):
    if not condition:
        raise TaskAuthorityError(message)


def _text(value, name, limit=256):
    _require(type(value) is str and bool(value.strip()) and len(value) <= limit,
             'Invalid bounded ' + name)
    return value


def _number(value, name, low=0., high=math.inf, *, positive=False):
    try: valid = type(value) in (int, float) and math.isfinite(value)
    except OverflowError: valid = False
    _require(valid and low <= value <= high and (not positive or value > 0), 'Invalid ' + name)
    return float(value)


def _json(value, maximum=MAX_BYTES):
    def plain(item, depth=0):
        _require(depth <= 24, 'Authorization JSON depth exceeded')
        if type(item) is dict:
            _require(all(type(key) is str for key in item), 'Authorization keys must be strings')
            for child in item.values(): plain(child, depth + 1)
        elif type(item) is list:
            _require(len(item) <= 4096, 'Authorization JSON array bound exceeded')
            for child in item: plain(child, depth + 1)
        elif type(item) in (int, float):
            _number(item, 'JSON number', -math.inf)
        else:
            _require(item is None or type(item) in (str, bool), 'Only plain authorization JSON is accepted')
    try:
        plain(value)
        raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                         allow_nan=False).encode('utf-8')
        _require(len(raw) <= maximum, 'Authorization byte bound exceeded')
        return raw
    except TaskAuthorityError:
        raise
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        raise TaskAuthorityError('Invalid authorization JSON') from exc


def _digest(value):
    return hashlib.sha256(_json(value)).hexdigest()


def _limits(value):
    _require(type(value) is GoalBudgetLimits, 'Explicit frozen GoalBudgetLimits required')
    # Normalize valid numeric spelling, without accepting bool as a number.
    rebuilt = GoalBudgetLimits(**asdict(value))
    return {'max_steps':rebuilt.max_steps,
        'max_step_translation_m':float(rebuilt.max_step_translation_m),
        'max_total_translation_m':float(rebuilt.max_total_translation_m),
        'max_duration_s':float(rebuilt.max_duration_s),
        'max_recoveries':rebuilt.max_recoveries,'max_segments':rebuilt.max_segments}


@dataclass(frozen=True)
class ClearanceTaskSpec:
    focal_id: str
    reference_id: str
    target_clearance_m: float = .001
    clearance_tolerance_m: float = 1e-6
    direction_world: tuple = (0., 0., 1.)
    reference_triangle_index: int | None = None
    limits: GoalBudgetLimits = field(default_factory=GoalBudgetLimits)

    def __post_init__(self):
        _text(self.focal_id, 'focal_id');_text(self.reference_id, 'reference_id')
        _require(self.focal_id != self.reference_id, 'Distinct task objects required')
        _number(self.target_clearance_m, 'target clearance', high=1., positive=True)
        _number(self.clearance_tolerance_m, 'clearance tolerance', high=1e-5)
        d = self.direction_world
        _require(type(d) is tuple and len(d) == 3, 'Frozen world Z direction required')
        for coordinate in d: _number(coordinate, 'direction coordinate', -1., 1.)
        _require(d[:2] == (0., 0.) and abs(d[2]) == 1., 'Only normalized world Z direction supported')
        index = self.reference_triangle_index
        _require(index is None or type(index) is int and 0 <= index < 1_000_000,
                 'Invalid original triangle index')
        _limits(self.limits)

    def to_dict(self):
        return {'solver':'support_plane','focal_id':self.focal_id,'reference_id':self.reference_id,
            'target_clearance_m':float(self.target_clearance_m),
            'clearance_tolerance_m':float(self.clearance_tolerance_m),
            'direction_world':[float(item) for item in self.direction_world],
            'reference_triangle_index':self.reference_triangle_index,'limits':_limits(self.limits)}


@dataclass(frozen=True)
class TaskApproval:
    event_id: str
    authorization_id: str

    def __post_init__(self):
        _text(self.event_id, 'authenticated task event')
        _text(self.authorization_id, 'authorization identity')


def _spec_from_dict(value):
    _require(type(value) is dict and set(value) == {'solver','focal_id','reference_id',
        'target_clearance_m','clearance_tolerance_m','direction_world','reference_triangle_index','limits'}
        and value['solver'] == 'support_plane', 'Invalid persisted task spec')
    _require(type(value['direction_world']) is list and type(value['limits']) is dict,
             'Invalid persisted task direction or limits')
    try:
        spec = ClearanceTaskSpec(value['focal_id'], value['reference_id'], value['target_clearance_m'],
            value['clearance_tolerance_m'], tuple(value['direction_world']),
            value['reference_triangle_index'], GoalBudgetLimits(**value['limits']))
    except (ValueError, TypeError, OverflowError) as exc:
        raise TaskAuthorityError('Invalid persisted task spec') from exc
    _require(spec.reference_triangle_index is not None and _json(spec.to_dict()) == _json(value),
             'Resolved normalized task spec required')
    return spec


def _scope(value, spec):
    _require(type(value) is dict and set(value) == _SCOPE_FIELDS, 'Complete resolved task scope required')
    build = value['engine_build_id']
    _require(type(build) is str and build.startswith('sha256:') and _HEX.fullmatch(build[7:]),
             'Explicit engine build required')
    _require(type(value['process_id']) is int and 1 <= value['process_id'] < 1 << 32, 'Invalid owned process identity')
    _require(type(value['clock_domain']) is str and _ID.fullmatch(value['clock_domain']),
             'Invalid trusted clock domain')
    for name in ('initial_capture_sha256','initial_native_sha256'):
        _require(type(value[name]) is str and _HEX.fullmatch(value[name]), 'Invalid initial evidence digest')
    triangle = value['reference_triangle_index']
    _require(type(triangle) is int and 0 <= triangle < 1_000_000, 'Explicit original triangle required')
    _require(spec.reference_triangle_index in (None, triangle), 'Original triangle conflicts with proposal')
    identity = value['host_identity']
    _require(type(identity) is dict and set(identity) == {'schema_version','document_epoch','object_instances','capture_scope'}
             and identity['schema_version'] == '1.0' and identity['capture_scope'] == 'complete_scene_meshes',
             'Complete original host identity required')
    _require(type(identity['document_epoch']) is str and _HEX.fullmatch(identity['document_epoch']),
             'Invalid document epoch')
    instances = identity['object_instances']
    _require(type(instances) is dict and 2 <= len(instances) <= 256, 'Complete bounded object instances required')
    for key, instance in instances.items():_text(key, 'object identity');_text(instance, 'object incarnation')
    _require(len(set(instances.values())) == len(instances)
             and spec.focal_id in instances and spec.reference_id in instances, 'Task object instances disagree')
    _json(value)
    return copy.deepcopy(value)


def _key(issuer, event):
    return _digest([issuer, event])


def _validate_payload(value):
    _require(type(value) is dict and set(value) == _PAYLOAD_FIELDS
             and value['schema_version'] == 'trusted-clearance-grant-v1', 'Invalid task grant payload')
    for name in ('issuer_id','event_id','authorization_id'):_text(value[name], name)
    key = _key(value['issuer_id'], value['event_id'])
    _require(value['key'] == key and value['goal_id'] == 'auth-goal:' + key
             and value['session_id'] == 'auth-session:' + key, 'Authorization event mapping changed')
    spec = _spec_from_dict(value['spec'])
    _require(value['spec_hash'] == _digest(value['spec']), 'Task spec digest mismatch')
    scope = _scope(value['scope'], spec)
    _require(scope['reference_triangle_index'] == spec.reference_triangle_index, 'Resolved triangle differs')
    issued = _number(value['issued_monotonic'], 'issued QPC time')
    deadline = _number(value['deadline_monotonic'], 'fixed grant deadline', positive=True)
    _require(deadline == issued + spec.limits.max_duration_s and deadline > issued, 'Grant deadline was renewed')
    _json(value)
    return value


class TaskGrant:
    __slots__ = ('_issuer', '_raw', '_seal')
    def __init__(self, *args, **kwargs):
        raise TaskAuthorityError('Task grants are issued only by a trusted authority')
    def __setattr__(self, name, value):
        raise AttributeError('TaskGrant is immutable')
    def payload(self):return self._issuer.verify(self)
    @property
    def key(self):return self.payload()['key']
    @property
    def goal_id(self):return self.payload()['goal_id']
    @property
    def session_id(self):return self.payload()['session_id']
    @property
    def spec_hash(self):return self.payload()['spec_hash']
    @property
    def issued_monotonic(self):return self.payload()['issued_monotonic']
    @property
    def deadline_monotonic(self):return self.payload()['deadline_monotonic']
    @property
    def spec_resolved(self):return _spec_from_dict(self.payload()['spec'])


class TrustedTaskAuthority:
    def __init__(self, issuer_id, approve_callback):
        self.issuer_id = _text(issuer_id, 'trusted issuer')
        _require(callable(approve_callback), 'Trusted embedding approval callback required')
        self._approve = approve_callback
        self._secret = secrets.token_bytes(32)

    def issue(self, spec, resolved_scope):
        _require(type(spec) is ClearanceTaskSpec, 'Typed frozen task proposal required')
        scope = _scope(resolved_scope, spec)
        resolved = ClearanceTaskSpec(spec.focal_id, spec.reference_id, spec.target_clearance_m,
            spec.clearance_tolerance_m, spec.direction_world, scope['reference_triangle_index'], spec.limits)
        approval = self._approve(resolved, copy.deepcopy(scope))
        if approval is None or approval is False:
            raise TaskAuthorizationDenied('Trusted task authorization denied')
        _require(type(approval) is TaskApproval, 'Approval must be a trusted typed TaskApproval, not JSON')
        key = _key(self.issuer_id, approval.event_id)
        issued = _number(time.perf_counter(), 'issued QPC time')
        payload = {'schema_version':'trusted-clearance-grant-v1','issuer_id':self.issuer_id,
            'event_id':approval.event_id,'authorization_id':approval.authorization_id,
            'key':key,'goal_id':'auth-goal:' + key,'session_id':'auth-session:' + key,
            'spec':resolved.to_dict(),'spec_hash':_digest(resolved.to_dict()),'scope':scope,
            'issued_monotonic':issued,'deadline_monotonic':issued + resolved.limits.max_duration_s}
        _validate_payload(payload)
        raw = _json(payload)
        grant = object.__new__(TaskGrant)
        object.__setattr__(grant, '_issuer', self);object.__setattr__(grant, '_raw', raw)
        object.__setattr__(grant, '_seal', hmac.new(self._secret, raw, hashlib.sha256).digest())
        return grant

    def verify(self, grant):
        _require(type(grant) is TaskGrant and getattr(grant, '_issuer', None) is self,
                 'Grant does not belong to this trusted issuer instance')
        _require(type(grant._raw) is bytes and type(grant._seal) is bytes
                 and hmac.compare_digest(grant._seal, hmac.new(self._secret, grant._raw, hashlib.sha256).digest()),
                 'Task grant issuer seal mismatch')
        payload = json.loads(grant._raw.decode('utf-8'))
        _validate_payload(payload)
        _require(payload['issuer_id'] == self.issuer_id, 'Issuer identity changed after grant issue')
        return payload


def _stable(payload):
    scope = {key:value for key,value in payload['scope'].items()
             if key not in ('initial_capture_sha256','initial_native_sha256')}
    return {key:payload[key] for key in ('issuer_id','event_id','authorization_id','key','goal_id',
                                        'session_id','spec','spec_hash')} | {'scope':scope}


def _parent(value, payload):
    parent = value.get('goal_supervision', {}).get('records', {}).get(payload['goal_id'])
    if parent is None:return None
    _require(type(parent) is dict, 'Invalid authorization parent')
    _require(parent.get('session_id') == payload['session_id']
             and parent.get('clock_domain') == payload['scope']['clock_domain']
             and parent.get('started_monotonic') == payload['issued_monotonic']
             and parent.get('deadline_monotonic') == payload['deadline_monotonic'],
             'Authorization parent identity, clock or fixed deadline changed')
    try:limits = _limits(GoalBudgetLimits(**parent['limits']))
    except (KeyError, ValueError, TypeError, OverflowError) as exc:
        raise TaskAuthorityError('Invalid authorization parent limits') from exc
    _require(_json(limits) == _json(payload['spec']['limits']), 'Authorization parent budget changed')
    for child in parent.get('children', []):
        request = child.get('request', {})
        for name in ('solver','focal_id','reference_id','target_clearance_m','clearance_tolerance_m',
                     'direction_world','reference_triangle_index'):
            _require(request.get(name) == payload['spec'][name], 'Authorized task constraints changed')
        entry = value.get('goal_segments', {}).get('records', {}).get(child['request_id'])
        if entry is not None:
            _require(entry.get('host_binding') == payload['scope']['host_identity'],
                     'Authorized child original host binding changed')
            result = entry.get('result')
            if result is not None:
                identity = result.get('runtime_identity')
                _require(type(identity) is dict and identity.get('mode') == 'live'
                         and identity.get('build_id') == payload['scope']['engine_build_id'],
                         'Authorized child engine build changed')
    return parent


def _own_unfinished(value, payload, parent):
    child_ids = {child['request_id'] for child in (parent or {}).get('children', [])}
    entries = value.get('goal_segments', {}).get('records', {})
    for identity in child_ids:
        entry = entries.get(identity)
        if type(entry) is not dict or entry.get('status') in {'running','execution_uncertain','segment_interrupted'}:
            return True
    pending = value.get('inflight')
    return type(pending) is dict and pending.get('session_id') == payload['session_id']


def validate_authorizations(value):
    """Validate a persisted index, never turn that JSON into a capability."""
    try:
        _require(type(value) is dict, 'Connector state must be an object')
        from .goal_journal import validate_goal_journal
        from .goal_execution import validate_segment_ledger
        validate_segment_ledger(value)
        validate_goal_journal(value)
        parents = value.get('goal_supervision', {}).get('records', {})
        if 'goal_authorizations' not in value:
            _require(not any(key.startswith('auth-goal:') for key in parents), 'Authorized parent has lost its issuer index')
            return
        index = value['goal_authorizations'];_json(index)
        _require(type(index) is dict and set(index) == {'schema_version','records'}
                 and index['schema_version'] == 'goal-authorizations-v1'
                 and type(index['records']) is dict and len(index['records']) <= MAX_AUTHORIZATIONS,
                 'Invalid bounded authorization index')
        blockers = [];owned_goals = set()
        for key, record in index['records'].items():
            _require(type(key) is str and _HEX.fullmatch(key) and type(record) is dict
                     and set(record) == _RECORD_FIELDS, 'Invalid authorization record')
            payload = _validate_payload(record['grant'])
            _require(key == payload['key'] and record['grant_sha256'] == _digest(payload), 'Persisted grant mapping or digest changed')
            _require(payload['goal_id'] not in owned_goals, 'Goal belongs to multiple authorizations')
            owned_goals.add(payload['goal_id'])
            status = record['status'];_require(status in _STATUSES, 'Invalid authorization status')
            reason = record['reason'];result = record['result']
            if reason is not None:_text(reason, 'authorization stop reason')
            if result is not None:
                _require(type(result) is dict, 'Bounded result summary must be an object')
                _json(result, MAX_RESULT_BYTES)
                for name in ('execution_authority','retry_authorized'):
                    _require(name not in result or result[name] is False, 'Persisted result cannot grant authority')
                for name in ('task_succeeded','host_closed'):
                    _require(name not in result or result[name] is None or type(result[name]) is bool,
                             'Result success and closure require exact booleans')
            parent = _parent(value, payload)
            if result is not None and result.get('task_succeeded') is True:
                _require(parent is not None and parent.get('status') == 'completed', 'Result success lacks a completed parent')
            if status == 'completed':
                _require(parent is not None and parent.get('status') == 'completed'
                         and not _own_unfinished(value,payload,parent)
                         and type(result) is dict and result.get('task_succeeded') is True
                         and result.get('host_closed') is True and reason == 'goal_satisfied',
                         'Completed authorization lacks verified parent and host closure')
            else:
                blockers.append(key)
                if status in {'reserved','active'}:
                    _require(reason is None and result is None, 'Live authorization has terminal result data')
                else:_require(reason is not None, 'Stopped authorization needs a reason')
        _require(len(blockers) <= 1, 'Multiple unresolved task authorizations')
        _require(all(not key.startswith('auth-goal:') or key in owned_goals for key in parents),
                 'Authorized parent has no issuer index record')
    except TaskAuthorityError:
        raise
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, OverflowError, RecursionError) as exc:
        raise TaskAuthorityError('Invalid persisted authorization state') from exc


def blocking_authorization(value):
    validate_authorizations(value)
    return next((key for key,record in value.get('goal_authorizations', {}).get('records', {}).items()
                 if record['status'] != 'completed'), None)


def claim_grant(value, grant):
    _require(type(grant) is TaskGrant, 'Only a live typed task capability can be claimed')
    payload = grant.payload()
    validate_authorizations(value)
    key = payload['key'];blocking = blocking_authorization(value)
    _require(blocking is None or blocking == key, 'Another task authorization requires review')
    records = value.get('goal_authorizations', {}).get('records', {})
    existing = records.get(key)
    if existing is not None:
        _require(_json(_stable(existing['grant'])) == _json(_stable(payload)),
                 'Authenticated task event conflicts with its original authorization')
        return {'fresh_claim':False,'key':key,'goal_id':existing['grant']['goal_id'],
            'session_id':existing['grant']['session_id'],'record':copy.deepcopy(existing),
            'mode':'historical' if existing['status'] == 'completed' else 'needs_review',
            'execution_authority':False}
    from .goal_journal import blocking_goal
    _require(blocking_goal(value) is None and value.get('inflight') is None,
             'Existing parent or host operation requires review')
    _require(payload['goal_id'] not in value.get('goal_supervision', {}).get('records', {}),
             'A parent cannot precede its task authorization claim')
    _require(len(records) < MAX_AUTHORIZATIONS, 'Authorization capacity exhausted; identities are never evicted')
    candidate = dict(value)
    index = copy.deepcopy(value.get('goal_authorizations', {'schema_version':'goal-authorizations-v1','records':{}}))
    candidate['goal_authorizations'] = index
    record = {'grant':payload,'grant_sha256':_digest(payload),'status':'reserved','reason':None,'result':None}
    index['records'][key] = record
    validate_authorizations(candidate)
    value['goal_authorizations'] = index
    return {'fresh_claim':True,'key':key,'goal_id':payload['goal_id'],'session_id':payload['session_id'],
            'record':copy.deepcopy(record),'mode':'fresh','execution_authority':False}


def set_authorization_state(value, key, status, *, result=None, reason=None):
    validate_authorizations(value)
    record = value.get('goal_authorizations', {}).get('records', {}).get(key)
    _require(type(record) is dict and status in _STATUSES, 'Unknown authorization or state')
    old = record['status']
    if status == 'completed' and reason is None:reason = 'goal_satisfied'
    if old in {'completed','stopped','frozen'}:
        _require(status == old and _json(result) == _json(record['result']) and reason == record['reason'],
                 'Terminal authorization cannot be reopened or renewed')
        return copy.deepcopy(record)
    _require(status in ({'active','stopped','frozen'} if old == 'reserved' else {'completed','stopped','frozen'}),
             'Invalid task authorization transition')
    if status == 'completed':
        from .goal_execution import unfinished_segment
        _require(value.get('inflight') is None and not unfinished_segment(value),
                 'Unfinished host execution blocks authorization completion')
    candidate = dict(value);index = copy.deepcopy(value['goal_authorizations'])
    candidate['goal_authorizations'] = index
    index['records'][key].update(status=status,reason=reason,result=copy.deepcopy(result))
    validate_authorizations(candidate)
    value['goal_authorizations'] = index
    return copy.deepcopy(index['records'][key])


__all__ = ['ClearanceTaskSpec','TaskApproval','TaskGrant','TrustedTaskAuthority',
    'TaskAuthorityError','TaskAuthorizationDenied','claim_grant','set_authorization_state',
    'validate_authorizations','blocking_authorization']
