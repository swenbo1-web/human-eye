"""Independent typed-read and render-restoration contracts without Blender I/O.

The native-evidence tests exercise the real producer against existing bpy
doubles. Render lifecycle tests isolate only rendering and state readback; root
must separately verify actual Blender state, images and metadata negotiation.
"""
from __future__ import annotations

import copy,json,time,unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch

from human_eye_plugin import episode_gateway as episode
from human_eye_plugin.blender_process import BlenderProcessHost
from human_eye_plugin.forward_deadline import counter_descriptor
from verification.test_blender_native_evidence import fixture,evaluated_copy
from verification.test_blender_host_contracts import BlenderHostError,FakeMatrix
from verification import test_common_owned_gateway as common_tests
from verification.model_trial.owned_goal_adapter import OwnedTaskIntent
from verification.model_trial.tools import ToolRejected,UnconfirmedToolOutcome
from verification.model_trial import common_owned_gateway as common

READONLY_PROTOCOL='owned-readonly-native-evidence-v1-20261031'
AUDIT_PROTOCOL='owned-native-render-audit-v1-20261031'


def state_sample():
    return {'schema_version':'native-render-state-v1',
        'scope':'render-helper-assigned-and-implicitly-dependent-scalars-camera-assets-selection',
        'scene_camera':None,'scene_objects':[],'global_objects':[],'camera_datablocks':[],
        'active_object':None,'selection':[],
        'render':{'engine':'BLENDER_EEVEE_NEXT','resolution_x':621,'resolution_y':319,
            'resolution_percentage':65,'filepath':'D:/private-owner/answer-image.png','film_transparent':True,
            'pixel_aspect_x':1.7,'pixel_aspect_y':.6,'use_border':True,'use_crop_to_border':True,
            'border_min_x':.13,'border_max_x':.79,'border_min_y':.21,'border_max_y':.92},
        'shading':{'light':'FLAT','color_type':'MATERIAL','background_type':'WORLD',
            'background_color':[.2,.4,.6],'show_shadows':False,'show_cavity':True,'show_object_outline':False},
        'image_settings':{'file_format':'OPEN_EXR','color_depth':'32','color_mode':'RGBA'},
        'image_color_management':{},'scene_display_settings':{},
        'view_settings':{'view_transform':'AgX','look':'None','exposure':1.25,'gamma':.8},
        'execution_authority':False}


def audit_sample(sequence=1,view='SCENE'):
    state=state_sample()
    return {'schema_version':'native-render-audit-v1','protocol':AUDIT_PROTOCOL,
        'status':'completed','view':view,'sequence':sequence,'before':state,'after':copy.deepcopy(state),
        'restored':True,'geometry_restored':True,'error':None,'state_capture_errors':[],
        'execution_authority':False}


