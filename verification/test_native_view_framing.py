"""Independent frustum invariants for native view framing; no Blender starts.

These tests reconstruct camera-space screen/depth coordinates from the returned
basis. They do not assume the helper's distance, padding or clipping formula.
Actual Blender float32 assignment, rendering and restoration need owned tests.
"""
from __future__ import annotations

import copy,math,unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

from human_eye_plugin import episode_gateway as episode
from verification.model_trial import common_owned_gateway as common
from verification.test_readonly_render_gateway import render_fixture,state_sample
from verification import test_readonly_render_gateway as render_tests
from verification.test_episode_gateway import translated


def native_boxes(*,center=(.071,-.043,.02),size=(.2,.2,.2),separation=.004):
    signs=[(x,y,z) for x in (-1.,1.) for y in (-1.,1.) for z in (-1.,1.)]
    # Faces are valid quads for this vertex ordering. Geometry is public, finite
    # and independent; no privileged target label enters the view calculation.
    faces=[[0,1,3,2],[4,6,7,5],[0,4,5,1],[2,3,7,6],[0,2,6,4],[1,5,7,3]]
    result={'unit':'m','coordinate_frame':'world','revision':'fixture:native-frustum','objects':[]}
    for index in range(2):
        pos=list(center);pos[2]+=index*(size[2]+separation)
        local=[[s[k]*size[k]/2 for k in range(3)] for s in signs]
        matrix=[[1.,0.,0.,pos[0]],[0.,1.,0.,pos[1]],[0.,0.,1.,pos[2]],[0.,0.,0.,1.]]
        result['objects'].append({'object_id':'obj'+str(index),'name':'Mesh'+str(index),
            'local_vertices':local,'world_vertices':[[v[k]+pos[k] for k in range(3)] for v in local],
            'matrix':matrix,'faces':copy.deepcopy(faces),'color':[.2,.4,.8,1.]})
    return result


def dot(a,b):return math.fsum(x*y for x,y in zip(a,b))
def difference(a,b):return [x-y for x,y in zip(a,b)]


