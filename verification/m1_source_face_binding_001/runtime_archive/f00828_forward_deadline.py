"""Bound a forward request to one same-machine Windows QPC deadline.

This stdlib-only contract is usable through direct file import in Blender.
It validates trusted local worker evidence, not signatures or task authority.
The final comparison is cooperative admission, not an atomic OS/setter action.
Legacy monotonic-clock deadlines must never be relabelled as QPC values.
"""
from __future__ import annotations

import copy
from fractions import Fraction
import hashlib
import json
import math
import re
import sys
import time

PROTOCOL = 'owned-qpc-forward-deadline-v1-20261030'
BASE_FIELDS = frozenset({'protocol', 'clock', 'goal_id', 'binding', 'process_id',
                         'parent_deadline_ns', 'forward_deadline_ns'})
WIRE_FIELDS = BASE_FIELDS | {'action_sha256', 'expected_revision', 'expected_fingerprint', 'request_nonce'}
_FULL_BINDING = {'host_epoch', 'document_epoch', 'focal_id', 'reference_id', 'object_instances'}
_COMPACT_BINDING = {'host_epoch', 'document_epoch', 'focal_id', 'reference_id', 'object_instances_sha256'}
_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$')
_MAX_NS = (1 << 63) - 1
_REFUSAL_FIELDS = {'protocol', 'source', 'code', 'forward_deadline', 'checked_ns',
    'mutation_started', 'forward_setter_entered', 'cancelled_event_id', 'retry_authorized', 'scope'}


class ForwardDeadlineError(ValueError):
    pass


DeadlineError = ForwardDeadlineError


def _require(condition, message):
    if not condition:
        raise ForwardDeadlineError(message)


def _integer(value, low=0, high=_MAX_NS):
    _require(type(value) is int and low <= value <= high, 'Invalid bounded deadline integer')
    return value


def _hex(value, length):
    return type(value) is str and len(value) == length and all(c in '0123456789abcdef' for c in value)


def _identifier(value):
    _require(type(value) is str and _ID.fullmatch(value) is not None, 'Invalid bounded goal identity')
    return value


def _text(value, limit=256):
    _require(type(value) is str and bool(value) and len(value) <= limit, 'Invalid bounded deadline text')
    return value


def _json(value):
    def plain(item, depth=0):
        _require(depth <= 24, 'Deadline JSON depth exceeded')
        if type(item) is dict:
            _require(all(type(k) is str for k in item), 'Deadline JSON keys must be strings')
            for child in item.values():plain(child, depth+1)
        elif type(item) in (list, tuple):
            _require(len(item) <= 1024, 'Deadline JSON array exceeded')
            for child in item:plain(child, depth+1)
        elif type(item) in (int, float):
            try:valid=math.isfinite(item)
            except OverflowError:valid=False
            _require(valid, 'Nonfinite deadline JSON')
        else:
            _require(item is None or type(item) in (str, bool), 'Plain deadline JSON required')
    try:
        plain(value)
        data=json.dumps(value,sort_keys=True,separators=(',', ':'),ensure_ascii=True,allow_nan=False).encode('utf-8')
        _require(len(data) <= 256*1024, 'Deadline JSON byte bound exceeded')
        return data
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        if isinstance(exc, ForwardDeadlineError):raise
        raise ForwardDeadlineError('Invalid deadline JSON') from exc


def _digest(value):
    return hashlib.sha256(_json(value)).hexdigest()