class ReadonlyNativeEvidenceTests(unittest.TestCase):
    def test_explicit_read_preserves_normal_native_shape_and_is_detached(self):
        host,part,base,_=fixture();strict=host.capture_evidence();value=host.capture_readonly_evidence()
        self.assertEqual(value['capture'],strict['capture']);self.assertEqual(value['native_scene'],strict['native_scene'])
        self.assertTrue(value['coherence']['read_only_evidence'])
        self.assertEqual(value['coherence']['read_only_evidence_protocol'],READONLY_PROTOCOL)
        self.assertIs(value['coherence']['execution_authority'],False)
        value['native_scene']['objects'][0]['matrix'][0][0]=900
        self.assertEqual(host.capture_evidence()['native_scene'],strict['native_scene'])
        self.assertEqual(part.assignments+base.assignments,0)

    def test_only_transform_locks_are_readable_without_becoming_executable(self):
        for key in ('lock_location','lock_rotation','lock_scale'):
            with self.subTest(key=key):
                host,part,base,_=fixture();setattr(part,key,(True,False,False))
                before=copy.deepcopy(part.matrix_world)
                with self.assertRaisesRegex(BlenderHostError,'independent static rigid meshes'):host.capture_evidence()
                value=host.capture_readonly_evidence()
                self.assertEqual(len(value['native_scene']['objects']),2)
                self.assertFalse(value['capture']['host_execution']['supported'])
                self.assertTrue(value['coherence']['raw_original_mesh_verified'])
                self.assertIs(value['coherence']['execution_authority'],False)
                self.assertEqual(part.matrix_world,before)
                self.assertEqual(getattr(part,key),(True,False,False))
                with self.assertRaises(BlenderHostError):
                    host.apply_transform({'focal_id':host.object_id(part),'translation':[0,0,.0001]},value['capture']['revision'])
                self.assertEqual(part.assignments+base.assignments,0)

    def test_locks_do_not_waive_any_other_unsupported_execution_reason(self):
        changes=[('parent',NS(name='Parent')),('children',[NS(name='Child')]),('constraints',[NS()]),
            ('modifiers',[NS(name='Deform',type='SUBSURF')]),('animation_data',NS()),
            ('rigid_body',NS()),('mode','EDIT'),('library',NS(filepath='private-linked.blend'))]
        for key,bad in changes:
            with self.subTest(key=key):
                host,part,base,_=fixture();part.lock_location=(True,False,False);setattr(part,key,bad)
                with self.assertRaisesRegex(BlenderHostError,'independent static rigid meshes'):
                    host.capture_readonly_evidence()
                self.assertEqual(part.assignments+base.assignments,0)

    def test_readonly_keeps_original_local_polygon_and_world_verification(self):
        for condition in ('local','polygon','matrix'):
            with self.subTest(condition=condition):
                host,part,base,_=fixture();part.lock_location=(True,False,False);evaluated=evaluated_copy(part)
                if condition=='local':evaluated.data.vertices[0].co=(.2,0,0)
                elif condition=='polygon':evaluated.data.polygons[0].vertices=[0,1,2]
                else:evaluated._matrix_world[0][3]+=.001
                with self.assertRaisesRegex(BlenderHostError,'original and evaluated'):
                    host.capture_readonly_evidence()
                self.assertEqual(part.assignments+base.assignments,0)

    def test_readonly_keeps_identity_and_metadata_requirements(self):
        for condition in ('identity','execution_metadata','identity_metadata'):
            with self.subTest(condition=condition):
                host,part,base,_=fixture();part.lock_scale=(True,False,False)
                if condition=='identity':del host.scene.session_uid
                else:setattr(host,condition,False)
                with self.assertRaises(BlenderHostError):host.capture_readonly_evidence()
                self.assertEqual(part.assignments+base.assignments,0)


class OwnerReadTransportTests(unittest.TestCase):
    def host(self):
        host=object.__new__(BlenderProcessHost);host._default_worker=True
        host._process=NS(pid=817);host._capabilities={
            'common_native_protocol':'owned-common-native-v1-20261031',
            'common_native_clock':counter_descriptor(),'process_id':817,
            'readonly_native_evidence_protocol':READONLY_PROTOCOL,'native_render_audit_protocol':AUDIT_PROTOCOL}
        host._request=Mock(side_effect=lambda name,args:{'name':name,'args':args})
        return host

    def test_exact_three_owner_commands_are_no_argument_reads(self):
        host=self.host()
        for name in ('capture_readonly_evidence','native_render_state','last_native_render_audit'):
            with self.subTest(name=name):
                self.assertEqual(getattr(host,name)(),{'name':name,'args':{}})
                with self.assertRaises(TypeError):getattr(host,name)({'permission':True})

    def test_wrong_fixed_worker_clock_pid_or_protocol_is_refused_before_rpc(self):
        for field,bad in [('common_native_clock',{}),('process_id',999),
            ('readonly_native_evidence_protocol',None),('native_render_audit_protocol','other')]:
            with self.subTest(field=field):
                host=self.host();host._capabilities[field]=bad
                name='capture_readonly_evidence' if field!='native_render_audit_protocol' else 'native_render_state'
                with self.assertRaises(ValueError):getattr(host,name)()
                host._request.assert_not_called()
        host=self.host();host._default_worker=False
        with self.assertRaises(ValueError):host.capture_readonly_evidence()
        host._request.assert_not_called()