class NativeViewFramingTests(unittest.TestCase):
    def frame(self,native,view,scale):return episode._native_view_frame(native,view,scale)

    def assert_contains(self,native,view,scale):
        before=copy.deepcopy(native);frame=self.frame(native,view,scale)
        self.assertEqual(native,before,'View planning may not modify the public mesh packet')
        fields={'center_bu','direction','right','up','camera_location_bu',
                'ortho_scale_bu','clip_start_bu','clip_end_bu'}
        self.assertTrue(fields<=set(frame))
        for field in ('center_bu','direction','right','up','camera_location_bu'):
            self.assertEqual(len(frame[field]),3)
            self.assertTrue(all(type(x) in (int,float) and math.isfinite(x) for x in frame[field]))
        axes=[frame[field] for field in ('right','up','direction')]
        for axis in axes:self.assertAlmostEqual(dot(axis,axis),1.,places=12)
        for a,b in ((0,1),(0,2),(1,2)):self.assertAlmostEqual(dot(axes[a],axes[b]),0.,places=12)
        self.assertGreater(frame['ortho_scale_bu'],0.)
        self.assertGreater(frame['clip_start_bu'],0.)
        self.assertGreater(frame['clip_end_bu'],frame['clip_start_bu'])
        screen=[]
        for obj in native['objects']:
            for point in obj['world_vertices']:
                host=[p/scale for p in point]
                relative=difference(host,frame['camera_location_bu'])
                x=dot(relative,frame['right']);y=dot(relative,frame['up'])
                depth=-dot(relative,frame['direction'])
                tolerance=max(1.,abs(x),abs(y),depth)*1e-10
                self.assertLessEqual(abs(x),frame['ortho_scale_bu']/2+tolerance)
                self.assertLessEqual(abs(y),frame['ortho_scale_bu']/2+tolerance)
                self.assertGreaterEqual(depth,frame['clip_start_bu']-tolerance)
                self.assertLessEqual(depth,frame['clip_end_bu']+tolerance)
                screen.append((x/frame['ortho_scale_bu'],y/frame['ortho_scale_bu']))
        return frame,screen

    def test_all_views_contain_standard_geometry_and_depth_stretched_geometry(self):
        for size in ((.2,.2,.2),(.2,.2,20.),(40.,.1,.2),(.1,40.,.2)):
            for view in ('XY','XZ','SCENE'):
                with self.subTest(size=size,view=view):
                    self.assert_contains(native_boxes(size=size),view,1.)

    def test_same_physical_scene_uses_equivalent_projection_across_unit_scales(self):
        native=native_boxes()
        for view in ('XY','XZ','SCENE'):
            reference,screen=self.assert_contains(native,view,1.)
            for scale in (.001,1000.):
                with self.subTest(view=view,scale=scale):
                    value,other=self.assert_contains(native,view,scale)
                    for a,b in zip(screen,other):
                        for x,y in zip(a,b):self.assertAlmostEqual(x,y,places=10)
                    self.assertAlmostEqual(value['ortho_scale_bu']*scale,reference['ortho_scale_bu'],places=10)

    def test_translation_changes_camera_but_preserves_projection(self):
        standard=native_boxes()
        translated=native_boxes(center=(1000000.071,-1000000.043,1000000.02))
        for view in ('XY','XZ','SCENE'):
            _,screen=self.assert_contains(standard,view,1.)
            _,other=self.assert_contains(translated,view,1.)
            for a,b in zip(screen,other):
                for x,y in zip(a,b):self.assertAlmostEqual(x,y,places=7)

    def test_extreme_aspect_is_contained_without_claiming_subpixel_legibility(self):
        native=native_boxes(size=(100.,.001,.001))
        for view in ('XY','XZ','SCENE'):
            self.assert_contains(native,view,1.)

    def test_vertex_and_object_permutations_do_not_change_framing(self):
        original=native_boxes(size=(1.,2.,3.));other=copy.deepcopy(original)
        other['objects'].reverse()
        for obj in other['objects']:obj['world_vertices'].reverse()
        for view in ('XY','XZ','SCENE'):
            self.assertEqual(self.frame(original,view,1.),self.frame(other,view,1.))

    def test_invalid_unit_and_view_rejected(self):
        for bad in (0.,-1.,True,False,None,'1',math.inf,math.nan):
            with self.subTest(scale=bad):
                with self.assertRaises(episode.EpisodePrewriteRefused):self.frame(native_boxes(),'XY',bad)
        for bad in ('', 'xy', None,1):
            with self.subTest(view=bad):
                with self.assertRaises(episode.EpisodePrewriteRefused):self.frame(native_boxes(),bad,1.)

    def test_empty_nonfinite_and_overflowing_geometry_rejected(self):
        variants=[]
        bad=native_boxes();bad['objects']=[];variants.append(bad)
        bad=native_boxes();bad['objects'][0]['world_vertices']=[];variants.append(bad)
        bad=native_boxes()
        for obj in bad['objects']:obj['world_vertices']=[[0.,0.,0.] for _ in obj['world_vertices']]
        variants.append(bad)
        for value in (math.nan,math.inf,-math.inf,True,'1'):
            bad=native_boxes();bad['objects'][0]['world_vertices'][0][0]=value;variants.append(bad)
        for bad in variants:
            with self.subTest(packet=str(bad)[:120]):
                with self.assertRaises(episode.EpisodePrewriteRefused):self.frame(bad,'XY',1.)
        huge=native_boxes(center=(1e40,0.,0.))
        with self.assertRaises(episode.EpisodePrewriteRefused):self.frame(huge,'XY',1e-10)

    def test_actual_readback_refuses_clamped_camera_values_and_missing_frustum_coverage(self):
        native=native_boxes();scale=1.;frame=self.frame(native,'SCENE',scale)
        def camera():
            axes=[frame[key] for key in ('right','up','direction')]
            matrix=[[axes[col][row] for col in range(3)]+[frame['camera_location_bu'][row]] for row in range(3)]
            matrix.append([0.,0.,0.,1.])
            return NS(matrix_world=matrix),NS(ortho_scale=frame['ortho_scale_bu'],
                clip_start=frame['clip_start_bu'],clip_end=frame['clip_end_bu'])
        obj,data=camera()
        episode._check_native_view_frame(obj,data,native,scale,frame)
        for key in ('ortho_scale','clip_start','clip_end'):
            with self.subTest(field=key):
                obj,data=camera();setattr(data,key,getattr(data,key)*.5)
                with self.assertRaisesRegex(episode.EpisodePrewriteRefused,'parameter_clamped'):
                    episode._check_native_view_frame(obj,data,native,scale,frame)
        obj,data=camera();obj.matrix_world[0][3]+=100.
        with self.assertRaisesRegex(episode.EpisodePrewriteRefused,'frustum_incomplete'):
            episode._check_native_view_frame(obj,data,native,scale,frame)

    def test_no_enabled_view_layer_refused_before_assets_or_mathutils_import(self):
        for layers in ([],[NS(use=False)],[NS(use=False),NS(use=False)]):
            with self.subTest(layers=layers):
                with self.assertRaisesRegex(episode.EpisodePrewriteRefused,'native_view_layer_unavailable'):
                    episode.native_look(None,NS(view_layers=layers),NS(),native_boxes(),'XY')

    def test_host_renders_fresh_geometry_instead_of_initial_episode_snapshot(self):
        host,module,state=render_tests.RenderLifecycleTests().ready()
        initial=host.owned_episode_status()['initial_native']
        focal=state['record']['binding']['focal_id']
        fresh=translated(initial,focal,.0005)
        self.assertNotEqual(fresh,initial)
        before=state_sample()
        with patch.object(module,'native_render_state',side_effect=[before,copy.deepcopy(before)]),\
             patch.object(host,'native_scene_query',side_effect=[copy.deepcopy(fresh),copy.deepcopy(fresh)]),\
             patch.object(module,'native_look',return_value={'image':True}) as render:
            self.assertEqual(host.native_look('SCENE'),{'image':True})
        self.assertEqual(render.call_args.args[3],fresh)
        self.assertNotEqual(render.call_args.args[3],initial)
        self.assertTrue(host.last_native_render_audit()['restored'])


