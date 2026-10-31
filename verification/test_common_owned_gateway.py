"""Independent owner/router contracts using real typed tasks and pure ledger.

No Blender or provider starts. Installation claims/capability RPCs and automatic
dispatch are isolated; root must separately certify the installed worker and
raw paired geometry/image/physical trace artifacts.
"""
from __future__ import annotations

import base64,copy,io,json,struct,time,unittest,zlib
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image,PngImagePlugin
from human_eye_plugin.blender_process import BlenderProcessHost,HostRemoteError
from human_eye_plugin.forward_deadline import counter_descriptor
from human_eye_plugin.goal_budget import GoalBudgetLimits
from human_eye_plugin.runtime_identity import runtime_identity
from human_eye_plugin.task_authority import ClearanceTaskSpec
from human_eye_plugin import episode_gateway as ledger
from verification.test_blender_native_evidence import fixture
from verification.test_episode_gateway import translated
from verification.model_trial.deadline import EpisodeDeadline
from verification.model_trial.owned_goal_adapter import OwnedTaskIntent
from verification.model_trial.tools import _NATIVE,ToolRejected,UnconfirmedToolOutcome
from verification.model_trial import common_owned_gateway as common


class ProcessDouble:
    def __init__(self):self.pid=9137;self.returncode=None;self.kill_calls=0
    def poll(self):return self.returncode
    def kill(self):self.returncode=-9;self.kill_calls+=1


def png_chunks(raw):
    assert raw[:8]==b'\x89PNG\r\n\x1a\n'
    result=[];offset=8
    while offset<len(raw):
        assert len(raw)-offset>=12
        length=struct.unpack('>I',raw[offset:offset+4])[0]
        kind=raw[offset+4:offset+8];payload=raw[offset+8:offset+8+length]
        assert len(payload)==length and len(raw)>=offset+12+length
        crc=struct.unpack('>I',raw[offset+8+length:offset+12+length])[0]
        assert crc==zlib.crc32(kind+payload)&0xffffffff
        result.append((kind,payload));offset+=length+12
        if kind==b'IEND':break
    assert offset==len(raw) and result[-1][0]==b'IEND'
    return result


def png_chunk(kind,payload):
    return struct.pack('>I',len(payload))+kind+payload+struct.pack('>I',zlib.crc32(kind+payload)&0xffffffff)


