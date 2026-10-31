"""Independent pure contracts for episode-wide physical entry accounting.

Raw geometry comes from the existing Blender-host doubles. No Blender process,
provider, GUI or production connector is used. These tests do not certify real
native rendering or the worker's exclusive coverage claim.
"""
from __future__ import annotations

import copy
from fractions import Fraction
import hashlib
import json
import time
import unittest

from verification.test_blender_native_evidence import fixture
from human_eye_plugin import episode_gateway as gateway


def digest_native(native):
    native['revision']='native:'+hashlib.sha256(json.dumps(native['objects'],
        sort_keys=True,separators=(',', ':'),ensure_ascii=True,allow_nan=False).encode()).hexdigest()
    return native


def translated(native,focal_id,dz):
    value=copy.deepcopy(native)
    obj=next(v for v in value['objects'] if v['object_id']==focal_id)
    old=obj['matrix'][2][3]
    obj['matrix'][2][3]=old+dz
    # Match the native evidence's binary64 original local-to-world forward map.
    obj['world_vertices']=[[sum(obj['matrix'][r][k]*v[k] for k in range(3))+obj['matrix'][r][3]
                            for r in range(3)] for v in obj['local_vertices']]
    return digest_native(value)


class EpisodeGatewayTests(unittest.TestCase):
    def setUp(self):
        host,part,base,_=fixture()
        packet=host.capture_evidence()
        self.native=packet['native_scene']
        self.focal=host.object_id(part);self.reference=host.object_id(base)
        self.binding=host._motion_binding(packet['capture'],self.focal,self.reference)
        self.store={};self.now=1_000_000_000;self.deadline=9_000_000_000

    def begin(self,**changes):
        args=dict(episode_id='episode-one',binding=self.binding,initial_native=self.native,
                  deadline_ns=self.deadline,now_ns=self.now)
        args.update(changes)
        return gateway.begin_episode(self.store,**args)

    def snapshot(self):return gateway.snapshot(self.store)

    def reserve(self,before=None,dz=.0005,**changes):
        before=self.native if before is None else before
        obj=next(v for v in before['objects'] if v['object_id']==self.focal)
        target=[obj['matrix'][i][3] for i in range(3)];target[2]+=dz
        args=dict(helper='_assign_translation',object_id=self.focal,requested_world=target,
                  before_native=before,binding=self.binding,now_ns=self.now+1,kind='forward')
        args.update(changes)
        return gateway.reserve_setter(self.store,**args)

    def confirmed(self,before=None,dz=.0005,**reserve_changes):
        before=self.native if before is None else before
        index=self.reserve(before,dz,**reserve_changes)
        after=translated(before,self.focal,dz)
        gateway.confirm_setter(self.store,index,after_native=after,now_ns=self.now+2)
        return after,index

    def test_initial_report_is_private_non_authorizing_and_detached(self):
        self.begin();report=self.snapshot()
        self.assertEqual(report['episode_id'],'episode-one')
        self.assertEqual(report['deadline_ns'],self.deadline)
        self.assertEqual(report['binding'],self.binding)
        self.assertEqual(report['actual_setter_count'],0)
        self.assertEqual(report['reserved_event_count'],0)
        self.assertEqual(report['remaining_setters'],8)
        report['binding']['object_instances'].clear()
        report['limits']['max_setters']=99
        self.assertEqual(self.snapshot()['binding'],self.binding)
        self.assertEqual(self.snapshot()['remaining_setters'],8)
        self.assertNotEqual(self.snapshot().get('execution_authority'),True)

    def test_native_and_automatic_helper_entries_share_one_ordered_meter(self):
        self.begin();current=self.native
        for helper in ('native_transform','_assign_translation','_assign_matrix'):
            self.now+=10
            current,index=self.confirmed(current,helper=helper)
        report=self.snapshot()
        self.assertEqual(report['actual_setter_count'],3)
        self.assertEqual(report['reserved_event_count'],3)
        self.assertEqual(report['remaining_setters'],5)
        self.assertEqual(len(report['events']),3)
        self.assertEqual(report['unknown_event_count'],0)
        actual=abs(next(v for v in current['objects'] if v['object_id']==self.focal)['matrix'][2][3]-4.)
        self.assertEqual(report['actual_cumulative_translation_m'],actual)

    def test_rebind_cannot_reset_spend_or_extend_original_deadline(self):
        self.begin();self.confirmed();original=self.snapshot()
        for changes in ({'episode_id':'new-episode'}, {'deadline_ns':self.deadline+1},
                        {'limits':{'max_setters':7}}, {'read_only':True}):
            with self.subTest(changes=changes):
                with self.assertRaises(Exception):self.begin(**changes)
                report=self.snapshot()
                self.assertEqual(report['actual_setter_count'],1)
                self.assertEqual(report['reserved_event_count'],1)
                self.assertEqual(report['deadline_ns'],original['deadline_ns'])

    def test_strict_limits_reject_boolean_nonfinite_and_expansion(self):
        cases=[{'max_setters':True},{'max_setters':9},{'max_setters':0},
               {'max_step_translation_m':float('nan')},{'max_step_translation_m':float('inf')},
               {'max_step_translation_m':.0010001},{'max_total_translation_m':.0080001},
               {'max_total_translation_m':-1.},{'unexpected':'control'}]
        for limits in cases:
            with self.subTest(limits=limits):
                self.store={}
                with self.assertRaises(Exception):self.begin(limits=limits)
                self.assertFalse(self.store)

    def test_strict_absolute_clock_and_maximum_window(self):
        for changes in ({'now_ns':True},{'deadline_ns':True},{'deadline_ns':self.now},
                        {'deadline_ns':self.now+180_000_000_001}):
            with self.subTest(changes=changes):
                self.store={}
                with self.assertRaises(Exception):self.begin(**changes)
                self.assertFalse(self.store)

    def test_readonly_refuses_before_any_entry(self):
        self.begin(read_only=True)
        with self.assertRaises(gateway.EpisodePrewriteRefused):self.reserve()
        report=self.snapshot()
        self.assertEqual(report['events'],[])
        self.assertEqual(report['actual_setter_count'],0)
        self.assertEqual(report['reserved_event_count'],0)

    def test_expired_clock_refuses_before_any_entry(self):
        self.begin()
        with self.assertRaises(gateway.EpisodePrewriteRefused):self.reserve(now_ns=self.deadline)
        self.assertEqual(self.snapshot()['reserved_event_count'],0)
        self.assertEqual(self.snapshot()['actual_setter_count'],0)

    def test_requested_xy_wrong_object_and_over_step_refuse_before_entry(self):
        self.begin()
        for changes in ({'requested_world':[2.0001,3.,4.]},{'object_id':self.reference},
                        {'requested_world':[2.,3.,4.002]}):
            with self.subTest(changes=changes):
                with self.assertRaises(gateway.EpisodePrewriteRefused):self.reserve(**changes)
                self.assertEqual(self.snapshot()['reserved_event_count'],0)

    def test_forward_capacity_keeps_one_original_rollback_slot(self):
        self.begin(limits={'max_setters':2})
        current,_=self.confirmed()
        self.now+=10
        with self.assertRaises(gateway.EpisodePrewriteRefused):self.reserve(current)
        report=self.snapshot()
        self.assertEqual(report['actual_setter_count'],1)
        self.assertEqual(report['reserved_event_count'],1)
        self.assertEqual(report['remaining_setters'],1)

    def test_forward_capacity_keeps_original_return_path(self):
        self.begin(limits={'max_total_translation_m':.0011})
        current,_=self.confirmed()
        self.now+=10
        with self.assertRaises(gateway.EpisodePrewriteRefused):self.reserve(current)
        report=self.snapshot()
        self.assertEqual(report['actual_setter_count'],1)
        self.assertLessEqual(report['actual_cumulative_translation_m'],.0011)

    def test_unknown_entry_never_becomes_false_zero_or_all_complete(self):
        self.begin();index=self.reserve()
        gateway.mark_unknown(self.store,index,'lost_actual_readback')
        report=self.snapshot()
        self.assertEqual(report['unknown_event_count'],1)
        self.assertEqual(report['reserved_event_count'],1)
        self.assertIsNotNone(report['frozen_reason'])
        self.assertNotEqual(report.get('all_channels_complete'),True)
        before=copy.deepcopy(report)
        with self.assertRaises(Exception):self.reserve()
        self.assertEqual(self.snapshot()['reserved_event_count'],before['reserved_event_count'])
        self.assertEqual(self.snapshot()['unknown_event_count'],1)

    def test_binding_change_freezes_and_does_not_allow_a_new_entry(self):
        self.begin()
        for key,value in [('host_epoch','b'*32),('document_epoch','c'*64)]:
            changed=copy.deepcopy(self.binding);changed[key]=value
            with self.subTest(key=key):
                with self.assertRaises(Exception):self.reserve(binding=changed)
                self.assertEqual(self.snapshot()['reserved_event_count'],0)
        self.assertIsNotNone(self.snapshot()['frozen_reason'])

    def test_external_native_scene_change_is_not_a_fresh_budget_baseline(self):
        self.begin();external=translated(self.native,self.focal,.0001)
        with self.assertRaises(Exception):self.reserve(external)
        self.assertEqual(self.snapshot()['reserved_event_count'],0)
        self.assertIsNotNone(self.snapshot()['frozen_reason'])

    def test_final_native_invariants_detect_nonfocal_change(self):
        self.begin();index=self.reserve();after=translated(self.native,self.focal,.0005)
        other=next(v for v in after['objects'] if v['object_id']==self.reference)
        other['color'][0]+=.01;digest_native(after)
        with self.assertRaises(Exception):gateway.confirm_setter(self.store,index,after_native=after,now_ns=self.now+2)
        self.assertIsNotNone(self.snapshot()['frozen_reason'])
        with self.assertRaises(Exception):self.reserve(after)

    def test_actual_quantization_exceeding_original_cap_freezes(self):
        self.begin();index=self.reserve(dz=.0009)
        after=translated(self.native,self.focal,.0011)
        with self.assertRaises(Exception):gateway.confirm_setter(self.store,index,after_native=after,now_ns=self.now+2)
        report=self.snapshot()
        self.assertIsNotNone(report['frozen_reason'])
        self.assertEqual(report['reserved_event_count'],1)
        with self.assertRaises(Exception):self.reserve(after)

    def test_cursor_returns_trace_suffix_without_refilling_total(self):
        self.begin();current,_=self.confirmed();self.now+=10;self.confirmed(current)
        full=self.snapshot();suffix=gateway.snapshot(self.store,after_event_count=1)
        self.assertEqual(len(full['events']),2)
        self.assertEqual(len(suffix['events']),1)
        for key in ('actual_setter_count','reserved_event_count','remaining_setters',
                    'actual_cumulative_translation_m','remaining_translation_m'):
            self.assertEqual(suffix[key],full[key])
        self.assertLessEqual(Fraction(full['actual_cumulative_translation_m'])+
                             Fraction(full['remaining_translation_m']),Fraction(.008))

    def test_final_entry_gate_cancels_reservation_after_original_deadline(self):
        self.begin();index=self.reserve()
        with self.assertRaises(gateway.EpisodePrewriteRefused):
            gateway.enter_setter(self.store,index,now_ns=self.deadline)
        report=self.snapshot()
        self.assertEqual(report['reserved_event_count'],1)
        self.assertEqual(report['actual_setter_count'],0)
        self.assertEqual(report['unknown_event_count'],0)
        self.assertEqual(report['events'][0]['state'],'cancelled_before_entry')
        self.assertEqual(report['events'][0]['before_native'],report['events'][0]['after_native'])
        with self.assertRaises(Exception):gateway.enter_setter(self.store,index,now_ns=self.deadline-1)
        self.assertEqual(self.snapshot()['actual_setter_count'],0)