class Properties(list):
    def get(self,key):return next((p for p in self if p.identifier==key),None)


class RNASettings(NS):
    def __init__(self,**values):
        super().__init__(**values)
        def kind(value):
            if type(value) is bool:return 'BOOLEAN'
            if type(value) is int:return 'INT'
            if type(value) is str:return 'ENUM'
            return 'FLOAT'
        self.bl_rna=NS(properties=Properties([NS(identifier=k,type=kind(v),is_readonly=False,
            is_enum_flag=isinstance(v,set)) for k,v in values.items()]))


def render_fixture():
    host,part,base,_=fixture()
    part.select_get=lambda:True;base.select_get=lambda:False
    camera=NS(name='ExistingCamera',name_full='ExistingCamera',session_uid=700,type='CAMERA',
        matrix_world=FakeMatrix([[1.,0,0,2.],[0,1.,0,3.],[0,0,1.,4.],[0,0,0,1.]]),
        data=RNASettings(type='PERSP',lens=63.,ortho_scale=9.,clip_start=.2,clip_end=110.))
    camera.data.name=camera.data.name_full='ExistingCameraData';camera.data.session_uid=701
    camera.select_get=lambda:True
    host.scene.camera=camera;host.scene.objects.append(camera)
    image=RNASettings(file_format='OPEN_EXR',color_mode='RGBA',color_depth='32',compression=37,
        quality=86,color_management='OVERRIDE',custom_array=[.2,.6,.8])
    view=RNASettings(view_transform='AgX',look='None',exposure=1.25,gamma=.8,
        use_curve_mapping=False,white_balance_temperature=5200.)
    host.scene.render=NS(**state_sample()['render'],image_settings=image)
    host.scene.display=NS(shading=NS(**state_sample()['shading']))
    host.scene.view_settings=view;host.view_layer.objects.active=base
    host.bpy.data.objects=list(host.scene.objects);host.bpy.data.cameras=[camera.data]
    return host,part,base,camera


class RenderStateProjectionTests(unittest.TestCase):
    def test_state_captures_assets_selection_changed_properties_and_rna_dependents(self):
        host,part,base,camera=render_fixture()
        state=episode.native_render_state(host.bpy,host.scene,host.view_layer)
        self.assertEqual(state['schema_version'],'native-render-state-v1')
        self.assertEqual(state['scene_camera']['identity']['session_uid'],700)
        self.assertEqual(state['scene_camera']['data_settings']['lens'],63.)
        self.assertEqual(state['active_object']['session_uid'],base.session_uid)
        self.assertEqual(len(state['scene_objects']),3)
        self.assertEqual(len(state['global_objects']),3)
        self.assertEqual(len(state['camera_datablocks']),1)
        self.assertEqual(state['image_settings']['custom_array'],[.2,.6,.8])
        self.assertEqual(state['view_settings']['white_balance_temperature'],5200.)
        self.assertFalse(state['execution_authority'])
        self.assertIn('D:/private-owner/answer-image.png',json.dumps(state))
        host.scene.render.image_settings.custom_array[0]=.7
        self.assertEqual(state['image_settings']['custom_array'][0],.2)
        self.assertNotEqual(state,episode.native_render_state(host.bpy,host.scene,host.view_layer))

    def test_asset_identity_changes_detected_even_if_names_stay_the_same(self):
        host,part,base,camera=render_fixture();first=episode.native_render_state(host.bpy,host.scene,host.view_layer)
        camera.session_uid+=1
        second=episode.native_render_state(host.bpy,host.scene,host.view_layer)
        self.assertNotEqual(first['scene_camera'],second['scene_camera'])
        self.assertNotEqual(first['global_objects'],second['global_objects'])

    def test_nonfinite_state_is_rejected_instead_of_claiming_complete_restoration(self):
        host,_,_,_=render_fixture();host.scene.view_settings.gamma=float('nan')
        with self.assertRaises(ValueError):episode.native_render_state(host.bpy,host.scene,host.view_layer)

    def test_scalar_restore_handles_format_dependencies_and_keeps_other_restores_after_error(self):
        class Dependent(RNASettings):
            def __setattr__(self,key,value):
                super().__setattr__(key,value)
                if key=='file_format' and 'bl_rna' in self.__dict__:
                    super().__setattr__('color_depth','8');super().__setattr__('color_mode','RGB')
        image=Dependent(file_format='PNG',color_mode='RGB',color_depth='8',quality=30)
        errors=[];episode._restore_scalar_state(image,{'file_format':'OPEN_EXR','color_depth':'32','color_mode':'RGBA','quality':80},
            errors,first=('file_format',))
        self.assertEqual(errors,[]);self.assertEqual((image.file_format,image.color_depth,image.color_mode,image.quality),('OPEN_EXR','32','RGBA',80))
        class SomeFailures:
            def __init__(self):self.good=0
            @property
            def bad(self):return 1
            @bad.setter
            def bad(self,value):raise RuntimeError('deliberate restore failure')
        target=SomeFailures();episode._restore_scalar_state(target,{'bad':4,'good':9},errors)
        self.assertEqual(target.good,9);self.assertEqual(len(errors),1)


