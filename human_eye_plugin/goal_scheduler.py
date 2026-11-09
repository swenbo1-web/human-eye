"""Finite automatic clearance tasks for an explicitly trusted owned embedding.

This private Python entry is deliberately absent from the model tool surface.
It combines existing solvers, durable journals and the fixed typed worker;
native review is evidence, never authority. A stopped task is not resumed here.
"""
from __future__ import annotations

import copy
import hashlib
import json
import threading
import time

from . import goal_journal as journal
from .auto_router import _ValidatedObservation
from .goal_continuation import (ContinuationPolicy, inspect_current_clearance,
                                review_continuation)
from .goal_segment import validate_clearance_segment_request
from .goal_supervision import (make_owned_host_context, owned_clock_domain,
                               owned_host_counter, validate_owned_motion_report)
from .live_service import LiveSpatialService
from .task_authority import (ClearanceTaskSpec, TrustedTaskAuthority,
    claim_grant, set_authorization_state)


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('utf-8')


def _digest(value):
    return hashlib.sha256(_json(value)).hexdigest()


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _forward_caps_with_rollback_reserve(caps, report):
    """Tighten original caps before dispatch; rollback spends the same budget.

    The native host requires a spare setter and a return path before every
    forward write. A missing reserve is a known planning refusal, never an
    excuse to expand the grant or to discover that limit during apply().
    """
    setters = report.get('remaining_setters')
    path = report.get('remaining_translation_m')
    _require(type(setters) is int and 2 <= setters <= 8,
             'host_rollback_setter_reserve_unavailable')
    _require(type(path) in (int, float) and 0 < path <= .008,
             'host_rollback_path_reserve_unavailable')
    bounded = copy.deepcopy(caps)
    bounded['max_steps'] = min(caps['max_steps'], setters - 1)
    bounded['max_step_translation_m'] = min(caps['max_step_translation_m'], path / 2.)
    bounded['max_total_translation_m'] = min(caps['max_total_translation_m'],
        path - bounded['max_step_translation_m'])
    _require(bounded['max_steps'] > 0 and bounded['max_step_translation_m'] > 0
        and bounded['max_total_translation_m'] > 0, 'host_rollback_reserve_unavailable')
    return bounded


def _retain_original_triangle(capture, meshes, spec, selector):
    """A group representative may differ from an independently valid intent.

    Reprove both finite triangles on this exact capture and compare their
    oriented rational planes. A coplanar count or rounded normal cannot
    replace a foot on the originally selected triangle. This path only runs
    for an explicit mismatch; it neither changes intent nor authorizes it.
    """
    from .support_plane_candidate import (
        _preflight, _rational_mesh, _certificate_from_rationals, _sub, _cross, _dot,
    )
    _require(_preflight(capture, {'focal_id':spec.focal_id,
        'reference_id':spec.reference_id}) is None, 'original_triangle_resource_limit')
    by_id = {mesh.object_id:mesh for mesh in meshes}
    _require(spec.focal_id in by_id and spec.reference_id in by_id,
             'original_triangle_pair_missing')
    representative = selector.get('reference_triangle_index')
    _require(type(representative) is int and representative >= 0,
             'discovered_triangle_index_invalid')
    try:
        fv, _ = _rational_mesh(by_id[spec.focal_id])
        rv, rf = _rational_mesh(by_id[spec.reference_id])
    except ArithmeticError as exc:
        raise ValueError('original_triangle_geometry_unsupported:' + str(exc)) from exc
    original = spec.reference_triangle_index
    _require(type(original) is int and 0 <= original < len(rf),
             'original_triangle_outside_original_mesh')
    _require(representative < len(rf), 'discovered_triangle_outside_original_mesh')
    try:
        _certificate_from_rationals(fv, rv, rf, original)
    except ArithmeticError as exc:
        raise ValueError('original_triangle_no_exact_support_witness:' + str(exc)) from exc
    try:
        _certificate_from_rationals(fv, rv, rf, representative)
    except ArithmeticError as exc:
        raise ValueError('discovered_triangle_no_exact_support_witness:' + str(exc)) from exc
    def plane_key(index):
        a,b,c = (rv[i] for i in rf[index])
        normal = _cross(_sub(b,a), _sub(c,a))
        divisor = max(abs(value) for value in normal)
        return tuple(value/divisor for value in normal) + (_dot(normal,a)/divisor,)
    _require(plane_key(original) == plane_key(representative),
             'original_triangle_not_discovered_oriented_plane')
    retained = copy.deepcopy(selector)
    retained['reference_triangle_index'] = original
    return retained


