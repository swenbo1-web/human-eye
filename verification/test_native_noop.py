"""Explicit-native no-effect admission and preserved accounting boundaries.

These use pure bpy doubles and do not certify actual Blender storage. Positive
real binary32 quantization and transport acknowledgement need owned acceptance.
"""
from __future__ import annotations

import copy,sys,time,unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

from verification import test_blender_host_contracts as host_tests
from verification.test_blender_native_evidence import fixture
from verification import test_common_owned_gateway as common_tests


class LocationObject(host_tests.FakeObject):
    @property
    def location(self):return [self._matrix_world[k][3] for k in range(3)]

    @location.setter
    def location(self,values):
        self.assignments+=1
        for k,value in enumerate(values):self._matrix_world[k][3]=float(value)


class NativeNoopHostTests(unittest.TestCase):
    def ready(self,*,location=True,readonly=False,scale=1.):
        host,part,base,_=fixture(scale)
        if location:part.__class__=LocationObject
        self.host,self.part,self.base=host,part,base
        self.focal,self.reference=host.object_id(part),host.object_id(base)
        self.initial=host.capture_evidence()
        host.begin_owned_episode('explicit-native-noop',self.focal,self.reference,
            deadline_ns=time.perf_counter_ns()+20_000_000_000,read_only=readonly)
        self.addCleanup(lambda:None)
        return host

    def move(self,dz,*,identity=None,revision=None):
        native=self.host.native_scene_query()
        return self.host.native_transform(identity or self.focal,[0.,0.,dz],revision or native['revision'])

    def assert_zero_and_unchanged(self,before):
        after=self.host.owned_episode_status()
        self.assertEqual(after['actual_setter_count'],0)
        self.assertEqual(after['reserved_event_count'],0)
        self.assertEqual(after['remaining_setters'],before['remaining_setters'])
        self.assertEqual(after['remaining_translation_m'],before['remaining_translation_m'])
        self.assertEqual(after['deadline_ns'],before['deadline_ns'])
        self.assertEqual(after['limits'],before['limits'])
        self.assertEqual(after['frozen_reason'],before['frozen_reason'])
        self.assertEqual(after['events'],before['events'])
        self.assertEqual(self.host.capture_evidence()['native_scene'],self.initial['native_scene'])
        self.assertEqual(self.part.assignments+self.base.assignments,0)

    def test_repeated_exact_zero_does_not_spend_entries_and_valid_step_still_works(self):
        self.ready();before=self.host.owned_episode_status()
        for _ in range(12):
            with self.assertRaisesRegex(host_tests._module.EpisodePrewriteRefused,'native_no_effect'):
                self.move(0.)
        self.assert_zero_and_unchanged(before)
        applied=self.move(.0005)
        self.assertTrue(applied['applied'])
        self.assertAlmostEqual(applied['delta_world_m'][2],.0005,places=12)
        self.assertEqual(self.host.owned_episode_status()['actual_setter_count'],1)
        self.assertEqual(self.part.assignments,1)

    def test_matrix_only_zero_is_refused_before_any_assignment(self):
        self.ready(location=False);before=self.host.owned_episode_status()
        with self.assertRaisesRegex(host_tests._module.EpisodePrewriteRefused,'native_no_effect'):
            self.move(-0.)
        self.assert_zero_and_unchanged(before)

    def test_readonly_preflight_is_not_replaced_by_noop_refusal(self):
        self.ready(readonly=True);before=self.host.owned_episode_status()
        with self.assertRaisesRegex(host_tests._module.EpisodePrewriteRefused,'episode_read_only'):
            self.move(0.)
        self.assert_zero_and_unchanged(before)

    def test_original_deadline_preflight_dominates_noop_admission(self):
        self.ready();before=self.host.owned_episode_status()
        record=self.host._episode_store()[1]['record']
        with patch.object(host_tests._module.time,'perf_counter_ns',return_value=record['deadline_ns']):
            with self.assertRaisesRegex(host_tests._module.EpisodePrewriteRefused,'episode_deadline_expired'):
                self.move(0.)
        self.assert_zero_and_unchanged(before)

    def test_unknown_and_frozen_original_episode_are_not_made_usable_by_noop(self):
        for unknown in (False,True):
            with self.subTest(unknown=unknown):
                self.ready();module,state=self.host._episode_store()
                if unknown:
                    native=state['record']['initial_native']
                    obj=next(v for v in native['objects'] if v['object_id']==self.focal)
                    index=module.reserve_setter(state,helper='native_transform',object_id=self.focal,
                        requested_world=[obj['matrix'][k][3]+(.0005 if k==2 else 0.) for k in range(3)],
                        before_native=native,binding=state['record']['binding'],now_ns=time.perf_counter_ns())
                    module.mark_unknown(state,index)
                else:module.freeze_episode(state,'owner-failure-already-observed')
                before=self.host.owned_episode_status()
                with self.assertRaises(host_tests._module.EpisodeUncertain):self.move(0.)
                after=self.host.owned_episode_status()
                self.assertEqual(after['events'],before['events'])
                self.assertEqual(after['frozen_reason'],before['frozen_reason'])
                self.assertEqual(self.part.assignments,0)

    def test_active_goal_and_stale_or_wrong_target_checks_precede_noop(self):
        self.ready();before=self.host.owned_episode_status()
        with self.assertRaisesRegex(host_tests._module.EpisodePrewriteRefused,'native_wrong_object'):
            self.move(0.,identity=self.reference)
        with self.assertRaisesRegex(host_tests._module.EpisodePrewriteRefused,'native_stale_revision'):
            self.move(0.,revision='outdated')
        self.host.begin_motion_goal('active-child',self.focal,self.reference)
        with self.assertRaisesRegex(host_tests._module.EpisodePrewriteRefused,'native_blocked_by_active_or_unresolved_goal'):
            self.move(0.)
        self.assert_zero_and_unchanged(before)

    def test_overcap_request_not_hidden_by_forced_noop_classification(self):
        self.ready();before=self.host.owned_episode_status()
        with patch.object(self.host,'_native_translation_is_noop',return_value=True) as classifier:
            with self.assertRaisesRegex(host_tests._module.EpisodePrewriteRefused,'episode_requested_step_cap'):
                self.move(.0011)
        classifier.assert_not_called()
        self.assert_zero_and_unchanged(before)

    def test_original_rollback_reserve_cap_still_precedes_noop(self):
        self.ready();state=self.host._episode_store()[1];state['record']['limits']['max_setters']=1
        before=self.host.owned_episode_status()
        with self.assertRaisesRegex(host_tests._module.EpisodePrewriteRefused,'episode_rollback_reserve'):
            self.move(0.)
        self.assert_zero_and_unchanged(before)

    def test_non_bpy_storage_is_not_assumed_binary32(self):
        self.ready();self.part._matrix_world[2][3]=100000.
        target=self.part.location[:];target[2]+=.0001
        self.assertFalse(self.host._native_translation_is_noop(self.part,target))
        class Vector32(list):
            def __init__(self,value):super().__init__([host_tests._module._binary32_nearest(x) for x in value])
        fake_bpy=NS(types=NS(Object=LocationObject))
        with patch.dict(sys.modules,{'bpy':fake_bpy,'mathutils':NS(Vector=Vector32)}):
            self.assertFalse(self.host._native_translation_is_noop(self.part,target))

    def test_known_noop_does_not_intercept_shared_rollback_helpers(self):
        self.ready();self.host._verify_readback=lambda *args:(_ for _ in ()).throw(RuntimeError('owned injected readback failure'))
        native=self.host.capture_scene()
        with patch.object(self.host,'_native_translation_is_noop',side_effect=AssertionError('native-only check reached rollback')):
            with self.assertRaises(Exception):
                self.host.apply_transform({'focal_id':self.focal,'reference_id':self.reference,
                    'translation':[0.,0.,.0005]},native['revision'])
        meter=self.host.owned_episode_status()
        self.assertEqual(self.part.assignments,2)
        self.assertEqual(meter['actual_setter_count'],2)
        self.assertEqual([v['kind'] for v in meter['events']],['forward','rollback'])
        self.assertEqual(meter['last_native'],self.initial['native_scene'])
        self.assertIsNotNone(meter['frozen_reason'])


class NativeNoopTransportTests(unittest.TestCase):
    def test_existing_known_preentry_envelope_preserves_public_zero_and_later_use(self):
        case=common_tests.CommonOwnedGatewayTests()
        case.setUp();self.addCleanup(case.doCleanups)
        value,_=case.gateway()
        case.native_failure=common_tests.HostRemoteError({'type':'EpisodePrewriteRefused','message':'native_no_effect',
            'mutation_uncertain':False,'known_preentry_refusal':True,'executed':False})
        before=copy.deepcopy(value.private_snapshot()['episode_status'])
        result=case.move(value,0.)
        self.assertEqual(result,{'applied':False,'executed':False,'status':'rejected_before_mutation',
            'reason':'known_native_preentry_refusal'})
        self.assertFalse(value.uncertain_outcome)
        self.assertEqual(value.private_snapshot()['episode_status'],before)
        case.native_failure=None
        self.assertTrue(case.move(value,.0005)['applied'])
        self.assertEqual(value.private_snapshot()['episode_status']['actual_setter_count'],1)


if __name__=='__main__':unittest.main()