def counter_descriptor():
    """Refuse unsupported runtimes; equal function names do not prove clocks."""
    _require(sys.platform == 'win32' and sys.implementation.name == 'cpython'
             and tuple(sys.version_info[:2]) >= (3,10), 'System-wide Windows CPython QPC is required')
    info=time.get_clock_info('perf_counter')
    _require(info.implementation == 'QueryPerformanceCounter()' and info.monotonic is True
             and info.adjustable is False, 'Required Windows QPC clock is unavailable')
    resolution=info.resolution
    _require(type(resolution) in (int,float) and not isinstance(resolution,bool)
             and math.isfinite(resolution) and 0 < resolution <= 1., 'Invalid QPC resolution')
    scaled=Fraction(resolution)*1_000_000_000
    tick_ns=max(1, -(-scaled.numerator//scaled.denominator))
    return {'source':'windows_systemwide_qpc', 'unit':'ns',
            'implementation':'QueryPerformanceCounter()', 'resolution_ns':tick_ns,
            # Microsoft documents ambiguous cross-thread ordering within one
            # QPC tick. Add one integer-nanosecond conversion margin as well.
            'guard_ns':tick_ns+1}


def _binding(value):
    _require(type(value) is dict and set(value) in (_FULL_BINDING, _COMPACT_BINDING),
             'Complete deadline host binding required')
    _require(_hex(value['host_epoch'],32) and _hex(value['document_epoch'],64), 'Invalid host/document epoch')
    focal,reference=_text(value['focal_id']),_text(value['reference_id'])
    _require(focal != reference, 'Distinct deadline objects required')
    if 'object_instances' in value:
        instances=value['object_instances']
        _require(type(instances) is dict and 2 <= len(instances) <= 256,
                 'Complete bounded object incarnation map required')
        for identity,instance in instances.items():_text(identity);_text(instance)
        _require(focal in instances and reference in instances and len(set(instances.values())) == len(instances),
                 'Deadline object incarnations disagree')
        digest=_digest(instances)
    else:
        digest=value['object_instances_sha256']
        _require(_hex(digest,64), 'Invalid complete incarnation digest')
    return {'host_epoch':value['host_epoch'], 'document_epoch':value['document_epoch'],
            'focal_id':focal, 'reference_id':reference, 'object_instances_sha256':digest}


def _base(value):
    _require(type(value) is dict and set(value) in (BASE_FIELDS, WIRE_FIELDS), 'Invalid deadline envelope fields')
    _json(value)
    _require(value['protocol'] == PROTOCOL, 'Unsupported forward deadline protocol')
    _require(_json(value['clock']) == _json(counter_descriptor()), 'QPC clock descriptor mismatch')
    _identifier(value['goal_id']);_integer(value['process_id'],1,(1<<32)-1)
    parent=_integer(value['parent_deadline_ns']);forward=_integer(value['forward_deadline_ns'])
    _require(forward <= parent, 'Forward deadline expands its parent deadline')
    compact=_binding(value['binding'])
    _require(set(value['binding']) == _COMPACT_BINDING and _json(compact)==_json(value['binding']),
             'Wire binding must use the canonical compact incarnation digest')
    if set(value) == WIRE_FIELDS:
        _require(_hex(value['action_sha256'],64) and _hex(value['expected_fingerprint'],64)
                 and _hex(value['request_nonce'],32), 'Invalid current request deadline binding')
        _text(value['expected_revision'])
    return copy.deepcopy({key:value[key] for key in BASE_FIELDS})


def validate_base(base, *, binding=None, process_id=None, goal_id=None):
    """Shape-only without expected facts; no execution permission is returned."""
    _require(type(base) is dict and set(base) == BASE_FIELDS, 'A base deadline lease is required')
    result=_base(base)
    if binding is not None:
        _require(_json(result['binding'])==_json(_binding(binding)), 'Host identity differs from deadline lease')
    if process_id is not None:
        _require(result['process_id']==_integer(process_id,1,(1<<32)-1), 'Host process differs from deadline lease')
    if goal_id is not None:
        _require(result['goal_id']==_identifier(goal_id), 'Goal differs from deadline lease')
    return result


def _floor_ns(seconds):
    try:valid=type(seconds) in (int,float) and math.isfinite(seconds) and seconds >= 0
    except OverflowError:valid=False
    _require(valid, 'Finite nonnegative QPC deadline seconds required')
    value=Fraction(seconds)*1_000_000_000
    return _integer(value.numerator//value.denominator)


def make_deadline(parent_deadline_s, forward_deadline_s, *, goal_id, binding, process_id):
    parent_ns=_floor_ns(parent_deadline_s);forward_ns=_floor_ns(forward_deadline_s)
    _require(Fraction(forward_deadline_s) <= Fraction(parent_deadline_s), 'Forward deadline expands parent')
    result={'protocol':PROTOCOL, 'clock':counter_descriptor(), 'goal_id':_identifier(goal_id),
        'binding':_binding(binding), 'process_id':_integer(process_id,1,(1<<32)-1),
        'parent_deadline_ns':parent_ns, 'forward_deadline_ns':forward_ns}
    return validate_base(result)


def _action_digest(action, binding):
    _require(type(action) is dict and set(action) <= {'focal_id','reference_id','translation','rotation_euler_deg'}
             and {'translation','rotation_euler_deg'} & set(action), 'Invalid bound forward action')
    _require(action.get('focal_id')==binding['focal_id'] and action.get('reference_id')==binding['reference_id'],
             'Forward action roles differ from deadline binding')
    for name in ('translation','rotation_euler_deg'):
        if name in action:
            vector=action[name]
            _require(type(vector) in (list,tuple) and len(vector)==3, 'Invalid forward action vector')
            try:valid=all(type(v) in (int,float) and math.isfinite(v) for v in vector)
            except OverflowError:valid=False
            _require(valid, 'Invalid forward action numbers')
    return _digest(action)


def bind_deadline(base, *, action, expected_revision, expected_fingerprint, request_nonce):
    result=_base(base)
    _require(_hex(expected_fingerprint,64) and _hex(request_nonce,32), 'Fresh scene fingerprint and nonce required')
    result.update(action_sha256=_action_digest(action,result['binding']),
        expected_revision=_text(expected_revision),expected_fingerprint=expected_fingerprint,request_nonce=request_nonce)
    if set(base) == WIRE_FIELDS:
        _require(_json(base)==_json(result), 'A bound deadline cannot be rebound to another request')
    _json(result)
    return result


def validate_deadline(wire, *, action, expected_revision, expected_fingerprint, request_nonce,
                      binding, process_id, goal_id=None):
    _require(type(wire) is dict and set(wire)==WIRE_FIELDS, 'Complete forward deadline wire required')
    expected=bind_deadline(wire,action=action,expected_revision=expected_revision,
        expected_fingerprint=expected_fingerprint,request_nonce=request_nonce)
    validate_base(_base(expected),binding=binding,process_id=process_id,goal_id=goal_id)
    return expected


def expired(wire, *, now_ns=None):
    base=_base(wire)
    instant=time.perf_counter_ns() if now_ns is None else now_ns
    return _integer(instant)+base['clock']['guard_ns'] >= base['forward_deadline_ns']


def build_refusal(wire, *, checked_ns, cancelled_event_id=None):
    _require(type(wire) is dict and set(wire)==WIRE_FIELDS, 'Bound request required for deadline refusal')
    _base(wire);_integer(checked_ns)
    _require(expired(wire,now_ns=checked_ns), 'Cannot certify an unexpired deadline refusal')
    if cancelled_event_id is not None:
        _require(cancelled_event_id==wire['request_nonce']+':forward', 'Cancellation identity differs from current request')
    return {'status':'rejected_before_mutation','rejection':{
        'protocol':PROTOCOL,'source':'blender_scene_host','code':'host_forward_deadline_expired',
        'forward_deadline':copy.deepcopy(wire),'checked_ns':checked_ns,
        'mutation_started':False,'forward_setter_entered':False,
        'cancelled_event_id':cancelled_event_id,'retry_authorized':False,
        'scope':'bound_forward_request_only'}}


def validate_refusal(value, *, forward_deadline, action, expected_revision, expected_fingerprint, request_nonce):
    wire=bind_deadline(forward_deadline,action=action,expected_revision=expected_revision,
        expected_fingerprint=expected_fingerprint,request_nonce=request_nonce)
    _require(type(value) is dict and set(value)=={'status','rejection'}
             and value['status']=='rejected_before_mutation','Invalid deadline refusal envelope')
    proof=value['rejection']
    _require(type(proof) is dict and set(proof)==_REFUSAL_FIELDS, 'Invalid deadline refusal fields')
    expected=build_refusal(wire,checked_ns=proof['checked_ns'],cancelled_event_id=proof['cancelled_event_id'])['rejection']
    _require(_json(proof)==_json(expected), 'Deadline refusal is not bound to this forward request')
    return copy.deepcopy(proof)


__all__=['PROTOCOL','BASE_FIELDS','WIRE_FIELDS','ForwardDeadlineError','DeadlineError',
 'counter_descriptor','make_deadline','validate_base','bind_deadline','validate_deadline',
 'expired','build_refusal','validate_refusal']