class NativeRenderFramingAuditTests(unittest.TestCase):
    def actual_state_double(self):
        host,_,_,_=render_fixture()
        return episode.native_render_state(host.bpy,host.scene,host.view_layer)

    def test_each_normalized_framing_property_is_in_audit_and_required_by_consumer(self):
        state=self.actual_state_double()
        expected={'pixel_aspect_x':1.7,'pixel_aspect_y':.6,'use_border':True,'use_crop_to_border':True,
            'border_min_x':.13,'border_max_x':.79,'border_min_y':.21,'border_max_y':.92}
        names=[row['identity']['name'] for row in state['scene_objects'] if row['type']=='MESH']
        common._validate_private_render_state(state,names)
        for key,value in expected.items():
            with self.subTest(field=key):
                self.assertEqual(state['render'][key],value)
                missing=copy.deepcopy(state);del missing['render'][key]
                with self.assertRaises(ValueError):common._validate_private_render_state(missing,names)

    def test_invalid_framing_field_types_and_ranges_are_rejected(self):
        state=self.actual_state_double()
        names=[row['identity']['name'] for row in state['scene_objects'] if row['type']=='MESH']
        for key,bad_value in (('pixel_aspect_x',0.),('pixel_aspect_y',math.nan),
                ('pixel_aspect_x',True),('use_border',1),('use_crop_to_border','false'),
                ('border_min_x',-.01),('border_max_y',1.01),('border_min_y',math.inf)):
            with self.subTest(field=key,value=bad_value):
                bad=copy.deepcopy(state);bad['render'][key]=bad_value
                with self.assertRaises(ValueError):common._validate_private_render_state(bad,names)


if __name__=='__main__':unittest.main()
