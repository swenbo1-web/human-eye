"""Bounded, in-memory accounting for one explicitly granted clearance goal.

This module neither grants execution rights nor verifies the authenticity of a
host meter.  A trusted caller must bind the meter to fresh native evidence.
There is no cross-process ledger, crash recovery, or permission to reconstruct
this object after an unknown outcome.  No tools or host code are called here.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import math
import threading
import time


class GoalBudgetError(ValueError):
    pass


class GoalBudgetStopped(GoalBudgetError):
    pass


def _number(value, name, *, positive=False):
    try:
        valid=type(value) in (int,float) and math.isfinite(value)
    except OverflowError:
        valid=False
    if not valid or value < 0 or positive and value == 0:
        raise GoalBudgetError(name + ' must be finite and nonnegative' + (' and positive' if positive else ''))
    return float(value)


def _integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise GoalBudgetError(name + ' is outside its integer range')
    return value


def _identifier(value, name):
    if type(value) is not str or not value.strip() or len(value) > 256:
        raise GoalBudgetError(name + ' must be a nonempty bounded identifier')
    return value


def _digest(value, limit):
    # Numeric JSON normalization permits the engine's int->float normalization
    # while preserving booleans as booleans; counters are validated separately.
    def normalized(item):
        if type(item) in (int, float):
            if not math.isfinite(item):
                raise GoalBudgetError('nonfinite JSON number')
            return float(item)
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise GoalBudgetError('JSON keys must be strings')
            return {key: normalized(v) for key, v in item.items()}
        if type(item) in (list, tuple):
            return [normalized(v) for v in item]
        if item is None or type(item) in (str, bool):
            return item
        raise GoalBudgetError('only plain JSON data is accepted')
    try:
        encoded = json.dumps(normalized(value), sort_keys=True, separators=(',', ':'),
                             ensure_ascii=True, allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, RecursionError, OverflowError) as exc:
        raise GoalBudgetError('invalid or excessively deep JSON data') from exc
    if len(encoded) > limit:
        raise GoalBudgetError('serialized accounting input exceeds its bound')
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class GoalBudgetLimits:
    max_steps: int = 8
    max_step_translation_m: float = .001
    max_total_translation_m: float = .008
    max_duration_s: float = 30.
    max_recoveries: int = 1
    max_segments: int = 3

    def __post_init__(self):
        _integer(self.max_steps, 'max_steps', 1, 8)
        _integer(self.max_recoveries, 'max_recoveries', 0, 2)
        _integer(self.max_segments, 'max_segments', 1, 3)
        for name, maximum in (('max_step_translation_m', .001),
                              ('max_total_translation_m', .008), ('max_duration_s', 180.)):
            if _number(getattr(self, name), name, positive=True) > maximum:
                raise GoalBudgetError(name + ' exceeds the frozen maximum')


_CAPS = ('max_steps', 'max_step_translation_m', 'max_total_translation_m', 'max_duration_s')
_SELECTORS = {'reference_triangle_index', 'selection_binding'}


def _goal(request):
    return {key: value for key, value in request.items() if key not in _CAPS and key not in _SELECTORS}


def _has_rollback(value):
    if type(value) is dict:
        for key, item in value.items():
            if 'rollback' in key.lower() or key.lower() == 'rolled_back':
                if item not in (False, None, 0, '', []):
                    return True
            if key == 'status' and type(item) is str and ('rollback' in item.lower() or item == 'rolled_back'):
                return True
            if _has_rollback(item):
                return True
    elif type(value) in (list, tuple):
        return any(_has_rollback(item) for item in value)
    return False


def _floor_float(value):
    result = float(value)
    if Fraction(result) > value:
        result = math.nextafter(result, 0.)
    return max(0., result)


def _sum_matches(reported, exact):
    # Only consistency of a float summary, never a relaxed motion cap. The
    # exact sum and the host's reported total are each checked against the cap.
    return abs(Fraction(reported)-exact) <= Fraction(math.ulp(reported))


class GoalBudget:
    """One caller-owned coordination session; never an authorization object."""
    def __init__(self, limits=None, *, clock=time.monotonic, started=None):
        self.limits = limits or GoalBudgetLimits()
        if type(self.limits) is not GoalBudgetLimits or not callable(clock):
            raise GoalBudgetError('frozen limits and a trusted clock are required')
        beginning = clock() if started is None else started
        if type(beginning) not in (int, float) or not math.isfinite(beginning):
            raise GoalBudgetError('started must be a finite monotonic timestamp')
        self._started = float(beginning)
        self._deadline = self._started + self.limits.max_duration_s
        if not math.isfinite(self._deadline) or self._deadline <= self._started:
            raise GoalBudgetError('deadline is not representable')
        self._clock = clock
        self._lock = threading.RLock()
        self._requests = {}
        self._segments = {}
        self._steps = set()
        self._operations = set()
        self._goal_digest = None
        self._pending = None
        self._motion = Fraction(0)
        self._recoveries = 0
        self._poisoned = False
        self._stopped = None
        self._last_end_revision = None
        self._late_accounted = False

    @property
    def started(self): return self._started

    @property
    def deadline(self): return self._deadline

    @property
    def poisoned(self): return self._poisoned

    def _remaining_time(self):
        now = self._clock()
        if type(now) not in (int, float) or not math.isfinite(now) or now < self._started:
            self._poison('untrustworthy_monotonic_clock')
        return max(0., self._deadline - now)

    def _poison(self, reason):
        self._poisoned = True
        self._stopped = reason
        raise GoalBudgetStopped(reason)

    def poison(self, reason='unknown_segment_outcome'):
        with self._lock:
            self._poison(_identifier(reason, 'reason'))

    def _admit(self):
        if self._poisoned or self._stopped is not None:
            raise GoalBudgetStopped(self._stopped or 'poisoned_goal_budget')
        if self._remaining_time() <= 0:
            self._stopped = 'goal_time_budget_exhausted'
            raise GoalBudgetStopped(self._stopped)

    def _caps(self):
        steps = self.limits.max_steps - len(self._steps)
        motion = Fraction(self.limits.max_total_translation_m) - self._motion
        left = self._remaining_time()
        if steps <= 0 or motion <= 0 or left <= 0:
            raise GoalBudgetStopped('goal_motion_step_or_time_budget_exhausted')
        remaining_motion = _floor_float(motion)
        return {'max_steps': steps,
                'max_step_translation_m': min(self.limits.max_step_translation_m, remaining_motion),
                'max_total_translation_m': remaining_motion,
                'max_duration_s': min(30., left)}

    def next_request_caps(self):
        with self._lock:
            self._admit()
            if self._pending is not None:
                raise GoalBudgetStopped('a_segment_outcome_is_still_pending')
            if len(self._requests) >= self.limits.max_segments:
                raise GoalBudgetStopped('goal_segment_budget_exhausted')
            if self._requests and self._recoveries >= self.limits.max_recoveries:
                raise GoalBudgetStopped('goal_recovery_budget_exhausted')
            return self._caps()

    def _validate_request(self, request):
        if type(request) is not dict:
            raise GoalBudgetError('request must be a JSON object')
        for name in ('focal_id', 'reference_id'):
            _identifier(request.get(name), name)
        if request['focal_id'] == request['reference_id']:
            raise GoalBudgetError('goal pair must contain distinct objects')
        _number(request.get('target_clearance_m'), 'target_clearance_m', positive=True)
        _number(request.get('clearance_tolerance_m'), 'clearance_tolerance_m')
        if request.get('solver') == 'support_plane':
            direction = request.get('direction_world')
            if type(direction) not in (list, tuple) or len(direction) != 3:
                raise GoalBudgetError('world Z direction is required')
            for value in direction:
                try:valid=type(value) in (int,float) and math.isfinite(value)
                except OverflowError:valid=False
                if not valid:raise GoalBudgetError('direction must contain finite numbers')
            if direction[0] != 0 or direction[1] != 0 or abs(direction[2]) != 1:
                raise GoalBudgetError('only normalized world Z goals are supported')
        elif request.get('solver') is not None or request.get('axis') not in ('+z', '-z'):
            raise GoalBudgetError('only explicit world Z box/support-plane goals are supported')
        _integer(request.get('max_steps'), 'max_steps', 1, 8)
        for field in _CAPS[1:]: _number(request.get(field), field, positive=True)
        _digest(request, 65536)

    def reserve_segment(self, request_id, request):
        with self._lock:
            self._admit()
            _identifier(request_id, 'request_id')
            self._validate_request(request)
            request_digest = _digest(request, 65536)
            previous = self._requests.get(request_id)
            if previous is not None:
                if request_digest not in (previous['request_digest'],previous['effective_request_digest']):
                    self._poison('request_id_payload_conflict')
                return {'request_id':request_id,'fresh_reservation':False,
                        'state':previous['state'],'execution_authority':False,
                        'request':copy.deepcopy(previous['request'])}
            caps = self.next_request_caps()
            for field in _CAPS[:-1]:
                if request[field] > caps[field]:
                    raise GoalBudgetError('segment exceeds remaining goal cap: ' + field)
            if request['max_duration_s'] > min(30.,self.limits.max_duration_s):
                raise GoalBudgetError('segment exceeds the fixed duration cap')
            effective_request=copy.deepcopy(request)
            # A caps snapshot can age while a fresh selector is prepared. Do
            # not reject the clock merely for advancing, or grant a new window.
            effective_request['max_duration_s']=min(request['max_duration_s'],caps['max_duration_s'])
            goal_digest = _digest(_goal(request), 65536)
            if self._goal_digest is not None and self._goal_digest != goal_digest:
                raise GoalBudgetError('goal_identity_or_constraints_changed')
            binding=request.get('selection_binding')
            if (self._last_end_revision is not None and type(binding) is dict
                    and binding.get('scene_revision')!=self._last_end_revision):
                raise GoalBudgetError('selection_revision_does_not_follow_confirmed_segment')
            self._goal_digest = goal_digest
            if self._requests:
                self._recoveries += 1
            self._requests[request_id] = {'state':'pending','request_digest':request_digest,
                'effective_request_digest':_digest(effective_request,65536),
                'request':effective_request,'receipt_digest':None}
            self._pending = request_id
            return {'request_id':request_id,'fresh_reservation':True,'state':'pending',
                    'execution_authority':False,'request':copy.deepcopy(effective_request)}

    def _physical(self, meter, motions, *, duplicate=False):
        if type(meter) is not dict or meter.get('complete') is not True:
            self._poison('physical_accounting_incomplete')
        if _integer(meter.get('rollback_count'), 'rollback_count', 0, 8) != 0:
            self._poison('rollback_requires_external_review')
        count = _integer(meter.get('actual_setter_count'), 'actual_setter_count', 0, 8)
        total = _number(meter.get('actual_cumulative_translation_m'), 'actual_cumulative_translation_m')
        expected_count = len(self._steps) + (0 if duplicate else len(motions))
        expected_motion = self._motion + (Fraction(0) if duplicate else sum((Fraction(v) for v in motions), Fraction(0)))
        if count != expected_count or not _sum_matches(total,expected_motion):
            self._poison('physical_meter_does_not_match_confirmed_steps')
        if (count > self.limits.max_steps or expected_motion > Fraction(self.limits.max_total_translation_m)
                or total > self.limits.max_total_translation_m):
            self._poison('actual_goal_motion_or_step_cap_exceeded')
        if duplicate:
            return
        per_step = meter.get('step_motions_m')
        if type(per_step) is not list or len(per_step) != len(motions):
            self._poison('physical_step_accounting_incomplete')
        for measured, reported in zip(per_step, motions):
            if _number(measured,'physical_step_motion',positive=True) != reported:
                self._poison('physical_step_motion_disagrees_with_receipt')

    def confirm_segment(self, receipt, *, physical_meter):
        """Account only a known result plus an independently collected meter.

        The caller authenticates/binds physical_meter. Its cumulative count and
        path include all channels and rollback; this module checks consistency
        and rejects unaccounted setters rather than inferring them from net pose.
        """
        with self._lock:
            try:
                if self._poisoned:
                    raise GoalBudgetStopped(self._stopped)
                if type(receipt) is not dict:
                    self._poison('segment_receipt_is_not_a_JSON_object')
                request_id = _identifier(receipt.get('request_id'),'request_id')
                record = self._requests.get(request_id)
                if record is None:
                    self._poison('unreserved_segment_receipt')
                semantic = {k:v for k,v in receipt.items() if k not in ('replayed','historical_receipt')}
                receipt_digest = _digest(semantic, 8*1024*1024)
                if record['receipt_digest'] is not None:
                    if receipt_digest != record['receipt_digest']:
                        self._poison('request_id_receipt_conflict')
                    self._physical(physical_meter, [], duplicate=True)
                    return self._snapshot(deduplicated=True)
                if self._pending != request_id:
                    self._poison('segment_does_not_match_pending_reservation')
                if (receipt.get('replayed',False) is not False
                        or receipt.get('historical_receipt',False) is not False):
                    self._poison('historical_receipt_cannot_confirm_a_new_reservation')
                status = receipt.get('status')
                if status not in ('satisfied','review_required','blocked') or receipt.get('executed') is None:
                    self._poison('unknown_or_incomplete_segment_outcome')
                if _has_rollback(receipt):
                    self._poison('rollback_requires_external_review')
                reported_request = receipt.get('request')
                self._validate_request(reported_request)
                original = record['request']
                if _digest({k:v for k,v in reported_request.items() if k not in _CAPS},65536) != _digest(
                        {k:v for k,v in original.items() if k not in _CAPS},65536):
                    self._poison('segment_request_identity_changed')
                if any(reported_request[field] > original[field] for field in _CAPS):
                    self._poison('segment_receipt_expanded_reserved_caps')
                segment_id = _identifier(receipt.get('segment_id'),'segment_id')
                if segment_id in self._segments:
                    self._poison('segment_id_reused_for_another_request')
                steps = receipt.get('steps')
                if type(steps) is not list or len(steps) > reported_request['max_steps']:
                    self._poison('step_accounting_incomplete_or_over_reserved_cap')
                previous_revision=_identifier(receipt.get('base_revision'),'base_revision')
                end_revision=_identifier(receipt.get('end_revision'),'end_revision')
                if self._last_end_revision is not None and previous_revision!=self._last_end_revision:
                    self._poison('segment_chain_does_not_follow_confirmed_readback')
                motions=[];new_steps=set();new_operations=set()
                for index,step in enumerate(steps):
                    if type(step) is not dict or step.get('state') != 'complete' or type(step.get('step_index')) is not int or step['step_index'] != index:
                        self._poison('step_is_unconfirmed_or_out_of_order')
                    step_id = _identifier(step.get('step_id'),'step_id')
                    operation_id = _identifier(step.get('operation_id'),'operation_id')
                    if step_id in self._steps or step_id in new_steps or operation_id in self._operations or operation_id in new_operations:
                        self._poison('physical_step_or_operation_id_reused')
                    result=step.get('result')
                    if (type(result) is not dict or result.get('status')!='verified'
                            or any(result.get(key) is not True for key in ('executed','verified','execution_verified'))
                            or not isinstance(result.get('actual_scene_revision'),str)
                            or not result['actual_scene_revision']):
                        self._poison('step_execution_not_confirmed_verified')
                    host_receipt=result.get('receipt')
                    if (type(host_receipt) is not dict or host_receipt.get('host_execution_verified') is not True
                            or host_receipt.get('focal_id')!=original['focal_id']
                            or host_receipt.get('before_revision')!=previous_revision
                            or host_receipt.get('after_revision')!=result['actual_scene_revision']
                            or host_receipt['after_revision']==previous_revision):
                        self._poison('step_host_receipt_chain_incomplete')
                    previous_revision=host_receipt['after_revision']
                    action=step.get('action')
                    if type(action) is not dict or action.get('focal_id') != original['focal_id'] or action.get('reference_id') != original['reference_id']:
                        self._poison('step_object_roles_changed')
                    delta=action.get('translation');rotation=action.get('rotation_euler_deg')
                    if type(delta) is not list or len(delta)!=3 or type(rotation) is not list or len(rotation)!=3:
                        self._poison('step_transform_accounting_incomplete')
                    if any(type(v) not in (int,float) or not math.isfinite(v) for v in delta+rotation):
                        self._poison('invalid_step_transform')
                    if delta[0]!=0 or delta[1]!=0 or any(rotation):
                        self._poison('step_exceeded_world_Z_translation_scope')
                    motion=_number(step.get('actual_translation_m'),'actual_translation_m',positive=True)
                    if (motion > reported_request['max_step_translation_m'] or motion > self.limits.max_step_translation_m
                            or math.hypot(*delta)>reported_request['max_step_translation_m']):
                        self._poison('actual_or_requested_step_cap_exceeded')
                    motions.append(motion);new_steps.add(step_id);new_operations.add(operation_id)
                total=_number(receipt.get('actual_total_translation_m'),'actual_total_translation_m')
                if not _sum_matches(total,sum((Fraction(v) for v in motions),Fraction(0))):
                    self._poison('segment_actual_motion_sum_disagrees')
                if total>reported_request['max_total_translation_m']:
                    self._poison('actual_segment_motion_cap_exceeded')
                if receipt.get('executed') is not bool(steps) or receipt.get('task_succeeded') is not (status=='satisfied'):
                    self._poison('segment_result_semantics_disagree')
                if end_revision!=previous_revision:
                    self._poison('segment_end_revision_disagrees')
                self._physical(physical_meter,motions)
                self._motion += sum((Fraction(v) for v in motions),Fraction(0))
                self._steps.update(new_steps);self._operations.update(new_operations)
                self._segments[segment_id]=request_id
                self._last_end_revision=end_revision
                record.update(state='confirmed',receipt_digest=receipt_digest,segment_id=segment_id)
                self._pending=None
                if self._remaining_time()<=0:
                    self._stopped='goal_time_budget_exhausted'
                    self._late_accounted=True
                elif status in ('satisfied','blocked'):
                    self._stopped='goal_'+status
                return self._snapshot(deduplicated=False)
            except GoalBudgetStopped:
                raise
            except (GoalBudgetError,ValueError,TypeError,KeyError,IndexError,RecursionError,OverflowError):
                self._poison('invalid_or_incomplete_segment_accounting')

    def _snapshot(self, *, deduplicated=False):
        return {'schema_version':'goal-budget-v1','scope':'single_in_memory_coordination_session',
            'execution_authority':False,'physical_meter_authenticity_verified':False,
            'requires_external_physical_meter':True,'cross_process_or_crash_recovery':False,
            'started_monotonic':self._started,'deadline_monotonic':self._deadline,
            'remaining_duration_s':self._remaining_time(),'confirmed_steps':len(self._steps),
            'actual_total_translation_m':float(self._motion),
            'remaining_steps':max(0,self.limits.max_steps-len(self._steps)),
            'remaining_translation_m':_floor_float(max(Fraction(0),Fraction(self.limits.max_total_translation_m)-self._motion)),
            'segments_reserved':len(self._requests),'recoveries_used':self._recoveries,
            'remaining_recoveries':max(0,self.limits.max_recoveries-self._recoveries),
            'pending_request_id':self._pending,'poisoned':self._poisoned,
            'late_accounted_only':self._late_accounted,
            'stopped_reason':self._stopped,'deduplicated':deduplicated}

    def snapshot(self):
        with self._lock:return self._snapshot()


__all__=['GoalBudget','GoalBudgetLimits','GoalBudgetError','GoalBudgetStopped']
