"""Fresh router/host gates for exact orthogonal solids and strict wording."""
from __future__ import annotations
import copy
import json
import unittest
from unittest.mock import patch
import numpy as np
from human_eye_plugin.auto_router import HumanEyeAutoRouter
from human_eye_plugin.host_runtime import GuardedHostRuntime
from verification.test_complex_scene_quality import fixture, observe, pair
from verification.test_host_runtime import MutableHost


class ConcaveObservationFlowTests(unittest.TestCase):
    def event(self, value, observed, delta):
        return dict(event='before_action', session_id='complex-quality',
            observation_id=observed['observation_id'], focal_id=value['focal'],
            reference_id=value['reference'], action={'translation':delta})

    def test_hole_and_L_are_measured_with_original_surface_witnesses(self):
        for name in ('square_hole','L_slot'):
            with self.subTest(name=name):
                value=fixture(name)
                result=observe(value)
                facts=json.loads(result['context_text'])
                measured=facts['measurement']
                self.assertEqual(result['observation_status'],'complete',result)
                self.assertEqual(measured['clearance_state'],'positive_clearance')
                self.assertNotIn('alignment_state',measured)
                self.assertNotIn('display_signed_clearance_m',measured)
                self.assertEqual(measured['measurement_method'],'exact_orthogonal_cell_union_sat')
                self.assertAlmostEqual(measured['signed_clearance_m'],value['oracle']['clearance_m'],places=12)
                self.assertAlmostEqual(np.linalg.norm(np.array(measured['point_a_world'])-measured['point_b_world']),
                    measured['signed_clearance_m'],places=12)
                self.assertEqual(measured['witness_source'],'current_original_full_mesh_surface_features')

    def test_safe_endpoint_inside_hole_and_L_is_allowed(self):
        for name,delta in (('square_hole',[.018,0,0]),('L_slot',[-.039,0,0])):
            with self.subTest(name=name):
                value=fixture(name);router=HumanEyeAutoRouter(quad_size=64)
                seen=observe(value,router=router)
                allowed=router.handle_event(self.event(value,seen,delta))
                self.assertIs(allowed['allow_action'],True,allowed)
                self.assertEqual(allowed['execution_scope'],'terminal_geometry_only')
                self.assertTrue(allowed['rigid_frame_valid'])

    def test_hole_wall_crossing_endpoint_is_rejected(self):
        value=fixture('square_hole');router=HumanEyeAutoRouter(quad_size=64)
        seen=observe(value,router=router)
        denied=router.handle_event(self.event(value,seen,[.020,0,0]))
        self.assertIs(denied['allow_action'],False)
        self.assertEqual(denied['reason_codes'],['candidate_collision'])

    def test_new_class_does_not_bypass_explicit_invalid_host_frame(self):
        value=fixture('square_hole')
        target=next(item for item in value['scene']['meshes'] if item['object_id']==value['focal'])
        target['local_axes']=[[1,0,0],[1,0,0],[0,0,1]]
        router=HumanEyeAutoRouter(quad_size=64)
        seen=observe(value,router=router)
        self.assertFalse(seen['rigid_frame_valid'])
        denied=router.handle_event(self.event(value,seen,[.018,0,0]))
        self.assertIs(denied['allow_action'],False)
        self.assertEqual(denied['reason_codes'],['unverified_geometry_or_frame'])

    def test_unknown_extra_solid_still_blocks_execution(self):
        value=fixture('square_hole')
        extra=copy.deepcopy(value['scene']['meshes'][1]);extra['object_id']='open-extra'
        extra['mark_label']='#open-extra';extra['is_focal_target']=False
        extra['faces']=extra['faces'][:-1]
        value['scene']['meshes'].append(extra)
        router=HumanEyeAutoRouter(quad_size=64);seen=observe(value,router=router)
        self.assertEqual(seen['observation_status'],'partial')
        denied=router.handle_event(self.event(value,seen,[.018,0,0]))
        self.assertFalse(denied['allow_action'])
        self.assertEqual(denied['reason_codes'],['partial_observation_not_actionable'])

    def test_old_persisted_observation_cannot_authorize_new_contract(self):
        value=fixture('square_hole');router=HumanEyeAutoRouter(quad_size=64)
        seen=observe(value,router=router)
        saved=router.export_state()
        saved['sessions'][0][1]['observation']['contract_revision']='v1-host-rigid-frame-observation-20261023'
        restored=HumanEyeAutoRouter(quad_size=64);restored.import_state(saved)
        denied=restored.handle_event(self.event(value,seen,[.018,0,0]))
        self.assertFalse(denied['allow_action'])
        self.assertEqual(denied['reason_codes'],['stale_or_missing_observation'])
        fresh=observe(value,router=restored)
        self.assertEqual(json.loads(fresh['context_text'])['measurement']['clearance_state'],'positive_clearance')

    def test_observation_measurement_cache_is_not_used_for_execution(self):
        value=fixture('square_hole');router=HumanEyeAutoRouter(quad_size=64)
        seen=observe(value,router=router)
        with patch.object(router.scene_cache,'pair_measurement',side_effect=AssertionError('Execution reused observation measurement')):
            allowed=router.handle_event(self.event(value,seen,[.018,0,0]))
        self.assertTrue(allowed['allow_action'],allowed)

    def test_general_rotation_of_concave_focal_remains_unknown(self):
        value=fixture('square_hole');router=HumanEyeAutoRouter(quad_size=64)
        kwargs=dict(event='before_model',session_id='rotate-concave',scene=value['scene'],
            task_kind='spatial_3d',focal_id=value['reference'],reference_id=value['focal'],include_image=False)
        seen=router.handle_event(kwargs)
        self.assertEqual(seen['observation_status'],'complete',seen)
        denied=router.handle_event(dict(event='before_action',session_id='rotate-concave',
            focal_id=value['reference'],reference_id=value['focal'],observation_id=seen['observation_id'],
            action={'rotation_euler_deg':[0,0,3]}))
        self.assertFalse(denied['allow_action'])
        self.assertEqual(denied['reason_codes'],['candidate_geometry_unknown'])

    def test_real_readback_contract_and_goal_work_with_concave_reference(self):
        value=fixture('square_hole');host=MutableHost()
        host.scene=copy.deepcopy(value['scene']);host.scene['revision']='r1'
        runtime=GuardedHostRuntime(host,quad_size=64)
        prepared=runtime.before_model(session_id='hole-host',task_instruction='Inspect hole clearance.',
            task_kind='spatial_3d',messages=[],focal_id=value['focal'],reference_id=value['reference'],include_image=False)
        self.assertFalse(prepared['routing']['requires_reobserve'],prepared)
        result=runtime.execute_action(session_id='hole-host',action={'focal_id':value['focal'],
            'reference_id':value['reference'],'translation':[.018,0,0]},
            goal={'target_clearance_m':.001,'clearance_tolerance_m':1e-10})
        self.assertTrue(result['execution_verified'],result)
        self.assertEqual(result['goal_evaluation'],'goal_satisfied')
        self.assertEqual(host.calls,1)
        self.assertAlmostEqual(result['goal_verification']['measurements']['signed_clearance_m'],.001,places=12)

    def test_collision_does_not_write_mutable_host(self):
        value=fixture('square_hole');host=MutableHost()
        host.scene=copy.deepcopy(value['scene']);host.scene['revision']='r1'
        before=copy.deepcopy(host.scene);runtime=GuardedHostRuntime(host,quad_size=64)
        prepared=runtime.before_model(session_id='hole-host',task_instruction='Inspect hole clearance.',
            task_kind='spatial_3d',messages=[],focal_id=value['focal'],reference_id=value['reference'],include_image=False)
        self.assertFalse(prepared['routing']['requires_reobserve'],prepared)
        result=runtime.execute_action(session_id='hole-host',action={'focal_id':value['focal'],
            'reference_id':value['reference'],'translation':[.020,0,0]})
        self.assertFalse(result['executed'],result)
        self.assertIn('candidate_collision',result['reason_codes'])
        self.assertEqual(host.calls,0)
        self.assertEqual(host.scene,before)


if __name__=='__main__':unittest.main()

