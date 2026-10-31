"""Multiscale transport, publication and independent geometry contracts.

These tests never start Blender. Installed fixed-worker rendering and actual
RNA restoration are separately required by the owned acceptance harness.
"""
from __future__ import annotations
import base64,copy,hashlib,io,json,math,unittest
from unittest.mock import Mock,patch

from PIL import Image,PngImagePlugin
from human_eye_plugin import episode_gateway as renderer
from human_eye_plugin.blender_process import BlenderProcessHost,MULTISCALE_PROTOCOL
from human_eye_plugin.forward_deadline import counter_descriptor
from verification import test_common_owned_gateway as prior
from verification.model_trial import common_owned_gateway as common
from verification.model_trial.owned_goal_adapter import OwnedTaskIntent
from verification.model_trial.tools import _NATIVE,ToolRejected,UnconfirmedToolOutcome


def frame_proof(frame,public,native,view,kind):
    axes=[frame[key] for key in ('right','up','direction')]
    matrix=[[axes[col][row] for col in range(3)]+[frame['camera_location_bu'][row]] for row in range(3)]
    matrix.append([0.,0.,0.,1.])
    points=[p for obj in native['objects'] for p in obj['world_vertices']]
    def project(p):
        delta=[p[k]-frame['camera_location_bu'][k] for k in range(3)]
        return [math.fsum(delta[k]*axis[k] for k in range(3)) for axis in axes]
    projected=[project(p) for p in points];half=frame['ortho_scale_bu']/2
    center=project(public['center_world_m'])
    return {'schema_version':'native-render-frustum-v1','view':view,'unit_scale_m':1.,
        'camera_matrix_host_units':matrix,'ortho_scale_bu':frame['ortho_scale_bu'],
        'clip_start_bu':frame['clip_start_bu'],'clip_end_bu':frame['clip_end_bu'],
        'resolution_px':[384,384],'pixel_aspect':[1.,1.],
        'screen_coverage':public['screen_coverage'],'depth_coverage':'all_native_vertices',
        'depth_vertex_count':len(points),'screen_vertex_count':len(points) if kind=='overview' else 1,
        'checked_center_world_m':copy.deepcopy(public['center_world_m']),
        'center_ndc':[center[k]/half for k in (0,1)],
        'max_abs_screen_bu':[max(abs(p[k]) for p in projected) for k in (0,1)],
        'min_depth_bu':min(-p[2] for p in projected),'max_depth_bu':max(-p[2] for p in projected)}


class MultiscaleTransportTests(unittest.TestCase):
    def host(self):
        host=object.__new__(BlenderProcessHost)
        host._default_worker=True;host._process=prior.ProcessDouble()
        host._capabilities={'common_native_protocol':common.PROTOCOL,'common_native_clock':counter_descriptor(),
            'process_id':host._process.pid,'native_multiscale_protocol':MULTISCALE_PROTOCOL}
        host._request=Mock(return_value={'typed':True})
        return host

    def test_two_typed_commands_have_only_their_fixed_arguments(self):
        host=self.host()
        self.assertEqual(host.native_look_multiscale(),{'typed':True})
        host._request.assert_called_once_with('native_look_multiscale',{'view':'SCENE'})
        host._request.reset_mock();host.last_native_multiscale_audit()
        host._request.assert_called_once_with('last_native_multiscale_audit',{})

    def test_default_worker_pid_qpc_and_dedicated_protocol_are_required(self):
        for change in ('custom','pid','clock','protocol'):
            host=self.host()
            if change=='custom':host._default_worker=False
            elif change=='pid':host._capabilities['process_id']+=1
            elif change=='clock':host._capabilities['common_native_clock']={}
            else:host._capabilities['native_multiscale_protocol']='other'
            with self.subTest(change=change),self.assertRaises(ValueError):host.native_look_multiscale('XY')
            host._request.assert_not_called()


