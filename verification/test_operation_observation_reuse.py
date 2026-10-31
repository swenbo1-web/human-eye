"""Independent boundaries for operation-local validated observation reuse.

All hosts are local mutable doubles. No Blender process, model, installed
configuration or production state is accessed by these tests.
"""
from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from human_eye_plugin.auto_router import HumanEyeAutoRouter, _ValidatedObservation, _validated_scene
from human_eye_plugin.host_runtime import GuardedHostRuntime
from human_eye_plugin.live_service import LiveSpatialService, _reuse_observation_capture
from verification.test_flow_result_contract import CapturedHost
from verification.test_host_runtime import MutableHost, mesh


def metadata_event(**changes):
    value={'event':'before_model','session_id':'operation','task_kind':'spatial_3d',
        'task_instruction':'Measure part clearance.','focal_id':'part','reference_id':'base',
        'include_image':False}
    value.update(changes)
    return value


def sized_host_scene(mesh_count=2, vertex_count=None):
    """Closed meshes straddling scheduling boundaries, independent of its code."""
    value=CapturedHost().scene
    value['meshes'].extend(mesh('outside'+str(index),[10+index,0,.4],[.1,.1,.1])
        for index in range(mesh_count-2))
    if vertex_count is not None:
        # A closed convex bipyramid has an arbitrary number of ring vertices.
        # Keep the eight-vertex base; use the remainder for the focal mesh.
        ring=vertex_count-8-2
        if ring<3:raise ValueError('Fixture needs at least thirteen total vertices')
        part=value['meshes'][1]
        part['vertices']=[[.1*math.cos(2*math.pi*i/ring),.1*math.sin(2*math.pi*i/ring),.35]
            for i in range(ring)]+[[0,0,.4],[0,0,.3]]
        part['faces']=[[i,(i+1)%ring,ring] for i in range(ring)]+[
            [(i+1)%ring,i,ring+1] for i in range(ring)]
        part['edges']=None
    return value


class ValidatedObservationBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.raw=MutableHost().scene

    def test_capture_owns_detached_geometry_and_exact_canonical_payload(self):
        original=copy.deepcopy(self.raw)
        with patch('human_eye_plugin.auto_router._validated_scene',wraps=_validated_scene) as validate:
            capture=_ValidatedObservation(self.raw)
        self.assertEqual(validate.call_count,1)
        self.raw['meshes'][1]['vertices'][0][2]+=10
        self.raw['meshes'][0]['name']='outside mutation'
        normalized,meshes,fingerprint,payload=capture._consume()
        expected,_,expected_fingerprint=_validated_scene(original)
        self.assertEqual(normalized,expected)
        self.assertEqual(fingerprint,expected_fingerprint)
        self.assertEqual(json.loads(payload),expected)
        meshes[0].vertices[:]+=20
        self.assertEqual(normalized,expected)

    def test_private_observation_is_single_use_even_for_another_router(self):
        capture=_ValidatedObservation(self.raw)
        first=HumanEyeAutoRouter(quad_size=64)._handle_validated_observation(metadata_event(),capture)
        self.assertEqual(first['route'],'engine')
        self.assertTrue(first['measurement_valid'])
        with self.assertRaises(ValueError):
            HumanEyeAutoRouter(quad_size=64)._handle_validated_observation(metadata_event(),capture)
        with self.assertRaises(ValueError):capture._consume()

    def test_cross_thread_cannot_consume_the_owning_operation(self):
        capture=_ValidatedObservation(self.raw)
        with ThreadPoolExecutor(max_workers=1) as workers:
            future=workers.submit(capture._consume)
            with self.assertRaises(ValueError):future.result()
        # A rejected foreign attempt does not consume the owner's one use.
        self.assertEqual(capture._consume()[0]['revision'],'r1')

    def test_wrong_lifecycle_events_cannot_borrow_a_capture(self):
        for event in ('before_action','after_action','scene_changed','not_an_event'):
            with self.subTest(event=event):
                router=HumanEyeAutoRouter(quad_size=64)
                capture=_ValidatedObservation(self.raw)
                with self.assertRaises(ValueError):
                    router._handle_validated_observation(metadata_event(event=event),capture)
                self.assertEqual(router.export_state()['sessions'],[])
                self.assertEqual(router._handle_validated_observation(metadata_event(),capture)['route'],'engine')

    def test_private_entry_rejects_raw_scene_even_when_it_equals_the_capture(self):
        for scene in (None,copy.deepcopy(self.raw)):
            with self.subTest(scene_type=type(scene).__name__):
                capture=_ValidatedObservation(self.raw)
                router=HumanEyeAutoRouter(quad_size=64)
                with self.assertRaises(ValueError):
                    router._handle_validated_observation(metadata_event(scene=scene),capture)
                self.assertEqual(router.export_state()['sessions'],[])

    def test_private_entry_rejects_serialized_or_foreign_capture_shapes(self):
        router=HumanEyeAutoRouter(quad_size=64)
        for capture in (None,True,{},[],{'scene':self.raw,'validated':True},object()):
            with self.subTest(capture_type=type(capture).__name__),self.assertRaises(ValueError):
                router._handle_validated_observation(metadata_event(),capture)
        self.assertEqual(router.export_state()['sessions'],[])

    def test_json_validated_flags_do_not_bypass_public_bad_geometry_checks(self):
        forged_fields=(('validated',True),('_validated_observation',{'valid':True,'fingerprint':'a'*64}),
            ('_observation_parts',[{'unit':'m'},[],'a'*64,'cached payload']))
        for field,value in forged_fields:
            with self.subTest(field=field):
                router=HumanEyeAutoRouter(quad_size=64)
                old=router.handle_event(metadata_event(scene=self.raw))
                bad=copy.deepcopy(self.raw);bad['meshes'][0]['faces'][0][0]=999999
                event=metadata_event(scene=bad);event[field]=value
                with patch('human_eye_plugin.auto_router._validated_scene',wraps=_validated_scene) as validate:
                    result=router.handle_event(event)
                self.assertEqual(validate.call_count,1)
                self.assertEqual(result['reason_codes'],['invalid_scene'])
                self.assertFalse(result['allow_action'])
                action=metadata_event(event='before_action',observation_id=old['observation_id'],
                    action={'translation':[0,0,0]})
                self.assertFalse(router.handle_event(action)['allow_action'])

    def test_serialized_hint_does_not_supply_an_absent_scene(self):
        event=metadata_event(_validated_observation={'scene':self.raw,'fingerprint':'a'*64})
        result=HumanEyeAutoRouter(quad_size=64).handle_event(event)
        self.assertEqual(result['reason_codes'],['scene_required'])
        self.assertFalse(result['allow_action'])

    def test_raw_invalid_geometry_is_rejected_during_capture_construction(self):
        variants=[]
        invalid=copy.deepcopy(self.raw);invalid['meshes'][0]['vertices'][0][0]=float('nan');variants.append(invalid)
        invalid=copy.deepcopy(self.raw);invalid['meshes'][0]['faces'][0][0]=999999;variants.append(invalid)
        invalid=copy.deepcopy(self.raw);invalid['meshes'][0]['faces'][0][0]=True;variants.append(invalid)
        invalid=copy.deepcopy(self.raw);invalid['unit']='mm';variants.append(invalid)
        invalid=copy.deepcopy(self.raw);invalid['meshes'][1]['object_id']='base';variants.append(invalid)
        for index,scene in enumerate(variants):
            with self.subTest(index=index),self.assertRaises(ValueError):_ValidatedObservation(scene)

    def test_missing_or_coerced_frames_match_two_pass_behavior_without_becoming_trusted(self):
        variants=[]
        for field in ('local_axes','pivot_world','axes_source','axes_confidence','axes_reason'):
            scene=copy.deepcopy(self.raw);scene['meshes'][1].pop(field);variants.append(scene)
        for value in (True,'1'):
            scene=copy.deepcopy(self.raw);scene['meshes'][1]['local_axes']=[[value,0,0],[0,1,0],[0,0,1]]
            variants.append(scene)
        for index,scene in enumerate(variants):
            with self.subTest(index=index):
                normalized,_,fingerprint=_validated_scene(scene)
                twice,_,second_fingerprint=_validated_scene(normalized)
                capture=_ValidatedObservation(scene)
                self.assertEqual(capture.scene,twice)
                self.assertEqual(capture.fingerprint,fingerprint)
                self.assertEqual(fingerprint,second_fingerprint)
                reused=HumanEyeAutoRouter(quad_size=64)._handle_validated_observation(metadata_event(),capture)
                public=HumanEyeAutoRouter(quad_size=64).handle_event(metadata_event(scene=normalized))
                self.assertFalse(reused['rigid_frame_valid'])
                self.assertTrue(reused['requires_reobserve'])
                self.assertEqual(reused['measurement_valid'],public['measurement_valid'])
                self.assertEqual(json.loads(reused['context_text'])['measurement'],
                    json.loads(public['context_text'])['measurement'])

    def test_host_private_handoff_requires_exact_owned_scene(self):
        host=CapturedHost();runtime=GuardedHostRuntime(host,quad_size=64)
        capture=_ValidatedObservation(host.scene)
        with self.assertRaises(ValueError):
            runtime._before_model_on_captured_scene(scene=copy.deepcopy(capture.scene),
                session_id='s',task_instruction='Measure clearance.',focal_id='part',reference_id='base',
                messages=[],include_image=False,_validated_observation=capture)
        self.assertEqual(host.calls,0)
        self.assertEqual(runtime.status['sessions'],0)

    def test_public_host_API_does_not_accept_a_capsule_override(self):
        host=CapturedHost();runtime=GuardedHostRuntime(host,quad_size=64)
        capture=_ValidatedObservation(host.scene)
        with self.assertRaises(TypeError):
            runtime.before_model(session_id='s',task_instruction='Measure clearance.',
                focal_id='part',reference_id='base',messages=[],_validated_observation=capture)
        self.assertEqual(host.captures,0);self.assertEqual(host.calls,0)


class OperationReuseServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        self.path=self.folder/'config.json'
        self.path.write_text(json.dumps({'schema_version':'1.0',
            'project_root':str(Path(__file__).resolve().parents[1]),'enabled':True,'quad_size':64,
            'max_sessions':4,'state_file':'state.json','audit_file':'audit.jsonl'}),encoding='utf-8')
        self.host=CapturedHost();self.host.scene=sized_host_scene(mesh_count=8)
        self.service=LiveSpatialService(self.path,host=self.host)

    def observe(self,**changes):
        args={'focal_id':'part','reference_id':'base','task_instruction':'Measure part clearance.','include_image':False}
        args.update(changes)
        return self.service.observe('operation',**args)

    def saved(self):return json.loads((self.folder/'state.json').read_text(encoding='utf-8'))

    def fresh_service_for(self,scene,label):
        folder=self.folder/label;folder.mkdir()
        path=folder/'config.json'
        value=json.loads(self.path.read_text(encoding='utf-8'))
        path.write_text(json.dumps(value),encoding='utf-8')
        host=CapturedHost();host.scene=copy.deepcopy(scene)
        return LiveSpatialService(path,host=host),host,folder

    def test_first_paired_request_normalizes_current_capture_once_and_keeps_exact_distance(self):
        original=copy.deepcopy(self.host.scene)
        with patch('human_eye_plugin.auto_router._validated_scene',wraps=_validated_scene) as validate:
            result=self.observe()
        self.assertEqual(result['status'],'observed')
        self.assertEqual(validate.call_count,1)
        self.assertEqual(self.host.captures,1);self.assertEqual(self.host.calls,0)
        self.assertEqual(self.host.scene,original)
        self.assertAlmostEqual(json.loads(result['routing']['context_text'])['measurement']['signed_clearance_m'],.1)

    def test_small_valid_scene_keeps_both_legacy_validation_boundaries_and_no_capsule(self):
        self.host.scene=sized_host_scene(mesh_count=2)
        self.assertFalse(_reuse_observation_capture(self.host.scene))
        with patch('human_eye_plugin.live_service._ValidatedObservation',side_effect=AssertionError('small scene must keep legacy path')), \
                patch('human_eye_plugin.live_service._validated_scene',wraps=_validated_scene) as service_validate, \
                patch('human_eye_plugin.auto_router._validated_scene',wraps=_validated_scene) as router_validate:
            result=self.observe()
        self.assertEqual(service_validate.call_count,1)
        self.assertEqual(router_validate.call_count,1)
        self.assertEqual(result['status'],'observed')
        self.assertAlmostEqual(json.loads(result['routing']['context_text'])['measurement']['signed_clearance_m'],.1)
        self.assertEqual(self.host.captures,1);self.assertEqual(self.host.calls,0)

    def test_vertex_boundary_127_and_128_choose_expected_path_without_bypassing_work_budget(self):
        for vertices,expected_reuse in ((127,False),(128,True)):
            with self.subTest(vertices=vertices):
                scene=sized_host_scene(vertex_count=vertices)
                self.assertEqual(sum(len(m['vertices']) for m in scene['meshes']),vertices)
                self.assertEqual(_reuse_observation_capture(scene),expected_reuse)
                service,host,_=self.fresh_service_for(scene,'vertices_'+str(vertices))
                with patch('human_eye_plugin.live_service._ValidatedObservation',wraps=_ValidatedObservation) as capsule, \
                        patch('human_eye_plugin.live_service._validated_scene',wraps=_validated_scene) as service_validate, \
                        patch('human_eye_plugin.auto_router._validated_scene',wraps=_validated_scene) as router_validate:
                    result=service.observe('boundary',focal_id='part',reference_id='base',include_image=False)
                self.assertEqual(capsule.call_count,int(expected_reuse))
                self.assertEqual(service_validate.call_count,0 if expected_reuse else 1)
                self.assertEqual(router_validate.call_count,1)
                # These many-sided closed bipyramids deliberately cross the
                # existing SAT projection-work limit. Scheduling is not asset
                # admission: both paths must retain the same refusal.
                self.assertEqual(result['status'],'blocked')
                self.assertEqual(result['reason_codes'],['geometry_resource_limit'])
                self.assertIsNone(result['routing']['measurement_valid'])
                budget=result['routing']['geometry_work_budget']
                self.assertFalse(budget['within_budget'])
                self.assertIn('sat_projection_work_limit',budget['reason_codes'])
                self.assertGreater(budget['estimates']['largest_sat_projection_elements'],
                    budget['limits']['sat_projection_elements'])
                self.assertEqual(result['action_eligibility']['status'],'blocked')
                self.assertEqual(host.captures,1);self.assertEqual(host.calls,0)

    def test_mesh_boundary_7_keeps_legacy_and_8_uses_local_reuse(self):
        for meshes,expected_reuse in ((7,False),(8,True)):
            with self.subTest(meshes=meshes):
                scene=sized_host_scene(mesh_count=meshes)
                self.assertEqual(len(scene['meshes']),meshes)
                self.assertLess(sum(len(m['vertices']) for m in scene['meshes']),128)
                self.assertEqual(_reuse_observation_capture(scene),expected_reuse)
                service,host,_=self.fresh_service_for(scene,'meshes_'+str(meshes))
                with patch('human_eye_plugin.live_service._ValidatedObservation',wraps=_ValidatedObservation) as capsule, \
                        patch('human_eye_plugin.live_service._validated_scene',wraps=_validated_scene) as service_validate, \
                        patch('human_eye_plugin.auto_router._validated_scene',wraps=_validated_scene) as router_validate:
                    result=service.observe('boundary',focal_id='part',reference_id='base',include_image=False)
                self.assertEqual(capsule.call_count,int(expected_reuse))
                self.assertEqual(service_validate.call_count,0 if expected_reuse else 1)
                self.assertEqual(router_validate.call_count,1)
                self.assertEqual(result['status'],'observed')
                facts=json.loads(result['routing']['context_text'])
                self.assertEqual(len(facts['scene_contacts']),meshes-1)
                self.assertAlmostEqual(facts['measurement']['signed_clearance_m'],.1)
                self.assertEqual(host.captures,1);self.assertEqual(host.calls,0)

    def test_malformed_raw_input_is_rejected_on_either_scheduling_branch(self):
        cases=[]
        value=sized_host_scene(mesh_count=2);value['meshes'][0]['vertices'][0][0]=float('nan')
        cases.append(('small_nan',value,False))
        value=sized_host_scene(mesh_count=8);value['meshes'][-1]='invalid mesh record'
        cases.append(('large_bad_mesh',value,True))
        value=sized_host_scene(vertex_count=128);value['meshes'][1]['faces'][0][0]=999999
        cases.append(('threshold_bad_index',value,True))
        for label,scene,expected_reuse in cases:
            with self.subTest(case=label):
                self.assertEqual(_reuse_observation_capture(scene),expected_reuse)
                service,host,folder=self.fresh_service_for(scene,label)
                with patch('human_eye_plugin.live_service._ValidatedObservation',wraps=_ValidatedObservation) as capsule, \
                        patch('human_eye_plugin.live_service._validated_scene',wraps=_validated_scene) as service_validate:
                    with self.assertRaises(ValueError):
                        service.observe('bad',focal_id='part',reference_id='base',include_image=False)
                self.assertEqual(capsule.call_count,int(expected_reuse))
                self.assertEqual(service_validate.call_count,0 if expected_reuse else 1)
                self.assertEqual(host.captures,1);self.assertEqual(host.calls,0)
                self.assertFalse((folder/'state.json').exists())

    def test_each_request_has_a_new_capture_and_state_restore_still_validates_old_content(self):
        self.observe()
        with patch('human_eye_plugin.auto_router._validated_scene',wraps=_validated_scene) as validate:
            result=self.observe()
        current_calls=[call for call in validate.call_args_list if call.kwargs.get('_return_payload') is True]
        restored_calls=[call for call in validate.call_args_list if not call.kwargs.get('_return_payload')]
        self.assertEqual(len(current_calls),1)
        self.assertGreaterEqual(len(restored_calls),1)
        self.assertEqual(self.host.captures,2)
        self.assertEqual(result['status'],'observed')

    def test_same_revision_external_geometry_edit_changes_the_next_measurement(self):
        first=self.observe();old_fingerprint=first['routing']['scene_fingerprint']
        for vertex in self.host.scene['meshes'][1]['vertices']:vertex[2]+=.01
        self.host.scene['meshes'][1]['pivot_world'][2]+=.01
        second=self.observe()
        self.assertEqual(self.host.scene['revision'],'r1')
        self.assertNotEqual(second['routing']['scene_fingerprint'],old_fingerprint)
        self.assertNotEqual(second['routing']['observation_id'],first['routing']['observation_id'])
        self.assertAlmostEqual(json.loads(second['routing']['context_text'])['measurement']['signed_clearance_m'],.11)
        self.assertEqual(self.host.captures,2);self.assertEqual(self.host.calls,0)

    def test_corrupt_persisted_snapshot_is_rejected_before_a_new_host_capture(self):
        self.observe();state=self.saved();captures=self.host.captures
        state['runtime']['router']['sessions'][0][1]['scene']['meshes'][0]['vertices'][0][0]+=2
        state['runtime']['router']['sessions'][0][1]['validated']=True
        (self.folder/'state.json').write_text(json.dumps(state),encoding='utf-8')
        with self.assertRaises(ValueError):self.observe()
        self.assertEqual(self.host.captures,captures)
        self.assertEqual(self.host.calls,0)
        self.assertEqual(self.saved(),state)

    def test_partial_unknown_scene_does_not_become_executable_when_pair_goal_is_satisfied(self):
        surface=mesh('open_surface',[10,0,.5],[.1,.1,.1]);surface['faces']=surface['faces'][:2];surface['edges']=None
        self.host.scene['meshes'].append(surface)
        result=self.observe(goal={'target_clearance_m':.1,'clearance_tolerance_m':1e-7})
        self.assertEqual(result['status'],'partial')
        self.assertTrue(result['pair_goal']['satisfied'])
        self.assertEqual(result['action_eligibility']['status'],'blocked')
        self.assertIn('open_surface',result['scene_assessment']['unknown_object_ids'])
        self.assertIsNone(result['routing']['observation_id'])
        self.assertEqual(self.saved()['runtime']['sessions'],[])
        self.assertEqual(self.host.calls,0)

    def test_unpaired_observation_keeps_overview_and_persists_no_capsule(self):
        # The standard two-object fixture has a unique focal flag and pair;
        # a single object is genuinely unpaired.
        self.host.scene['meshes']=self.host.scene['meshes'][:1]
        result=self.service.observe('operation',include_image=False)
        self.assertEqual(result['status'],'overview')
        self.assertTrue(result['routing']['requires_reobserve'])
        self.assertIsNone(result['routing']['observation_id'])
        state=self.saved()
        self.assertEqual(state['runtime']['sessions'],[])
        self.assertNotIn('_ValidatedObservation',json.dumps(state))
        self.assertNotIn('_validated_observation',json.dumps(state))
        self.assertEqual(self.host.calls,0)

    def test_mutating_returned_diagnostics_cannot_poison_the_next_observation(self):
        result=self.observe();result['objects'][0]['name']='return-value poisoning'
        result['routing']['rigid_frame']['objects']['focal']['pivot_world_m'][2]+=99
        saved=self.saved()
        self.assertNotIn('return-value poisoning',json.dumps(saved))
        next_result=self.observe()
        self.assertAlmostEqual(json.loads(next_result['routing']['context_text'])['measurement']['signed_clearance_m'],.1)
        self.assertEqual(self.host.scene['meshes'][1]['pivot_world'][2],.35)