class EpisodeHostHookTests(unittest.TestCase):
    def setUp(self):
        self.host,self.part,self.base,_=fixture()
        self.pair={'focal_id':self.host.object_id(self.part),'reference_id':self.host.object_id(self.base)}
        self.initial=self.host.capture_evidence()
        self.host.begin_owned_episode('episode-host-hook',**self.pair,
            deadline_ns=time.perf_counter_ns()+10_000_000_000)

    def move(self,amount=.0005):
        before=self.host.capture_scene()
        return self.host.apply_transform({**self.pair,'translation':[0.,0.,amount]},before['revision'])

    def test_unmanaged_legacy_apply_is_still_metered_by_episode_at_actual_helper(self):
        self.move();self.move()
        report=self.host.owned_episode_status()
        self.assertEqual(self.part.assignments,2)
        self.assertEqual(report['actual_setter_count'],2)
        self.assertEqual(report['reserved_event_count'],2)
        self.assertEqual(report['events'][0]['before_native'],self.initial['native_scene'])
        self.assertEqual(report['events'][0]['after_native'],report['events'][1]['before_native'])
        self.assertEqual(report['events'][1]['after_native'],self.host.capture_evidence()['native_scene'])
        self.assertEqual(self.base.assignments,0)

    def test_host_readback_failure_counts_and_preserves_original_bounded_rollback(self):
        self.host._verify_readback=lambda *args:(_ for _ in ()).throw(RuntimeError('owner forced verification failure'))
        with self.assertRaises(Exception):self.move()
        report=self.host.owned_episode_status()
        self.assertEqual(self.part.assignments,2,'Global accounting must retain the existing bounded rollback')
        self.assertEqual(self.part.matrix_world[2][3],4.)
        self.assertEqual(report['actual_setter_count'],2)
        self.assertEqual([v['kind'] for v in report['events']],['forward','rollback'])
        self.assertEqual(report['events'][-1]['after_native'],self.initial['native_scene'])
        self.assertIsNotNone(report['frozen_reason'])
        with self.assertRaises(Exception):self.move()
        self.assertEqual(self.part.assignments,2)

    def test_global_preflight_zero_does_not_forge_a_goal_actual_setter(self):
        self.host._episode_store()[1]['record']['limits']['max_setters']=1
        self.host.begin_motion_goal('child-goal',**self.pair)
        with self.assertRaises(Exception):self.move()
        global_report=self.host.owned_episode_status()
        child_report=self.host.motion_goal_status('child-goal')
        self.assertEqual(self.part.assignments,0)
        self.assertEqual(global_report['reserved_event_count'],0)
        self.assertEqual(global_report['actual_setter_count'],0)
        self.assertEqual(child_report['reserved_event_count'],0)
        self.assertEqual(child_report['physical_meter']['actual_setter_count'],0)

    def test_global_reservation_delay_cancels_both_meters_after_goal_gate_passes(self):
        from verification.test_host_forward_deadline import HostForwardDeadlineTests
        case=HostForwardDeadlineTests('test_require_shell_blocks_ordinary_apply_before_parent_binding')
        case.setUp();self.addCleanup(case.doCleanups)
        host=case.host
        host.begin_owned_episode('late-global-entry',**case.pair,deadline_ns=150_000_000_000)
        action,args=case.invocation() # Original per-goal forward deadline is180s.
        original=host._episode_before_setter;entry_seen=[];enter_original=host._episode_enter_setter
        def delayed(obj,values,helper,*,preflight=False):
            token=original(obj,values,helper,preflight=preflight)
            if not preflight:case.now_ns=150_000_000_000
            return token
        def record_goal_gate(token):
            entry_seen.append(host._forward_setter_context['entered'])
            return enter_original(token)
        host._episode_before_setter=delayed;host._episode_enter_setter=record_goal_gate
        with self.assertRaises(Exception):host.apply_transform(action,**args)
        episode=host.owned_episode_status();goal=host.motion_goal_status(case.goal)
        self.assertEqual(entry_seen,[True],'Per-goal gate passed, but final original episode gate must still cancel')
        self.assertEqual(case.part.assignments,0)
        self.assertEqual(episode['reserved_event_count'],1)
        self.assertEqual(episode['actual_setter_count'],0)
        self.assertEqual(episode['events'][0]['state'],'cancelled_before_entry')
        self.assertEqual(goal['physical_meter']['actual_setter_count'],0)
        self.assertEqual(goal['physical_meter']['rollback_count'],0)
        self.assertEqual(goal['cancelled_before_entry_count'],1)
        self.assertEqual(goal['unknown_event_count'],0)

    def test_earlier_goal_gate_expiry_cancels_both_reserved_entries(self):
        from verification.test_host_forward_deadline import HostForwardDeadlineTests
        case=HostForwardDeadlineTests('test_require_shell_blocks_ordinary_apply_before_parent_binding')
        case.setUp();self.addCleanup(case.doCleanups)
        host=case.host
        host.begin_owned_episode('early-goal-entry',**case.pair,deadline_ns=170_000_000_000)
        action,args=case.invocation(case.base_lease(forward_s=101.))
        original=host._episode_before_setter
        def delayed(obj,values,helper,*,preflight=False):
            token=original(obj,values,helper,preflight=preflight)
            if not preflight:case.now_ns=101_000_000_000
            return token
        host._episode_before_setter=delayed
        result=host.apply_transform(action,**args)
        self.assertEqual(result['status'],'rejected_before_mutation')
        episode=host.owned_episode_status();goal=host.motion_goal_status(case.goal)
        self.assertEqual(case.part.assignments,0)
        self.assertEqual(episode['events'][0]['state'],'cancelled_before_entry')
        self.assertEqual(episode['actual_setter_count'],0)
        self.assertEqual(goal['physical_meter']['actual_setter_count'],0)
        self.assertEqual(goal['cancelled_before_entry_count'],1)
        self.assertEqual(goal['unknown_event_count'],0)


if __name__=='__main__':unittest.main()
