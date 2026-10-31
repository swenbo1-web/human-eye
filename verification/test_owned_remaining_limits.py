"""Original owned budgets and remaining facts, using real pure ledger reports.

No Blender/provider is started. Scheduler seams test trusted argument plumbing;
they are not substitutes for release-level owned-host execution evidence.
"""
import copy
from fractions import Fraction
import math
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from human_eye_plugin import goal_supervision as supervision
from human_eye_plugin import goal_scheduler as scheduler
from human_eye_plugin import host_motion_ledger as ledger
from human_eye_plugin.goal_budget import GoalBudgetLimits
from human_eye_plugin.task_authority import ClearanceTaskSpec, TrustedTaskAuthority, TaskApproval
from verification import test_owned_report_validation as fixture
from verification import test_goal_budget as budget_fixture


def promote(report):
    report = copy.deepcopy(report)
    report['coverage'] = {'protocol':fixture.PROTOCOL, 'scope':fixture.OWNED_SCOPE,
        'process_id':fixture.PID, 'generic_code_execution':False, 'ui_attached':False}
    report['scope'] = fixture.OWNED_SCOPE
    report['all_channels_complete'] = not report['closed']
    report['goal_budget_eligible'] = not report['closed']
    report['physical_meter']['complete'] = not report['closed']
    return report


def real_state(motions=(), *, cancelled=0, limits=None, closed=False, goal='goal'):
    limits = limits or GoalBudgetLimits()
    state = {}; binding = fixture.original_binding(); world = [0., 0., 0.]
    fingerprint = '1' * 64
    ledger.begin_goal(state, goal, binding=binding, initial_world=world,
        scene_fingerprint=fingerprint, now=100., limits={
            'max_setters':limits.max_steps, 'max_step_translation_m':limits.max_step_translation_m,
            'max_total_translation_m':limits.max_total_translation_m,
            'max_duration_s':min(30., limits.max_duration_s)})
    for index, amount in enumerate(list(motions) + [None] * cancelled):
        event = 'event-' + str(index)
        target = world[:] if amount is None else [0., 0., world[2] + (-1 if index % 2 else 1) * amount]
        ledger.reserve_setter(state, goal, event, binding=binding,
            before_world=world, requested_world=target, before_scene_fingerprint=fingerprint,
            now=100. + index / 10.)
        if amount is None:
            ledger.cancel_setter(state, goal, event, binding=binding, now=100. + index / 10.)
        else:
            fingerprint = format(index + 2, '064x')
            ledger.confirm_setter(state, goal, event, binding=binding,
                after_world=target, after_scene_fingerprint=fingerprint, now=100. + index / 10.)
            world = target
    if closed:
        ledger.end_goal(state, goal, binding=binding, now=101.)
    return state


def report_for(state, *, cursor=0, goal='goal'):
    return promote(ledger.snapshot(state, goal, after_event_count=cursor))