class OwnedGoalScheduler:
    """One authenticated task, one original budget, bounded automatic children.

    The authority must authenticate an external stable task event. Neither the
    supplied proposal nor a persisted grant can replace that Python capability.
    A second instance/process sees the durable claim and only returns history
    or a review requirement. It cannot reconstruct dispatch permission.
    """
    def __init__(self, config_path, host, authority):
        _require(type(authority) is TrustedTaskAuthority, 'trusted_task_authority_required')
        self.host = host
        self.authority = authority
        self.service = LiveSpatialService(config_path, host=host)
        self._run_lock = threading.Lock()
        self._ticket = None
        self._grant = None
        self._host_binding = None
        self._handoff = None

    def _capture(self):
        packet = self.host.capture_evidence()
        observation = _ValidatedObservation(packet['capture'])
        # capture_evidence exports both views in the same host traversal.
        # Keep the existing envelope shape without claiming a second sample.
        envelope = {'capture': observation.scene, 'native_scene': copy.deepcopy(packet['native_scene']),
                    'capture_confirmation': copy.deepcopy(observation.scene)}
        self._captured_observation = (envelope, observation)
        return envelope

    def _observation(self, envelope):
        retained = getattr(self, '_captured_observation', None)
        if retained is not None and retained[0] is envelope:
            retained[1]._require_scene(envelope['capture'])
            return retained[1]
        return _ValidatedObservation(envelope['capture'])

    def _discover(self, spec, envelope, session_id):
        from .support_plane_discovery import discover_support_planes
        observation = self._observation(envelope)
        discovery = discover_support_planes(observation.scene, spec.focal_id, spec.reference_id,
            {'direction_world': list(spec.direction_world)}, _observation=observation)
        _require(discovery.get('status') == 'complete'
                 and discovery.get('ambiguous') is False
                 and discovery.get('omitted_candidate_count') == 0
                 and len(discovery.get('candidates', [])) == 1, 'unique_complete_support_required')
        selector = copy.deepcopy(discovery['candidates'][0]['selector'])
        capture, meshes, fingerprint = observation.scene, observation.meshes, observation.fingerprint
        expected = {'scene_revision': capture['revision'], 'scene_fingerprint': fingerprint,
                    'focal_id': spec.focal_id, 'reference_id': spec.reference_id}
        _require(selector.get('selection_binding') == expected, 'discovery_not_original_fresh_capture')
        if spec.reference_triangle_index not in (None, selector.get('reference_triangle_index')):
            selector = _retain_original_triangle(capture, meshes, spec, selector)
        return selector

    @staticmethod
    def _policy(spec, build):
        limits = spec.limits
        return ContinuationPolicy(spec.focal_id, spec.reference_id,
            spec.target_clearance_m, spec.clearance_tolerance_m, spec.direction_world,
            spec.reference_triangle_index, limits.max_step_translation_m,
            limits.max_steps, limits.max_total_translation_m, limits.max_recoveries,
            expected_engine_build_id=build,
            max_segment_duration_s=min(30., limits.max_duration_s))

    def _claim(self, grant):
        with self.service._locked() as (value, runtime):
            # Existing event lookup precedes legacy blocking checks, so history
            # remains readable while another task is unresolved.
            existing = grant.key in value.get('goal_authorizations', {}).get('records', {})
            if not existing:
                from .goal_execution import unfinished_segment
                _require(not value.get('inflight') and not runtime.status['quarantined']
                         and not unfinished_segment(value)
                         and journal.blocking_goal(value) is None,
                         'prior_write_requires_review')
            claimed = claim_grant(value, grant)
            if claimed['fresh_claim']:
                payload = grant.payload()
                journal.create_goal(value, grant.goal_id, grant.session_id,
                    limits=grant.spec_resolved.limits,
                    clock_domain=payload['scope']['clock_domain'], now=grant.issued_monotonic)
                journal.snapshot(value, grant.goal_id,
                    clock_domain=payload['scope']['clock_domain'], now=time.perf_counter())
                set_authorization_state(value, grant.key, 'active')
                self.service._save(value, runtime)
            return claimed

    def _authorize_dispatch(self, goal_id, session_id, child_id, request):
        # Called under the connector lock: no service reentry or host I/O.
        ticket = self._ticket
        grant = self._grant
        if ticket is None or grant is None:
            return False
        try:
            if self._handoff is not None:self._handoff.check()
            payload = self.authority.verify(grant)
            valid = (ticket['used'] is False and time.perf_counter() < grant.deadline_monotonic
                and (goal_id, session_id, child_id) ==
                    (grant.goal_id, grant.session_id, ticket['child_id'])
                and _json(request) == _json(ticket['request'])
                and payload['scope']['engine_build_id'] == self.service.describe_runtime()['build_id'])
            for field in ('solver', 'focal_id', 'reference_id', 'target_clearance_m',
                          'clearance_tolerance_m', 'direction_world', 'reference_triangle_index'):
                valid = valid and request.get(field) == payload['spec'][field]
            if valid:
                ticket['used'] = True
            return valid is True
        except Exception:
            return False

    def _record_stop(self, grant, result, reason):
        if grant is None:
            return result
        try:
            with self.service._locked() as (value, runtime):
                record = value.get('goal_authorizations', {}).get('records', {}).get(grant.key)
                if record is not None and record['status'] in {'reserved', 'active'}:
                    set_authorization_state(value, grant.key, 'frozen',
                        result=result, reason=reason[:256])
                    self.service._save(value, runtime)
        except Exception as exc:
            # The already persisted reservation/active record remains blocking.
            result['stop_persistence_error'] = type(exc).__name__
        return result

    def _finish(self, grant, policy, last, budget, result):
        # Serialize final release with all connector writes. The independent
        # native and physical checks must precede closing the registered scope.
        with self.service._locked() as (value, runtime):
            _require(self.service._identity_rejection() is None, 'runtime_identity_changed')
            self.authority.verify(grant)
            limits = grant.spec_resolved.limits
            parent = value['goal_supervision']['records'][grant.goal_id]
            _require(parent['status'] == 'completed' and not value.get('inflight')
                     and not runtime.status['quarantined']
                     and all(c['confirmed_monotonic'] is not None for c in parent['children']),
                     'parent_not_safely_completed')
            _require(time.perf_counter() < grant.deadline_monotonic, 'task_deadline_expired_before_release')
            with self.host.transaction():
                final = self._capture()
                _require(_json(final) == _json(last), 'final_scene_changed')
                check = inspect_current_clearance(final, policy)
                _require(check['decision'] == 'already_satisfied', 'final_native_goal_not_satisfied')
                _require(self._host_binding is not None, 'original_registered_host_binding_unavailable')
                meter = validate_owned_motion_report(self.host, grant.goal_id,
                    self.host.motion_goal_status(grant.goal_id), expected_binding=self._host_binding,
                    expected_limits=limits)
                physical = meter.get('physical_meter', {})
                scope = grant.payload()['scope']
                binding = meter.get('binding', {})
                _require(meter.get('closed') is False and meter.get('frozen_reason') is None
                    and meter.get('all_channels_complete') is True
                    and meter.get('registered_events_complete') is True
                    and meter.get('unknown_event_count') == 0
                    and physical.get('complete') is True and physical.get('rollback_count') == 0
                    and physical.get('actual_setter_count') == budget['confirmed_steps']
                    and physical.get('actual_cumulative_translation_m') == budget['actual_total_translation_m']
                    and binding.get('document_epoch') == scope['host_identity']['document_epoch']
                    and binding.get('object_instances') == scope['host_identity']['object_instances']
                    and self.host._process.pid == scope['process_id']
                    and binding.get('focal_id') == policy.focal_id
                    and binding.get('reference_id') == policy.reference_id,
                    'final_physical_meter_disagrees')
                _require(time.perf_counter() < grant.deadline_monotonic, 'task_deadline_expired_before_release')
                closed = validate_owned_motion_report(self.host, grant.goal_id,
                    self.host.end_motion_goal(grant.goal_id),
                    expected_binding=self._host_binding,
                    expected_limits=limits, closed=True)
                _require(closed.get('reserved_event_count') == meter['reserved_event_count']
                    and closed.get('cancelled_before_entry_count') == meter['cancelled_before_entry_count']
                    and {k:v for k,v in closed.get('physical_meter', {}).items() if k != 'complete'}
                        == {k:v for k,v in physical.items() if k != 'complete'},
                    'host_release_not_confirmed')
            result.update(status='completed', task_succeeded=True, host_closed=True,
                physical_task_succeeded=True, execution_phase='physical_completion_verified',
                completion_persistence='unknown',
                host_process_alive=self.host.is_alive,
                clearance_at_task_end_m=check['current_clearance_m'])
            # The record is committed iff the existing atomic save commits.
            # A failed/lost acknowledgement leaves the caller's copy unknown.
            committed_result = dict(result, completion_persistence='committed')
            set_authorization_state(value, grant.key, 'completed', result=committed_result)
            self.service._save(value, runtime)
            result['completion_persistence'] = 'committed'
            return result

    def run(self, spec):
        with self._run_lock:
            from .goal_execution import ArmAxialTaskSpec, run_arm_axial_step
            if type(spec) is ArmAxialTaskSpec:
                return run_arm_axial_step(self.service, spec)
            return self._run(spec)

    def run_registered(self, handoff):
        from .task_entry import _TaskHandoff
        _require(type(handoff) is _TaskHandoff and handoff.entry._scheduler is self
            and handoff.live.get('handoff') is handoff and not handoff.used,
            'private_original_task_handoff_required')
        with self._run_lock:
            result=self._run(handoff.live['resolved'],_handoff=handoff)
            reasons=result.get('reason_codes',[])
            text=' '.join(reasons)
            kind=('completed' if result['status']=='completed' else
                'revoked' if 'revok' in text else 'expired_or_budget' if any(x in text for x in ('expired','budget','deadline','limit')) else
                'external_change' if 'changed' in text else 'review_required')
            result['review_event']=dict(schema='owned-task-review-v1',event_id=handoff.live['grant'].key+':review',
                kind=kind,reason_codes=copy.deepcopy(reasons),historical=False,
                task_succeeded=result['task_succeeded'],executed_this_call=result['executed_this_call'],
                new_setter_count=result['new_setter_count'],execution_authority=False,retry_authorized=False,
                delivery='returned_to_trusted_embedding_not_durable_outbox')
            return result

    def _run(self, spec, *, _handoff=None):
        result = {'schema_version': 'owned-goal-scheduler-v1', 'status': 'review_required',
            'task_succeeded': False, 'executed_this_call': False, 'new_setter_count': 0,
            'engine_confirmed_steps': 0, 'host_closed': False, 'segments': [],
            'execution_phase': 'not_submitted', 'physical_task_succeeded': None,
            'completion_persistence': 'not_attempted',
            'execution_authority': False, 'retry_authorized': False,
            'presentation_scope': 'recorded_task_end_snapshot_not_current_after_return'}
        grant = None
        fresh_claim = False
        self._grant = None
        self._host_binding = None
        self._ticket = None
        self._handoff = _handoff
        try:
            _require(type(spec) is ClearanceTaskSpec, 'frozen_clearance_task_spec_required')
            _require(self.service.config.get('enabled', True), 'connector_disabled')
            _require(self.service._identity_rejection() is None, 'runtime_identity_changed')
            if _handoff is not None:
                # Own the original active reservation even if take() refuses;
                # stopping it never creates another grant or budget window.
                grant=_handoff.live['grant'];fresh_claim=True
                grant,initial,resolved=_handoff.take(self)
                scope=grant.payload()['scope'];build=scope['engine_build_id']
                policy=self._policy(resolved,build)
            else:
                counter = owned_host_counter(self.host)
                initial = self._capture()
                selector = self._discover(spec, initial, 'scheduler-discovery')
                from dataclasses import replace
                resolved = replace(spec, reference_triangle_index=selector['reference_triangle_index'])
                build = self.service.describe_runtime()['build_id']
                policy = self._policy(resolved, build)
                native = inspect_current_clearance(initial, policy)
                _require(native['decision'] != 'stop', 'initial_native_review:' + ','.join(native['reason_codes']))
                scope = {'engine_build_id': build, 'process_id': self.host._process.pid,
                    'host_identity': initial['capture']['host_identity'],
                    'reference_triangle_index': resolved.reference_triangle_index,
                    'initial_capture_sha256': _digest(initial['capture']),
                    'initial_native_sha256': _digest(initial['native_scene']),
                    'clock_domain': owned_clock_domain(initial['capture']['host_identity']['document_epoch'], counter)}
                grant = self.authority.issue(resolved, scope)
                claimed = self._claim(grant)
                if not claimed['fresh_claim']:
                    previous = copy.deepcopy(claimed['record'].get('result') or result)
                    previous.update(historical_receipt=True, replayed=True,
                        current_scene_revalidated=False, executed_this_call=False, new_setter_count=0,
                        execution_phase='not_submitted',
                        execution_authority=False, retry_authorized=False)
                    if claimed['mode'] != 'historical':
                        previous.update(status='review_required', task_succeeded=False,
                                        reason_codes=['existing_authorization_requires_review'])
                    return previous
            self._grant = grant
            fresh_claim = True
            result.update(goal_id=grant.goal_id, session_id=grant.session_id,
                authorization_key=grant.key, runtime_build_id=build,
                target_clearance_m=resolved.target_clearance_m)
            _require(time.perf_counter() < grant.deadline_monotonic, 'task_deadline_expired_before_start')
            with self.host.transaction():
                if _handoff is not None:_handoff.check()
                fresh = self._capture()
                _require(_json(fresh) == _json(initial), 'initial_scene_changed_before_registration')
                limits = resolved.limits
                self.host.begin_motion_goal(grant.goal_id, resolved.focal_id, resolved.reference_id,
                    limits={'max_setters': limits.max_steps,
                        'max_step_translation_m': limits.max_step_translation_m,
                        'max_total_translation_m': limits.max_total_translation_m,
                        'max_duration_s': min(30., limits.max_duration_s)})
                registered = validate_owned_motion_report(self.host, grant.goal_id,
                    self.host.motion_goal_status(grant.goal_id), expected_limits=limits)
                binding = registered['binding']
                _require(binding['document_epoch'] == scope['host_identity']['document_epoch']
                    and binding['object_instances'] == scope['host_identity']['object_instances']
                    and binding['focal_id'] == resolved.focal_id
                    and binding['reference_id'] == resolved.reference_id
                    and registered['physical_meter']['actual_setter_count'] == 0
                    and registered['reserved_event_count'] == 0,
                    'initial_registered_host_binding_disagrees')
                self._host_binding = copy.deepcopy(binding)
                context = make_owned_host_context(self.host, grant.goal_id, self._authorize_dispatch,
                    expected_binding=self._host_binding, expected_limits=limits,
                    **({'commit_guard':_handoff.commit_guard} if _handoff is not None else {}))
                _require(context.clock_domain() == scope['clock_domain'], 'registered_clock_domain_changed')
                self.service._supervisor_context = context
            last = initial
            for index in range(resolved.limits.max_segments):
                if _handoff is not None:_handoff.check()
                _require(time.perf_counter() < grant.deadline_monotonic, 'task_deadline_expired')
                before = self._capture()
                _require(_json(before) == _json(last), 'scene_changed_between_segments')
                selector = self._discover(resolved, before, grant.session_id)
                caps = self.service.goal_supervision('caps', grant.goal_id)['caps']
                native_before = inspect_current_clearance(before, policy)
                _require(native_before['decision'] != 'stop', 'fresh_native_review_failed')
                if native_before['decision'] != 'already_satisfied':
                    with self.host.transaction():
                        report = validate_owned_motion_report(self.host, grant.goal_id,
                            self.host.motion_goal_status(grant.goal_id),
                            expected_binding=self._host_binding, expected_limits=limits)
                    caps = _forward_caps_with_rollback_reserve(caps, report)
                request = {k: v for k, v in resolved.to_dict().items() if k != 'limits'}
                request.update(selector)
                request.update(caps)
                child_id = grant.goal_id + ':segment:' + str(index + 1)
                reservation = self.service.goal_supervision('reserve', grant.goal_id,
                    request_id=child_id, request=request)
                _require(reservation['fresh_reservation'] is True, 'child_reservation_not_fresh')
                request = validate_clearance_segment_request(reservation['request'])
                plan_handoff = {}
                preview = self.service.run_clearance_segment(grant.session_id,
                    child_id + ':preview', request, execute=False, include_image=False,
                    _initial_observation=self._observation(before), _plan_handoff=plan_handoff)
                candidate = preview.get('candidate') or {}
                result['last_preview'] = {'status': preview.get('status'),
                    'candidate_status': candidate.get('status'),
                    'reason_codes': candidate.get('reason_codes', preview.get('reason_codes', []))}
                _require(preview.get('status') == 'preview' and preview.get('executed') is False
                    and candidate.get('status') in {'candidate', 'goal_satisfied'},
                    'fresh_preview_not_executable')
                if _handoff is not None:_handoff.check()
                self._ticket = {'child_id': child_id, 'request': copy.deepcopy(request), 'used': False}
                # This call can raise after the host setter or durable commit.
                # Mark uncertainty before crossing that boundary. Preserve a
                # prior segment's confirmed execution and accounting lower bound.
                previously_executed = result['executed_this_call']
                result['execution_phase'] = 'dispatch_started'
                result['executed_this_call'] = True if previously_executed is True else None
                result['new_setter_count'] = None
                try:
                    receipt = self.service.run_supervised_clearance_segment(grant.goal_id,
                        grant.session_id, child_id, request, _plan_handoff=plan_handoff)
                finally:
                    self._ticket = None
                # Persist known physical accounting before native post-review.
                # Unknowns are frozen by reconciliation, never resent here.
                executed = receipt.get('executed')
                result['execution_phase'] = 'receipt_received'
                result['executed_this_call'] = (True if previously_executed is True or executed is True
                    else False if previously_executed is False and executed is False else None)
                budget = self.service.goal_supervision('reconcile', grant.goal_id, request_id=child_id)
                result['execution_phase'] = 'reconciled'
                result['engine_confirmed_steps'] = budget['confirmed_steps']
                result['new_setter_count'] = budget['confirmed_steps']
                result['budget'] = {k: budget[k] for k in ('started_monotonic', 'deadline_monotonic',
                    'confirmed_steps', 'actual_total_translation_m', 'segments_reserved', 'recoveries_used',
                    'journal_status', 'journal_reason', 'late_accounted_only')}
                if _handoff is not None:_handoff.check()
                current = self._capture()
                if receipt.get('status') == 'satisfied' and receipt.get('steps') == []:
                    zero = inspect_current_clearance(current, policy)
                    _require(inspect_current_clearance(before, policy)['decision'] == 'already_satisfied'
                        and zero['decision'] == 'already_satisfied'
                        and _json(current) == _json(before), 'zero_step_native_review_failed')
                    review = {**zero, 'decision': 'completed'}
                else:
                    review = review_continuation(before, current, receipt, policy)
                result['segments'].append({'request_id': child_id, 'status': receipt.get('status'),
                    'confirmed_steps': len(receipt.get('steps', [])), 'review_decision': review['decision'],
                    'reason_codes': review['reason_codes']})
                _require(not budget['late_accounted_only'], 'late_accounted_requires_review')
                if review['decision'] == 'completed' and budget['journal_status'] == 'completed':
                    if _handoff is not None:_handoff.check()
                    return self._finish(grant, policy, current, budget, result)
                _require(review['decision'] == 'eligible_for_fresh_preview',
                         'native_continuation_denied:' + ','.join(review['reason_codes']))
                _require(budget['journal_status'] == 'active', 'whole_goal_budget_stopped')
                last = current
            raise ValueError('whole_goal_segment_limit_reached')
        except Exception as exc:
            reason = (type(exc).__name__ + ':' + str(exc))[:256]
            # _finish may have verified physical completion and closed the
            # host before its final save raised. Keep that evidence, while
            # normal completion requires an acknowledged completion record.
            result.update(status='review_required', task_succeeded=False)
            result['reason_codes'] = [reason]
            return self._record_stop(grant if fresh_claim else None, result, reason)
        finally:
            self._ticket = None
            self._grant = None
            self._handoff = None


__all__ = ['OwnedGoalScheduler']
