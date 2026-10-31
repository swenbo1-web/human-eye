"""Provider-free owner bridge for the separate C-autonomous trial branch.

This module is not a model tool or part of the old A/B/C TrialRouter. The
trusted runner freezes one typed intent and original evidence. ``run()`` takes
no proposal, event, permission, path or budget supplied by a model.

The original episode watchdog owns the exact fixed-worker process. It imposes
an outer execution bound; the scheduler retains its own, possibly tighter,
grant deadline. Their numeric deadlines are not claimed to be identical. This
does not yet port the common native/image/compute gateway, so formal eligibility
and common-native parity stay false.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
import hashlib
import json
import math
import re
import threading
import time

from .deadline import DeadlineExceeded, EpisodeDeadline


BRANCH = 'C-autonomous'
SCHEMA = 'owned-autonomous-trial-public-v1'
_BUILD = re.compile(r'^sha256:[0-9a-f]{64}$')


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('utf8')


def _digest(value):
    return hashlib.sha256(_json(value)).hexdigest()


def _copy_spec(spec):
    # Lazy imports keep the old engine-free A/router import path unchanged.
    from human_eye_plugin.goal_budget import GoalBudgetLimits
    from human_eye_plugin.task_authority import ClearanceTaskSpec
    _require(type(spec) is ClearanceTaskSpec, 'trusted_frozen_task_spec_required')
    raw = spec.to_dict()
    return ClearanceTaskSpec(raw['focal_id'], raw['reference_id'],
        raw['target_clearance_m'], raw['clearance_tolerance_m'],
        tuple(raw['direction_world']), raw['reference_triangle_index'],
        GoalBudgetLimits(**raw['limits']))


@dataclass(frozen=True)
class OwnedTaskIntent:
    """Owner-authenticated input; constructing Python objects is trusted code.

    Neither this type nor its JSON spelling is a remote capability. The owner
    must authenticate the task before constructing it. This first bridge keeps
    an explicit original support triangle, rather than guessing authorization
    for a subsequently discovered triangle.
    """
    spec: object
    event_id: str
    authorization_id: str
    read_only: bool = False

    def __post_init__(self):
        from human_eye_plugin.task_authority import TaskApproval
        normalized = _copy_spec(self.spec)
        _require(normalized.reference_triangle_index is not None,
                 'owner_original_triangle_required')
        TaskApproval(self.event_id, self.authorization_id)
        _require(type(self.read_only) is bool, 'owner_read_only_boolean_required')
        object.__setattr__(self, 'spec', normalized)


class OwnedGoalEpisode:
    """One immutable owner registration, one attempt, owner-only raw evidence.

    The runner retains this object and its host. The public surface is the
    return from ``run()``/``public_receipt()``; ``private_snapshot()`` is solely
    for the trusted artifact writer and independent scorer, never model input.
    Cleanup remains the runner's responsibility: close/reap the owned host,
    then call ``close()``, then close the shared EpisodeDeadline.
    """

    def __init__(self, config_path, host, *, task, initial_evidence, deadline,
                 expected_build_id, issuer_id):
        from human_eye_plugin.auto_router import _validated_scene
        from human_eye_plugin.goal_scheduler import OwnedGoalScheduler
        from human_eye_plugin.goal_supervision import owned_clock_domain, owned_host_counter
        from human_eye_plugin.runtime_identity import runtime_identity, check_source_drift
        from human_eye_plugin.task_authority import TaskApproval, TrustedTaskAuthority
        _require(type(task) is OwnedTaskIntent, 'trusted_typed_owner_intent_required')
        _require(type(deadline) is EpisodeDeadline and deadline.clock is time.perf_counter,
                 'original_perf_counter_episode_required')
        _require(deadline.watchdog_active is True, 'original_episode_watchdog_required')
        deadline.check()
        _require(type(expected_build_id) is str and _BUILD.fullmatch(expected_build_id),
                 'exact_expected_build_required')
        identity = runtime_identity(mode='live')
        _require(identity.get('build_id') == expected_build_id
                 and identity.get('source_kind') == 'installed_distribution'
                 and check_source_drift().get('compatible') is True,
                 'frozen_installed_runtime_required')
        counter = owned_host_counter(host)
        _require(type(initial_evidence) is dict
                 and {'capture', 'native_scene'} <= set(initial_evidence),
                 'original_owner_evidence_required')
        capture = _validated_scene(initial_evidence['capture'])[0]
        native = copy.deepcopy(initial_evidence['native_scene'])
        _require(type(native) is dict, 'original_native_object_required')
        # Match the product's exact JSON hash spelling; no numeric rounding.
        _json(native)
        self._task = OwnedTaskIntent(task.spec, task.event_id,
                                     task.authorization_id, task.read_only)
        self._spec = self._task.spec
        self._host = host
        self._process = host._process
        self._pid = self._process.pid
        self._deadline = deadline
        self._original_episode_window = deadline.snapshot()
        self._expected_build_id = expected_build_id
        self._scope = {'engine_build_id': expected_build_id, 'process_id': self._pid,
            'host_identity': copy.deepcopy(capture['host_identity']),
            'reference_triangle_index': self._spec.reference_triangle_index,
            'initial_capture_sha256': _digest(capture),
            'initial_native_sha256': _digest(native),
            'clock_domain': owned_clock_domain(capture['host_identity']['document_epoch'], counter)}
        self._initial = {'capture': copy.deepcopy(capture), 'native_scene': native}
        self._lock = threading.RLock()
        self._revoked = threading.Event()
        self._attempted = False
        self._closed = False
        self._status = 'ready'
        self._raw_result = None
        self._exception = None
        self._approval_events = []
        self._started_perf = None
        self._finished_perf = None
        self._kill_requested = False
        self._kill_error = None
        self._unregister = None

        def approve(resolved, scope):
            # Called before the product issues a grant; both sides of the
            # comparison must still be within the ORIGINAL episode window.
            accepted = False
            reason = 'owner_registration_mismatch'
            try:
                self._check_active()
                _require(self._task.read_only is False, 'owner_task_is_read_only')
                _require(_json(resolved.to_dict()) == _json(self._spec.to_dict())
                         and _json(scope) == _json(self._scope), reason)
                self._check_active()
                accepted = True
            except (ValueError, DeadlineExceeded):
                pass
            self._approval_events.append({'approved': accepted,
                'received_spec': copy.deepcopy(resolved.to_dict()),
                'received_scope': copy.deepcopy(scope),
                'episode_expired_at_callback': self._revoked.is_set()})
            if not accepted:
                return None
            return TaskApproval(self._task.event_id, self._task.authorization_id)

        self._authority = TrustedTaskAuthority(issuer_id, approve)
        self._scheduler = OwnedGoalScheduler(config_path, host, self._authority)
        _require(self._scheduler.service.describe_runtime()['build_id'] == expected_build_id,
                 'scheduler_runtime_changed')
        # Bind after validation; the callback performs no host RPC, lock wait,
        # process wait, filesystem I/O, or action. It never kills another PID.
        self._unregister = deadline.add_expiry_callback(self._expire_owned)
        self._check_active()

    @property
    def bound_deadline(self):
        return self._deadline

    @property
    def deadline_enforced(self):
        return (not self._closed and not self._revoked.is_set()
                and self._deadline.watchdog_active and self._host.is_alive
                and self._host._process is self._process and self._process.pid == self._pid)

    @property
    def uncertain_outcome(self):
        return self._status in ('unknown', 'expired', 'review_required')

    def bind_deadline(self, budget):
        """Compatibility with a future router; renewal/replacement is denied."""
        _require(budget is self._deadline, 'episode_deadline_cannot_be_replaced')
        self._check_active()
        return self

    def _check_active(self):
        _require(not self._closed and not self._revoked.is_set(), 'episode_admission_revoked')
        self._deadline.check()
        _require(self._deadline.watchdog_active is True, 'episode_watchdog_not_active')
        _require(self._host.is_alive and self._host._process is self._process
                 and self._process.pid == self._pid, 'original_owned_process_unavailable')

    def _expire_owned(self):
        # This may run while scheduler.run owns the adapter/host locks. Keep
        # cancellation independent of those locks and defer reaping to owner.
        self._revoked.set()
        self._host._poisoned = True
        if self._process.pid == self._pid and self._process.poll() is None:
            try:
                self._kill_requested = True
                self._process.kill()
            except OSError as exc:
                self._kill_error = type(exc).__name__

    def run(self):
        """Attempt the registered task once; later calls only return history."""
        with self._lock:
            if self._attempted:
                return self._public(historical=True)
            self._attempted = True
            self._started_perf = time.perf_counter()
            try:
                self._check_active()
                if self._task.read_only:
                    self._status = 'refused'
                    self._raw_result = {'task_succeeded': False, 'executed_this_call': False,
                                        'new_setter_count': 0, 'reason_codes': ['owner_read_only_task']}
                else:
                    result = self._scheduler.run(self._spec)
                    _require(type(result) is dict, 'scheduler_result_not_plain_object')
                    self._raw_result = copy.deepcopy(result)
                    if self._revoked.is_set() or self._deadline.expired:
                        self._status = 'expired'
                    elif result.get('historical_receipt') is True or result.get('replayed') is True:
                        # A persisted old task-end receipt is not evidence of
                        # completing this new episode's current scene.
                        self._status = 'historical'
                    elif result.get('task_succeeded') is True:
                        self._status = 'completed'
                    elif result.get('new_setter_count') is None or result.get('executed_this_call') is None:
                        self._status = 'unknown'
                    else:
                        # Every non-success is absorbing even if it is a known
                        # zero-write refusal. Never find a new event to retry.
                        self._status = 'review_required'
            except Exception as exc:
                self._exception = {'type': type(exc).__name__, 'message': str(exc)}
                self._status = 'expired' if self._revoked.is_set() or self._deadline.expired else 'unknown'
            finally:
                self._finished_perf = time.perf_counter()
            return self._public(historical=False)

    def _public(self, *, historical):
        raw = self._raw_result if type(self._raw_result) is dict else {}
        count = raw.get('new_setter_count')
        count = count if type(count) is int and 0 <= count <= self._spec.limits.max_steps else None
        status = 'expired' if self._revoked.is_set() and not self._attempted else self._status
        uncertain = status in ('unknown', 'expired')
        output = {'schema_version': SCHEMA, 'branch': BRANCH, 'status': status,
            'task_succeeded': status == 'completed',
            'historical_receipt': historical or raw.get('historical_receipt') is True,
            'executed_this_call': False if historical else None if uncertain else raw.get('executed_this_call') is True,
            'new_setter_count_this_call': 0 if historical else None if uncertain else count,
            'recorded_task_setter_count': None if uncertain else count,
            'execution_authority': False, 'retry_authorized': False,
            'current_scene_revalidated': False,
            'presentation_scope': 'recorded_task_end_snapshot_not_current_after_return',
            'formal_eligible': False, 'common_native_parity': False, 'provider_requests': 0}
        gap = raw.get('clearance_at_task_end_m')
        if (self._status == 'completed' and type(gap) in (int, float)
                and math.isfinite(gap) and gap >= 0):
            output['recorded_clearance_m'] = float(gap)
        return output

    def public_receipt(self):
        with self._lock:
            return self._public(historical=self._attempted)

    def private_snapshot(self):
        """Owner artifact API. Never place this return in model input/output."""
        with self._lock:
            return copy.deepcopy({'schema_version': 'owned-autonomous-trial-private-v1',
                'branch': BRANCH, 'registered_task': {
                    'spec': self._spec.to_dict(), 'event_id': self._task.event_id,
                    'authorization_id': self._task.authorization_id, 'read_only': self._task.read_only},
                'original_scope': self._scope, 'original_evidence': self._initial,
                'original_episode_window': self._original_episode_window,
                'episode_deadline': self._deadline.snapshot(),
                'authority_events': self._approval_events, 'scheduler_result': self._raw_result,
                'private_exception': self._exception,
                'status': self._public(historical=self._attempted)['status'],
                'started_perf': self._started_perf, 'finished_perf': self._finished_perf,
                'kill_requested': self._kill_requested, 'kill_error': self._kill_error,
                'formal_eligible': False, 'common_native_parity': False,
                'provider_requests': 0,
                'deadline_contract': 'outer_original_episode_watchdog_and_original_inner_grant_minimum_not_numeric_equality',
                'remaining_gates': ['Port common native query/image/compute/write gateway without weakening A',
                    'Shared physical accounting between native and automatic routes before formal trials',
                    'Bind actual provider usage/spend/deadline and hidden paired trial protocol']})

    def close(self):
        """Unregister only after owner closes/reaps the original worker."""
        with self._lock:
            _require(self._process.poll() is not None, 'owned_process_must_be_reaped_before_adapter_close')
            self._closed = True
            if self._unregister is not None:
                self._unregister()
                self._unregister = None


__all__ = ['BRANCH', 'OwnedTaskIntent', 'OwnedGoalEpisode']
