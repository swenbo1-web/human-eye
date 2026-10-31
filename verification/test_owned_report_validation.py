"""Shared owned-report grammar and final-release fault checks, no real host.

The host ledger and durable task/child fixtures exercise real record grammar.
Python doubles inject report/close faults; they are not physical proof.
"""
from contextlib import contextmanager
import copy
import importlib
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from human_eye_plugin import goal_supervision as supervision
from human_eye_plugin import goal_scheduler as scheduler_module
from human_eye_plugin import host_motion_ledger as ledger
from human_eye_plugin import task_authority as authority
from verification.test_goal_continuation import fixture as native_fixture


PID = 1234
PROTOCOL = 'owned-typed-worker-meter-v1-20261030'
OWNED_SCOPE = 'all_legal_setters_of_this_owned_typed_worker'


def original_binding():
    return {'host_epoch':'c' * 32, 'document_epoch':'a' * 64,
        'focal_id':'part', 'reference_id':'base',
        'object_instances':{'part':'part-instance', 'base':'base-instance'}}


def motion_report(goal='goal', *, closed=False, binding=None):
    """Use the real pure host ledger, then mirror fixed-worker promotion."""
    state = {}
    binding = original_binding() if binding is None else copy.deepcopy(binding)
    ledger.begin_goal(state, goal, binding=binding, initial_world=[0.,0.,0.],
        scene_fingerprint='1' * 64, now=100.)
    ledger.reserve_setter(state, goal, 'setter-1', binding=binding,
        before_world=[0.,0.,0.], requested_world=[0.,0.,.001],
        before_scene_fingerprint='1' * 64, now=100.)
    report = ledger.confirm_setter(state, goal, 'setter-1', binding=binding,
        after_world=[0.,0.,.001], after_scene_fingerprint='2' * 64, now=101.)
    if closed:
        report = ledger.end_goal(state, goal, binding=binding, now=101.)
    report['coverage'] = {'protocol':PROTOCOL, 'scope':OWNED_SCOPE,
        'process_id':PID, 'generic_code_execution':False, 'ui_attached':False,
        'external_process_or_modified_worker_proof':False}
    report['registered_source_scope'] = report['scope']
    report['scope'] = OWNED_SCOPE
    report['all_channels_complete'] = not closed
    report['goal_budget_eligible'] = not closed
    report['physical_meter']['complete'] = not closed
    return report


class _Host:
    def __init__(self, report):
        self._process = NS(pid=PID)
        self.is_alive = True
        self.report = copy.deepcopy(report)
        self.ends = []
        self.depth = 0
        self.close_change = None
        self.close_error = None

    @contextmanager
    def transaction(self):
        self.depth += 1
        try:yield self
        finally:self.depth -= 1

    def motion_goal_status(self, goal, after_event_count=0):
        assert self.depth > 0
        return copy.deepcopy(self.report)

    def end_motion_goal(self, goal):
        assert self.depth > 0
        self.ends.append(goal)
        value = copy.deepcopy(self.report)
        value['closed'] = True
        value['all_channels_complete'] = False
        value['goal_budget_eligible'] = False
        value['physical_meter']['complete'] = False
        if self.close_change is not None:self.close_change(value)
        self.report = value
        if self.close_error is not None:raise self.close_error
        return copy.deepcopy(value)


class _Service:
    def __init__(self, value, build, domain):
        self.value = value
        self.runtime = NS(status={'quarantined':False})
        self.build = build
        self.depth = 0
        self.saves = 0
        self._supervisor_context = NS(clock_domain=lambda:domain)
    def _identity_rejection(self):return None
    def describe_runtime(self):return {'build_id':self.build}
    @contextmanager
    def _locked(self):
        self.depth += 1
        try:yield self.value, self.runtime
        finally:self.depth -= 1
    def _save(self, value, runtime):
        assert self.depth > 0
        authority.validate_authorizations(value)
        self.saves += 1


