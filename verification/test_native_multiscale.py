"""Geometric opportunity and atomic lifecycle contracts, no Blender started.

Actual pixel quality and real RNA proof must be checked by owned acceptance.
"""
from __future__ import annotations
import base64,copy,hashlib,math,time,unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
from human_eye_plugin import episode_gateway as episode
from verification import test_readonly_render_gateway as old_render


FACES=[[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],
       [2,3,7],[2,7,6],[1,2,6],[1,6,5],[3,0,4],[3,4,7]]
SIGNS=[(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]

def box(identity,center,size):
    points=[[center[k]+sign[k]*size[k]/2 for k in range(3)] for sign in SIGNS]
    return {'object_id':identity,'world_vertices':points,'faces':copy.deepcopy(FACES)}

def scene(kind='standard',view='SCENE'):
    native={'unit':'m','coordinate_frame':'world','revision':'native:multiscale-pure','objects':[
        box('base',[0.,0.,0.],[.2,.2,.2]),box('part',[0.,0.,.154],[.06,.06,.1])]}
    if kind in ('deep','occluded','dense'):
        native['objects'].append(box('remote',[.4,.4,20. if kind!='dense' else .4],[.1,.1,.1]))
    if kind=='long':
        native['objects'][0]=box('base',[0.,0.,0.],[200.,.2,.2])
        native['objects'][1]=box('part',[0.,0.,.154],[60.,.06,.1])
    if kind=='occluded':
        direction=episode._native_view_frame(native,view,1.)['direction']
        native['objects'].append(box('occluder',[direction[k]*.5+([0.,0.,.154][k]) for k in range(3)],[.3,.3,.3]))
    return native

def camera(frame):
    axes=[frame[key] for key in ('right','up','direction')]
    matrix=[[axes[c][r] for c in range(3)]+[frame['camera_location_bu'][r]] for r in range(3)]
    matrix.append([0.,0.,0.,1.])
    return NS(matrix_world=matrix),NS(ortho_scale=frame['ortho_scale_bu'],
        clip_start=frame['clip_start_bu'],clip_end=frame['clip_end_bu'])

RENDER=NS(resolution_x=384,resolution_y=384,resolution_percentage=100,pixel_aspect_x=1.,pixel_aspect_y=1.)

class NativeMultiscaleGeometryTests(unittest.TestCase):
    def plan(self,native,view='SCENE',scale=1.,**options):
        return episode.plan_native_multiscale(native,'part',view,scale,**options)

    def test_ordinary_scene_keeps_one_image_and_never_traces_extra_ray(self):
        for kind in ('standard','dense'):
            for view in ('XY','XZ','SCENE'):
                native=scene(kind);before=copy.deepcopy(native)
                with patch.object(episode,'_central_focal_sample',side_effect=AssertionError('unnecessary ray')):
                    plan,_,detail=self.plan(native,view)
                self.assertFalse(plan['detail_included']);self.assertEqual(plan['image_count'],1)
                self.assertEqual(plan['reason_code'],'overview_sufficient');self.assertIsNone(detail)
                self.assertEqual(native,before)

    def test_xy_basis_matches_existing_real_track_quaternion_roll(self):
        # Regression from the factory Blender5.2 mathutils probe: the existing
        # axial to_track_quat/Euler renderer has right=-X and up=-Y, not +X/+Y.
        plan,frame,_=self.plan(scene(),'XY')
        self.assertEqual(frame['right'],[-1.,0.,0.])
        self.assertEqual(frame['up'],[0.,-1.,0.])
        self.assertEqual(plan['overview']['eye_direction_world'],[0.,0.,1.])

    def test_deep_scene_adds_detail_only_for_diluted_views(self):
        native=scene('deep')
        self.assertFalse(self.plan(native,'XY')[0]['detail_included'])
        for view in ('XZ','SCENE'):
            plan,overview,detail=self.plan(native,view)
            self.assertTrue(plan['detail_included']);self.assertEqual(plan['image_count'],2)
            self.assertLess(plan['feature']['overview_px'],12)
            self.assertGreaterEqual(plan['feature']['detail_px'],32)
            self.assertGreater(plan['feature']['zoom'],2)
            self.assertEqual(plan['visibility']['status'],'focal_first')
            self.assertEqual(plan['detail']['screen_coverage'],'intentional_local_window')

    def test_long_diagonal_object_is_not_mistaken_for_thick_axis_aligned_bbox(self):
        for view in ('XY','XZ','SCENE'):
            plan,_,detail=self.plan(scene('long'),view)
            self.assertTrue(plan['detail_included'])
            self.assertLess(plan['feature']['overview_px'],1)
            self.assertGreater(plan['feature']['zoom'],32)
            self.assertLessEqual(plan['feature']['zoom'],4096)

    def test_same_scene_keeps_occluder_and_declines_unhelpful_hidden_detail(self):
        native=scene('occluded','SCENE');before=copy.deepcopy(native)
        plan,_,detail=self.plan(native)
        self.assertLess(plan['feature']['overview_px'],12)
        self.assertEqual(plan['visibility']['status'],'other_or_uncertain')
        self.assertEqual(plan['reason_code'],'central_ray_occluded_or_unknown')
        self.assertFalse(plan['detail_included']);self.assertIsNone(detail)
        self.assertEqual(native,before)

    def test_hidden_focal_declines_detail_without_tracing_or_hiding_other_assets(self):
        with patch.object(episode,'_central_focal_sample',side_effect=AssertionError('hidden focal ray')):
            plan,_,detail=self.plan(scene('long'),focal_hidden_render=True)
        self.assertEqual(plan['reason_code'],'focal_not_renderable');self.assertIsNone(detail)

    def test_focus_and_scene_sampling_work_are_bounded(self):
        native=scene('long');native['objects'][1]['world_vertices']*=9
        with patch.object(episode,'_central_focal_sample') as ray:
            plan,_,detail=self.plan(native)
        self.assertEqual(plan['reason_code'],'focus_budget_exceeded');ray.assert_not_called();self.assertIsNone(detail)
        native=scene('long');native['objects'][0]['faces']*=400
        plan,_,detail=self.plan(native)
        self.assertEqual(plan['reason_code'],'occlusion_budget_exceeded');self.assertIsNone(detail)

    def test_zoom_cap_does_not_buy_a_useless_extra_frame(self):
        native=scene('deep');native['objects'][-1]=box('remote',[.4,.4,1e8],[.1,.1,.1])
        plan,_,detail=self.plan(native,'XZ')
        self.assertEqual(plan['reason_code'],'detail_insufficient_at_zoom_cap')
        self.assertIsNone(detail);self.assertEqual(plan['feature']['zoom'],4096)

    def test_physical_plan_and_decision_are_unit_covariant(self):
        native=scene('long');reference=self.plan(native,'SCENE')[0]
        for scale in (.001,1000.):
            plan,_,_=self.plan(native,'SCENE',scale)
            self.assertEqual(plan['detail_included'],reference['detail_included'])
            for key in ('width_m','overview_px','detail_px','zoom'):
                self.assertAlmostEqual(plan['feature'][key],reference['feature'][key],places=9)
            for axis in range(3):self.assertAlmostEqual(plan['detail']['center_world_m'][axis],reference['detail']['center_world_m'][axis])

    def test_private_frustum_crops_screen_but_keeps_all_depth_and_center(self):
        native=scene('long');plan,overview,detail=self.plan(native)
        obj,data=camera(detail)
        proof=episode._check_native_view_frame(obj,data,native,1.,detail,
            screen_coverage='intentional_local_window',render=RENDER,view='SCENE')
        self.assertEqual(proof['depth_vertex_count'],16);self.assertEqual(proof['screen_vertex_count'],1)
        self.assertGreater(max(proof['max_abs_screen_bu']),data.ortho_scale/2)
        self.assertGreaterEqual(proof['min_depth_bu'],data.clip_start)
        self.assertLessEqual(proof['max_depth_bu'],data.clip_end)
        self.assertTrue(all(abs(x)<.02 for x in proof['center_ndc']))
        bad,data2=camera(detail)
        for row in range(3):bad.matrix_world[row][0]*=1.01
        with self.assertRaisesRegex(episode.EpisodePrewriteRefused,'orientation_changed'):
            episode._check_native_view_frame(bad,data2,native,1.,detail,
                screen_coverage='intentional_local_window',render=RENDER,view='SCENE')
        with self.assertRaises(episode.EpisodePrewriteRefused):
            episode._check_native_view_frame(obj,data,native,1.,detail)
        obj.matrix_world[0][3]+=1.
        with self.assertRaisesRegex(episode.EpisodePrewriteRefused,'center_quantized'):
            episode._check_native_view_frame(obj,data,native,1.,detail,
                screen_coverage='intentional_local_window',render=RENDER,view='SCENE')


class NativeMultiscaleLifecycleTests(unittest.TestCase):
    def ready(self):
        host,module,state=old_render.RenderLifecycleTests().ready()
        native=host.native_scene_query();frame=module._native_view_frame(native,'SCENE',host._scale())
        focal=state['record']['binding']['focal_id']
        plan,_,_=module.plan_native_multiscale(native,focal,'SCENE',host._scale())
        plan.update(image_count=2,detail_included=True,detail=module._public_view_frame(frame,host._scale(),'intentional_local_window'))
        self.host,self.module,self.state,self.native=host,module,state,native
        self.plan,self.frame=plan,frame
        return host

    def fake_render(self,bpy,scene,layer,native,view,**options):
        proof={'fake_actual_frustum':True}
        options['_frustum_sink'].append(proof)
        raw=b'fake native image '+str(len(getattr(self,'rendered',[]))).encode()
        self.rendered=getattr(self,'rendered',[])+[raw]
        return {'mime_type':'image/png','image_base64':base64.b64encode(raw).decode(),
            'width':384,'height':384,'view':view,'source':'hostdouble_only'}

    def patches(self,renderer=None):
        return (patch.object(self.module,'plan_native_multiscale',return_value=(self.plan,self.frame,self.frame)),
                patch.object(self.module,'native_render_state',side_effect=lambda *args:copy.deepcopy(old_render.state_sample())),
                patch.object(self.module,'native_look',side_effect=renderer or self.fake_render))

    def test_two_frames_are_atomic_detached_and_charge_no_motion_or_deadline(self):
        host=self.ready();before=host.owned_episode_status()
        a,b,c=self.patches()
        with a,b,c:value=host.native_look_multiscale('SCENE')
        audit=host.last_native_multiscale_audit()
        self.assertEqual(audit['status'],'completed');self.assertEqual(set(value),{'overview','detail','plan'})
        self.assertEqual([row['kind'] for row in audit['frames']],['overview','detail'])
        self.assertEqual([row['render_audit']['sequence'] for row in audit['frames']],[1,2])
        self.assertEqual(audit['native_revision_before'],audit['native_revision_after'])
        for i,row in enumerate(audit['frames']):
            self.assertTrue(row['render_audit']['restored']);self.assertEqual(row['png_sha256'],hashlib.sha256(self.rendered[i]).hexdigest())
        value['plan']['detail_included']=False;audit['frames'].clear()
        self.assertTrue(host.last_native_multiscale_audit()['plan']['detail_included'])
        after=host.owned_episode_status()
        for key in ('events','remaining_setters','remaining_translation_m','deadline_ns','limits'):
            self.assertEqual(after[key],before[key])

    def test_second_failure_never_publishes_partial_success_and_freezes_episode(self):
        host=self.ready();calls=[]
        def render(*args,**options):
            calls.append(True)
            if len(calls)==2:raise RuntimeError('owner-private detail failure')
            return self.fake_render(*args,**options)
        a,b,c=self.patches(render)
        with a,b,c,self.assertRaises(RuntimeError):host.native_look_multiscale('SCENE')
        audit=host.last_native_multiscale_audit()
        self.assertEqual(audit['status'],'failed');self.assertEqual(len(audit['frames']),2)
        self.assertEqual(audit['frames'][0]['render_audit']['status'],'completed')
        self.assertEqual(audit['frames'][1]['render_audit']['status'],'failed')
        self.assertIsNone(audit['frames'][1]['png_sha256'])
        self.assertEqual(host.owned_episode_status()['actual_setter_count'],0)
        self.assertIsNotNone(host.owned_episode_status()['frozen_reason'])

    def test_revision_drift_between_frames_stops_before_second_render(self):
        host=self.ready();original=host._native_render_view;calls=[]
        def changed(*args,**options):
            value=original(*args,**options);calls.append(True)
            if len(calls)==1:
                obj=next(o for o in host._objects(host._depsgraph()) if host.object_id(o)==self.state['record']['binding']['focal_id'])
                obj._matrix_world[2][3]+=.0001
            return value
        a,b,c=self.patches()
        with a,b,c,patch.object(host,'_native_render_view',side_effect=changed),self.assertRaises(Exception):
            host.native_look_multiscale('SCENE')
        self.assertEqual(len(self.rendered),1)
        self.assertEqual(host.last_native_multiscale_audit()['status'],'failed')

    def test_original_deadline_expiring_after_overview_cannot_start_detail(self):
        host=self.ready();original=host._native_render_view
        deadline=host.owned_episode_status()['deadline_ns'];now=[time.perf_counter_ns()]
        def finish_at_deadline(*args,**options):
            value=original(*args,**options);now[0]=deadline;return value
        a,b,c=self.patches()
        with a,b,c,patch.object(time,'perf_counter_ns',side_effect=lambda:now[0]),\
             patch.object(host,'_native_render_view',side_effect=finish_at_deadline),\
             self.assertRaisesRegex(Exception,'original_deadline_expired'):
            host.native_look_multiscale('SCENE')
        audit=host.last_native_multiscale_audit()
        self.assertEqual(len(self.rendered),1);self.assertEqual(audit['status'],'failed')
        self.assertEqual(len(audit['frames']),1)
        self.assertEqual(host.owned_episode_status()['deadline_ns'],deadline)


if __name__=='__main__':unittest.main()
