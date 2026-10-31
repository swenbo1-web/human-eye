"""Host routing contracts tested against actual meshes, probes and PNGs."""
import base64
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin.auto_router import HumanEyeAutoRouter


SIGNS = np.array([[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],
                  [-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]], dtype=float)
FACES = [[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],
         [2,3,7],[2,7,6],[1,2,6],[1,6,5],[3,0,4],[3,4,7]]


def box(oid, center, size, focal=False):
    return MeshEntity3D(oid, '#' + oid, oid,
        SIGNS * np.array(size) / 2 + np.array(center), np.array(FACES),
        None, (70, 140, 210), focal, local_axes=np.eye(3)).to_dict()


def scene(revision='r1'):
    return {"revision": revision, "unit": "m", "coordinate_frame": "world",
            "source": "local_contract_fixture", "meshes": [
                box('base', [0,0,.1], [1.4,1.2,.2]),
                box('part', [0,0,.35], [.3,.2,.1], True)]}


def observation(sid='a', **changes):
    event = {'event':'before_model', 'session_id':sid, 'scene':scene(),
             'task_kind':'spatial_3d', 'focal_id':'part', 'reference_id':'base',
             'task_instruction':'Measure clearance.'}
    event.update(changes)
    return event


def action(obs, sid='a', **changes):
    event = {'event':'before_action','session_id':sid,
             'observation_id':obs['observation_id'], 'focal_id':'part','reference_id':'base',
             'action':{'translation':[0,0,.1], 'rotation_euler_deg':[0,0,0]}}
    event.update(changes)
    return event


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.router = HumanEyeAutoRouter(quad_size=64)

    def observe(self, **changes):
        return self.router.handle_event(observation(**changes))

    def test_native_no_scene_does_not_construct_demo(self):
        for kind in ('general','image_2d','ocr',None):
            evt = {'event':'before_model','session_id':'a','task_kind':kind}
            with patch('human_eye_plugin.auto_router.QuadCognitiveCanvasCompositor') as renderer:
                result = self.router.handle_event(evt)
            self.assertEqual(result['route'], 'native'); renderer.assert_not_called()
        self.assertEqual(self.router.export_state()['sessions'], [])

    def test_explicit_native_even_with_scene(self):
        result = self.observe(task_kind='image_2d')
        self.assertEqual(result['route'],'native')

    def test_3d_without_scene_blocks_and_force_does_not_invent_scene(self):
        for router in (self.router, HumanEyeAutoRouter(mode='force_3d')):
            result = router.handle_event({'event':'before_model','session_id':'a','task_kind':'spatial_3d'})
            self.assertEqual(result['reason_codes'],['scene_required'])

    def test_actual_probe_png_no_prescribed_answer(self):
        result = self.observe()
        self.assertEqual(result['route'],'engine', result)
        self.assertTrue(result['engine_invoked']); self.assertTrue(result['measurement_valid'])
        self.assertTrue(result['axes_valid'])
        facts = json.loads(result['context_text'])
        self.assertAlmostEqual(facts['measurement']['signed_clearance_m'], .1)
        for banned in ('canonical_mcp_tool_call','translation_xyz_m','rotation_euler_deg_xyz','system_prompt'):
            self.assertNotIn(banned, result['context_text'])
        with Image.open(io.BytesIO(base64.b64decode(result['image']['data'],validate=True))) as img:
            self.assertEqual(img.size,(128,128)); self.assertEqual(img.format,'PNG')

    def test_cache_deepcopy_and_task_pair_changes(self):
        initial = self.observe(); oid = initial['observation_id']
        initial['image']['data'] = 'mutated'
        cached = self.observe()
        self.assertTrue(cached['cache_hit']); self.assertFalse(cached['engine_invoked'])
        self.assertEqual(cached['observation_id'],oid); self.assertNotEqual(cached['image']['data'],'mutated')
        changed = self.observe(task_instruction='Measure another fact.')
        self.assertNotEqual(changed['observation_id'],oid)
        self.assertFalse(changed['cache_hit'])

    def test_scene_input_not_retained_by_reference(self):
        event = observation(); result = self.router.handle_event(event)
        event['scene']['meshes'][1]['vertices'][0][2] -= .3
        allowed = self.router.handle_event(action(result))
        self.assertTrue(allowed['allow_action'])

    def test_session_isolation_and_session_lru(self):
        result = self.observe()
        self.assertEqual(self.router.handle_event(action(result,sid='b'))['route'],'blocked')
        router = HumanEyeAutoRouter(quad_size=64,max_sessions=1)
        old = router.handle_event(observation('a'))
        router.handle_event(observation('b'))
        self.assertEqual(router.handle_event(action(old))['reason_codes'],['scene_required'])

    def test_revision_geometry_topology_identity_provenance_changes_invalidate(self):
        for mutate in (
            lambda s:s.update(revision='r2'),
            lambda s:s['meshes'][1]['vertices'][0].__setitem__(2,.299),
            lambda s:s['meshes'][1]['faces'].__setitem__(0,[0,1,2]),
            lambda s:s['meshes'][1].update(axes_reason='changed'),
            lambda s:s.update(source='different_host'),
        ):
            self.router = HumanEyeAutoRouter(quad_size=64)
            result = self.observe(); updated = scene(); mutate(updated)
            blocked = self.router.handle_event(action(result,scene=updated))
            self.assertEqual(blocked['reason_codes'],['stale_or_missing_observation'])

    def test_bad_scene_invalidates_previous_observation(self):
        result = self.observe(); bad = scene(); bad['unit']='mm'
        self.assertEqual(self.router.handle_event(action(result,scene=bad))['reason_codes'],['invalid_scene'])
        self.assertFalse(self.router.handle_event(action(result))['allow_action'])

    def test_invalid_geometry_rejected_before_casting(self):
        for mutate in (
            lambda s:s['meshes'][1]['faces'][0].__setitem__(0,2.7),
            lambda s:s['meshes'][1]['faces'][0].__setitem__(0,-1),
            lambda s:s['meshes'][1]['faces'][0].__setitem__(0,999),
            lambda s:s['meshes'][1]['vertices'][0].__setitem__(0,float('nan')),
            lambda s:s['meshes'][1].update(object_id='base'),
            lambda s:s['meshes'][1].update(mark_label='#base'),
            lambda s:s['meshes'][1].update(pivot_world=[1,2]),
        ):
            bad = scene(); mutate(bad)
            self.assertEqual(self.observe(scene=bad)['reason_codes'],['invalid_scene'])

    def test_no_object_id_fallback(self):
        self.assertEqual(self.observe(focal_id='missing')['reason_codes'],['pair_or_frame_required'])
        third = scene(); third['meshes'].append(box('third',[2,0,.2],[.1,.1,.1]))
        event = observation(scene=third); event.pop('reference_id')
        self.assertEqual(self.router.handle_event(event)['reason_codes'],['pair_or_frame_required'])

    def test_ttl_expiry_future_clock_and_reobserve(self):
        now = [1000.]
        self.router = HumanEyeAutoRouter(quad_size=64,clock=lambda:now[0],observation_ttl_s=5)
        result = self.observe(); now[0]=1006
        self.assertEqual(self.router.handle_event(action(result))['reason_codes'],['observation_expired'])
        new = self.observe(); self.assertNotEqual(new['observation_id'],result['observation_id'])
        now[0] = 990
        self.assertEqual(self.router.handle_event(action(new))['reason_codes'],['observation_expired'])

    def test_exact_proposal_collision_blocked_no_nominal_correction(self):
        result = self.observe()
        blocked = self.router.handle_event(action(result, action={'translation':[0,0,-.15]}))
        self.assertEqual(blocked['reason_codes'],['candidate_collision'])
        self.assertTrue(blocked['engine_invoked'])

    def test_third_object_collision_is_checked(self):
        sc = scene(); sc['meshes'].append(box('obstacle',[.5,0,.35],[.2,.2,.2]))
        result = self.observe(scene=sc)
        blocked = self.router.handle_event(action(result,action={'translation':[.5,0,0]}))
        self.assertEqual(blocked['reason_codes'],['candidate_collision'])
        self.assertIn('obstacle',blocked['context_text'])

    def test_unknown_third_geometry_not_certified(self):
        sc=scene(); third=box('obstacle',[.5,0,.35],[.2,.2,.2]);third['faces']=third['faces'][:-2]
        sc['meshes'].append(third); result=self.observe(scene=sc)
        blocked=self.router.handle_event(action(result,action={'translation':[.5,0,0]}))
        self.assertFalse(blocked['allow_action'])

    def test_open_target_and_ambiguous_axes_cannot_drive_action(self):
        for field in ('faces','axes'):
            sc=scene()
            if field=='faces':sc['meshes'][1]['faces']=sc['meshes'][1]['faces'][:-2]
            else:
                sc['meshes'][1].pop('local_axes');sc['meshes'][1]['axes_source']='inferred_pca'
                sc['meshes'][1]['axes_confidence']='ambiguous'
                sc['meshes'][1]['vertices']=(SIGNS*.1+[0,0,.35]).tolist()
            result=self.observe(scene=sc)
            self.assertFalse(self.router.handle_event(action(result))['allow_action'])

    def test_unsupported_or_nonfinite_action_rejected(self):
        result = self.observe()
        for command in ({}, {'quaternion':[1,0,0,0]}, {'translation':[0,0,0],'rotation_quaternion_wxyz':[1,0,0,0]},
                        {'translation':[float('nan'),0,0]}, {'translation':[True,0,0]},
                        {'translation':[0,0]}, {'translation':['1',0,0]}):
            self.assertFalse(self.router.handle_event(action(result,action=command))['allow_action'])

    def test_pair_yaw_binding(self):
        result=self.observe()
        self.assertEqual(self.router.handle_event(action(result,yaw_symmetry_order=4))['reason_codes'],['observation_pair_mismatch'])
        self.assertEqual(self.router.handle_event(action(result,focal_id='base',reference_id='part'))['reason_codes'],['observation_pair_mismatch'])

    def test_action_ids_cannot_conflict_with_measured_pair(self):
        result=self.observe()
        blocked=self.router.handle_event(action(result,action={
            'focal_id':'base','reference_id':'part','translation':[0,0,0]}))
        self.assertFalse(blocked['allow_action'])

    def test_native_request_scene_update_invalidates_old_authority(self):
        old=self.observe();sc=scene('r2')
        sc['meshes'][1]=MeshEntity3D.from_dict(sc['meshes'][1]).translated([0,0,-.15]).to_dict()
        native=self.observe(scene=sc,task_kind='general')
        self.assertEqual(native['route'],'native');self.assertEqual(native['scene_revision'],'r2')
        self.assertFalse(self.router.handle_event(action(old))['allow_action'])

    def test_allowed_action_is_not_execution_and_requires_readback(self):
        result=self.observe(); permitted=self.router.handle_event(action(result))
        self.assertTrue(permitted['allow_action']);self.assertEqual(permitted['execution_scope'],'terminal_geometry_only')
        self.assertFalse(json.loads(permitted['context_text'])['host_execution_verified'])
        self.assertEqual(self.router.handle_event(action(result))['reason_codes'],['action_pending_readback'])
        after={'event':'after_action','session_id':'a','focal_id':'part','reference_id':'base','scene':scene()}
        self.assertEqual(self.router.handle_event(after)['reason_codes'],['host_readback_required'])

    def test_missing_readback_cannot_reauthorize_old_scene(self):
        result=self.observe();self.router.handle_event(action(result))
        post={'event':'after_action','session_id':'a'}
        self.assertEqual(self.router.handle_event(post)['reason_codes'],['host_readback_required'])
        reobserved=self.router.handle_event({'event':'before_model','session_id':'a','task_kind':'spatial_3d'})
        self.assertFalse(self.router.handle_event(action(reobserved))['allow_action'])
        fresh=self.observe(scene=scene('r2'))
        self.assertTrue(self.router.handle_event(action(fresh))['allow_action'])

    def test_invalid_scene_or_same_revision_geometry_cannot_clear_pending(self):
        for bad_kind in ('invalid','same_revision_changed'):
            self.router=HumanEyeAutoRouter(quad_size=64)
            result=self.observe();self.router.handle_event(action(result))
            sc=scene()
            if bad_kind=='invalid':sc['unit']='mm'
            else:sc['meshes'][1]['vertices'][0][0] += .01
            self.observe(scene=sc)
            again=self.observe()
            self.assertFalse(self.router.handle_event(action(again))['allow_action'])

    def test_lru_does_not_drop_pending_host_readback(self):
        self.router=HumanEyeAutoRouter(quad_size=64,max_sessions=1)
        result=self.observe();self.router.handle_event(action(result))
        other=self.router.handle_event(observation('b'))
        self.assertEqual(other['reason_codes'],['sessions_awaiting_host_readback'])
        old=self.observe()
        self.assertFalse(self.router.handle_event(action(old))['allow_action'])

    def test_engine_failure_does_not_erase_pending_readback(self):
        result=self.observe();self.router.handle_event(action(result))
        with patch('human_eye_plugin.auto_router.SpatialAnomalySniffer.probe_closest_clearance',
                   side_effect=RuntimeError('simulated engine error')):
            failed=self.observe()
        self.assertEqual(failed['reason_codes'],['engine_error'])
        observed=self.observe()
        self.assertFalse(self.router.handle_event(action(observed))['allow_action'])

    def test_realistic_host_readback_matches_proposed_transform(self):
        result=self.observe();self.router.handle_event(action(result))
        sc=scene('r2')
        sc['meshes'][1]=MeshEntity3D.from_dict(sc['meshes'][1]).translated([0,0,.1]).to_dict()
        post=self.router.handle_event({'event':'after_action','session_id':'a','scene':sc,
                                       'focal_id':'part','reference_id':'base'})
        self.assertEqual(post['route'],'engine',post)
        self.assertAlmostEqual(json.loads(post['context_text'])['measurement']['signed_clearance_m'],.2)
        self.assertNotEqual(post['observation_id'],result['observation_id'])

    def test_mismatched_host_readback_blocks(self):
        result=self.observe();self.router.handle_event(action(result))
        post=self.router.handle_event({'event':'after_action','session_id':'a','scene':scene('r2')})
        self.assertEqual(post['reason_codes'],['host_action_mismatch'])

    def test_readback_checks_topology_and_provenance(self):
        for mutate in (
            lambda m:m['faces'].__setitem__(0,[0,1,2]),
            lambda m:m.update(axes_reason='different_frame_origin'),
        ):
            self.router=HumanEyeAutoRouter(quad_size=64)
            result=self.observe();self.router.handle_event(action(result))
            sc=scene('r2');sc['meshes'][1]=MeshEntity3D.from_dict(
                sc['meshes'][1]).translated([0,0,.1]).to_dict()
            mutate(sc['meshes'][1])
            post=self.router.handle_event({'event':'after_action','session_id':'a','scene':sc})
            self.assertEqual(post['reason_codes'],['host_action_mismatch'])

    def test_readback_checks_moving_third_object(self):
        sc=scene();sc['meshes'].append(box('obstacle',[1,0,.35],[.2,.2,.2]))
        result=self.observe(scene=sc);self.assertTrue(self.router.handle_event(action(result))['allow_action'])
        sc['revision']='r2'
        sc['meshes'][1]=MeshEntity3D.from_dict(sc['meshes'][1]).translated([0,0,.1]).to_dict()
        sc['meshes'][2]=box('obstacle',[0,0,.45],[.2,.2,.2])
        post=self.router.handle_event({'event':'after_action','session_id':'a','scene':sc,
                                      'focal_id':'part','reference_id':'base'})
        self.assertEqual(post['reason_codes'],['host_collision_detected'])

    def test_off_does_not_bypass_action_guard(self):
        router=HumanEyeAutoRouter(mode='off')
        self.assertEqual(router.handle_event(observation())['route'],'native')
        self.assertFalse(router.handle_event(action({'observation_id':'fake'}))['allow_action'])

    def test_export_import_and_corrupt_state(self):
        result=self.observe();state=self.router.export_state()
        other=HumanEyeAutoRouter(quad_size=64);other.import_state(state)
        self.assertTrue(other.handle_event(action(result))['allow_action'])
        state['sessions'][0][1]['scene']['revision']='corrupt'
        with self.assertRaises(ValueError):other.import_state(state)

    def test_large_world_scene_keeps_measurements_and_fits_canvas(self):
        sc=scene()
        for mesh in sc['meshes']:
            mesh['vertices']=(np.array(mesh['vertices'])+[100,0,0]).tolist()
        result=self.observe(scene=sc)
        self.assertEqual(result['route'],'engine');self.assertIsNotNone(result['image'])
        facts=json.loads(result['context_text'])
        self.assertFalse(facts['canvas']['geometry_scaled'])
        self.assertEqual(facts['canvas']['renderer'],'adaptive_world_metre_surface_raster_v1')
        self.assertTrue(all(view['geometry_depth_pixels'] > 0 for view in facts['canvas']['views']))

    def test_jsonlines_worker_survives_error_and_persists_session(self):
        request=observation()
        lines=[{'id':1,'payload':request}, {'id':2,'payload':request}]
        run=subprocess.run([sys.executable,'-B','-m','human_eye_plugin.router_server','--quad-size','64'],
                           input='broken\n'+ '{"id":NaN,"event":"before_model","session_id":"a"}\n'+
                                 '{"id":{},"event":"before_model","session_id":"a"}\n'+
                                 '\n'.join(json.dumps(x) for x in lines)+'\n',
                           text=True,capture_output=True,cwd=Path(__file__).resolve().parents[1],timeout=20)
        self.assertEqual(run.returncode,0,run.stderr)
        output=[json.loads(x) for x in run.stdout.splitlines()]
        for result in output[:3]:self.assertIn('error',result)
        self.assertEqual(output[3]['id'],1)
        self.assertTrue(output[4]['result']['cache_hit'])


if __name__=='__main__':unittest.main()
