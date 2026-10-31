"""Final native-assignment deadline gates, with actual counting test doubles."""
import copy
import json
import os
import time
import unittest
from unittest.mock import patch

from human_eye_plugin import forward_deadline as contract
from human_eye_plugin.auto_router import _validated_scene
from verification.test_blender_native_evidence import fixture
from verification.test_blender_host_contracts import BlenderHostError, FakeObject


class LocationObject(FakeObject):
    @property
    def location(self):return [self._matrix_world[r][3] for r in range(3)]

    @location.setter
    def location(self, values):
        self.assignments+=1
        for r in range(3):self._matrix_world[r][3]=values[r]


class HostForwardDeadlineTests(unittest.TestCase):
    def setUp(self):
        self.host,self.part,self.base,_=fixture()
        self.pair={'focal_id':self.host.object_id(self.part),'reference_id':self.host.object_id(self.base)}
        self.goal='goal-1'
        self.now_ns=100_000_000_000
        self.patch=patch('time.perf_counter_ns',side_effect=lambda:self.now_ns)
        self.patch.start();self.addCleanup(self.patch.stop)
        self.host.begin_motion_goal(self.goal,**self.pair)
        self.profile=self.host.require_forward_deadline(self.goal)
        self.binding=self.host.motion_goal_status(self.goal)['binding']

    def base_lease(self,parent_s=200.,forward_s=180.):
        return contract.make_deadline(parent_s,forward_s,goal_id=self.goal,
            binding=self.binding,process_id=os.getpid())

    def invocation(self,base=None,nonce='a'*32):
        scene=self.host.capture_scene()
        _,_,fingerprint=_validated_scene(scene)
        action={**self.pair,'translation':[0.,0.,.0005],'rotation_euler_deg':[0.,0.,0.]}
        wire=contract.bind_deadline(base or self.base_lease(),action=action,
            expected_revision=scene['revision'],expected_fingerprint=fingerprint,request_nonce=nonce)
        return action,{'expected_revision':scene['revision'],'expected_fingerprint':fingerprint,
            'request_nonce':nonce,'forward_deadline':wire}

    def move(self,base=None,nonce='a'*32):
        action,args=self.invocation(base,nonce)
        return self.host.apply_transform(action,**args),action,args

    def test_require_shell_blocks_ordinary_apply_before_parent_binding(self):
        scene=self.host.capture_scene()
        with self.assertRaises(BlenderHostError):self.host.apply_transform(
            {**self.pair,'translation':[0,0,.0005]},scene['revision'])
        report=self.host.motion_goal_status(self.goal)
        self.assertEqual(self.part.assignments,0)
        self.assertEqual(report['reserved_event_count'],0)
        self.assertIsNone(report['forward_deadline_requirement']['parent_deadline_ns'])

    def test_first_wire_fixes_parent_and_ordinary_apply_cannot_bypass_later(self):
        result,_,_=self.move()
        self.assertTrue(result['receipt']['host_execution_verified'])
        report=self.host.motion_goal_status(self.goal)
        self.assertEqual(report['forward_deadline_requirement']['parent_deadline_ns'],200_000_000_000)
        scene=self.host.capture_scene()
        with self.assertRaises(BlenderHostError):self.host.apply_transform(
            {**self.pair,'translation':[0,0,.0005]},scene['revision'])
        self.assertEqual(self.part.assignments,1)

    def test_bind_same_parent_is_idempotent_and_child_deadline_can_shrink(self):
        first=self.host.bind_forward_deadline(self.base_lease())
        second=self.host.bind_forward_deadline(self.base_lease(forward_s=150.))
        self.assertEqual(first['parent_deadline_ns'],second['parent_deadline_ns'])
        self.assertTrue(second['forward_admission_open'])
        self.assertEqual(self.part.assignments,0)

    def test_parent_deadline_cannot_expand_or_change_even_to_earlier_value(self):
        self.host.bind_forward_deadline(self.base_lease())
        for parent in (201.,199.):
            with self.subTest(parent=parent):
                with self.assertRaises(BlenderHostError):self.host.bind_forward_deadline(self.base_lease(parent_s=parent))
        self.assertEqual(self.part.assignments,0)

    def test_at_guard_boundary_refuses_without_setter_or_rollback(self):
        action,args=self.invocation()
        wire=args['forward_deadline']
        self.now_ns=wire['forward_deadline_ns']-wire['clock']['guard_ns']
        result=self.host.apply_transform(action,**args)
        proof=contract.validate_refusal(result,forward_deadline=wire,action=action,
            expected_revision=args['expected_revision'],expected_fingerprint=args['expected_fingerprint'],
            request_nonce=args['request_nonce'])
        report=self.host.motion_goal_status(self.goal)
        self.assertEqual(self.part.assignments,0)
        self.assertEqual(report['physical_meter']['actual_setter_count'],0)
        self.assertEqual(report['physical_meter']['rollback_count'],0)
        self.assertEqual(report['unknown_event_count'],0)
        self.assertEqual(report['cancelled_before_entry_count'],1)
        self.assertTrue(report['registered_events_complete'])
        self.assertEqual(proof['cancelled_event_id'],'a'*32+':forward')

    def test_one_ns_before_guard_boundary_still_enters(self):
        action,args=self.invocation();wire=args['forward_deadline']
        self.now_ns=wire['forward_deadline_ns']-wire['clock']['guard_ns']-1
        result=self.host.apply_transform(action,**args)
        self.assertTrue(result['receipt']['host_execution_verified'])
        self.assertEqual(self.part.assignments,1)

    def test_reservation_delay_is_included_by_final_helper_gate(self):
        action,args=self.invocation();original=self.host._reserve_motion_setter
        def delayed(*a,**kw):
            result=original(*a,**kw)
            self.now_ns=args['forward_deadline']['forward_deadline_ns']
            return result
        self.host._reserve_motion_setter=delayed
        result=self.host.apply_transform(action,**args)
        self.assertEqual(result['status'],'rejected_before_mutation')
        self.assertEqual(self.part.assignments,0)
        self.assertEqual(self.host.motion_goal_status(self.goal)['cancelled_before_entry_count'],1)

    def test_delay_in_assign_wrapper_still_reaches_the_native_helper_gate(self):
        action,args=self.invocation();original=self.host._assign_matrix
        def delayed(*a,**kw):
            self.now_ns=args['forward_deadline']['forward_deadline_ns']
            return original(*a,**kw)
        self.host._assign_matrix=delayed
        self.assertEqual(self.host.apply_transform(action,**args)['status'],'rejected_before_mutation')
        self.assertEqual(self.part.assignments,0)

    def test_location_path_checks_after_wrapper_delay_before_native_setter(self):
        self.part.__class__=LocationObject
        action,args=self.invocation();original=self.host._assign_translation
        def delayed(*a,**kw):
            self.now_ns=args['forward_deadline']['forward_deadline_ns']
            return original(*a,**kw)
        self.host._assign_translation=delayed
        result=self.host.apply_transform(action,**args)
        self.assertEqual(result['status'],'rejected_before_mutation')
        self.assertEqual(self.part.assignments,0)
        self.assertEqual(self.host.motion_goal_status(self.goal)['cancelled_before_entry_count'],1)

    def test_location_path_enters_before_deadline(self):
        self.part.__class__=LocationObject
        result,_,_=self.move()
        self.assertTrue(result['receipt']['host_execution_verified'])
        self.assertEqual(self.part.assignments,1)
        self.assertEqual(self.host.motion_goal_status(self.goal)['physical_meter']['actual_setter_count'],1)

    def test_capture_and_proposal_delay_are_included(self):
        action,args=self.invocation();original=self.host._capture
        def delayed(*a,**kw):
            result=original(*a,**kw)
            self.now_ns=args['forward_deadline']['forward_deadline_ns']
            return result
        self.host._capture=delayed
        self.assertEqual(self.host.apply_transform(action,**args)['status'],'rejected_before_mutation')
        self.assertEqual(self.part.assignments,0)

    def test_new_requirement_cannot_be_registered_after_an_unprotected_setter(self):
        other,part,base,_=fixture()
        pair={'focal_id':other.object_id(part),'reference_id':other.object_id(base)}
        other.begin_motion_goal('other-goal',**pair)
        before=other.capture_scene();fingerprint=_validated_scene(before)[2]
        other.apply_transform({**pair,'translation':[0,0,.0005]},before['revision'],fingerprint,'b'*32)
        with self.assertRaises(BlenderHostError):other.require_forward_deadline('other-goal')
        self.assertEqual(part.assignments,1)

    def test_cancelled_identity_remains_and_cannot_enter_after_new_child_deadline(self):
        action,args=self.invocation(self.base_lease(forward_s=101.))
        self.now_ns=101_000_000_000
        self.host.apply_transform(action,**args)
        with self.assertRaises(Exception):self.move(self.base_lease(forward_s=190.))
        report=self.host.motion_goal_status(self.goal)
        self.assertEqual(self.part.assignments,0)
        self.assertEqual(report['reserved_event_count'],1)
        self.assertEqual(report['cancelled_before_entry_count'],1)

    def test_late_readback_keeps_known_entered_facts_and_does_not_cancel(self):
        action,args=self.invocation();original=self.host._assign_matrix
        def late(*a,**kw):
            original(*a,**kw)
            self.now_ns=201_000_000_000
        self.host._assign_matrix=late
        self.assertTrue(self.host.apply_transform(action,**args)['receipt']['host_execution_verified'])
        report=self.host.motion_goal_status(self.goal)
        self.assertEqual(self.part.assignments,1)
        self.assertEqual(report['physical_meter']['actual_setter_count'],1)
        self.assertEqual(report['cancelled_before_entry_count'],0)
        self.assertTrue(report['registered_events_complete'])
        self.assertFalse(report['forward_admission_open'])

    def test_bounded_rollback_is_counted_after_forward_deadline(self):
        action,args=self.invocation()
        def fail(*a,**kw):
            self.now_ns=201_000_000_000
            raise RuntimeError('owned readback mismatch')
        self.host._verify_readback=fail
        with self.assertRaises(BlenderHostError):self.host.apply_transform(action,**args)
        report=self.host.motion_goal_status(self.goal)
        self.assertEqual(self.part.assignments,2)
        self.assertEqual(report['physical_meter']['actual_setter_count'],2)
        self.assertEqual(report['physical_meter']['rollback_count'],1)
        self.assertEqual(report['cancelled_before_entry_count'],0)
        self.assertEqual(self.part.matrix_world[2][3],4.)
        self.assertIsNotNone(report['frozen_reason'])

    def test_wrong_action_nonce_pid_or_document_reject_before_entry(self):
        action,args=self.invocation()
        for field,value in [('request_nonce','b'*32),('process_id',os.getpid()+1),
                            ('expected_fingerprint','e'*64)]:
            with self.subTest(field=field):
                bad=copy.deepcopy(args);bad['forward_deadline'][field]=value
                with self.assertRaises(ValueError):self.host.apply_transform(action,**bad)
        bad=copy.deepcopy(args);bad['forward_deadline']['binding']['document_epoch']='d'*64
        with self.assertRaises(ValueError):self.host.apply_transform(action,**bad)
        self.assertEqual(self.part.assignments,0)
        self.assertEqual(self.host.motion_goal_status(self.goal)['reserved_event_count'],0)

    def test_new_bridge_cannot_lose_the_requirement_or_extend_parent(self):
        self.host.bind_forward_deadline(self.base_lease())
        other=type(self.host)(bpy_module=self.host.bpy,execution_metadata=True,identity_metadata=True)
        with self.assertRaises(BlenderHostError):other.bind_forward_deadline(self.base_lease(parent_s=201.))
        scene=other.capture_scene()
        with self.assertRaises(BlenderHostError):other.apply_transform(
            {**self.pair,'translation':[0,0,.0005]},scene['revision'])
        self.assertEqual(self.part.assignments,0)

    def test_cancelled_tombstone_roundtrip_is_not_unknown_or_actual_setter(self):
        action,args=self.invocation();self.now_ns=190_000_000_000
        self.host.apply_transform(action,**args)
        module,state=self.host._motion_store()
        detached=json.loads(json.dumps(state));module.validate_ledger(detached)
        event=detached['records'][self.goal]['events'][0]
        self.assertEqual(event['state'],'cancelled_before_entry')
        self.assertEqual(event['actual_translation_m'],0.)
        with self.assertRaises(module.HostMotionStopped):module.confirm_setter(detached,self.goal,event['event_id'],
            binding=self.binding,after_world=event['before_world'],
            after_scene_fingerprint=event['before_scene_fingerprint'],now=time.monotonic())


if __name__=='__main__':unittest.main()