class RenderLifecycleTests(unittest.TestCase):
    def ready(self):
        host,part,base,_=fixture();packet=host.capture_evidence()
        host.begin_owned_episode('render-case',host.object_id(part),host.object_id(base),time.perf_counter_ns()+60_000_000_000)
        module,state=host._episode_store()
        return host,module,state

    def test_success_stores_actual_before_after_detached_without_authority(self):
        host,module,state=self.ready();before=state_sample();image={'native_output':True}
        with patch.object(module,'native_render_state',side_effect=[copy.deepcopy(before),copy.deepcopy(before)]),\
             patch.object(module,'native_look',return_value=image):
            self.assertIs(host.native_look('SCENE'),image)
        audit=host.last_native_render_audit()
        self.assertEqual(audit['status'],'completed');self.assertTrue(audit['restored']);self.assertTrue(audit['geometry_restored'])
        self.assertEqual(audit['before'],audit['after']);self.assertIsNone(state['record']['frozen_reason'])
        audit['before']['render']['resolution_x']=1
        self.assertEqual(host.last_native_render_audit()['before']['render']['resolution_x'],621)
        self.assertFalse(audit['execution_authority'])

    def test_changed_after_state_rejects_image_and_freezes_episode(self):
        host,module,state=self.ready();before=state_sample();after=copy.deepcopy(before);after['render']['resolution_x']+=1
        with patch.object(module,'native_render_state',side_effect=[before,after]),patch.object(module,'native_look',return_value={'image':'not releasable'}):
            with self.assertRaisesRegex(BlenderHostError,'not_restored'):host.native_look('XY')
        audit=host.last_native_render_audit();self.assertFalse(audit['restored'])
        self.assertEqual(audit['status'],'failed');self.assertIsNotNone(state['record']['frozen_reason'])
        self.assertEqual(host.owned_episode_status()['actual_setter_count'],0)

    def test_render_failure_is_recorded_even_when_state_restores(self):
        host,module,state=self.ready();before=state_sample()
        with patch.object(module,'native_render_state',side_effect=[before,copy.deepcopy(before)]),\
             patch.object(module,'native_look',side_effect=RuntimeError('renderer raised')):
            with self.assertRaisesRegex(RuntimeError,'renderer raised'):host.native_look('XZ')
        audit=host.last_native_render_audit()
        self.assertTrue(audit['restored']);self.assertEqual(audit['status'],'failed')
        self.assertEqual(audit['error']['type'],'RuntimeError');self.assertIsNotNone(state['record']['frozen_reason'])

    def test_unavailable_after_snapshot_cannot_count_as_restored(self):
        host,module,state=self.ready()
        with patch.object(module,'native_render_state',side_effect=[state_sample(),RuntimeError('state unavailable')]),\
             patch.object(module,'native_look',return_value={'image':True}):
            with self.assertRaises(BlenderHostError):host.native_look('SCENE')
        audit=host.last_native_render_audit()
        self.assertIsNone(audit['after']);self.assertFalse(audit['restored'])
        self.assertEqual(audit['state_capture_errors'][0]['stage'],'after')
        self.assertIsNotNone(state['record']['frozen_reason'])


