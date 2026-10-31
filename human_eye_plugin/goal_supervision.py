"""Private service bridge for durable, bounded goal coordination.

This is not an MCP tool and provides no default automatic execution policy.
The embedding host supplies same-boot monotonic identity, explicit dispatch
authorization and an independent physical meter through Python callbacks.
JSON request fields and child receipts cannot impersonate these capabilities.
All journal changes use the connector's existing lock and atomic state writer.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import math
import time

from . import goal_journal as journal


@dataclass(frozen=True)
class GoalSupervisorContext:
    """Trusted embedding callbacks; constructing this object grants no rights.

    clock_domain() must identify the actual monotonic clock implementation and
    epoch across processes. authorize_dispatch(goal_id, session_id, child_id, request) must
    bind the explicit task, identities, fresh evidence and continuation review.
    physical_meter(goal_id, child_id, child_entry) must cover every actual
    setter including other channels and rollback, bound to this goal/host.
    Callbacks run under the connector lock: no reentry or host mutations.
    """
    clock_domain: object
    authorize_dispatch: object
    physical_meter: object
    clock: object = None
    forward_deadline: object = None

    def __post_init__(self):
        if not all(callable(value) for value in
                   (self.clock_domain, self.authorize_dispatch, self.physical_meter)):
            raise ValueError('Trusted Python supervisor callbacks are required')
        if self.clock is not None and not callable(self.clock):
            raise ValueError('Optional supervisor clock must be a trusted callable')
        if self.forward_deadline is not None and (not callable(self.forward_deadline) or self.clock is None):
            raise ValueError('Forward deadline binding requires an explicit trusted clock')


def _context(service):
    context = service._supervisor_context
    if type(context) is not GoalSupervisorContext:
        raise journal.GoalJournalStopped('trusted_supervisor_context_unavailable')
    return context


def _stamp(context):
    # A local callback, rather than a tool argument, binds the clock epoch.
    return {'clock_domain': context.clock_domain(), 'now': (context.clock or time.monotonic)()}


def update(service, operation, goal_id, session_id=None, *, request_id=None,
           request=None, limits=None):
    """Journal operations only; never dispatch or automatically resend a child."""
    context = _context(service)
    if operation not in {'begin', 'caps', 'reserve', 'reconcile', 'snapshot'}:
        raise ValueError('Unsupported private supervisor operation')
    rejected = service._identity_rejection()
    if rejected is not None:
        return rejected
    if not service.config.get('enabled', True):
        raise journal.GoalJournalStopped('connector_disabled')
    with service._locked() as (value, runtime):
        try:
            stamp = _stamp(context)
            if operation == 'begin':
                if value.get('inflight') or runtime.status['quarantined']:
                    raise journal.GoalJournalStopped('host_quarantined')
                from .goal_execution import unfinished_segment
                if unfinished_segment(value):
                    raise journal.GoalJournalStopped('unfinished_child_requires_review')
                result = journal.create_goal(value, goal_id, session_id,
                    limits=limits, **stamp)
            elif operation == 'caps':
                result = {'caps': journal.next_caps(value, goal_id, **stamp),
                          'execution_authority': False}
            elif operation == 'reserve':
                from .goal_segment import validate_clearance_segment_request
                request = validate_clearance_segment_request(request)
                result = journal.reserve_segment(value, goal_id, request_id, request, **stamp)
            elif operation == 'snapshot':
                result = journal.snapshot(value, goal_id, **stamp)
            else:
                entry = value.get('goal_segments', {}).get('records', {}).get(request_id)
                # Missing/running results are frozen by the journal, without
                # asking the host to infer a path from a net endpoint pose.
                meter = None
                if type(entry) is dict and entry.get('status') != 'running':
                    try:
                        meter = context.physical_meter(goal_id, request_id, copy.deepcopy(entry))
                    except Exception:
                        pass  # An unavailable meter cannot authorize another segment.
                # Include the independently collected evidence's latency and
                # recheck the clock epoch after its callback returns.
                stamp = _stamp(context)
                result = journal.reconcile_child(value, goal_id, request_id,
                                                physical_meter=meter, **stamp)
        except journal.GoalJournalError:
            # Journal failures can deliberately freeze a reservation. Preserve
            # that state before propagating the refusal to the trusted caller.
            service._save(value, runtime)
            raise
        service._save(value, runtime)
        return result


def write_blocker(value, *, parent_goal_id=None, request_id=None, historical=False):
    """Ordinary write routes cannot bypass a pending parent reservation."""
    owner = journal.child_owner(value, request_id) if request_id is not None else None
    if parent_goal_id is not None and owner != parent_goal_id:
        return 'supervised_child_owner_mismatch'
    if historical:
        # Exact request conflict checking still runs in the child core.
        return None
    if 'goal_authorizations' in value:
        from .task_authority import blocking_authorization
        key = blocking_authorization(value)
        if key is not None:
            authority_goal = value['goal_authorizations']['records'][key]['grant']['goal_id']
            if parent_goal_id != authority_goal:
                return 'trusted_task_authorization_requires_review'
    active = journal.blocking_goal(value)
    if parent_goal_id is None:
        if owner is not None or active is not None:
            return 'durable_goal_supervision_requires_review'
    elif active != parent_goal_id:
        return 'supervised_goal_not_active'
    return None


def dispatch_locked(service, value, runtime, goal_id, session_id, request_id, request):
    """Called by the child core after acquiring its one connector lock."""
    context = _context(service)
    if context.authorize_dispatch(goal_id, session_id, request_id, copy.deepcopy(request)) is not True:
        raise journal.GoalJournalStopped('trusted_dispatch_authorization_denied')
    try:
        result = journal.mark_dispatched(value, goal_id, request_id, session_id, request,
                                         **_stamp(context))
    except journal.GoalJournalError:
        service._save(value, runtime)
        raise
    # This must finish before any host call. A crash with no child receipt is
    # deliberately unresolved, never proof that resending is safe.
    service._save(value, runtime)
    return result['deadline_monotonic']


def owned_host_counter(host):
    """Validate the owned route without registering or authorizing a task."""
    from .blender_process import BlenderProcessHost
    if type(host) is not BlenderProcessHost or host._default_worker is not True:
        raise journal.GoalJournalStopped('fixed_owned_typed_host_required')
    from .forward_deadline import PROTOCOL as DEADLINE_PROTOCOL, counter_descriptor
    counter = counter_descriptor()
    capabilities = host.capabilities()
    protocol = 'owned-typed-worker-meter-v1-20261030'
    if (not host.is_alive or capabilities.get('connection') != 'owned_headless_process'
            or capabilities.get('motion_meter_protocol') != protocol
            or capabilities.get('generic_code_execution') is not False
            or capabilities.get('attaches_to_open_window') is not False
            or capabilities.get('process_id') != host._process.pid
            or capabilities.get('forward_deadline_protocol') != DEADLINE_PROTOCOL
            or capabilities.get('forward_deadline_clock') != counter):
        raise journal.GoalJournalStopped('owned_host_meter_capability_unavailable')
    return counter


def owned_clock_domain(document_epoch, counter):
    domain_value = [document_epoch, 'owned-qpc-parent-v1', counter]
    return 'owned-clock:' + hashlib.sha256(json.dumps(domain_value,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def validate_owned_motion_report(host, goal_id, report, *, expected_binding=None,
                                 expected_limits=None, closed=False):
    """Validate fixed-owned-worker facts without granting execution rights.

    The embedding first verifies the exact owned host capability. A closed
    report legitimately loses eligibility/complete flags, but still needs
    known unchanged identities and physical accounting. step_motions_m may
    be a suffix when the caller requested an event cursor. expected_limits is
    the original trusted grant, never a limit reconstructed from this report.
    """
    def require(condition, reason='owned_host_motion_evidence_incomplete'):
        if not condition:
            raise journal.GoalJournalStopped(reason)

    def count(value, maximum=8):
        return type(value) is int and 0 <= value <= maximum

    def number(value):
        try:
            return type(value) in (int, float) and math.isfinite(value) and value >= 0
        except OverflowError:
            return False

    from .goal_budget import GoalBudgetLimits
    require(expected_limits is None or type(expected_limits) is GoalBudgetLimits,
            'owned_host_original_limits_invalid')
    limits = GoalBudgetLimits() if expected_limits is None else expected_limits
    try:
        limits.__post_init__()
    except ValueError as exc:
        raise journal.GoalJournalStopped('owned_host_original_limits_invalid') from exc

    require(type(closed) is bool and type(report) is dict)
    require(host.is_alive is True, 'owned_host_no_longer_alive')
    pid = host._process.pid
    require(type(pid) is int and pid > 0)
    coverage = report.get('coverage')
    physical = report.get('physical_meter')
    require(type(coverage) is dict and type(physical) is dict)
    eligible = not closed
    require(report.get('schema_version') == 'host-motion-ledger-v1'
        and report.get('goal_id') == goal_id
        and report.get('scope') == 'all_legal_setters_of_this_owned_typed_worker'
        and report.get('execution_authority') is False
        and report.get('all_channels_complete') is eligible
        and report.get('goal_budget_eligible') is eligible
        and report.get('registered_events_complete') is True
        and report.get('closed') is closed
        and report.get('frozen_reason') is None
        and type(report.get('unknown_event_count')) is int
        and report['unknown_event_count'] == 0
        and coverage.get('protocol') == 'owned-typed-worker-meter-v1-20261030'
        and coverage.get('scope') == 'all_legal_setters_of_this_owned_typed_worker'
        and type(coverage.get('process_id')) is int and coverage['process_id'] == pid
        and coverage.get('generic_code_execution') is False
        and coverage.get('ui_attached') is False
        and physical.get('complete') is eligible)
    from .host_motion_ledger import _binding
    try:
        binding = _binding(report.get('binding'))
        original = None if expected_binding is None else _binding(expected_binding)
    except ValueError as exc:
        raise journal.GoalJournalStopped('owned_host_binding_invalid') from exc
    require(original is None or binding == original, 'owned_host_original_binding_changed')
    actual = physical.get('actual_setter_count')
    path = physical.get('actual_cumulative_translation_m')
    motions = physical.get('step_motions_m')
    reserved = report.get('reserved_event_count')
    cancelled = report.get('cancelled_before_entry_count')
    remaining = report.get('remaining_setters')
    remaining_path = report.get('remaining_translation_m')
    require(count(actual) and count(reserved) and count(cancelled)
        and reserved == actual + cancelled
        and type(physical.get('rollback_count')) is int and physical['rollback_count'] == 0
        and number(path) and path <= limits.max_total_translation_m
        and type(motions) is list and len(motions) <= actual
        and all(number(value) and value <= limits.max_step_translation_m for value in motions),
        'owned_host_physical_facts_invalid')
    require(count(remaining) and remaining + reserved <= limits.max_steps
        and number(remaining_path) and remaining_path <= limits.max_total_translation_m,
        'owned_host_remaining_facts_invalid')
    if expected_limits is not None:
        require(remaining + reserved == limits.max_steps,
                'owned_host_remaining_setters_disagree')

    cap = Fraction(limits.max_total_translation_m)
    suffix = sum((Fraction(value) for value in motions), Fraction())
    if len(motions) == actual:
        # The ledger rounds the exact binary motion sum once, but floors the
        # exact remainder separately. Subtracting their displayed floats can
        # reject a valid report by one ULP after several setters.
        require(suffix <= cap and float(suffix) == path,
                'owned_host_physical_suffix_disagrees')
        if expected_limits is not None:
            exact_remaining = cap - suffix
            floored = float(exact_remaining)
            if Fraction(floored) > exact_remaining:
                floored = math.nextafter(floored, 0.)
            require(remaining_path == floored, 'owned_host_remaining_path_disagrees')
        else:
            require(suffix + Fraction(remaining_path) <= cap,
                    'owned_host_remaining_path_disagrees')
    else:
        # A cursor omits earlier motions. Bound their possible exact sum by
        # the rounding interval of the cumulative float, the known suffix,
        # and the original per-setter limit. Do not equate suffix and total.
        p = float(path)
        lower = max(Fraction(), (Fraction(math.nextafter(p, -math.inf)) + Fraction(p)) / 2)
        upper = (Fraction(p) + Fraction(math.nextafter(p, math.inf))) / 2
        lower_closed = float(lower) == p
        upper_closed = float(upper) == p

        def bound_low(value, inclusive=True):
            nonlocal lower, lower_closed
            if value > lower:
                lower, lower_closed = value, inclusive
            elif value == lower:
                lower_closed = lower_closed and inclusive

        def bound_high(value, inclusive=True):
            nonlocal upper, upper_closed
            if value < upper:
                upper, upper_closed = value, inclusive
            elif value == upper:
                upper_closed = upper_closed and inclusive

        bound_low(suffix)
        bound_high(suffix + (actual - len(motions)) * Fraction(limits.max_step_translation_m))
        bound_high(cap)
        if expected_limits is not None:
            # floor(cap - exact_sum) == remaining_path. Both underclaims and
            # overclaims must fit this interval; the report supplies no cap.
            bound_low(cap - Fraction(math.nextafter(float(remaining_path), math.inf)), False)
        bound_high(cap - Fraction(remaining_path))
        require(lower < upper or lower == upper and lower_closed and upper_closed,
                'owned_host_remaining_path_disagrees')
    return copy.deepcopy(report)


def make_owned_host_context(host, goal_id, authorize_dispatch, *, expected_binding=None,
                           expected_limits=None):
    """Bind a registered goal to the fixed owned typed Blender worker.

    Its coverage is this isolated worker's legal setters, under trusted local
    code/process assumptions. The callback still owns task and fresh review
    rights. Shared MCP, custom workers and JSON proposals cannot grant them.
    """
    if not callable(authorize_dispatch):
        raise journal.GoalJournalStopped('trusted_dispatch_callback_required')
    from .forward_deadline import make_deadline
    counter = owned_host_counter(host)
    binding = copy.deepcopy(expected_binding)

    def checked_report(cursor=0):
        if not host.is_alive:
            raise journal.GoalJournalStopped('owned_host_no_longer_alive')
        report = host.motion_goal_status(goal_id, after_event_count=cursor)
        return validate_owned_motion_report(host, goal_id, report, expected_binding=binding,
                                            expected_limits=expected_limits)

    initial = checked_report()
    binding = initial['binding']
    host.require_forward_deadline(goal_id)
    # New managed parents start directly on the negotiated common QPC clock.
    # Persisted legacy monotonic parents have a different domain and may not
    # change clocks, reconstruct their start, or acquire another time window.
    domain = owned_clock_domain(binding['document_epoch'], counter)

    def clock_domain():
        if not host.is_alive:
            raise journal.GoalJournalStopped('owned_host_no_longer_alive')
        # A new Blender process/document needs a new context and cannot renew
        # this goal's persisted deadline.
        return domain

    def authorize(parent_id, session_id, child_id, request):
        if (parent_id != goal_id or request.get('focal_id') != binding['focal_id']
                or request.get('reference_id') != binding['reference_id'] or not host.is_alive):
            return False
        return authorize_dispatch(parent_id, session_id, child_id, request) is True

    def physical_meter(parent_id, child_id, entry):
        if parent_id != goal_id or entry.get('parent_goal_id') != goal_id:
            raise journal.GoalJournalStopped('owned_host_goal_binding_mismatch')
        identity = entry.get('host_binding', {})
        if (identity.get('document_epoch') != binding['document_epoch']
                or identity.get('object_instances') != binding['object_instances']):
            raise journal.GoalJournalStopped('owned_host_child_identity_mismatch')
        with host.transaction():
            report = checked_report()
            count = report['physical_meter']['actual_setter_count']
            steps = entry.get('steps')
            if type(steps) is not list or type(count) is not int or count < len(steps):
                raise journal.GoalJournalStopped('owned_host_step_meter_mismatch')
            report = checked_report(count - len(steps))
            if report['binding'] != binding or report['physical_meter']['actual_setter_count'] != count:
                raise journal.GoalJournalStopped('owned_host_evidence_changed_during_meter_read')
            return copy.deepcopy(report['physical_meter'])

    bound_parent = [None]
    def forward_deadline(parent_deadline, step_deadline):
        base = make_deadline(parent_deadline, step_deadline, goal_id=goal_id,
                             binding=binding, process_id=host._process.pid)
        if bound_parent[0] is None:
            host.bind_forward_deadline(base)
            bound_parent[0] = base['parent_deadline_ns']
        elif base['parent_deadline_ns'] != bound_parent[0]:
            raise journal.GoalJournalStopped('owned_parent_deadline_must_not_change')
        return base

    return GoalSupervisorContext(clock_domain, authorize, physical_meter,
                                 clock=time.perf_counter, forward_deadline=forward_deadline)


__all__ = ['GoalSupervisorContext', 'make_owned_host_context',
           'owned_host_counter', 'owned_clock_domain', 'validate_owned_motion_report']
