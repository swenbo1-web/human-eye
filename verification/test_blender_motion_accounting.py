"""Actual adapter setter accounting with independent bpy test doubles."""
import copy
import hashlib
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

from verification.test_blender_native_evidence import fixture
from verification.test_blender_host_contracts import BlenderHostError
from human_eye_plugin.goal_supervision import make_owned_host_context
from human_eye_plugin.auto_router import _validated_scene


class BlenderMotionAccountingTests(unittest.TestCase):
    def setUp(self):
        self.host, self.part, self.base, _ = fixture()
        self.pair={'focal_id':self.host.object_id(self.part), 'reference_id':self.host.object_id(self.base)}

    def begin(self, **changes):
        return self.host.begin_motion_goal('goal-1', **self.pair, **changes)

    def move(self, amount=.0005, **changes):
        action={**self.pair, 'translation':[0.,0.,amount], 'rotation_euler_deg':[0.,0.,0.]}
        action.update(changes)
        before=self.host.capture_scene()
        return self.host.apply_transform(action, before['revision'],
            expected_fingerprint=_validated_scene(before)[2], request_nonce='a'*32)

    def test_registered_actual_setter_and_default_shared_scope_are_separate(self):
        initial=self.begin()
        result=self.move()
        report=self.host.motion_goal_status('goal-1')
        self.assertEqual(self.part.assignments, 1)
        self.assertEqual(report['physical_meter']['actual_setter_count'], 1)
        actual=abs(self.part.matrix_world[2][3]-4.)
        self.assertEqual(report['physical_meter']['actual_cumulative_translation_m'], actual)
        self.assertTrue(report['registered_events_complete'])
        self.assertFalse(report['all_channels_complete'])
        self.assertFalse(report['physical_meter']['complete'])
        self.assertFalse(report['goal_budget_eligible'])
        self.assertEqual(report['clock_domain'], initial['clock_domain'])
        self.assertNotIn('physical_meter', result['receipt'])

    def test_namespace_counter_survives_new_host_module_instance(self):
        self.begin();self.move()
        other=type(self.host)(bpy_module=self.host.bpy, execution_metadata=True, identity_metadata=True)
        report=other.motion_goal_status('goal-1')
        self.assertEqual(report['physical_meter']['actual_setter_count'], 1)
        self.assertEqual(other.capture_evidence()['capture'], self.host.capture_scene())

    def test_external_edit_freezes_before_another_registered_setter(self):
        self.begin();self.part.matrix_world[2][3]+=.0002
        with self.assertRaises(Exception):self.move()
        self.assertEqual(self.part.assignments, 0)
        report=self.host.motion_goal_status('goal-1')
        self.assertFalse(report['registered_events_complete'])
        self.assertIsNotNone(report['frozen_reason'])

    def test_unknown_actual_setter_is_not_claimed_zero_write(self):
        self.begin()
        original=self.host._assign_matrix
        def fail_after_assignment(obj, rows):
            original(obj, rows)
            self.part.to_mesh=lambda:(_ for _ in ()).throw(RuntimeError('owned unavailable geometry'))
            raise RuntimeError('owned setter raised after entry')
        self.host._assign_matrix=fail_after_assignment
        with self.assertRaises(BlenderHostError):self.move()
        self.assertEqual(self.part.assignments, 1)
        report=self.host.motion_goal_status('goal-1')
        self.assertEqual(report['unknown_event_count'], 1)
        self.assertFalse(report['registered_events_complete'])
        self.assertIn('lower bound', report['setter_count_semantics'])
        self.assertFalse(report['physical_meter']['complete'])

    def test_known_failed_verification_accounts_forward_and_rollback(self):
        self.begin()
        self.host._verify_readback=lambda *args:(_ for _ in ()).throw(RuntimeError('owned verification failure'))
        with self.assertRaises(BlenderHostError):self.move()
        report=self.host.motion_goal_status('goal-1')
        self.assertEqual(self.part.assignments, 2)
        self.assertEqual(self.part.matrix_world[2][3], 4.)
        self.assertEqual(report['physical_meter']['actual_setter_count'], 2)
        self.assertEqual(report['physical_meter']['rollback_count'], 1)
        self.assertAlmostEqual(report['physical_meter']['actual_cumulative_translation_m'], .001)
        self.assertFalse(report['registered_events_complete'])
        with self.assertRaises(Exception):self.move()
        self.assertEqual(self.part.assignments, 2)

    def test_preflight_keeps_one_rollback_slot(self):
        self.begin(limits={'max_setters':1})
        with self.assertRaises(BlenderHostError):self.move()
        self.assertEqual(self.part.assignments, 0)
        self.assertEqual(self.host.motion_goal_status('goal-1')['reserved_event_count'], 0)

    def test_exact_step_cap_without_precision_margin_is_rejected_before_setter(self):
        self.begin()
        with self.assertRaises(BlenderHostError):self.move(.001)
        self.assertEqual(self.part.assignments, 0)
        self.assertEqual(self.host.motion_goal_status('goal-1')['reserved_event_count'], 0)

    def test_same_nonce_never_reexecutes_a_registered_setter(self):
        self.begin();self.move()
        with self.assertRaises(Exception):self.move()
        self.assertEqual(self.part.assignments, 1)

    def test_registered_scope_refuses_rotation_other_pair_and_xy(self):
        for changes in ({'translation':[.0001,0,0]}, {'rotation_euler_deg':[0,0,.01]},
                        {'focal_id':self.pair['reference_id'],'reference_id':self.pair['focal_id']}):
            with self.subTest(changes=changes):
                self.setUp();self.begin()
                with self.assertRaises(BlenderHostError):self.move(**changes)
                self.assertEqual(self.part.assignments+self.base.assignments, 0)

    def test_rebegin_after_motion_is_not_an_implicit_restart(self):
        first=self.begin();self.move()
        with self.assertRaises(Exception):self.begin()
        report=self.host.motion_goal_status('goal-1')
        self.assertEqual(first['started_monotonic'], report['started_monotonic'])
        self.assertFalse(report['registered_events_complete'])

    def test_context_factory_refuses_shared_or_json_hosts(self):
        with self.assertRaises(Exception):make_owned_host_context(self.host,'goal-1',lambda *a:True)
        with self.assertRaises(Exception):make_owned_host_context({'coverage':True},'goal-1',lambda *a:True)


if __name__=='__main__':unittest.main()