def final_fixture(module=scheduler_module):
    # Import the module, not a TestCase symbol, so broad discovery does not
    # accidentally execute another module's methods a second time.
    grammar = importlib.import_module('verification.test_task_authority')
    pure = grammar.TaskAuthorityTests('test_model_dictionary_cannot_issue_or_claim_a_capability')
    pure.setUp()
    grant = pure.active()
    pure.child(grant)
    _, last, _, _ = native_fixture(True)
    facts = grant.payload()
    last['capture']['host_identity'] = copy.deepcopy(facts['scope']['host_identity'])
    last['capture_confirmation'] = copy.deepcopy(last['capture'])
    report = motion_report(grant.goal_id)
    host = _Host(report)
    service = _Service(pure.value, facts['scope']['engine_build_id'], facts['scope']['clock_domain'])
    obj = module.OwnedGoalScheduler.__new__(module.OwnedGoalScheduler)
    obj.host = host
    obj.service = service
    obj.authority = pure.issuer
    obj._host_binding = copy.deepcopy(report['binding'])
    obj._capture = lambda:copy.deepcopy(last)
    policy = obj._policy(grant.spec_resolved, facts['scope']['engine_build_id'])
    budget = {'confirmed_steps':1, 'actual_total_translation_m':.001}
    return obj, grant, policy, last, budget


def change(path, value):
    def apply(report):
        owner = report
        for key in path[:-1]:owner = owner[key]
        owner[path[-1]] = copy.deepcopy(value)
    return apply


class OwnedReportValidatorTests(unittest.TestCase):
    def setUp(self):
        self.host = _Host(motion_report())
        self.binding = original_binding()

    def check(self, report=None, **kwargs):
        fn = getattr(supervision, 'validate_owned_motion_report', None)
        self.assertTrue(callable(fn), 'Shared validator must exist')
        return fn(self.host, 'goal', self.host.report if report is None else report,
                  expected_binding=self.binding, **kwargs)

    def reject(self, mutations, *, closed=False):
        for label, mutate in mutations:
            value = motion_report(closed=closed)
            mutate(value)
            with self.subTest(fault=label), self.assertRaises((ValueError, TypeError)):
                self.check(value, closed=closed)

    def test_complete_open_and_closed_reports_are_accepted(self):
        for closed in (False, True):
            with self.subTest(closed=closed):self.check(motion_report(closed=closed), closed=closed)

    def test_report_validation_does_not_mutate_input_or_expected_binding(self):
        report = copy.deepcopy(self.host.report); binding = copy.deepcopy(self.binding)
        detached = self.check(report)
        self.assertEqual(report, self.host.report);self.assertEqual(binding, self.binding)
        detached['binding']['object_instances']['part'] = 'not-an-original-instance'
        detached['physical_meter']['step_motions_m'].clear()
        self.assertEqual(report, self.host.report);self.assertEqual(binding, self.binding)

    def test_full_binding_and_goal_are_checked(self):
        self.reject([
            ('goal',change(['goal_id'],'other')),
            ('host_epoch',change(['binding','host_epoch'],'d' * 32)),
            ('document',change(['binding','document_epoch'],'b' * 64)),
            ('instance',change(['binding','object_instances','part'],'different')),
            ('background_instance',change(['binding','object_instances','extra'],'extra-instance')),
            ('roles',change(['binding','focal_id'],'base')),
            ('binding_missing',lambda v:v.pop('binding')),
            ('binding_not_object',change(['binding'],[])),
        ])

    def test_coverage_pid_protocol_scope_and_legal_channel_flags_are_checked(self):
        self.reject([
            ('pid',change(['coverage','process_id'],PID + 1)),
            ('pid_bool',change(['coverage','process_id'],True)),
            ('protocol',change(['coverage','protocol'],'shared-json')),
            ('coverage_scope',change(['coverage','scope'],'registered_only')),
            ('top_scope',change(['scope'],'registered_only')),
            ('generic',change(['coverage','generic_code_execution'],True)),
            ('ui',change(['coverage','ui_attached'],True)),
            ('coverage_missing',lambda v:v.pop('coverage')),
        ])

    def test_unknown_frozen_or_incomplete_open_report_is_rejected(self):
        self.reject([
            ('unknown',change(['unknown_event_count'],1)),
            ('unknown_bool',change(['unknown_event_count'],False)),
            ('frozen',change(['frozen_reason'],'owner-change')),
            ('registered',change(['registered_events_complete'],False)),
            ('complete',change(['all_channels_complete'],False)),
            ('eligible',change(['goal_budget_eligible'],False)),
            ('physical',change(['physical_meter','complete'],False)),
            ('closed',change(['closed'],True)),
        ])

    def test_closed_report_requires_post_close_completeness_semantics(self):
        self.reject([
            ('not_closed',change(['closed'],False)),
            ('all_complete',change(['all_channels_complete'],True)),
            ('eligible',change(['goal_budget_eligible'],True)),
            ('physical_complete',change(['physical_meter','complete'],True)),
            ('unknown',change(['unknown_event_count'],1)),
            ('registered',change(['registered_events_complete'],False)),
        ], closed=True)

    def test_physical_counters_cannot_use_bool_or_nonfinite_motion(self):
        self.reject([
            ('count_bool',change(['physical_meter','actual_setter_count'],True)),
            ('count_negative',change(['physical_meter','actual_setter_count'],-1)),
            ('rollback_bool',change(['physical_meter','rollback_count'],False)),
            ('path_nan',change(['physical_meter','actual_cumulative_translation_m'],float('nan'))),
            ('path_inf',change(['physical_meter','actual_cumulative_translation_m'],float('inf'))),
            ('path_huge_int',change(['physical_meter','actual_cumulative_translation_m'],1 << 4096)),
            ('path_negative',change(['physical_meter','actual_cumulative_translation_m'],-.001)),
            ('step_nan',change(['physical_meter','step_motions_m'],[float('nan')])),
        ])

    def test_suffix_step_meter_is_not_mistaken_for_complete_history(self):
        value = motion_report()
        value['physical_meter']['step_motions_m'] = []
        self.check(value)

    def test_dead_host_is_rejected(self):
        self.host.is_alive = False
        with self.assertRaises((ValueError, TypeError)):self.check()


