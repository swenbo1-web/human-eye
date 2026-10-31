"""Host-local setter facts, without importing Blender or engine receipts."""
import copy
import hashlib
import json
import math
from unittest.mock import patch
import unittest

from human_eye_plugin import host_motion_ledger as ledger


def fp(value):return hashlib.sha256(str(value).encode()).hexdigest()


def binding():
    return {'host_epoch':'a'*32,'document_epoch':'b'*64,'focal_id':'part','reference_id':'base',
            'object_instances':{'part':'instance-part','base':'instance-base'}}


class HostMotionLedgerTests(unittest.TestCase):
    def setUp(self):
        self.state={};self.binding=binding();self.now=100.
        self.start()

    def start(self,**changes):
        args={'binding':self.binding,'initial_world':[0.,0.,0.],
            'scene_fingerprint':fp('initial'),'now':self.now}
        args.update(changes)
        return ledger.begin_goal(self.state,'goal',**args)

    def record(self):return self.state['records']['goal']

    def reserve(self,identity='event-1',motion=.0005,**changes):
        record=self.record();before=record['last_world'][:]
        args={'binding':self.binding,'before_world':before,
            'requested_world':[before[0],before[1],before[2]+motion],
            'before_scene_fingerprint':record['last_scene_fingerprint'],'now':self.now}
        args.update(changes)
        return ledger.reserve_setter(self.state,'goal',identity,**args)

    def confirm(self,identity='event-1',**changes):
        event=next(event for event in self.record()['events'] if event['event_id']==identity)
        args={'binding':self.binding,'after_world':event['requested_world'][:],
            'after_scene_fingerprint':fp(identity),'now':self.now}
        args.update(changes)
        return ledger.confirm_setter(self.state,'goal',identity,**args)

    def write(self,identity='event-1',motion=.0005):
        self.reserve(identity,motion);self.now+=.1
        return self.confirm(identity)

    def assert_loadable(self):
        ledger.validate_ledger(self.state)
        loaded=json.loads(json.dumps(self.state,allow_nan=False))
        ledger.validate_ledger(loaded)
        self.assertEqual(self.state,loaded)

    def test_actual_path_is_independent_of_any_segment_receipt(self):
        self.reserve();self.now+=.1
        report=self.confirm(after_world=[0,0,.00050001])
        self.assertEqual(report['physical_meter']['actual_setter_count'],1)
        self.assertEqual(report['physical_meter']['actual_cumulative_translation_m'],.00050001)
        self.assertEqual(report['physical_meter']['step_motions_m'],[.00050001])
        self.assertTrue(report['registered_events_complete'])
        self.assert_loadable()

    def test_complete_is_never_promoted_by_registered_facts(self):
        report=self.write()
        self.assertFalse(report['physical_meter']['complete'])
        self.assertFalse(report['all_channels_complete'])
        self.assertFalse(report['goal_budget_eligible'])
        self.assertFalse(report['external_ABA_detection'])
        self.assertFalse(report['execution_authority'])

    def test_duplicate_reservation_returns_history_and_never_new_permission(self):
        self.write();self.now+=5
        result=self.reserve(before_world=[0,0,0],requested_world=[0,0,.0005],
                            before_scene_fingerprint=fp('initial'))
        self.assertFalse(result['fresh_reservation'])
        self.assertEqual(len(self.record()['events']),1)
        self.assertFalse(result['execution_authority'])

    def test_pending_attempt_cannot_be_retried(self):
        self.reserve()
        with self.assertRaises(ledger.HostMotionStopped):self.reserve()
        self.assertEqual(len(self.record()['events']),1)
        self.assertIsNotNone(self.record()['frozen_reason'])
        self.assert_loadable()

    def test_duplicate_confirmation_is_idempotent(self):
        self.write();before=copy.deepcopy(self.record()['events'])
        self.now+=100
        result=self.confirm()
        self.assertEqual(result['physical_meter']['actual_setter_count'],1)
        self.assertEqual(before,self.record()['events'])

    def test_confirmation_conflict_freezes_without_replacing_actual_facts(self):
        self.write();before=copy.deepcopy(self.record()['events'])
        with self.assertRaises(ledger.HostMotionStopped):self.confirm(after_world=[0,0,.0006])
        self.assertEqual(before,self.record()['events'])
        self.assert_loadable()

    def test_identity_conflict_freezes_and_keeps_deadline(self):
        self.write();deadline=self.record()['deadline_monotonic']
        with self.assertRaises(ledger.HostMotionStopped):self.start(initial_world=[0,0,1.])
        self.assertEqual(self.record()['deadline_monotonic'],deadline)
        self.assert_loadable()

    def test_begin_same_goal_does_not_renew_time(self):
        self.now+=20
        report=self.start()
        self.assertEqual(report['started_monotonic'],100.)
        self.assertEqual(report['deadline_monotonic'],130.)
        self.assertEqual(report['remaining_duration_s'],10.)

    def test_new_goal_id_cannot_reset_open_budget(self):
        self.write()
        with self.assertRaises(ledger.HostMotionStopped):
            ledger.begin_goal(self.state,'replacement',binding=self.binding,initial_world=[0,0,.0005],
                scene_fingerprint=fp('current'),now=self.now)
        self.assertEqual(len(self.state['records']),1)

    def test_host_epoch_change_cannot_resume_or_start_replacement(self):
        changed=copy.deepcopy(self.binding);changed['host_epoch']='c'*32
        with self.assertRaises(ledger.HostMotionStopped):self.reserve(binding=changed)
        self.assert_loadable()
        with self.assertRaises(ledger.HostMotionStopped):
            ledger.begin_goal(self.state,'replacement',binding=changed,initial_world=[0,0,0],
                scene_fingerprint=fp('initial'),now=self.now)

    def test_closed_history_rejects_host_epoch_reuse(self):
        ledger.end_goal(self.state,'goal',binding=self.binding,now=self.now)
        changed=copy.deepcopy(self.binding);changed['host_epoch']='c'*32
        with self.assertRaises(ledger.HostMotionStopped):
            ledger.begin_goal(self.state,'replacement',binding=changed,initial_world=[0,0,0],
                scene_fingerprint=fp('initial'),now=self.now)
        self.assert_loadable()

    def test_document_and_object_incarnation_changes_freeze(self):
        for field in ('document_epoch','object_instances'):
            self.setUp();changed=copy.deepcopy(self.binding)
            changed[field]='c'*64 if field=='document_epoch' else {'part':'new','base':'instance-base'}
            with self.assertRaises(ledger.HostMotionStopped):self.reserve(binding=changed)
            self.assert_loadable()

    def test_clock_backwards_freezes_without_backdating(self):
        self.now=99.
        with self.assertRaises(ledger.HostMotionStopped):self.reserve()
        self.assertEqual(self.record()['last_seen_monotonic'],100.)
        self.assert_loadable()

    def test_deadline_prevents_new_forward_registration(self):
        self.now=130.
        with self.assertRaises(ledger.HostMotionStopped):self.reserve()
        self.assertEqual(len(self.record()['events']),0)

    def test_late_confirmation_accounts_actual_fact_and_freezes(self):
        self.reserve();self.now=131.
        result=self.confirm()
        self.assertEqual(result['physical_meter']['actual_setter_count'],1)
        self.assertEqual(result['physical_meter']['actual_cumulative_translation_m'],.0005)
        self.assertEqual(result['frozen_reason'],'setter_confirmation_after_deadline')
        self.assertFalse(result['registered_events_complete'])
        self.assert_loadable()

    def test_actual_step_over_cap_is_not_clipped(self):
        self.reserve();self.now+=.1
        result=self.confirm(after_world=[0,0,.00101])
        self.assertEqual(result['physical_meter']['actual_cumulative_translation_m'],.00101)
        self.assertEqual(result['frozen_reason'],'actual_step_cap_exceeded')
        self.assert_loadable()

    def test_actual_total_over_cap_is_retained(self):
        self.state={};self.start(limits={'max_total_translation_m':.0005})
        self.reserve();self.now+=.1
        result=self.confirm(after_world=[0,0,.000500001])
        self.assertEqual(result['frozen_reason'],'actual_total_cap_exceeded')
        self.assertGreater(result['physical_meter']['actual_cumulative_translation_m'],.0005)
        self.assert_loadable()

    def test_requested_motion_over_cap_never_reserves(self):
        with self.assertRaises(ledger.HostMotionStopped):self.reserve(motion=.00101)
        self.assertEqual(len(self.record()['events']),0)

    def test_requested_off_axis_motion_never_reserves(self):
        with self.assertRaises(ledger.HostMotionStopped):self.reserve(requested_world=[.0001,0,.0001])
        self.assertEqual(len(self.record()['events']),0)

    def test_actual_off_axis_motion_is_accounted_but_frozen(self):
        self.reserve();self.now+=.1
        result=self.confirm(after_world=[.000001,0,.0005])
        self.assertEqual(result['physical_meter']['actual_cumulative_translation_m'],math.hypot(.000001,.0005))
        self.assertIsNotNone(result['frozen_reason'])
        self.assert_loadable()

    def test_external_scene_change_freezes_even_with_same_pivot(self):
        with self.assertRaises(ledger.HostMotionStopped):
            ledger.observe_scene(self.state,'goal',binding=self.binding,world_position=[0,0,0],
                scene_fingerprint=fp('changed'),now=self.now)
        self.assertFalse(ledger.snapshot(self.state,'goal')['registered_events_complete'])
        self.assert_loadable()

    def test_unknown_attempt_retained_without_zero_write_claim(self):
        self.reserve()
        with self.assertRaises(ledger.HostMotionStopped):ledger.mark_unknown(self.state,'goal',event_id='event-1')
        report=ledger.snapshot(self.state,'goal')
        self.assertEqual(report['reserved_event_count'],1)
        self.assertEqual(report['unknown_event_count'],1)
        self.assertFalse(report['physical_meter']['complete'])
        with self.assertRaises(ledger.HostMotionStopped):self.confirm()
        self.assert_loadable()

    def test_known_rollback_counts_both_setters_and_full_path(self):
        self.write();self.now+=.1
        self.reserve('rollback',motion=-.0005,kind='rollback')
        self.now+=.1
        result=self.confirm('rollback')
        self.assertEqual(result['physical_meter']['actual_setter_count'],2)
        self.assertEqual(result['physical_meter']['actual_cumulative_translation_m'],.001)
        self.assertEqual(result['physical_meter']['rollback_count'],1)
        self.assertFalse(result['registered_events_complete'])
        self.assertEqual(self.record()['last_world'],[0,0,0])
        self.assert_loadable()

    def test_rollback_keeps_unknown_forward_event_and_never_recovers_complete(self):
        self.reserve()
        with self.assertRaises(ledger.HostMotionStopped):ledger.mark_unknown(self.state,'goal',event_id='event-1')
        self.now+=.1
        self.reserve('rollback',kind='rollback',before_world=[0,0,.0004],requested_world=[0,0,0],
            before_scene_fingerprint=fp('partially-mutated'))
        self.now+=.1
        report=self.confirm('rollback')
        self.assertEqual(report['unknown_event_count'],1)
        self.assertEqual(report['physical_meter']['actual_setter_count'],1)
        self.assertEqual(report['physical_meter']['actual_cumulative_translation_m'],.0004)
        self.assertEqual(len(self.record()['events']),2)
        self.assertFalse(report['registered_events_complete'])
        self.assert_loadable()

    def test_zero_distance_setter_still_counts(self):
        self.reserve(motion=0);self.now+=.1
        report=self.confirm(after_scene_fingerprint=fp('initial'))
        self.assertEqual(report['physical_meter']['actual_setter_count'],1)
        self.assertEqual(report['physical_meter']['step_motions_m'],[0.])
        self.assertEqual(report['remaining_setters'],7)

    def test_eighth_event_blocks_ninth_and_never_evicts(self):
        for i in range(8):self.write('event-'+str(i),motion=.00001)
        before=copy.deepcopy(self.record()['events'])
        with self.assertRaises(ledger.HostMotionStopped):self.reserve('ninth',motion=.00001)
        self.assertEqual(before,self.record()['events'])
        self.assert_loadable()

    def test_close_requires_confirmed_unfrozen_scope(self):
        self.reserve()
        with self.assertRaises(ledger.HostMotionStopped):ledger.end_goal(self.state,'goal',binding=self.binding,now=self.now)
        self.assertFalse(self.record()['closed'])

    def test_close_is_not_goal_completion_claim(self):
        self.write()
        report=ledger.end_goal(self.state,'goal',binding=self.binding,now=self.now)
        self.assertTrue(report['closed'])
        self.assertNotIn('task_succeeded',report)
        self.assertFalse(report['goal_budget_eligible'])

    def test_closed_goal_accepts_historical_reads_but_no_new_event(self):
        self.write();ledger.end_goal(self.state,'goal',binding=self.binding,now=self.now)
        self.assertTrue(ledger.snapshot(self.state,'goal')['closed'])
        with self.assertRaises(ledger.HostMotionStopped):self.reserve('new-event')
        with self.assertRaises(ledger.HostMotionStopped):self.start(initial_world=[1,0,0])
        self.assert_loadable()

    def test_event_cursor_returns_only_subsequent_confirmed_paths(self):
        self.write('first',motion=.0002);self.write('second',motion=.0003)
        report=ledger.snapshot(self.state,'goal',after_event_count=1)
        self.assertEqual(report['physical_meter']['actual_setter_count'],2)
        self.assertEqual(len(report['physical_meter']['step_motions_m']),1)
        self.assertEqual(report['physical_meter']['step_motions_m'][0],self.record()['events'][1]['actual_translation_m'])

    def test_invalid_cursor_and_boolean_numbers_refused(self):
        for cursor in (-1,True,1,1.0):
            with self.assertRaises(ledger.HostMotionError):ledger.snapshot(self.state,'goal',after_event_count=cursor)
        for point in ([True,0,0],[0,math.inf,0],[0,math.nan,0],(0,0,0)):
            with self.assertRaises(ledger.HostMotionError):self.reserve(before_world=point)

    def test_state_reload_detects_cache_and_event_tampering(self):
        self.write()
        for mutate in (
            lambda s:s['records']['goal'].__setitem__('deadline_monotonic',200.),
            lambda s:s['records']['goal'].__setitem__('last_world',[0,0,.002]),
            lambda s:s['records']['goal']['events'][0].__setitem__('actual_translation_m',.0001),
            lambda s:s['records']['goal'].__setitem__('remaining_setters',8)):
            altered=copy.deepcopy(self.state);mutate(altered)
            with self.assertRaises(ledger.HostMotionError):ledger.validate_ledger(altered)

    def test_limits_only_tighten_host_hard_caps(self):
        for limits in ({'max_setters':9},{'max_setters':True},{'max_step_translation_m':.002},
            {'max_total_translation_m':.009},{'max_duration_s':31},{'unknown':1}):
            with self.assertRaises(ledger.HostMotionError):
                ledger.begin_goal({},'other',binding=self.binding,initial_world=[0,0,0],
                    scene_fingerprint=fp('i'),now=100.,limits=limits)

    def test_state_and_report_are_detached_from_caller_data(self):
        self.binding['object_instances']['part']='mutated-caller'
        report=ledger.snapshot(self.state,'goal')
        self.assertEqual(report['binding']['object_instances']['part'],'instance-part')
        report['binding']['object_instances']['part']='mutated-report'
        self.assertEqual(self.record()['binding']['object_instances']['part'],'instance-part')

    def test_host_capacity_has_no_automatic_history_eviction(self):
        ledger.end_goal(self.state,'goal',binding=self.binding,now=self.now)
        with patch.object(ledger,'MAX_GOALS',1):
            with self.assertRaises(ledger.HostMotionStopped):
                ledger.begin_goal(self.state,'other',binding=self.binding,initial_world=[0,0,0],
                    scene_fingerprint=fp('i'),now=self.now)
        self.assertEqual(list(self.state['records']),['goal'])

    def test_loaded_boolean_deadline_and_endpoint_cache_are_refused(self):
        self.state={};self.now=0.;self.start(limits={'max_duration_s':1.})
        for field,value in (('deadline_monotonic',True),('last_world',[False,0,0])):
            altered=copy.deepcopy(self.state);altered['records']['goal'][field]=value
            with self.assertRaises(ledger.HostMotionError):ledger.validate_ledger(altered)

    def test_late_fact_cannot_be_loaded_without_freeze(self):
        self.reserve();self.now=131.;self.confirm()
        self.record()['frozen_reason']=None
        with self.assertRaises(ledger.HostMotionError):ledger.validate_ledger(self.state)

    def test_rollback_cannot_be_loaded_without_freeze(self):
        self.write();self.reserve('rollback',motion=-.0005,kind='rollback');self.now+=.1
        self.confirm('rollback');self.record()['frozen_reason']=None
        with self.assertRaises(ledger.HostMotionError):ledger.validate_ledger(self.state)

    def test_timestamp_capacity_failure_keeps_state_loadable(self):
        cap=len(ledger._encoded(self.state))
        self.now=1e10
        with patch.object(ledger,'MAX_BYTES',cap):
            with self.assertRaises(ledger.HostMotionStopped):self.reserve()
            ledger.validate_ledger(self.state)
            self.assertEqual(self.record()['last_seen_monotonic'],100.)
        self.assert_loadable()

    def test_reservation_capacity_failure_publishes_no_partial_event(self):
        cap=len(ledger._encoded(self.state))+50
        with patch.object(ledger,'MAX_BYTES',cap):
            with self.assertRaises(ledger.HostMotionError):self.reserve()
            ledger.validate_ledger(self.state)
        self.assertEqual(len(self.record()['events']),0)
        self.assert_loadable()

    def test_loaded_unrepresentable_clock_window_is_refused(self):
        record=self.record();record['started_monotonic']=1e100
        record['deadline_monotonic']=1e100;record['last_seen_monotonic']=1e100
        with self.assertRaises(ledger.HostMotionError):ledger.validate_ledger(self.state)


if __name__=='__main__':unittest.main()
