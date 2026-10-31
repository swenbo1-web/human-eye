"""Finite live goal segments using the existing checked single-step core.

The connector lock owns a short segment, not every possible Blender editor.
Receipts are bounded and never silently evicted: an old request identity must
not turn into a new write. Ambiguous submissions remain quarantined; unfinished
segments from another process are reported, never automatically continued.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import time
import uuid

from .auto_router import _validated_scene, _trace_span
from .goal_segment import (validate_clearance_segment_request,
                           solve_segment_candidate, clearance_segment_goal,
                           selection_binding_rejection)
from .telemetry import (annotate, current_trace, build_goal_step_metrics,
                        summarize_goal_segment_metrics)

MAX_SEGMENT_RECEIPTS = 64
_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$')
_FINAL = {'satisfied', 'blocked', 'review_required', 'execution_uncertain', 'segment_interrupted'}
_KNOWN_STEP = {'verified', 'no_op', 'blocked', 'invalid_action', 'invalid_goal', 'observation_required'}
_PREPARATION_REFUSALS = {'implementation_mismatch', 'host_quarantined', 'disabled'}
_STEP_RECEIPT_FIELDS = {'status', 'executed', 'verified', 'execution_verified', 'goal_evaluation',
    'task_succeeded', 'actual_scene_revision', 'reason_codes', 'receipt'}
_STEP_DEADLINE_FIELDS = {'host_prewrite_refusal', 'host_mutation_started', 'forward_deadline'}


def _identifier(value, field):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(field + ' requires 1..128 simple identity characters')
    return value


def _fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
        allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def validate_segment_ledger(value):
    """Old connector states have no ledger; malformed new ledgers fail closed."""
    if 'goal_segments' not in value:
        return
    ledger = value['goal_segments']
    if (not isinstance(ledger, dict) or set(ledger) != {'schema_version', 'records'}
            or ledger['schema_version'] != '1.0' or not isinstance(ledger['records'], dict)
            or len(ledger['records']) > 64):
        raise ValueError('Invalid persisted goal segment ledger')
    for identity, entry in ledger['records'].items():
        _identifier(identity, 'persisted request_id')
        if isinstance(entry, dict) and 'parent_goal_id' in entry:
            _identifier(entry['parent_goal_id'], 'persisted parent_goal_id')
            if 'goal_supervision' not in value:
                raise ValueError('Supervised child has lost its parent journal')
        if (not isinstance(entry, dict) or not {'request_fingerprint', 'segment_id', 'session_id',
                'request', 'status', 'steps', 'result', 'base_revision', 'end_revision'}.issubset(entry)
                or entry['status'] not in _FINAL | {'running'}
                or not isinstance(entry['request_fingerprint'], str)
                or not re.fullmatch(r'[a-f0-9]{64}', entry['request_fingerprint'])
                or not isinstance(entry['steps'], list) or len(entry['steps']) > 8
                or entry['result'] is not None and not isinstance(entry['result'], dict)):
            raise ValueError('Invalid persisted goal segment record')
        _identifier(entry['segment_id'], 'persisted segment_id')
        _identifier(entry['session_id'], 'persisted session_id')
        request = validate_clearance_segment_request(entry['request'])
        if request != entry['request']:
            raise ValueError('Persisted goal request is not normalized')
        if _fingerprint({'session_id': entry['session_id'], 'request': request}) != entry['request_fingerprint']:
            raise ValueError('Persisted goal request fingerprint mismatch')
        seen = set()
        for index, step in enumerate(entry['steps']):
            if (not isinstance(step, dict) or step.get('state') not in {'planned', 'submitting', 'complete', 'uncertain'}
                    or step.get('step_index') != index or step.get('step_id') in seen
                    or not isinstance(step.get('action'), dict)):
                raise ValueError('Invalid persisted goal step')
            _identifier(step.get('step_id'), 'persisted step_id')
            seen.add(step['step_id'])
        if entry['status'] != 'running' and entry['result'] is None:
            raise ValueError('Final goal segment has no receipt')
        if entry['result'] is not None and (
                entry['result'].get('status') != entry['status']
                or entry['result'].get('request_id') != identity
                or entry['result'].get('segment_id') != entry['segment_id']
                or entry['result'].get('request') != entry['request']
                or entry['result'].get('steps') != entry['steps']):
            raise ValueError('Persisted goal receipt identity or state mismatch')
        if entry['result'] is not None and entry['result'].get('task_succeeded') is not (entry['status'] == 'satisfied'):
            raise ValueError('Persisted goal success contradicts its status')
        for step in entry['steps']:
            if step['state'] in {'complete', 'uncertain'} and not isinstance(step.get('result'), dict):
                raise ValueError('Persisted completed step has no result')
            if step['state'] in {'complete', 'uncertain'}:
                receipt = step['result']
                if (set(receipt) not in (_STEP_RECEIPT_FIELDS, _STEP_RECEIPT_FIELDS | _STEP_DEADLINE_FIELDS)
                        or not isinstance(receipt['status'], str)
                        or receipt['executed'] is not None and type(receipt['executed']) is not bool
                        or type(receipt['verified']) is not bool
                        or type(receipt['execution_verified']) is not bool
                        or receipt['verified'] != receipt['execution_verified']
                        or receipt['task_succeeded'] is not None and type(receipt['task_succeeded']) is not bool
                        or receipt['receipt'] is not None and not isinstance(receipt['receipt'], dict)
                        or not isinstance(receipt['reason_codes'], list)
                        or any(not isinstance(reason, str) or not reason for reason in receipt['reason_codes'])):
                    raise ValueError('Invalid persisted goal-step receipt')
                if set(receipt) == _STEP_RECEIPT_FIELDS | _STEP_DEADLINE_FIELDS:
                    from .forward_deadline import validate_refusal
                    proof = receipt['host_prewrite_refusal']
                    wire = receipt['forward_deadline']
                    if (receipt['status'] != 'blocked' or receipt['executed'] is not False
                            or receipt['host_mutation_started'] is not False
                            or not isinstance(wire, dict) or wire.get('goal_id') != entry.get('parent_goal_id')):
                        raise ValueError('Deadline no-write receipt semantics disagree')
                    validate_refusal({'status':'rejected_before_mutation','rejection':proof},
                        forward_deadline=wire, action=step['action'], expected_revision=wire['expected_revision'],
                        expected_fingerprint=wire['expected_fingerprint'], request_nonce=wire['request_nonce'])
                if step['state'] == 'complete':
                    if receipt['status'] not in _KNOWN_STEP | _PREPARATION_REFUSALS:
                        raise ValueError('Completed goal step has an unknown disposition')
                    verified = receipt['status'] == 'verified'
                    if (receipt['executed'] is not verified or receipt['execution_verified'] is not verified
                            or verified and (not isinstance(receipt['actual_scene_revision'], str)
                                             or not receipt['actual_scene_revision'])):
                        raise ValueError('Completed goal-step execution semantics disagree')
            if step['state'] in {'submitting', 'uncertain'}:
                pending = value.get('inflight')
                if (not isinstance(pending, dict) or pending.get('segment_id') != entry['segment_id']
                        or pending.get('step_id') != step['step_id']
                        or pending.get('operation_id') != step.get('operation_id')):
                    raise ValueError('Persisted goal step differs from pending operation')


def unfinished_segment(value):
    validate_segment_ledger(value)
    return any(entry['status'] == 'running' for entry in value.get('goal_segments', {}).get('records', {}).values())


def record_step_result(step, result):
    """Called inside the same atomic persist that clears a known inflight write."""
    known = result.get('status') in _KNOWN_STEP or (
        step.get('state') == 'planned' and result.get('status') in _PREPARATION_REFUSALS)
    step['state'] = 'complete' if known else 'uncertain'
    step['result'] = {field: copy.deepcopy(result.get(field)) for field in (
        'status', 'executed', 'verified', 'execution_verified', 'goal_evaluation', 'task_succeeded',
        'actual_scene_revision', 'reason_codes', 'receipt')}
    if isinstance(result.get('host_prewrite_refusal'), dict) and 'forward_deadline' in result:
        for field in _STEP_DEADLINE_FIELDS:
            step['result'][field] = copy.deepcopy(result.get(field))


def _result(status, *, reasons=(), **fields):
    return {'schema_version': '1.0', 'status': status, 'reason_codes': list(reasons),
        'task_succeeded': status == 'satisfied', 'review_required': status in {'review_required', 'segment_interrupted'},
        'execution_scope': 'terminal_geometry_only', 'swept_path_certified': False,
        'execution_authority': False, 'retry_authorized': False,
        'model_usage': 'unknown', **fields}


def _binding(scene):
    identity = scene.get('host_identity')
    if identity is None:
        return None
    # _validated_scene has checked the complete identity namespace and shape.
    return copy.deepcopy(identity)


def _metrics(segment_id, steps, elapsed_ns, outcome):
    """Ancillary metrics must never invalidate a completed write."""
    try:
        rows = []
        for step in steps:
            result = step.get('result', {})
            rows.append(build_goal_step_metrics(segment_id=segment_id, step_id=step['step_id'],
                step_index=step['step_index'], operation_id=step.get('operation_id'),
                outcome=result.get('status', 'unknown'), executed=result.get('executed'),
                execution_verified=result.get('execution_verified'),
                counters={'local_corrections': int(step['step_index'] > 0 and result.get('executed') is True)}))
        return summarize_goal_segment_metrics(rows, segment_id=segment_id,
            duration_ns=elapsed_ns, outcome=outcome)
    except Exception:
        return {'status': 'unavailable', 'scope': 'single_segment_not_whole_task', 'model_usage': 'unknown'}


def _capture(service, runtime):
    service._check_request_budget('before_segment_host_capture')
    with runtime._transaction(), _trace_span('host.segment_capture', kind='host', source_name='host_blender'):
        raw = service.host.capture_scene()
    scene, _, _ = _validated_scene(raw)
    return scene


def _pivot(scene, focal_id):
    return next(mesh['pivot_world'] for mesh in scene['meshes'] if mesh['object_id'] == focal_id)


def _first_step_plan(scene, request, readback_atol_m):
    """Plan the action the first submission can admit, without granting rights.

    The caller's normalized request remains the receipt identity. Only the
    detached solver input uses the smaller positive motion budgets. With no
    usable motion budget, still measure the original request so an already
    satisfied goal or a geometry refusal takes precedence over exhaustion.
    """
    margin = math.sqrt(3.) * readback_atol_m
    remaining = request['max_total_translation_m'] - margin
    step_limit = min(request['max_step_translation_m'] - margin, remaining)
    available = remaining > 0 and step_limit > 0
    bounded = (dict(request, max_total_translation_m=remaining,
                    max_step_translation_m=step_limit) if available else request)
    plan = solve_segment_candidate(scene, bounded)
    # Keep each solver's existing request shape, with the caller's caps. The
    # explicit planning metadata below carries the effective caps instead.
    for field in ('max_step_translation_m', 'max_total_translation_m'):
        plan['request'][field] = request[field]
    plan['effective_motion_budget'] = {
        'scope': 'first_step_planning_only', 'readback_margin_m': margin,
        'solver_input_scope': ('effective_positive_budget' if available
            else 'original_positive_budget_measurement_only'),
        'available': available, 'max_total_translation_m': max(0., remaining),
        'max_step_translation_m': max(0., step_limit)}
    if not available and plan['status'] == 'candidate':
        # The positive original request was used for measurement, never for
        # admission. Do not expose its inadmissible action or predictions.
        plan.update(status='motion_budget_exhausted', candidate=None,
            reason_codes=['segment_motion_or_precision_budget_exhausted'])
        for field in ('proposed_translation_m', 'predicted_plane_clearance_m',
                'predicted_absolute_error_m', 'step_clipped', 'candidate_certificate',
                'candidate_strict_geometry', 'candidate_clearance_m',
                'candidate_metric_agreement_tolerance_m', 'actual_max_vertex_translation_m'):
            plan.pop(field, None)
    return plan


def run_clearance_segment(service, session_id, request_id, request, *, execute=False,
                          include_image=False, _parent_goal_id=None):
    """Run under one connector lock; never call the locking public transform."""
    _identifier(session_id, 'session_id')
    _identifier(request_id, 'request_id')
    request = validate_clearance_segment_request(request)
    if type(execute) is not bool or type(include_image) is not bool:
        raise ValueError('execute and include_image must be booleans')
    rejected = service._identity_rejection()
    if rejected is not None:
        return rejected
    if not service.config.get('enabled', True):
        return _result('disabled')
    clock = time.monotonic
    if _parent_goal_id is not None:
        from .goal_supervision import _context
        clock = _context(service).clock or time.monotonic
    started = clock()
    started_ns = time.monotonic_ns()
    deadline = started + request['max_duration_s']
    parent_deadline = None
    signature = _fingerprint({'session_id': session_id, 'request': request})
    with service._locked() as (value, runtime):
        records = value.get('goal_segments', {}).get('records', {})
        previous = records.get(request_id)
        if execute and ('goal_supervision' in value or 'goal_authorizations' in value or _parent_goal_id is not None):
            from .goal_supervision import write_blocker
            reason = write_blocker(value, parent_goal_id=_parent_goal_id,
                request_id=request_id, historical=previous is not None)
            if reason is not None:
                return _result('segment_interrupted', reasons=[reason])
        if execute and previous is not None:
            if previous['request_fingerprint'] != signature:
                return _result('request_conflict', reasons=['request_identity_parameter_conflict'])
            if previous['status'] == 'running':
                uncertain = bool(value.get('inflight')) or any(step['state'] in {'submitting', 'uncertain'} for step in previous['steps'])
                return _result('execution_uncertain' if uncertain else 'segment_interrupted',
                    reasons=['unfinished_segment_never_automatically_resumed'], segment_id=previous['segment_id'],
                    request_id=request_id, historical_receipt=True, replayed=True,
                    steps=copy.deepcopy(previous['steps']))
            result = copy.deepcopy(previous['result'])
            result.update(replayed=True, historical_receipt=True, current_scene_revalidated=False)
            return result
        if value.get('inflight') or runtime.status['quarantined']:
            return _result('execution_uncertain', reasons=['host_quarantined'], executed=None)
        if unfinished_segment(value):
            return _result('segment_interrupted', reasons=['unfinished_goal_segment_requires_review'])
        if execute and len(records) >= MAX_SEGMENT_RECEIPTS:
            return _result('receipt_capacity_exhausted', reasons=['request_receipts_not_evicted'])
        if clock() >= deadline:
            return _result('review_required', reasons=['segment_time_budget_exhausted'])
        if execute and _parent_goal_id is not None:
            from .goal_supervision import dispatch_locked
            parent_deadline = dispatch_locked(service, value, runtime,
                _parent_goal_id, session_id, request_id, request)
            deadline = min(deadline, parent_deadline)
            if clock() >= deadline:
                return _result('review_required', reasons=['parent_goal_time_budget_exhausted'])
        scene = _capture(service, runtime)
        binding_rejection = (selection_binding_rejection(scene, request)
                             if 'selection_binding' in request else None)
        if binding_rejection is not None:
            # Historical receipts have already returned above. A fresh goal
            # or preview must not inherit a face index from a changed capture,
            # and a refused selection must not reserve a running receipt.
            return _result('blocked', reasons=[binding_rejection], executed=False,
                selection_binding_status='mismatch', requires_reobserve=True)
        if not execute:
            # Preview can inspect old hosts without an identity contract, but
            # does not persist observations, reserve IDs, or grant write rights.
            return _result('preview', candidate=_first_step_plan(scene, request,
                    runtime.router.readback_atol_m), executed=False,
                host_identity_available=_binding(scene) is not None,
                remaining_write_gates_required=True)
        if _binding(scene) is None:
            return _result('blocked', reasons=['host_identity_required_for_goal_segment'])
        # Resolve scene-dependent request errors (for example an original
        # triangle index outside this capture) before reserving a durable
        # running receipt. The first loop uses this exact captured plan;
        # Later steps recapture and check the complete snapshot before reusing
        # the preceding readback plan. A changed budget is still solved below.
        initial_plan = _first_step_plan(scene, request, runtime.router.readback_atol_m)
        if clock() >= deadline:
            return _result('review_required', reasons=['segment_time_budget_exhausted_after_initial_plan'])
        segment_id = uuid.uuid4().hex
        entry = {'request_fingerprint': signature, 'segment_id': segment_id,
            'session_id': session_id, 'request': copy.deepcopy(request), 'status': 'running',
            'steps': [], 'result': None, 'base_revision': scene['revision'], 'end_revision': scene['revision'],
            'host_binding': _binding(scene)}
        if _parent_goal_id is not None:
            entry['parent_goal_id'] = _parent_goal_id
        ledger = value.setdefault('goal_segments', {'schema_version': '1.0', 'records': {}})
        ledger['records'][request_id] = entry
        service._save(value, runtime)
        feature = None
        total_motion = 0.0
        last_plan = None
        last_plan_scene_fingerprint = None
        actual = scene
        last_error = None
        signs = []

        def finish(status, reasons=()):
            elapsed_ns = max(0, time.monotonic_ns() - started_ns)
            result = _result(status, reasons=reasons, request_id=request_id, segment_id=segment_id,
                request=copy.deepcopy(request), steps=copy.deepcopy(entry['steps']),
                base_revision=entry['base_revision'], end_revision=entry['end_revision'],
                residual=copy.deepcopy(last_plan), actual_total_translation_m=total_motion,
                elapsed_s=max(0., clock() - started), replayed=False, historical_receipt=False,
                metrics=_metrics(segment_id, entry['steps'], elapsed_ns, status),
                runtime_identity=service.describe_runtime(),
                executed=(None if status == 'execution_uncertain' else
                    any(step.get('result', {}).get('executed') is True for step in entry['steps'])))
            result['execution_status'] = ('execution_uncertain' if result['executed'] is None else
                'executed_verified' if result['executed'] else 'not_executed')
            result['task_succeeded_scope'] = (
                'requested_original_support_triangle_pair_clearance_at_segment_end'
                if request.get('solver') == 'support_plane'
                else 'requested_box_pair_face_clearance_at_segment_end')
            result['goal_source'] = 'caller_supplied_not_verified_user_intent'
            entry['status'] = status
            entry['result'] = copy.deepcopy(result)
            # Receipts contain no PNG, full scene, or mutable runtime state.
            service._save(value, runtime)
            if include_image and status != 'execution_uncertain':
                try:
                    prepared = runtime._before_model_on_captured_scene(scene=actual, session_id=session_id,
                        task_instruction='Final bounded clearance segment observation.',
                        focal_id=request['focal_id'], reference_id=request['reference_id'],
                        messages=[], format='mcp', include_image=True, supports_images=True)
                    result['routing'] = prepared['routing']
                    result['presentation_scope'] = 'segment_end_snapshot_not_current_after_return'
                except Exception:
                    result['presentation_status'] = 'unavailable'
            service.record_event('clearance_segment', session_id=session_id, segment_id=segment_id,
                status=status, confirmed_steps=sum(step.get('result', {}).get('verified') is True for step in entry['steps']))
            return result

        while True:
            if clock() >= deadline:
                return finish('review_required', ['segment_time_budget_exhausted'])
            if feature is not None:
                scene = _capture(service, runtime)
                if (scene['revision'] != actual['revision']
                        or _fingerprint(scene) != last_plan_scene_fingerprint):
                    return finish('review_required', ['external_scene_change_between_steps'])
            actual = scene
            if _binding(scene) != entry['host_binding']:
                return finish('review_required', ['host_object_or_document_identity_changed'])
            if feature is None:
                last_plan = initial_plan
            # Otherwise last_plan is the previous verified readback's solve
            # with this same private request and feature. The fresh capture
            # above matches its frozen complete input, including capabilities
            # and object identity. It is not a cross-request/action cache.
            if last_plan['goal_satisfied']:
                from .task_verification import evaluate_spatial_goal
                try:
                    evaluation = evaluate_spatial_goal(scene, clearance_segment_goal(request))
                except Exception:
                    return finish('review_required', ['goal_evaluation_unavailable'])
                if evaluation['task_succeeded'] is True:
                    return finish('satisfied')
                return finish('review_required', ['independent_goal_evaluator_not_satisfied'])
            if last_plan['status'] != 'candidate':
                if (last_plan['status'] == 'motion_budget_exhausted'
                        or last_plan['status'] == 'precision_floor'
                        and last_plan.get('effective_motion_budget', {}).get('available')):
                    return finish('review_required', last_plan['reason_codes'])
                return finish('blocked' if not entry['steps'] else 'review_required', last_plan['reason_codes'])
            feature = last_plan['feature_signature']
            if len(entry['steps']) >= request['max_steps']:
                return finish('review_required', ['segment_step_budget_exhausted'])
            # Preserve room for the checked runtime's allowed readback error.
            margin = math.sqrt(3.) * runtime.router.readback_atol_m
            remaining = request['max_total_translation_m'] - total_motion - margin
            step_limit = request['max_step_translation_m'] - margin
            if remaining <= 0 or step_limit <= 0:
                return finish('review_required', ['segment_motion_or_precision_budget_exhausted'])
            bounded = dict(request, max_total_translation_m=min(request['max_total_translation_m'], remaining),
                max_step_translation_m=min(step_limit, remaining))
            if last_plan['proposed_translation_m'] > min(step_limit, remaining):
                last_plan = solve_segment_candidate(scene, bounded, expected_feature_signature=feature)
                if last_plan['status'] != 'candidate':
                    return finish('review_required', last_plan['reason_codes'])
            if last_error is not None and last_plan['absolute_error_m'] >= last_error:
                return finish('review_required', ['segment_stagnation'])
            signs.append(math.copysign(1., last_plan['signed_error_m']))
            if len(signs) >= 3 and signs[-1] == signs[-3] != signs[-2]:
                return finish('review_required', ['segment_oscillation'])
            action = last_plan['candidate']
            prepared = runtime._before_model_on_captured_scene(scene=scene, session_id=session_id,
                task_instruction=('Execute the current bounded original-support-triangle clearance target.'
                    if request.get('solver') == 'support_plane'
                    else 'Execute the current bounded box-face clearance target.'),
                focal_id=request['focal_id'], reference_id=request['reference_id'],
                messages=[], format='mcp', include_image=False, supports_images=False, final_include_image=False)
            if clock() >= deadline:
                return finish('review_required', ['segment_time_budget_exhausted_before_submit'])
            step = {'step_id': uuid.uuid4().hex, 'step_index': len(entry['steps']),
                    'state': 'planned', 'action': copy.deepcopy(action)}
            entry['steps'].append(step)
            try:
                annotate(segment_id=segment_id, step_id=step['step_id'])
            except Exception:
                pass
            before_pivot = _pivot(scene, request['focal_id'])
            result = service._transform_locked(value, runtime, session_id, action,
                clearance_segment_goal(request), prepared=prepared, segment_step=step, segment_id=segment_id,
                precommit_deadline=deadline, precommit_clock=clock,
                parent_deadline=parent_deadline)
            if 'result' not in step:
                record_step_result(step, result)
            if step['state'] == 'uncertain' or result.get('executed') is None:
                return finish('execution_uncertain', ['host_step_outcome_uncertain'])
            if result.get('status') not in {'verified', 'no_op'}:
                return finish('blocked' if not any(s.get('result', {}).get('executed') for s in entry['steps']) else 'review_required',
                    result.get('reason_codes') or [result.get('status', 'step_blocked')])
            actual = runtime._last_verified_scene
            if actual is None:
                return finish('execution_uncertain', ['verified_readback_snapshot_unavailable'])
            motion = math.dist(before_pivot, _pivot(actual, request['focal_id']))
            total_motion += motion
            step['actual_translation_m'] = motion
            entry['end_revision'] = actual['revision']
            last_error = last_plan['absolute_error_m']
            last_plan = solve_segment_candidate(actual, request, expected_feature_signature=feature)
            service._save(value, runtime)
            if total_motion > request['max_total_translation_m'] or motion > request['max_step_translation_m']:
                return finish('review_required', ['actual_motion_budget_exceeded'])
            if _binding(actual) != entry['host_binding']:
                return finish('review_required', ['host_object_or_document_identity_changed'])
            if last_plan['goal_satisfied'] and result.get('goal_evaluation') == 'goal_satisfied':
                return finish('satisfied')
            if last_plan['status'] not in {'candidate', 'goal_satisfied'}:
                return finish('review_required', last_plan['reason_codes'])
            if clock() >= deadline:
                return finish('review_required', ['segment_time_budget_exhausted'])
            # Freeze the content at planning time rather than hashing the
            # mutable runtime snapshot on the next iteration. This also stops
            # an aliased readback being changed together with the next capture.
            # Terminal steps return above, so they pay no extra fingerprint.
            last_plan_scene_fingerprint = _fingerprint(actual)
            # Confirmed but residual remains: only the next fresh capture may
            # authorize a different candidate. Never resend the preceding step.


__all__ = ['run_clearance_segment', 'validate_segment_ledger', 'unfinished_segment',
           'record_step_result', 'MAX_SEGMENT_RECEIPTS']