class SchedulerFinalReportTests(unittest.TestCase):
    def setUp(self):
        self.clock = patch('time.perf_counter', return_value=102.)
        self.clock.start();self.addCleanup(self.clock.stop)

    def finish(self, obj, grant, policy, last, budget):
        return obj._finish(grant, policy, last, budget,
            {'task_succeeded':False,'host_closed':False,'execution_authority':False,'retry_authorized':False})

    def pre_release_reject(self, mutations):
        for label, mutate in mutations:
            obj, grant, policy, last, budget = final_fixture()
            mutate(obj.host.report)
            with self.subTest(fault=label), self.assertRaises((ValueError, TypeError)):
                self.finish(obj, grant, policy, last, budget)
            self.assertEqual(obj.host.ends, [], label)
            self.assertEqual(obj.service.value['goal_authorizations']['records'][grant.key]['status'],'active')

    def test_final_open_goal_and_full_binding_mismatch_cannot_end(self):
        self.pre_release_reject([
            ('goal',change(['goal_id'],'other')),
            ('host_epoch',change(['binding','host_epoch'],'e' * 32)),
            ('instance',change(['binding','object_instances','part'],'replaced')),
            ('background',change(['binding','object_instances','extra'],'new')),
        ])

    def test_final_coverage_mismatch_cannot_end(self):
        self.pre_release_reject([
            ('pid',change(['coverage','process_id'],9999)),
            ('protocol',change(['coverage','protocol'],'wrong')),
            ('scope',change(['coverage','scope'],'registered_only')),
            ('generic',change(['coverage','generic_code_execution'],True)),
            ('ui',change(['coverage','ui_attached'],True)),
            ('eligibility',change(['goal_budget_eligible'],False)),
        ])

    def test_missing_original_registered_binding_cannot_self_attest(self):
        obj, grant, policy, last, budget = final_fixture()
        obj._host_binding = None
        with self.assertRaises((ValueError, TypeError)):
            self.finish(obj, grant, policy, last, budget)
        self.assertEqual(obj.host.ends, [])

    def test_known_meter_mismatch_still_cannot_end(self):
        self.pre_release_reject([
            ('count',change(['physical_meter','actual_setter_count'],2)),
            ('path',change(['physical_meter','actual_cumulative_translation_m'],.0011)),
            ('rollback',change(['physical_meter','rollback_count'],1)),
            ('count_bool',change(['physical_meter','actual_setter_count'],True)),
        ])

    def test_success_accepts_real_closed_flag_semantics_and_records_completion(self):
        obj, grant, policy, last, budget = final_fixture()
        answer = self.finish(obj, grant, policy, last, budget)
        self.assertTrue(answer['task_succeeded']);self.assertTrue(answer['host_closed'])
        self.assertEqual(obj.host.ends,[grant.goal_id])
        self.assertFalse(obj.host.report['physical_meter']['complete'])
        self.assertEqual(obj.service.value['goal_authorizations']['records'][grant.key]['status'],'completed')

    def test_closed_report_identity_or_coverage_lie_never_commits_success(self):
        for label, mutate in [
            ('goal',change(['goal_id'],'other')),
            ('pid',change(['coverage','process_id'],9999)),
            ('protocol',change(['coverage','protocol'],'wrong')),
            ('scope',change(['coverage','scope'],'registered_only')),
            ('host_epoch',change(['binding','host_epoch'],'e' * 32)),
            ('instance',change(['binding','object_instances','part'],'replaced')),
            ('false_live_complete',change(['all_channels_complete'],True)),
        ]:
            obj, grant, policy, last, budget = final_fixture()
            obj.host.close_change = mutate
            with self.subTest(fault=label), self.assertRaises((ValueError, TypeError)):
                self.finish(obj, grant, policy, last, budget)
            self.assertEqual(obj.host.ends,[grant.goal_id])
            self.assertEqual(obj.service.value['goal_authorizations']['records'][grant.key]['status'],'active')

    def test_closed_report_changed_physical_facts_never_commits_success(self):
        for label, mutate in [
            ('count',change(['physical_meter','actual_setter_count'],2)),
            ('path',change(['physical_meter','actual_cumulative_translation_m'],.0011)),
            ('rollback',change(['physical_meter','rollback_count'],1)),
            ('cancelled',change(['cancelled_before_entry_count'],1)),
            ('reserved',change(['reserved_event_count'],2)),
        ]:
            obj, grant, policy, last, budget = final_fixture()
            obj.host.close_change = mutate
            with self.subTest(fault=label), self.assertRaises((ValueError, TypeError)):
                self.finish(obj, grant, policy, last, budget)
            self.assertEqual(obj.host.ends,[grant.goal_id])
            self.assertEqual(obj.service.value['goal_authorizations']['records'][grant.key]['status'],'active')

    def test_lost_close_acknowledgement_stays_frozen_without_retry(self):
        obj, grant, policy, last, budget = final_fixture()
        obj.host.close_error = OSError('simulated close acknowledgement loss')
        result = {'task_succeeded':False,'host_closed':False}
        with self.assertRaises(OSError):self.finish(obj, grant, policy, last, budget)
        obj._record_stop(grant, result, 'OSError:simulated close acknowledgement loss')
        record = obj.service.value['goal_authorizations']['records'][grant.key]
        self.assertEqual(record['status'],'frozen');self.assertFalse(record['result']['host_closed'])
        self.assertEqual(obj.host.ends,[grant.goal_id])
        self.assertEqual(authority.blocking_authorization(obj.service.value),grant.key)

    def test_capture_status_and_end_all_share_host_and_connector_transaction(self):
        obj, grant, policy, last, budget = final_fixture()
        original = obj._capture
        def capture():
            self.assertGreater(obj.host.depth,0);self.assertGreater(obj.service.depth,0)
            return original()
        obj._capture = capture
        self.finish(obj, grant, policy, last, budget)


if __name__ == '__main__':unittest.main()