class CommonOwnedGatewayTests(unittest.TestCase):
    def setUp(self):
        guard=patch('subprocess.Popen',side_effect=AssertionError('contract test must not start a subprocess'))
        guard.start();self.addCleanup(guard.stop)
        backend,part,base,_=fixture();self.packet=backend.capture_evidence()
        self.focal=backend.object_id(part);self.reference=backend.object_id(base)
        self.binding=backend._motion_binding(self.packet['capture'],self.focal,self.reference)
        self.identity=runtime_identity(mode='live');self.identity['source_kind']='installed_distribution'
        self.counter=counter_descriptor();self.auto_instances=[]
        self.patchers=[
            patch('human_eye_plugin.runtime_identity.runtime_identity',side_effect=lambda **kw:copy.deepcopy(self.identity)),
            patch('human_eye_plugin.runtime_identity.check_source_drift',return_value={'compatible':True}),
            patch('human_eye_plugin.goal_supervision.owned_host_counter',return_value=self.counter)]
        for p in self.patchers:p.start();self.addCleanup(p.stop)
        self.spec=ClearanceTaskSpec(self.focal,self.reference,reference_triangle_index=2)
        self.state={};self.current=copy.deepcopy(self.packet);self.dispatches=[];self.status_mutation=lambda x:x
        self.native_failure=None
        self.host=object.__new__(BlenderProcessHost)
        self.host._process=ProcessDouble();self.host._poisoned=False;self.host._closed=False;self.host._default_worker=True
        self.host.capabilities=lambda:{'common_native_protocol':common.PROTOCOL,'common_native_clock':self.counter,
            'readonly_native_evidence_protocol':'owned-readonly-native-evidence-v1-20261031',
            'native_render_audit_protocol':'owned-native-render-audit-v1-20261031'}
        self.host.capture_evidence=lambda:copy.deepcopy(self.current)
        def readonly_evidence():
            value=copy.deepcopy(self.current)
            value['coherence'].update(read_only_evidence=True,
                read_only_evidence_protocol='owned-readonly-native-evidence-v1-20261031',execution_authority=False)
            return value
        self.host.capture_readonly_evidence=readonly_evidence
        def status(after_event_count=0):
            v=ledger.snapshot(self.state,after_event_count=after_event_count)
            v['coverage']={'protocol':common.PROTOCOL,'process_id':self.host._process.pid,
                'scope':'all_legal_setters_of_this_owned_typed_worker',
                'generic_code_execution':False,'ui_attached':False,
                'external_process_or_modified_worker_proof':False}
            return self.status_mutation(v)
        self.host.owned_episode_status=status
        def begin(episode_id,focal_id,reference_id,deadline_ns,read_only=False,limits=None):
            self.assertEqual((focal_id,reference_id),(self.focal,self.reference))
            ledger.begin_episode(self.state,episode_id=episode_id,binding=self.binding,
                initial_native=self.current['native_scene'],deadline_ns=deadline_ns,
                now_ns=time.perf_counter_ns(),read_only=read_only,limits=limits)
            return status()
        self.host.begin_owned_episode=begin
        self.host.native_scene_query=lambda:copy.deepcopy(self.current['native_scene'])
        def native(object_id,delta_world_m,expected_revision):
            self.dispatches.append({'object_id':object_id,'delta':list(delta_world_m),'revision':expected_revision})
            if self.native_failure is not None:raise self.native_failure
            old=self.current['native_scene'];obj=next(o for o in old['objects'] if o['object_id']==object_id)
            target=[obj['matrix'][i][3]+delta_world_m[i] for i in range(3)]
            index=ledger.reserve_setter(self.state,helper='native_transform',object_id=object_id,
                requested_world=target,before_native=old,binding=self.binding,now_ns=time.perf_counter_ns())
            new=translated(old,self.focal,delta_world_m[2])
            ledger.confirm_setter(self.state,index,after_native=new,now_ns=time.perf_counter_ns())
            self.current['native_scene']=new
            return {'applied':True}
        self.host.native_transform=native
        stream=io.BytesIO();Image.new('RGB',(384,384),(70,80,90)).save(stream,format='PNG')
        self.png=stream.getvalue()
        # Synchronize the negotiated owner-only audit protocol. The real state
        # projector runs on this synthetic bpy fixture; no native renderer or
        # physical measurement is claimed by these router contracts.
        backend.scene.camera=None
        backend.scene.render=SimpleNamespace(engine='BLENDER_EEVEE_NEXT',resolution_x=621,resolution_y=319,
            resolution_percentage=65,filepath='D:/private-owner/answer-image.png',film_transparent=True,
            pixel_aspect_x=1.7,pixel_aspect_y=.6,use_border=True,use_crop_to_border=True,
            border_min_x=.13,border_max_x=.79,border_min_y=.21,border_max_y=.92,
            image_settings=SimpleNamespace(file_format='OPEN_EXR',color_mode='RGBA',color_depth='32'))
        backend.scene.display=SimpleNamespace(shading=SimpleNamespace(light='FLAT',color_type='MATERIAL',
            background_type='WORLD',background_color=(.2,.4,.6),show_shadows=False,show_cavity=True,show_object_outline=False))
        backend.scene.view_settings=SimpleNamespace(view_transform='AgX',exposure=1.25,gamma=.8)
        part.select_get=lambda:True;base.select_get=lambda:False
        backend.bpy.data.objects=list(backend.scene.objects);backend.bpy.data.cameras=[]
        self.render_state=ledger.native_render_state(backend.bpy,backend.scene,backend.view_layer)
        self.render_sequence=0;self.render_audit=None
        def native_look(view):
            self.render_sequence+=1
            self.render_audit={'schema_version':'native-render-audit-v1',
                'protocol':'owned-native-render-audit-v1-20261031','status':'completed','view':view,
                'sequence':self.render_sequence,'before':copy.deepcopy(self.render_state),
                'after':copy.deepcopy(self.render_state),'restored':True,'geometry_restored':True,
                'error':None,'state_capture_errors':[],'execution_authority':False}
            return {'mime_type':'image/png','image_base64':base64.b64encode(self.png).decode(),
                'width':384,'height':384,'view':view,'private_path':'D:/owner/private/answer.json'}
        self.host.native_look=native_look
        self.host.last_native_render_audit=lambda:copy.deepcopy(self.render_audit)

    def gateway(self,arm='C2',*,task=None,deadline=None,packet=None):
        if deadline is None:
            deadline=EpisodeDeadline(180.,clock=time.perf_counter,watchdog=True);self.addCleanup(deadline.close)
        value=common.CommonOwnedGateway(arm,'owner-only-config-never-opened.json',self.host,
            task=task or OwnedTaskIntent(self.spec,'stable-owner-event','stable-owner-auth'),
            initial_evidence=self.packet if packet is None else packet,deadline=deadline,
            expected_build_id=self.identity['build_id'],issuer_id='unit-trusted-owner')
        def cleanup():
            self.host._process.returncode=0;value.close()
        self.addCleanup(cleanup)
        return value,deadline

    def move(self,value,dz=.0005):
        query=value.call('native_scene_query',{})
        return value.call('native_transform',{'object_id':self.focal,'delta_world_m':[0.,0.,dz],
                                              'expected_revision':query['revision']})

    def test_arm_schemas_have_identical_four_native_descriptions(self):
        a,_=self.gateway('A2')
        self.assertEqual(a.tool_schemas(),_NATIVE)
        schema=a.tool_schemas();schema[0]['description']='changed caller copy'
        self.assertEqual(a.tool_schemas(),_NATIVE)
        with self.assertRaises(ToolRejected):a.call(common.AUTO_NAME,{})
        self.assertEqual(self.dispatches,[])

    def test_C2_adds_only_empty_registered_task_entry(self):
        c,_=self.gateway()
        self.assertEqual(c.tool_schemas()[:4],_NATIVE)
        self.assertEqual(len(c.tool_schemas()),5)
        for args in ({'task':self.spec.to_dict()},{'authorization':True},{'max_steps':99}):
            with self.subTest(args=args):
                with self.assertRaises(ToolRejected):c.call(common.AUTO_NAME,args)
        self.assertEqual(self.dispatches,[])

    def test_raw_json_is_not_trusted_task_or_episode(self):
        with self.assertRaises(ValueError):self.gateway(task={'spec':self.spec.to_dict(),'approved':True})
        budget=EpisodeDeadline(180.,clock=time.monotonic,watchdog=True);self.addCleanup(budget.close)
        with self.assertRaises(ValueError):self.gateway(deadline=budget)

    def test_registration_gives_same_public_constraints_without_owner_ids(self):
        value,_=self.gateway();public=value.public_registration()
        self.assertEqual(public['task'],self.spec.to_dict())
        self.assertTrue(public['public_task_constraints'])
        self.assertNotIn('stable-owner-auth',json.dumps(public))
        self.assertNotIn('stable-owner-event',json.dumps(public))
        self.assertNotIn('native_scene',json.dumps(public))

    def test_private_extras_are_not_projected_into_public_query_or_image(self):
        value,_=self.gateway()
        self.current['native_scene']['private_normal']=[0,0,1]
        self.current['native_scene']['objects'][0]['owner_token']='hidden-owner'
        query=value.call('native_scene_query',{})
        self.assertEqual(set(query),{'unit','coordinate_frame','revision','objects'})
        self.assertNotIn('hidden-owner',json.dumps(query))
        image=value.call('native_look',{'view':'SCENE'})
        self.assertEqual(set(image),{'mime_type','image_base64','width','height','view'})
        self.assertEqual(base64.b64decode(image['image_base64']),self.png)

    def test_invalid_nested_geometry_is_rejected_instead_of_leaking(self):
        for field,bad in [('matrix',{'owner_token':'hidden'}),('color',{'private_normal':[0,0,1]}),
                          ('world_vertices',[{'private_answer':'move .003'}]),('faces',[[True,1,2]])]:
            with self.subTest(field=field):
                raw=copy.deepcopy(self.packet['native_scene']);raw['objects'][0][field]=bad
                with self.assertRaises(ValueError):common._public_query(raw)

    def test_changed_initial_native_evidence_refuses_owner_registration(self):
        altered=copy.deepcopy(self.packet);altered['native_scene']['objects'][0]['color'][0]+=.01
        with self.assertRaises(ValueError):self.gateway(packet=altered)
        self.assertEqual(self.state,{})

    def test_rebind_cannot_replace_original_deadline(self):
        value,budget=self.gateway();other=EpisodeDeadline(180.,clock=time.perf_counter,watchdog=True)
        self.addCleanup(other.close)
        self.assertIs(value.bind_deadline(budget),value)
        with self.assertRaises(ValueError):value.bind_deadline(other)
        self.assertIs(value.bound_deadline,budget)

    def test_stale_revision_is_verified_preentry_and_does_not_dispatch(self):
        value,_=self.gateway()
        output=value.call('native_transform',{'object_id':self.focal,'delta_world_m':[0.,0.,.0005],
                                             'expected_revision':'stale-public-native-revision'})
        self.assertFalse(output['applied']);self.assertFalse(output['executed'])
        self.assertEqual(self.dispatches,[])
        self.assertEqual(value.private_snapshot()['episode_status']['actual_setter_count'],0)

    def test_exact_known_native_refusal_stays_zero_and_connection_usable(self):
        value,_=self.gateway()
        self.native_failure=HostRemoteError({'type':'EpisodePrewriteRefused','message':'known budget refusal',
            'mutation_uncertain':False,'known_preentry_refusal':True,'executed':False})
        output=self.move(value)
        self.assertFalse(output['applied']);self.assertFalse(value.uncertain_outcome)
        self.native_failure=None
        self.assertEqual(value.call('native_scene_query',{})['revision'],self.packet['native_scene']['revision'])

    def test_unknown_native_blocks_read_native_and_auto_retries(self):
        value,_=self.gateway();self.native_failure=OSError('actual write acknowledgement unavailable')
        with self.assertRaises(UnconfirmedToolOutcome):self.move(value)
        self.assertTrue(value.uncertain_outcome)
        for name,args in [('native_scene_query',{}),(common.AUTO_NAME,{})]:
            with self.subTest(name=name):
                with self.assertRaises(UnconfirmedToolOutcome):value.call(name,args)
        self.assertEqual(len(self.dispatches),1)

    def test_malformed_unknown_count_never_passes_complete_trace(self):
        value,_=self.gateway()
        self.status_mutation=lambda report:{**report,'unknown_event_count':False}
        with self.assertRaises(Exception):value.call('native_scene_query',{})
        self.assertEqual(self.dispatches,[])

    def test_inconsistent_path_remaining_cannot_expand_original_budget(self):
        value,_=self.gateway();self.move(value)
        self.status_mutation=lambda report:{**report,'remaining_translation_m':.008}
        with self.assertRaises(Exception):value.call('native_scene_query',{})
        self.assertEqual(len(self.dispatches),1)

    def test_malformed_meter_is_absorbing_across_later_channels(self):
        value,_=self.gateway()
        self.status_mutation=lambda report:{**report,'registered_events_complete':False}
        with self.assertRaises(Exception):value.call('native_scene_query',{})
        self.status_mutation=lambda report:report
        with self.assertRaises(UnconfirmedToolOutcome):value.call(common.AUTO_NAME,{})
        self.assertEqual(self.dispatches,[])

    def test_auto_constructor_failure_is_absorbing_without_None_replay(self):
        value,_=self.gateway()
        with patch.object(common,'OwnedGoalEpisode',side_effect=ValueError('owner rejected before dispatch')):
            try:first=value.run_registered_task()
            except Exception:first=None
            self.assertTrue(value.uncertain_outcome or first is not None and first.get('task_succeeded') is False)
            try:
                replay=value.run_registered_task()
            except UnconfirmedToolOutcome:pass
            except Exception as exc:self.fail('Failed auto construction must not replay as '+type(exc).__name__)
            else:
                self.assertFalse(replay['task_succeeded']);self.assertEqual(replay['new_setter_count_this_call'],0)
        self.assertEqual(self.dispatches,[])

    def test_real_episode_expiry_only_cancels_original_process(self):
        value,budget=self.gateway();process=self.host._process
        budget.expire('unit-original-window-expired')
        self.assertEqual(process.kill_calls,1)
        self.assertTrue(value.uncertain_outcome)
        with self.assertRaises(UnconfirmedToolOutcome):value.call('native_scene_query',{})
        self.assertEqual(self.dispatches,[])

    def image_response(self,raw,view='SCENE'):
        # PNG-specific fake render overrides must still produce the genuine
        # protocol shape, so malformed PNG tests reach PNG validation rather
        # than passing prematurely on a missing restoration audit.
        self.render_sequence+=1
        self.render_audit={'schema_version':'native-render-audit-v1',
            'protocol':'owned-native-render-audit-v1-20261031','status':'completed','view':view,
            'sequence':self.render_sequence,'before':copy.deepcopy(self.render_state),
            'after':copy.deepcopy(self.render_state),'restored':True,'geometry_restored':True,
            'error':None,'state_capture_errors':[],'execution_authority':False}
        return {'mime_type':'image/png','image_base64':base64.b64encode(raw).decode('ascii'),
                'width':384,'height':384,'view':view}

    def test_native_png_private_text_exif_and_unknown_ancillary_are_removed_without_pixel_change(self):
        image=Image.new('RGBA',(384,384),(70,80,90,173))
        image.putpixel((0,0),(1,2,3,0));image.putpixel((383,383),(210,5,30,255))
        metadata=PngImagePlugin.PngInfo()
        marker='D:/owner-private-arm-C2/fixture.blend'
        metadata.add_text('File',marker)
        metadata.add_itxt('ScenePath',marker)
        metadata.add_text('CompressedPath',marker,zip=True)
        stream=io.BytesIO();image.save(stream,format='PNG',pnginfo=metadata)
        chunks=png_chunks(stream.getvalue())
        exif=Image.Exif();exif[0x010e]=marker
        chunks.insert(1,(b'eXIf',exif.tobytes()[6:]))
        chunks.insert(2,(b'vpAg',marker.encode('ascii')))
        raw=b'\x89PNG\r\n\x1a\n'+b''.join(png_chunk(k,p) for k,p in chunks)
        self.host.native_look=lambda view:self.image_response(raw,view)
        value,_=self.gateway();public=value.call('native_look',{'view':'SCENE'})
        filtered=base64.b64decode(public['image_base64'],validate=True)
        self.assertNotIn(marker.encode('ascii'),filtered)
        self.assertFalse({k for k,p in png_chunks(filtered)}&{b'eXIf',b'tEXt',b'iTXt',b'zTXt',b'vpAg'})
        original_pixels=Image.open(io.BytesIO(raw)).convert('RGBA').tobytes()
        self.assertEqual(Image.open(io.BytesIO(filtered)).convert('RGBA').tobytes(),original_pixels)
        self.assertEqual([p for k,p in png_chunks(filtered) if k==b'IDAT'],
                         [p for k,p in png_chunks(raw) if k==b'IDAT'])

    def test_native_png_palette_transparency_is_preserved(self):
        image=Image.new('P',(384,384),1);image.putpalette([255,0,0,0,255,0]+[0,0,0]*254)
        image.putpixel((0,0),0);image.info['transparency']=bytes([0,151])
        metadata=PngImagePlugin.PngInfo();metadata.add_text('SourcePath','C:/private/fixture.blend')
        stream=io.BytesIO();image.save(stream,format='PNG',pnginfo=metadata)
        raw=stream.getvalue();self.host.native_look=lambda view:self.image_response(raw,view)
        value,_=self.gateway();filtered=base64.b64decode(value.call('native_look',{})['image_base64'])
        self.assertEqual(Image.open(io.BytesIO(filtered)).convert('RGBA').tobytes(),
                         Image.open(io.BytesIO(raw)).convert('RGBA').tobytes())
        self.assertIn(b'tRNS',{k for k,p in png_chunks(filtered)})

    def test_corrupted_native_png_crc_is_rejected(self):
        damaged=bytearray(self.png);offset=8
        while True:
            length=struct.unpack('>I',damaged[offset:offset+4])[0]
            if damaged[offset+4:offset+8]==b'IDAT':
                damaged[offset+8+length]^=1;break
            offset+=length+12
        self.host.native_look=lambda view:self.image_response(bytes(damaged),view)
        value,_=self.gateway()
        with self.assertRaises(ValueError):value.call('native_look',{})

    def test_truncated_or_trailing_native_png_data_is_rejected(self):
        for malformed in (self.png[:-4],self.png+b'D:/private/arm/fixture.blend'):
            with self.subTest(bytes=len(malformed)):
                self.state.clear();value,_=self.gateway()
                self.host.native_look=lambda view:self.image_response(malformed,view)
                with self.assertRaises(ValueError):value.call('native_look',{})

    def test_png_icc_profile_is_explicitly_unsupported_instead_of_leaking_or_changing_color(self):
        chunks=png_chunks(self.png)
        chunks.insert(1,(b'iCCP',b'owner-private-profile\0\0'+zlib.compress(b'D:/private/fixture.blend')))
        raw=b'\x89PNG\r\n\x1a\n'+b''.join(png_chunk(k,p) for k,p in chunks)
        self.host.native_look=lambda view:self.image_response(raw,view)
        value,_=self.gateway()
        with self.assertRaises(ValueError):value.call('native_look',{})


if __name__=='__main__':unittest.main()
