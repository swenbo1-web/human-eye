"""Production read-only routing/consumer contracts; no subprocess or GUI I/O.

Fixtures reuse known geometry and private audit shapes. Actual Blender pixels,
socket identity and automatic host activation remain separate acceptance gates.
"""
from __future__ import annotations
import base64,copy,hashlib,io,json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from PIL import Image,PngImagePlugin

from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer,_tool_result,LIVE_MCP_TOOLS_SCHEMA
from human_eye_plugin.live_hooks import route_live_hook
from human_eye_plugin.native_observation import (READONLY_OBSERVATION_PROTOCOL,READONLY_BUDGET_SCOPE,
    validate_readonly_observation)
from human_eye_plugin.query_policy import validate_query
from verification.test_live_service import SelfLockingHost
from verification import test_multiscale_entry as fixture_multiscale


class ReadonlyProductEntryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.config=self.root/'connector.json'
        self.config.write_text(json.dumps({'schema_version':'1.0','enabled':True,
            'project_root':str(Path(__file__).resolve().parents[1]),'state_file':'state.json',
            'audit_file':'audit.jsonl','quad_size':64,'native_visual_timeout_s':10.}),encoding='utf8')

    def native(self,*,far=False):
        helper=fixture_multiscale.MultiscaleEntryTests();helper.setUp();self.addCleanup(helper.doCleanups)
        helper.enable(far=far);case=helper.case;host=case.host
        host.capture_scene=Mock(side_effect=lambda:copy.deepcopy(case.current['capture']))
        caps={'schema_version':'native-readonly-capabilities-v1','protocol':READONLY_OBSERVATION_PROTOCOL,
            'process_id':host._process.pid,'clock':case.counter,'max_duration_ns':30_000_000_000,
            'host_source_sha256':'a'*64,'read_only':True,'execution_authority':False}
        host.native_observation_capabilities=Mock(return_value=caps)
        self.raw=None;self.arguments=None;self.mutate=lambda raw:None
        def observe(request_id,focal_id,reference_id,expected_capture_revision,deadline_ns,view):
            started=time.perf_counter_ns();result=helper.bundle(view)
            result['plan']['budget_scope']=READONLY_BUDGET_SCOPE
            bundle=copy.deepcopy(helper.last_bundle);bundle['plan']=copy.deepcopy(result['plan'])
            evidence=host.capture_readonly_evidence()
            coherence=evidence['coherence'];capture=evidence['capture']
            coherence.update(capture_revision=capture['revision'],native_revision=evidence['native_scene']['revision'],
                capture_fingerprint=hashlib.sha256(json.dumps(capture,sort_keys=True,separators=(',',':'),
                    ensure_ascii=False,allow_nan=False).encode()).hexdigest())
            result.update(evidence=evidence,observation={
                'schema_version':'native-readonly-observation-v1','protocol':READONLY_OBSERVATION_PROTOCOL,
                'request_id':request_id,'view':view,'status':'completed',
                'expected_capture_revision':expected_capture_revision,
                'binding':{**case.binding,'process_id':caps['process_id']},
                'started_ns':started,'deadline_ns':deadline_ns,'finished_ns':time.perf_counter_ns(),
                'capture_revision_before':capture['revision'],'capture_revision_after':capture['revision'],
                'native_revision_before':evidence['native_scene']['revision'],
                'native_revision_after':evidence['native_scene']['revision'],
                'geometry_restored':True,'state_restored':True,'quarantined':False,'error':None,
                'bundle':bundle,'read_only':True,'execution_authority':False})
            self.mutate(result);self.raw=copy.deepcopy(result)
            self.arguments=dict(captured=copy.deepcopy(capture),capabilities=copy.deepcopy(caps),request_id=request_id,
                focal_id=focal_id,reference_id=reference_id,deadline_ns=deadline_ns,view=view)
            return result
        host.observe_readonly_native=Mock(side_effect=observe)
        self.host,self.case=host,case
        return LiveSpatialService(self.config,host=host)

    def observe(self,service,**changes):
        return service.observe('test',focal_id=self.case.focal,reference_id=self.case.reference,**changes)

    def call(self,service,**arguments):
        return LiveSpatialMCPServer(service).handle_jsonrpc_message({'jsonrpc':'2.0','id':1,'method':'tools/call',
            'params':{'name':'human_eye_scene_observe','arguments':{'session_id':'test',
                'focal_id':self.case.focal,'reference_id':self.case.reference,**arguments}}})['result']

    def test_native_pair_is_delivered_after_save_without_old_canvas_or_persisted_pixels(self):
        service=self.native(far=True)
        with patch('human_eye_plugin.auto_router._render_scene_canvas_prepared',side_effect=AssertionError('old render')):
            output=self.observe(service,query={'native_visual':{'view':'XY'}})
        self.assertEqual(output['visual_delivery']['source'],'blender_native_multiscale')
        self.assertEqual(output['visual_delivery']['image_count'],2)
        self.assertNotIn('image',output['routing']);self.assertEqual(len(output['routing']['images']),2)
        self.host.native_observation_capabilities.assert_called_once();self.host.observe_readonly_native.assert_called_once()
        self.assertEqual(len(self.arguments['request_id']),32)
        self.assertEqual(json.loads(output['routing']['context_text'])['canvas']['source'],'blender_native_multiscale')
        persisted=(self.root/'state.json').read_text(encoding='utf8')
        for private in ('image_base64','native-multiscale-plan-v1','native-render-state-v1','private-owner','"images"'):
            self.assertNotIn(private,persisted)
        output['routing']['images'].clear()
        # The next observation creates a new lease; response mutation cannot
        # corrupt a cached response or turn old pixels into a fresh result.
        with patch('human_eye_plugin.auto_router._render_scene_canvas_prepared',side_effect=AssertionError('old render')):
            again=self.observe(service,query={'native_visual':{'view':'XY'}})
        self.assertEqual(len(again['routing']['images']),2)
        self.assertEqual(self.host.observe_readonly_native.call_count,2)

    def test_real_mcp_server_returns_two_native_blocks_and_no_private_json_in_full_and_brief(self):
        service=self.native(far=True)
        for detail in ('full','brief'):
            output=self.call(service,response_detail=detail,query={'native_visual':{'view':'XY'}})
            self.assertFalse(output['isError']);self.assertEqual([c['type'] for c in output['content']],['text','image','image'])
            text=output['content'][0]['text'];metadata=json.loads(text)
            self.assertEqual(metadata['visual_delivery']['plan']['image_count'],2)
            for value in ('image_base64','private-owner','private_path','render_audit','object_instances','host_source_sha256'):
                self.assertNotIn(value,text)
            self.assertNotIn('images',metadata.get('routing',{}))
        self.assertEqual(len(LIVE_MCP_TOOLS_SCHEMA),4)

    def test_default_auto_ordinary_scene_delivers_one_native_image(self):
        service=self.native();output=self.observe(service)
        self.assertEqual(output['visual_delivery']['requested_mode'],'auto')
        self.assertEqual(output['visual_delivery']['plan']['view'],'SCENE')
        self.assertEqual(output['visual_delivery']['image_count'],1)
        self.assertIsNone(output['visual_delivery']['plan']['detail'])
        self.assertEqual(validate_query(None),{'mode':'overview','max_exact_pairs':255})

    def test_declared_but_malformed_capability_is_not_a_legacy_fallback(self):
        service=self.native()
        for change in ({'protocol':READONLY_OBSERVATION_PROTOCOL},{'supported':False,'extra':True},
                       {**self.host.native_observation_capabilities.return_value,'process_id':True},
                       {**self.host.native_observation_capabilities.return_value,'clock':{}}):
            self.host.native_observation_capabilities.return_value=change
            with self.subTest(change=change),patch('human_eye_plugin.auto_router._render_scene_canvas_prepared',
                    side_effect=AssertionError('no projection fallback')),self.assertRaises(ValueError):
                self.observe(service)
        self.host.observe_readonly_native.assert_not_called()
        self.assertFalse((self.root/'state.json').exists())

    def test_include_image_false_never_probes_native_or_renders_projection_and_hook_does_not_claim_negotiation(self):
        service=self.native();self.host.native_observation_capabilities.side_effect=AssertionError('no cap')
        with (patch('human_eye_plugin.auto_router._render_scene_canvas_prepared',side_effect=AssertionError('old render')),
                patch('human_eye_plugin.live_service.render_scene_canvas',side_effect=AssertionError('overview render'))):
            output=self.observe(service,include_image=False)
            names=[m['name'] for m in self.case.current['capture']['meshes']]
            hook=route_live_hook({'hook_event_name':'UserPromptSubmit','session_id':'wire-unit',
                'prompt':f'Inspect Blender objects "{names[0]}" and "{names[1]}" clearance, observe only.'},
                service,invocation_source='manual_protocol_fixture')
        self.assertEqual(output['visual_delivery']['capability_status'],'not_probed')
        summary=json.loads(hook['hookSpecificOutput']['additionalContext'])
        self.assertEqual(summary['visual_delivery']['source'],'none')
        self.assertEqual(summary['visual_delivery']['capability_status'],'not_probed')
        self.assertEqual(summary['delivery'],'text_only_hook_no_native_image')
        self.host.native_observation_capabilities.assert_not_called();self.host.observe_readonly_native.assert_not_called()

    def test_projection_explicit_and_analytical_labels_never_probe(self):
        service=self.native();self.host.native_observation_capabilities.side_effect=AssertionError('no cap')
        for query in ({'native_visual':{'mode':'projection'}},{'label_object_ids':[self.case.focal]},
                      {'visual_diagnostic':'contact_section'}):
            output=self.observe(service,query=query)
            self.assertEqual(output['visual_delivery']['source'],'analytical_projection')
            self.assertEqual(output['visual_delivery']['capability_status'],'not_probed')
        self.host.native_observation_capabilities.assert_not_called();self.host.observe_readonly_native.assert_not_called()

    def test_legacy_host_fallback_is_explicit_and_forced_multiscale_fails(self):
        host=SelfLockingHost();service=LiveSpatialService(self.config,host=host)
        output=service.observe('old',focal_id='part',reference_id='base')
        self.assertEqual(output['visual_delivery']['source'],'analytical_projection')
        self.assertEqual(output['visual_delivery']['capability_status'],'unsupported')
        self.assertEqual(output['visual_delivery']['reason_code'],'host_native_observation_not_supported')
        with self.assertRaisesRegex(ValueError,'does not support'):
            service.observe('old',focal_id='part',reference_id='base',query={'native_visual':{'mode':'multiscale'}})
        self.assertEqual(host.calls,0)

    def test_invalid_visual_request_is_rejected_before_capture(self):
        service=self.native()
        invalid=[{'native_visual':None},{'native_visual':{'mode':True}},{'native_visual':{'view':'FOV'}},
            {'native_visual':{'deadline_ns':time.perf_counter_ns()+1000000}},
            {'native_visual':{'mode':'multiscale'},'label_object_ids':[self.case.focal]},
            {'native_visual':{'mode':'multiscale'},'visual_diagnostic':'contact_section'}]
        for query in invalid:
            with self.subTest(query=query),self.assertRaises(ValueError):self.observe(service,query=query)
        self.host.capture_scene.assert_not_called();self.host.native_observation_capabilities.assert_not_called()

    def test_negotiated_failure_never_falls_back_or_leaks_error_or_commits_state(self):
        service=self.native(far=True)
        self.host.observe_readonly_native.side_effect=OSError('D:/private-owner/secret.blend')
        with patch('human_eye_plugin.auto_router._render_scene_canvas_prepared',side_effect=AssertionError('old render')):
            response=self.call(service)
        self.assertTrue(response['isError']);self.assertEqual(len(response['content']),1)
        self.assertIn('no projection fallback',response['content'][0]['text'])
        self.assertNotIn('private-owner',response['content'][0]['text'])
        self.assertFalse((self.root/'state.json').exists())

    def test_complete_validator_rejects_each_corruption_without_partial_delivery(self):
        service=self.native(far=True);self.observe(service,query={'native_visual':{'view':'XY'}})
        mutations=[lambda x:x['observation'].update(execution_authority=True),
            lambda x:x['observation'].update(request_id='replayed'),
            lambda x:x['observation'].update(finished_ns=x['observation']['deadline_ns']),
            lambda x:x['observation']['binding'].update(process_id=123),
            lambda x:x['observation'].update(state_restored=False),
            lambda x:x['observation']['bundle']['frames'][1].update(png_sha256='f'*64),
            lambda x:x['observation']['bundle']['frames'][1]['frustum'].update(clip_end_bu=.001),
            lambda x:x['plan'].update(budget_scope='per_call_original_episode_deadline'),
            lambda x:x['evidence']['coherence'].update(read_only_evidence=False),
            lambda x:x['evidence']['capture'].update(revision='stale')]
        for mutation in mutations:
            raw=copy.deepcopy(self.raw);mutation(raw)
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                validate_readonly_observation(raw,**self.arguments)

    def test_corrupt_second_frame_fails_the_real_mcp_delivery_before_commit(self):
        service=self.native(far=True)
        self.mutate=lambda raw:raw['observation']['bundle']['frames'][1].update(png_sha256='0'*64)
        with patch('human_eye_plugin.auto_router._render_scene_canvas_prepared',side_effect=AssertionError('old render')):
            response=self.call(service,query={'native_visual':{'view':'XY'}})
        self.assertTrue(response['isError']);self.assertEqual([c['type'] for c in response['content']],['text'])
        self.assertNotIn('native-render',response['content'][0]['text'])
        self.assertFalse((self.root/'state.json').exists())

    def test_png_privacy_projection_preserves_rgba_and_bad_second_frame_is_atomic(self):
        image=Image.new('RGBA',(384,384),(20,120,230,73));stream=io.BytesIO()
        metadata=PngImagePlugin.PngInfo();metadata.add_text('file','D:/private-owner/secret.blend')
        image.save(stream,format='PNG',pnginfo=metadata)
        block={'type':'image','mimeType':'image/png','data':base64.b64encode(stream.getvalue()).decode()}
        value={'status':'observed','routing':{'images':[block,copy.deepcopy(block)]}}
        result=_tool_result(value,is_error=False)
        for content in result['content'][1:]:
            decoded=base64.b64decode(content['data']);self.assertNotIn(b'private-owner',decoded)
            self.assertEqual(Image.open(io.BytesIO(decoded)).convert('RGBA').tobytes(),image.tobytes())
        value['routing']['images'][1]['data']='not-base64'
        with self.assertRaises(ValueError):_tool_result(value,is_error=False)


if __name__=='__main__':unittest.main()