class ReadonlyRenderPublicBoundaryTests(unittest.TestCase):
    # Reuse only the existing fixture constructors, not its test methods.
    setUp=common_tests.CommonOwnedGatewayTests.setUp
    gateway=common_tests.CommonOwnedGatewayTests.gateway

    def test_readonly_ctor_uses_only_explicit_typed_read(self):
        self.host.capture_evidence=Mock(side_effect=AssertionError('readonly must not call strict producer'))
        typed_read=self.host.capture_readonly_evidence
        self.host.capture_readonly_evidence=Mock(side_effect=typed_read)
        value,_=self.gateway(task=OwnedTaskIntent(self.spec,'readonly-event','readonly-auth',read_only=True))
        self.host.capture_evidence.assert_not_called();self.host.capture_readonly_evidence.assert_called_once()
        self.assertFalse(value.run_registered_task()['task_succeeded']);self.assertEqual(self.dispatches,[])

    def test_false_readonly_flag_still_uses_strict_producer(self):
        self.host.capture_evidence=Mock(side_effect=lambda:copy.deepcopy(self.current))
        self.host.capture_readonly_evidence=Mock(side_effect=AssertionError('normal task cannot downgrade read'))
        self.gateway();self.host.capture_evidence.assert_called_once();self.host.capture_readonly_evidence.assert_not_called()

    def test_owner_diagnostics_stay_out_of_tools_and_public_image(self):
        value,_=self.gateway();output=value.call('native_look',{'view':'SCENE'})
        self.assertEqual(set(output),{'mime_type','image_base64','width','height','view'})
        names={v['name'] for v in value.tool_schemas()}
        self.assertTrue(names.isdisjoint({'capture_readonly_evidence','native_render_state','last_native_render_audit'}))
        raw=json.dumps(output);self.assertNotIn('private-owner',raw);self.assertNotIn('native-render-state',raw)
        private=value.private_snapshot();self.assertEqual(len(private['native_render_audits']),1)
        self.assertIn('D:/private-owner',json.dumps(private))

    def test_bad_incomplete_or_unrestored_audit_poison_all_channels(self):
        for mutation in ('protocol','missing_state','after_differs','restored','errors','sequence_bool'):
            with self.subTest(mutation=mutation):
                # Each independent object shares the untouched fresh pure ledger.
                self.state.clear();value,_=self.gateway();audit=audit_sample()
                if mutation=='protocol':audit['protocol']='wrong'
                elif mutation=='missing_state':audit['before']=audit['after']={'schema_version':'native-render-state-v1'}
                elif mutation=='after_differs':audit['after']['render']['resolution_x']+=1
                elif mutation=='restored':audit['restored']=False
                elif mutation=='errors':audit['state_capture_errors']=[{'stage':'after','type':'RuntimeError'}]
                else:audit['sequence']=True
                self.host.last_native_render_audit=lambda audit=audit:copy.deepcopy(audit)
                with self.assertRaises(UnconfirmedToolOutcome):value.call('native_look',{'view':'SCENE'})
                self.assertTrue(value.uncertain_outcome)
                with self.assertRaises(UnconfirmedToolOutcome):value.call('native_scene_query',{})
                with self.assertRaises(UnconfirmedToolOutcome):value.run_registered_task()
                self.assertEqual(self.dispatches,[])

    def test_render_failure_exception_with_private_path_is_owner_only(self):
        value,_=self.gateway()
        self.host.native_look=Mock(side_effect=OSError('D:/private-owner/answer-file.png render failed'))
        with self.assertRaises(UnconfirmedToolOutcome) as caught:value.call('native_look',{'view':'SCENE'})
        self.assertNotIn('private-owner',str(caught.exception));self.assertTrue(value.uncertain_outcome)
        self.assertIn('private-owner',json.dumps(value.private_snapshot()))
        self.assertEqual(self.dispatches,[])


if __name__=='__main__':unittest.main()