class MultiscaleEntryTests(unittest.TestCase):
    def setUp(self):
        self.case=prior.CommonOwnedGatewayTests();self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.modify=lambda raw,audit:None
        self.group_sequence=0;self.last_bundle=None

    def enable(self,*,far=False):
        if far:
            ref=self.case.reference
            obj=next(v for v in self.case.packet['native_scene']['objects'] if v['object_id']==ref)
            obj['matrix'][0][3]+=500.
            for p in obj['world_vertices']:p[0]+=500.
            mesh=next(v for v in self.case.packet['capture']['meshes'] if v['object_id']==ref)
            mesh['pivot_world'][0]+=500.
            for p in mesh['vertices']:p[0]+=500.
            self.case.packet['capture']['revision']+=':far'
            self.case.packet['native_scene']['revision']='native:'+common._digest(self.case.packet['native_scene']['objects'])
            self.case.current=copy.deepcopy(self.case.packet)
        caps=self.case.host.capabilities
        self.case.host.capabilities=lambda:{**caps(),'native_multiscale_protocol':MULTISCALE_PROTOCOL}
        self.case.host.native_look_multiscale=self.bundle
        self.case.host.last_native_multiscale_audit=lambda:copy.deepcopy(self.last_bundle)

    def bundle(self,view):
        self.group_sequence+=1;native=copy.deepcopy(self.case.current['native_scene'])
        plan,overview,detail=renderer.plan_native_multiscale(native,self.case.focal,view,1.)
        response={'overview':None,'detail':None,'plan':plan};frames=[]
        for kind,frame in [('overview',overview),('detail',detail)]:
            if frame is None:continue
            self.case.render_sequence+=1
            audit={'schema_version':'native-render-audit-v1','protocol':common.RENDER_AUDIT_PROTOCOL,
                'status':'completed','view':view,'sequence':self.case.render_sequence,
                'before':copy.deepcopy(self.case.render_state),'after':copy.deepcopy(self.case.render_state),
                'restored':True,'geometry_restored':True,'error':None,'state_capture_errors':[],
                'execution_authority':False}
            self.case.render_audit=copy.deepcopy(audit)
            response[kind]={'mime_type':'image/png','image_base64':base64.b64encode(self.case.png).decode(),
                'width':384,'height':384,'view':view,'private_path':'D:/owner/not-public.blend'}
            frames.append({'kind':kind,'png_sha256':hashlib.sha256(self.case.png).hexdigest(),
                'render_audit':audit,'frustum':frame_proof(frame,plan[kind],native,view,kind)})
        private={'schema_version':'native-multiscale-audit-v1','protocol':MULTISCALE_PROTOCOL,
            'status':'completed','view':view,'sequence':self.group_sequence,
            'native_revision_before':native['revision'],'native_revision_after':native['revision'],
            'plan':copy.deepcopy(plan),'frames':frames,'error':None,'execution_authority':False}
        self.modify(response,private);self.last_bundle=copy.deepcopy(private)
        return response

    def gateway(self,arm='C2',*,far=False,readonly=False):
        self.enable(far=far)
        task=OwnedTaskIntent(self.case.spec,'ms-event','ms-auth',read_only=readonly)
        value,_=self.case.gateway(arm,task=task)
        return value

    def look(self,value):return value.call(common.MULTISCALE_NAME,{'view':'XY'})

    def assert_poisoned_no_public_bundle(self,value):
        private=value.private_snapshot()
        self.assertTrue(private['poisoned'])
        self.assertEqual(private['native_multiscale_audits'],[])
        self.assertFalse(any(call['name']==common.MULTISCALE_NAME for call in private['public_calls']))
        for name,args in [('native_scene_query',{}),('native_look',{}),('native_compute',{'code':'result=1'}),
                (common.MULTISCALE_NAME,{}),(common.AUTO_NAME,{})]:
            with self.subTest(channel=name),self.assertRaises(UnconfirmedToolOutcome):value.call(name,args)

    def test_old_worker_keeps_original_schemas_and_five_field_image(self):
        value,_=self.case.gateway('A2')
        self.assertEqual(value.tool_schemas(),_NATIVE)
        self.assertEqual(set(value.call('native_look',{})),{'mime_type','image_base64','width','height','view'})
        with self.assertRaises(ToolRejected):value.call(common.MULTISCALE_NAME,{})

    def test_new_native_tool_is_identical_in_both_arms_and_detached(self):
        value=self.gateway('A2');schemas=value.tool_schemas()
        self.assertEqual(schemas[:4],_NATIVE)
        self.assertEqual(schemas[-1]['name'],common.MULTISCALE_NAME)
        schemas[-1]['description']='caller mutation'
        self.assertNotEqual(value.tool_schemas()[-1]['description'],'caller mutation')
        self.case.state.clear();other,_=self.case.gateway('C2')
        self.assertEqual(other.tool_schemas()[:-1],value.tool_schemas())
        self.assertEqual(other.tool_schemas()[-1]['name'],common.AUTO_NAME)

    def test_ordinary_scene_uses_one_image_and_one_restored_audit(self):
        value=self.gateway();result=self.look(value)
        self.assertEqual(set(result),{'overview','detail','plan'})
        self.assertIsNone(result['detail']);self.assertEqual(result['plan']['image_count'],1)
        self.assertEqual(result['plan']['reason_code'],'overview_sufficient')
        private=value.private_snapshot();self.assertEqual(len(private['native_render_audits']),1)
        self.assertEqual(len(private['native_multiscale_audits']),1)
        self.assertEqual(private['episode_status']['actual_setter_count'],0)

    def test_far_scene_two_images_have_declared_crop_and_preserve_pixel_payload(self):
        value=self.gateway(far=True);result=self.look(value)
        self.assertTrue(result['plan']['detail_included'])
        self.assertEqual(result['plan']['budget_scope'],'per_call_original_episode_deadline')
        self.assertLess(result['plan']['feature']['overview_px'],12)
        self.assertGreaterEqual(result['plan']['feature']['detail_px'],32)
        self.assertEqual(result['plan']['detail']['screen_coverage'],'intentional_local_window')
        self.assertEqual(result['plan']['detail']['depth_coverage'],'all_native_vertices')
        for kind in ('overview','detail'):
            self.assertEqual(set(result[kind]),{'mime_type','image_base64','width','height','view'})
            self.assertEqual(Image.open(io.BytesIO(base64.b64decode(result[kind]['image_base64']))).convert('RGBA').tobytes(),
                             Image.open(io.BytesIO(self.case.png)).convert('RGBA').tobytes())
        result['plan']['detail']['span_m']=999
        self.assertNotEqual(value.private_snapshot()['native_multiscale_audits'][0]['plan']['detail']['span_m'],999)

    def test_second_restore_failure_does_not_publish_or_commit_first_audit(self):
        value=self.gateway(far=True)
        self.modify=lambda raw,audit:audit['frames'][1]['render_audit'].update(restored=False)
        with self.assertRaises(UnconfirmedToolOutcome):self.look(value)
        self.assertEqual(value.private_snapshot()['native_render_audits'],[])
        self.assert_poisoned_no_public_bundle(value)

    def test_second_corrupt_png_also_aborts_the_whole_bundle(self):
        value=self.gateway(far=True)
        def corrupt(raw,audit):
            damaged=self.case.png[:-5]
            raw['detail']['image_base64']=base64.b64encode(damaged).decode()
            audit['frames'][1]['png_sha256']=hashlib.sha256(damaged).hexdigest()
        self.modify=corrupt
        with self.assertRaises(UnconfirmedToolOutcome):self.look(value)
        self.assertEqual(value.private_snapshot()['native_render_audits'],[])
        self.assert_poisoned_no_public_bundle(value)

    def test_duplicate_or_nonconsecutive_audits_and_stale_bundle_are_refused(self):
        for bad in ('duplicate','gap','revision','hash','count'):
            with self.subTest(bad=bad):
                self.case.state.clear();value=self.gateway(far=False)
                def mutate(raw,audit):
                    if bad=='duplicate':audit['frames'][0]['render_audit']['sequence']=0
                    elif bad=='gap':audit['native_revision_after']='stale'
                    elif bad=='revision':raw['plan']['scene_revision']='stale'
                    elif bad=='hash':audit['frames'][0]['png_sha256']='0'*64
                    else:audit['frames'].append(copy.deepcopy(audit['frames'][0]))
                self.modify=mutate
                with self.assertRaises(UnconfirmedToolOutcome):self.look(value)
                self.assert_poisoned_no_public_bundle(value)

    def test_private_and_public_plan_agreement_cannot_replace_geometry(self):
        for bad in ('center','span','feature','budget','permission','extra'):
            with self.subTest(bad=bad):
                self.case.state.clear();value=self.gateway()
                def mutate(raw,audit):
                    plan=raw['plan']
                    if bad=='center':plan['overview']['center_world_m'][0]+=1.
                    elif bad=='span':plan['overview']['span_m']*=2.
                    elif bad=='feature':plan['feature']['width_m']*=2.
                    elif bad=='budget':plan['max_total_pixels']+=1
                    elif bad=='permission':plan['execution_authority']=True
                    else:plan['owner_path']='D:/private/answer.json'
                    audit['plan']=copy.deepcopy(plan)
                self.modify=mutate
                with self.assertRaises(UnconfirmedToolOutcome) as caught:self.look(value)
                self.assertNotIn('D:/private',str(caught.exception))
                self.assert_poisoned_no_public_bundle(value)

    def test_actual_frustum_is_recomputed_from_every_scene_vertex(self):
        for bad in ('depth','count','camera','ndc'):
            with self.subTest(bad=bad):
                self.case.state.clear();value=self.gateway()
                def mutate(raw,audit):
                    proof=audit['frames'][0]['frustum']
                    if bad=='depth':proof['clip_end_bu']=proof['min_depth_bu']+.0001
                    elif bad=='count':proof['depth_vertex_count']-=1
                    elif bad=='camera':proof['camera_matrix_host_units'][0][3]+=1.
                    else:proof['center_ndc']=[.1,0.]
                self.modify=mutate
                with self.assertRaises(UnconfirmedToolOutcome):self.look(value)
                self.assert_poisoned_no_public_bundle(value)

    def test_both_pngs_remove_private_metadata_and_keep_rgba(self):
        value=self.gateway(far=True);marker='D:/private-owner/answer.blend'
        metadata=PngImagePlugin.PngInfo();metadata.add_text('Filename',marker)
        stream=io.BytesIO();Image.new('RGB',(384,384),(70,80,90)).save(stream,format='PNG',pnginfo=metadata)
        self.case.png=stream.getvalue();result=self.look(value)
        for kind in ('overview','detail'):
            raw=base64.b64decode(result[kind]['image_base64'],validate=True)
            self.assertNotIn(marker.encode(),raw)
            self.assertEqual(Image.open(io.BytesIO(raw)).convert('RGBA').tobytes(),
                Image.open(io.BytesIO(self.case.png)).convert('RGBA').tobytes())

    def test_readonly_bundle_preserves_original_deadline_and_zero_motion(self):
        value=self.gateway(far=True,readonly=True);before=value.private_snapshot()
        self.look(value);after=value.private_snapshot()
        self.assertEqual(after['episode_status'],before['episode_status'])
        self.assertEqual(after['original_episode_window'],before['original_episode_window'])
        self.assertEqual(after['episode_status']['actual_setter_count'],0)
        self.assertTrue(after['episode_status']['read_only'])

    def test_invalid_caller_shape_never_reaches_the_host(self):
        value=self.gateway();self.case.host.native_look_multiscale=Mock(side_effect=AssertionError('unexpected RPC'))
        for args in ({'view':'xy'},{'view':'XY','path':'D:/secret'},{'permission':True},{'max_images':9}):
            with self.subTest(args=args),self.assertRaises(ToolRejected):value.call(common.MULTISCALE_NAME,args)
        self.case.host.native_look_multiscale.assert_not_called()

    def test_successful_legacy_render_then_bundle_keeps_one_global_audit_sequence(self):
        value=self.gateway(far=True)
        value.call('native_look',{'view':'XY'})
        self.look(value)
        self.assertEqual([a['sequence'] for a in value.private_snapshot()['native_render_audits']],[1,2,3])
        self.modify=lambda raw,audit:audit['frames'][1]['render_audit'].update(sequence=audit['frames'][0]['render_audit']['sequence']+2)
        with self.assertRaises(UnconfirmedToolOutcome):self.look(value)
        self.assertEqual([a['sequence'] for a in value.private_snapshot()['native_render_audits']],[1,2,3])
        self.assertEqual(len(value.private_snapshot()['native_multiscale_audits']),1)

    def test_oversized_base64_is_rejected_before_decoding_or_partial_commit(self):
        value=self.gateway()
        self.modify=lambda raw,audit:raw['overview'].update(image_base64='A'*(4*((8*1024*1024+2)//3)+1))
        with patch.object(common.base64,'b64decode',side_effect=AssertionError('oversized PNG decoded')) as decode:
            with self.assertRaises(UnconfirmedToolOutcome):self.look(value)
            decode.assert_not_called()
        self.assertEqual(value.private_snapshot()['native_render_audits'],[])

    def test_bundle_cannot_claim_more_than_two_images_or_pixels(self):
        value=self.gateway(far=True)
        def expand(raw,audit):
            raw['plan']['image_count']=3;raw['plan']['max_images']=3;raw['plan']['max_total_pixels']=3*384*384
            audit['plan']=copy.deepcopy(raw['plan']);audit['frames'].append(copy.deepcopy(audit['frames'][-1]))
        self.modify=expand
        with self.assertRaises(UnconfirmedToolOutcome):self.look(value)
        self.assertEqual(value.private_snapshot()['native_render_audits'],[])

    def test_xy_metadata_matches_measured_native_roll_and_rejects_opposite_basis(self):
        value=self.gateway();result=self.look(value)
        frame=result['plan']['overview']
        # Owned Blender probe retained the native camera quaternion/Euler path.
        measured_right=[-1.,-1.5099580252808664e-7,0.]
        measured_up=[1.5099580252808664e-7,-1.,0.]
        self.assertGreater(sum(a*b for a,b in zip(frame['right_world'],measured_right)),.99999)
        self.assertGreater(sum(a*b for a,b in zip(frame['up_world'],measured_up)),.99999)
        def opposite(raw,audit):
            for key in ('right_world','up_world'):
                raw['plan']['overview'][key]=[-x for x in raw['plan']['overview'][key]]
            audit['plan']=copy.deepcopy(raw['plan'])
        self.modify=opposite
        with self.assertRaises(UnconfirmedToolOutcome):self.look(value)


if __name__=='__main__':unittest.main()