class OperationReuseExecutionFreshnessTests(unittest.TestCase):
    def prepare_private(self,host):
        runtime=GuardedHostRuntime(host,quad_size=64)
        capture=_ValidatedObservation(host.scene)
        prepared=runtime._before_model_on_captured_scene(scene=capture.scene,
            session_id='operation',task_instruction='Measure part clearance.',focal_id='part',reference_id='base',
            messages=[],include_image=False,_validated_observation=capture)
        self.assertEqual(prepared['routing']['route'],'engine')
        return runtime,prepared

    def test_external_obstacle_edit_after_reused_observation_still_blocks_at_fresh_execution(self):
        host=CapturedHost();runtime,prepared=self.prepare_private(host)
        for vertex in host.scene['meshes'][0]['vertices']:vertex[2]+=.2
        host.scene['meshes'][0]['pivot_world'][2]+=.2
        with patch('human_eye_plugin.host_runtime._validated_scene',wraps=_validated_scene) as host_validate, \
                patch('human_eye_plugin.auto_router._validated_scene',wraps=_validated_scene) as router_validate:
            result=runtime.execute_action(session_id='operation',action={'translation':[0,0,0]},
                observation_id=prepared['routing']['observation_id'])
        self.assertEqual(result['status'],'blocked')
        self.assertGreaterEqual(host_validate.call_count,1)
        self.assertGreaterEqual(router_validate.call_count,1)
        self.assertGreaterEqual(host.captures,1)
        self.assertEqual(host.calls,0)

    def test_successful_test_double_action_keeps_independent_precommit_capture_and_readback(self):
        host=CapturedHost();runtime,_=self.prepare_private(host)
        self.assertEqual(host.captures,0)
        with patch('human_eye_plugin.host_runtime._validated_scene',wraps=_validated_scene) as host_validate, \
                patch('human_eye_plugin.auto_router._validated_scene',wraps=_validated_scene) as router_validate:
            result=runtime.execute_action(session_id='operation',action={'translation':[0,0,.05]})
        self.assertEqual(result['status'],'verified',result)
        self.assertTrue(result['execution_verified'])
        self.assertEqual(host.calls,1)
        self.assertEqual(host.captures,2)
        self.assertGreaterEqual(host_validate.call_count,2)
        self.assertGreaterEqual(router_validate.call_count,2)
        self.assertEqual(host.scene['revision'],'r2')


if __name__=='__main__':unittest.main()