class OwnedRemainingLimitsTests(unittest.TestCase):
    def check(self, report, limits=None, **kwargs):
        return supervision.validate_owned_motion_report(fixture._Host(report), 'goal', report,
            expected_binding=fixture.original_binding(), expected_limits=limits, **kwargs)

    def test_real_ledger_zero_to_eight_closed_cancelled_suffix_rounding_matrix(self):
        checks = 0
        for amount in (0., math.nextafter(0., 1.), .0001, 2. ** -12, .0009,
                       math.nextafter(.001, 0.), .001):
            for count in range(9):
                for cancelled in {0, 8 - count}:
                    for closed in (False, True):
                        state = real_state([amount] * count, cancelled=cancelled, closed=closed)
                        for cursor in range(count + cancelled + 1):
                            report = report_for(state, cursor=cursor)
                            for _ in range(2):
                                self.assertEqual(self.check(report, GoalBudgetLimits(), closed=closed), report)
                            checks += 1
        self.assertGreater(checks, 1000)

    def test_original_tighter_limits_are_accepted_in_full_suffix_and_close(self):
        limits = GoalBudgetLimits(max_steps=4, max_step_translation_m=.0005,
            max_total_translation_m=.0015)
        for closed in (False, True):
            state = real_state([.0004, .0003], cancelled=1, limits=limits, closed=closed)
            for cursor in range(4):
                self.check(report_for(state, cursor=cursor), limits, closed=closed)

    def test_remaining_types_ranges_and_global_reservation_are_strict(self):
        base = report_for(real_state([.001]))
        for key, bads in (('remaining_setters', (None, True, False, 1., -1, 9, 10 ** 400)),
                ('remaining_translation_m', (None, True, False, -.001, .009, float('nan'),
                    float('inf'), 10 ** 400))):
            for bad in bads:
                with self.subTest(key=key, bad=repr(bad)):
                    report = copy.deepcopy(base); report[key] = bad
                    with self.assertRaises(ValueError):self.check(report)
        report = copy.deepcopy(base); report['remaining_setters'] = 8
        with self.assertRaises(ValueError):self.check(report)

    def test_original_remaining_cannot_be_forged_up_or_down_or_replace_limits(self):
        limits = GoalBudgetLimits(max_steps=4, max_step_translation_m=.0005,
            max_total_translation_m=.002)
        base = report_for(real_state([.0004, .0003], limits=limits))
        for cursor in (0, 1, 2):
            report = copy.deepcopy(base)
            report['physical_meter']['step_motions_m'] = base['physical_meter']['step_motions_m'][cursor:]
            for key, bads in (('remaining_setters', (1, 3, 6)),
                    ('remaining_translation_m', (.0001, .0019, .007))):
                for bad in bads:
                    with self.subTest(cursor=cursor, key=key, bad=bad):
                        changed = copy.deepcopy(report); changed[key] = bad
                        changed['limits'] = {'max_setters':8, 'max_total_translation_m':.008}
                        with self.assertRaises(ValueError):self.check(changed, limits)
        for bad in ({'max_steps':4}, True, NS(max_steps=4)):
            with self.assertRaises(ValueError):self.check(base, bad)

    def test_full_history_enforces_exact_sum_and_floor_even_one_ulp(self):
        report = report_for(real_state([.0009] * 7))
        for key in ('remaining_translation_m', 'actual_cumulative_translation_m'):
            for direction in (0., math.inf):
                changed = copy.deepcopy(report)
                owner = changed if key == 'remaining_translation_m' else changed['physical_meter']
                owner[key] = math.nextafter(owner[key], direction)
                with self.assertRaises(ValueError):self.check(changed, GoalBudgetLimits())

    def test_default_compatibility_does_not_invent_the_original_smaller_cap(self):
        limits = GoalBudgetLimits(max_steps=3, max_total_translation_m=.002)
        report = report_for(real_state([.0005], limits=limits))
        self.check(report)
        with self.assertRaises(ValueError):self.check(report, GoalBudgetLimits())

    def test_actual_path_and_each_motion_obey_original_grant(self):
        report = report_for(real_state([.001]))
        for limits in (GoalBudgetLimits(max_step_translation_m=.0005),
                       GoalBudgetLimits(max_total_translation_m=.0005)):
            with self.assertRaises(ValueError):self.check(report, limits)

    def test_snapshot_remaining_is_independent_of_nearest_cumulative_float(self):
        # This real ledger case has two separately rounded display values.
        state = real_state([.0001] * 7)
        report = report_for(state)
        exact = sum(map(Fraction, report['physical_meter']['step_motions_m']), Fraction())
        self.assertEqual(report['physical_meter']['actual_cumulative_translation_m'], float(exact))
        self.check(report, GoalBudgetLimits())
        self.check(report_for(state, cursor=6), GoalBudgetLimits())


class OwnedRemainingPlumbingTests(unittest.TestCase):
    def test_context_preserves_original_limits_for_every_full_and_suffix_read(self):
        limits = GoalBudgetLimits(max_steps=4, max_total_translation_m=.003)
        state = real_state([.0003, .0002, .0001], limits=limits)
        host = fixture._Host(report_for(state)); host.require_forward_deadline = lambda goal:None
        host.motion_goal_status = lambda goal, after_event_count=0:report_for(state, cursor=after_event_count)
        calls = []
        real = supervision.validate_owned_motion_report
        def checked(*args, **kwargs):
            self.assertIs(kwargs['expected_limits'], limits)
            calls.append(args[2]['physical_meter']['step_motions_m'])
            return real(*args, **kwargs)
        with patch.object(supervision, 'owned_host_counter', return_value={'unit':'counter'}), \
                patch.object(supervision, 'validate_owned_motion_report', side_effect=checked):
            context = supervision.make_owned_host_context(host, 'goal', lambda *args:True,
                expected_binding=fixture.original_binding(), expected_limits=limits)
            entry = {'parent_goal_id':'goal', 'host_binding':fixture.original_binding(), 'steps':[{}]}
            for _ in range(3):
                meter = context.physical_meter('goal', 'child', entry)
                self.assertEqual(len(meter['step_motions_m']), 1)
        self.assertEqual(len(calls), 7)

    def test_scheduler_finish_checks_original_limits_on_both_open_and_closed(self):
        with patch('time.perf_counter', return_value=102.):
            obj, grant, policy, last, budget = fixture.final_fixture()
            seen = []
            original = grant.spec_resolved.limits
            forwarded = []
            real = supervision.validate_owned_motion_report
            def checked(*args, **kwargs):
                self.assertEqual(kwargs['expected_limits'], original)
                forwarded.append(kwargs['expected_limits'])
                seen.append(kwargs.get('closed', False)); return real(*args, **kwargs)
            with patch.object(scheduler, 'validate_owned_motion_report', side_effect=checked):
                result = obj._finish(grant, policy, last, budget, {})
            self.assertTrue(result['task_succeeded']); self.assertEqual(seen, [False, True])
            self.assertIs(forwarded[0], forwarded[1])

    def test_scheduler_bad_remaining_cannot_release_even_at_zero_review(self):
        def zero_receipt(*args, **kwargs):
            kwargs['motions'] = ()
            return budget_fixture.receipt(*args, **kwargs)
        with patch('time.perf_counter', return_value=102.), \
                patch('verification.test_task_authority.receipt', side_effect=zero_receipt), \
                patch('verification.test_task_authority.meter', return_value=budget_fixture.meter(())):
            obj, grant, policy, last, budget = fixture.final_fixture()
            obj.host.report = report_for(real_state(goal=grant.goal_id), goal=grant.goal_id)
            budget = {'confirmed_steps':0, 'actual_total_translation_m':0.}
            obj.host.report['remaining_translation_m'] = .001
            with self.assertRaises(ValueError):obj._finish(grant, policy, last, budget, {})
            self.assertEqual(obj.host.ends, [])

    def test_zero_setter_final_review_still_requires_alive_host_and_original_budget(self):
        def zero_receipt(*args, **kwargs):
            kwargs['motions'] = ()
            return budget_fixture.receipt(*args, **kwargs)
        for fault in ('none', 'dead', 'rollback', 'closed_remaining'):
            with self.subTest(fault=fault), patch('time.perf_counter', return_value=102.), \
                    patch('verification.test_task_authority.receipt', side_effect=zero_receipt), \
                    patch('verification.test_task_authority.meter', return_value=budget_fixture.meter(())):
                obj, grant, policy, last, _ = fixture.final_fixture()
                obj.host.report = report_for(real_state(goal=grant.goal_id), goal=grant.goal_id)
                budget = {'confirmed_steps':0, 'actual_total_translation_m':0.}
                if fault == 'dead':obj.host.is_alive = False
                if fault == 'rollback':obj.host.report['physical_meter']['rollback_count'] = 1
                if fault == 'closed_remaining':
                    obj.host.close_change = lambda value:value.update(remaining_setters=7)
                if fault == 'none':
                    self.assertTrue(obj._finish(grant, policy, last, budget, {})['task_succeeded'])
                else:
                    with self.assertRaises(ValueError):obj._finish(grant, policy, last, budget, {})

    def test_scheduler_registration_context_and_dispatch_read_use_exact_grant(self):
        spec = ClearanceTaskSpec('part', 'base', limits=GoalBudgetLimits(max_steps=4,
            max_total_translation_m=.003))
        capture = {'capture':{'host_identity':{'schema_version':'1.0', 'document_epoch':'a' * 64,
            'object_instances':fixture.original_binding()['object_instances'],
            'capture_scope':'complete_scene_meshes'}}, 'native_scene':{}}
        host = fixture._Host({}); begun = []
        def begin(goal, focal, reference, *, limits):
            begun.append(copy.deepcopy(limits))
            host.report = report_for(real_state(limits=spec.limits, goal=goal), goal=goal)
        host.begin_motion_goal = begin
        obj = scheduler.OwnedGoalScheduler.__new__(scheduler.OwnedGoalScheduler)
        obj.host = host
        obj.service = NS(config={}, _identity_rejection=lambda:None,
            describe_runtime=lambda:{'build_id':'sha256:' + '1' * 64},
            goal_supervision=lambda *args:{'caps':{'max_steps':4,
                'max_step_translation_m':.001, 'max_total_translation_m':.003, 'max_duration_s':30.}})
        obj.authority = TrustedTaskAuthority('unit', lambda *args:TaskApproval('event', 'approval'))
        obj._capture = lambda:copy.deepcopy(capture)
        obj._discover = lambda *args:{'reference_triangle_index':2}
        obj._policy = lambda *args:object()
        obj._claim = lambda grant:{'fresh_claim':True}
        obj._record_stop = lambda grant, result, reason:result
        seen = []; forwarded = []; real = supervision.validate_owned_motion_report
        def checked(*args, **kwargs):
            self.assertEqual(kwargs['expected_limits'], obj._grant.spec_resolved.limits)
            forwarded.append(kwargs['expected_limits'])
            seen.append('read'); return real(*args, **kwargs)
        def context(*args, **kwargs):
            self.assertEqual(kwargs['expected_limits'], obj._grant.spec_resolved.limits)
            forwarded.append(kwargs['expected_limits'])
            seen.append('context')
            return NS(clock_domain=lambda:obj._grant.payload()['scope']['clock_domain'])
        def stop_at_caps(caps, report):
            seen.append('caps'); raise ValueError('unit stop before reservation')
        with patch('time.perf_counter', return_value=100.), \
                patch.object(scheduler, 'owned_host_counter', return_value={'unit':'counter'}), \
                patch.object(scheduler, 'inspect_current_clearance', return_value={'decision':'not_satisfied', 'reason_codes':[]}), \
                patch.object(scheduler, 'validate_owned_motion_report', side_effect=checked), \
                patch.object(scheduler, 'make_owned_host_context', side_effect=context), \
                patch.object(scheduler, '_forward_caps_with_rollback_reserve', side_effect=stop_at_caps):
            result = obj._run(spec)
        self.assertEqual(seen, ['read', 'context', 'read', 'caps'], result)
        self.assertTrue(all(item is forwarded[0] for item in forwarded))
        self.assertEqual(begun[0]['max_setters'], 4)
        self.assertEqual(begun[0]['max_total_translation_m'], .003)

    def test_caps_refuse_bool_and_nine_slots_without_expanding_original_budget(self):
        caps = {'max_steps':8, 'max_step_translation_m':.001,
            'max_total_translation_m':.008, 'max_duration_s':30.}
        for slots in (True, 0, 1, 9, 10 ** 400):
            with self.assertRaises(ValueError):scheduler._forward_caps_with_rollback_reserve(caps,
                {'remaining_setters':slots, 'remaining_translation_m':.008})
        for slots in range(2, 9):
            bounded = scheduler._forward_caps_with_rollback_reserve(caps,
                {'remaining_setters':slots, 'remaining_translation_m':.003})
            self.assertLessEqual(bounded['max_steps'], slots - 1)
            self.assertLessEqual(bounded['max_total_translation_m'] + bounded['max_step_translation_m'], .003)
            self.assertEqual(bounded['max_duration_s'], caps['max_duration_s'])


if __name__ == '__main__':unittest.main()
