"""Cross-request task/delta/capability behavior through the real service API."""
import copy
import json
from pathlib import Path
import tempfile
import time
import unittest

from human_eye_plugin.auto_router import _validated_scene
from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer
from human_eye_plugin.request_context import validate_task_context, validate_scene_delta_request
from human_eye_plugin.scene_delta import apply_scene_delta
from human_eye_plugin.scene_cache import SpatialSceneCache
from human_eye_plugin.task_metrics import summarize_task_run
from human_eye_plugin.telemetry import RequestTrace
from verification.test_clearance_segment_service import SegmentHost
from verification.test_host_runtime import mesh


class TaskMemoryIntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.config = self.folder/'config.json'
        self.config.write_text(json.dumps({'schema_version':'1.0',
            'project_root':str(Path(__file__).resolve().parents[1]),'state_file':'state.json',
            'audit_file':'events.jsonl','quad_size':64,'max_sessions':4}),encoding='utf-8')
        self.host = SegmentHost()
        self.host.scene['host_execution'] = {'schema_version':'1.0','operation':'rigid_transform',
            'supported':True,'scope':'independent_static_rigid_meshes','reasons':[]}
        self.service = LiveSpatialService(self.config,host=self.host)
        self.context = {'task_id':'clearance-task','task_run_id':'run-one'}
        self.goal = {'focal_id':'part','reference_id':'base','axis':'+z',
            'target_clearance_m':.001,'clearance_tolerance_m':1e-6}

    def observe(self, **changes):
        return self.service.observe('same-session',focal_id='part',reference_id='base',
            include_image=False,task_context=self.context,**changes)

    def rows(self):
        rows = [json.loads(line) for line in (self.folder/'events.jsonl').read_text(encoding='utf-8').splitlines()]
        return [row['trace'] for row in rows if row.get('event')=='request_trace']

    def test_empty_delta_request_provides_complete_reconstructable_snapshot(self):
        result = self.observe(scene_delta={})
        packet = result['scene_transport']
        self.assertEqual(packet['status'],'full')
        reconstructed = apply_scene_delta(None,packet)
        expected,_,fingerprint = _validated_scene(self.host.scene)
        self.assertEqual(reconstructed,expected)
        self.assertEqual(packet['target']['scene_fingerprint'],fingerprint)
        self.assertFalse(packet['execution_authority'])
        self.assertEqual(self.host.calls,0)

    def test_default_observation_does_not_add_full_mesh_transport(self):
        result = self.observe()
        self.assertNotIn('scene_transport',result)
        self.assertNotIn('vertices',result['objects'][0])
        self.assertEqual(result['request_trace']['task_context'],self.context)

    def test_base_lookup_and_new_goal_roundtrip_current_geometry(self):
        initial = self.observe(scene_delta={})['scene_transport']
        base = apply_scene_delta(None,initial)
        moved = self.service.run_clearance_segment('same-session','move-one',self.goal,
            execute=True,task_context=self.context)
        self.assertEqual(moved['status'],'satisfied')
        result = self.observe(scene_delta={
            'base_revision':initial['target']['scene_revision'],
            'base_fingerprint':initial['target']['scene_fingerprint']})
        packet = result['scene_transport']
        self.assertIn(packet['status'],{'full','delta'})
        actual = apply_scene_delta(base,packet)
        self.assertEqual(actual,_validated_scene(self.host.scene)[0])
        if packet['status']=='delta':
            with self.assertRaises(ValueError):
                apply_scene_delta(actual,packet)

    def test_unknown_or_evicted_base_resynchronizes_without_reusing_another_revision(self):
        self.observe()
        result = self.observe(scene_delta={'base_revision':'missing','base_fingerprint':'0'*64})
        self.assertEqual(result['scene_transport']['status'],'full')
        self.assertEqual(apply_scene_delta(None,result['scene_transport']),_validated_scene(self.host.scene)[0])

    def test_old_invalid_metadata_base_does_not_hide_fresh_observation(self):
        import hashlib
        bad=_validated_scene(self.host.scene)[0]
        bad['host_identity']['object_instances']['not-captured']='invalid-instance'
        encoded=json.dumps(bad,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()
        cache=SpatialSceneCache()
        cache.record_scene(bad)  # Older history contract validates geometry only.
        self.service._perception_cache=cache
        result=self.observe(scene_delta={'base_revision':bad['revision'],
            'base_fingerprint':hashlib.sha256(encoded).hexdigest()})
        self.assertEqual(result['status'],'observed')
        self.assertEqual(result['scene_transport']['status'],'full')
        self.assertEqual(result['scene_transport_diagnostic']['base_status'],'invalid_or_unusable_full_resync')
        self.assertEqual(apply_scene_delta(None,result['scene_transport']),_validated_scene(self.host.scene)[0])
        self.assertEqual(self.host.calls,0)

    def test_document_change_cannot_merge_old_delta(self):
        initial = self.observe(scene_delta={})['scene_transport']
        base = apply_scene_delta(None,initial)
        self.host.scene['host_identity']['document_epoch']='new-document'
        result = self.observe(scene_delta={'base_revision':initial['target']['scene_revision'],
            'base_fingerprint':initial['target']['scene_fingerprint']})
        self.assertEqual(result['scene_transport']['status'],'full')
        self.assertEqual(apply_scene_delta(base,result['scene_transport']),_validated_scene(self.host.scene)[0])

    def test_current_pair_capabilities_remain_non_authorizing(self):
        result = self.observe()
        capabilities = result['scene_capabilities']
        self.assertFalse(capabilities['execution_authority'])
        self.assertFalse(capabilities['changes_existing_gates'])
        self.assertEqual(capabilities['scene_revision'],result['routing']['scene_revision'])
        self.assertEqual(capabilities['scene']['candidate_endpoint']['status'],'not_evaluated')
        self.assertEqual(capabilities['scene']['swept_path']['status'],'not_evaluated')
        self.assertEqual({item['object_id'] for item in capabilities['objects']},{'part','base'})
        self.assertEqual(capabilities,json.loads(result['routing']['context_text'])['scene_capabilities'])

    def test_far_modifier_can_be_read_but_still_blocks_current_motion_domain(self):
        self.host.scene['meshes'].append(mesh('far',[10,0,0],[1,1,1]))
        self.host.scene['host_identity']['object_instances']['far']='far-instance'
        self.host.scene['host_execution'].update(supported=False,reasons=[{
            'object_id':'far','object_name':'far','reason':'modifiers_present'}])
        result = self.observe()
        capabilities = result['scene_capabilities']
        self.assertEqual(capabilities['scene']['captured_object_count'],3)
        self.assertEqual(capabilities['scene']['detailed_object_count'],2)
        self.assertEqual(capabilities['scene']['host_editability_gate']['status'],'unsupported')
        self.assertTrue(all(item['movable']['status']=='unsupported' for item in capabilities['objects']))
        refused = self.service.run_clearance_segment('same-session','unsupported-host',self.goal,execute=True)
        self.assertEqual(refused['status'],'blocked')
        self.assertEqual(self.host.calls,0)

    def test_three_real_request_traces_form_one_task_with_replay_separate(self):
        started = time.monotonic_ns()
        self.observe()
        self.service.run_clearance_segment('same-session','move-one',self.goal,execute=True,task_context=self.context)
        self.service.run_clearance_segment('same-session','move-one',self.goal,execute=True,task_context=self.context)
        duration = time.monotonic_ns()-started
        traces = self.rows()
        summary = summarize_task_run(traces,**self.context,duration_ns=duration,
            expected_request_ids=[row['request_id'] for row in traces])
        self.assertEqual(summary['outer_request_attempts'],3)
        self.assertEqual(summary['receipt_replayed_outer_requests'],1)
        self.assertEqual(summary['duration_ns'],duration)
        self.assertIsNone(summary['goal_completion_count'])
        self.assertEqual(summary['model_usage']['availability'],'unknown')
        self.assertTrue(summary['coverage']['complete_against_declared_requests'],summary)
        self.assertEqual(self.host.calls,1)
        calls = summary['span_evidence']['host_apply_call_spans']['observed_call_spans']
        self.assertEqual(calls,1)

    def test_conflicting_enclosing_task_context_is_refused_before_capture(self):
        with RequestTrace('host.context') as trace:
            trace.annotate(task_id='other',task_run_id='another-run')
            with self.assertRaises(ValueError):self.observe()
        self.assertEqual(self.host.captures,0)
        self.assertEqual(self.host.calls,0)

    def test_explicit_context_cannot_replace_partial_enclosing_labels(self):
        with RequestTrace('host.partial_context') as trace:
            trace.annotate(task_id='already-bound')
            with self.assertRaises(ValueError):self.observe()
        self.assertEqual(self.host.captures,0)

    def test_task_labels_do_not_require_copying_the_full_trace(self):
        from unittest.mock import PropertyMock, patch
        from human_eye_plugin.request_context import bind_task_context,trace_task_context
        with RequestTrace('host.light_context') as trace:
            with patch.object(RequestTrace,'record',new_callable=PropertyMock,
                              side_effect=AssertionError('full trace copied')):
                self.assertEqual(bind_task_context(trace,self.context),self.context)
                self.assertEqual(trace_task_context(trace),self.context)

    def test_mcp_context_and_transport_share_actual_service_trace(self):
        server = LiveSpatialMCPServer(self.service,default_session_id='same-session')
        result = server.handle_jsonrpc_message({'jsonrpc':'2.0','id':4,'method':'tools/call',
            'params':{'name':'human_eye_scene_observe','arguments':{'focal_id':'part','reference_id':'base',
                'task_context':self.context,'scene_delta':{}}}})['result']
        self.assertFalse(result['isError'])
        text = json.loads(result['content'][0]['text'])
        self.assertEqual(text['request_trace']['task_context'],self.context)
        rows = self.rows()
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['correlation']['task_id'],self.context['task_id'])

    def test_bad_optional_contexts_and_bases_fail_before_host_read(self):
        for context in ({},True,{'task_id':'x'},{**self.context,'grant':True},
                        {'task_id':' ','task_run_id':'r'},{'task_id':'x','task_run_id':'bad\n'}):
            with self.subTest(context=context),self.assertRaises(ValueError):
                self.service.observe('s',task_context=context)
        for reference in (True,{'base_revision':'r'},{'base_fingerprint':'0'*64},
                          {'base_revision':'r','base_fingerprint':'bad'}):
            with self.subTest(reference=reference),self.assertRaises(ValueError):
                self.service.observe('s',scene_delta=reference)
        self.assertEqual(self.host.captures,0)

    def test_bad_unicode_task_context_does_not_stop_stdio_or_read_host(self):
        import io
        from human_eye_plugin.live_spatial_mcp import run_stdio_mcp_server
        messages=[{'jsonrpc':'2.0','id':1,'method':'tools/call','params':{
            'name':'human_eye_scene_observe','arguments':{
                'task_context':{'task_id':'\ud800','task_run_id':'r'}}}},
            {'jsonrpc':'2.0','id':2,'method':'ping'}]
        incoming=io.StringIO(''.join(json.dumps(row)+'\n' for row in messages))
        outgoing=io.StringIO()
        run_stdio_mcp_server(self.service,incoming,outgoing)
        rows=[json.loads(line) for line in outgoing.getvalue().splitlines()]
        self.assertTrue(rows[0]['result']['isError'])
        self.assertEqual(rows[1],{'jsonrpc':'2.0','id':2,'result':{}})
        self.assertEqual(self.host.captures,0)
        self.assertEqual(self.host.calls,0)

    def test_wire_capability_aliases_preserve_full_sdk_facts_and_numeric_types(self):
        from human_eye_plugin.live_spatial_mcp import _tool_result
        sdk=self.observe()
        original=copy.deepcopy(sdk)
        wire=_tool_result(sdk,is_error=False)
        metadata=json.loads(wire['content'][0]['text'])
        self.assertEqual(sdk,original)
        self.assertEqual(metadata['scene_capabilities'],sdk['scene_capabilities'])
        self.assertEqual(metadata['routing']['scene_capabilities_ref'],'#/scene_capabilities')
        facts=json.loads(metadata['routing']['context_text'])
        self.assertEqual(facts.pop('scene_capabilities_ref'),'#/scene_capabilities')
        facts['scene_capabilities']=metadata['scene_capabilities']
        self.assertEqual(facts,json.loads(sdk['routing']['context_text']))
        conflicting={'scene_capabilities':{'v':False},'routing':{
            'scene_capabilities':{'v':0},'context_text':json.dumps({'scene_capabilities':{'v':0.0}})}}
        projected=json.loads(_tool_result(conflicting,is_error=False)['content'][0]['text'])
        self.assertIn('scene_capabilities',projected['routing'])
        self.assertIn('scene_capabilities',json.loads(projected['routing']['context_text']))

    def test_cache_lookup_requires_both_revision_and_complete_content(self):
        cache = SpatialSceneCache()
        first = _validated_scene(self.host.scene)[0]
        cache.record_scene(first)
        changed = copy.deepcopy(first)
        changed['meshes'][1]['name']='renamed'
        cache.record_scene(changed)
        fingerprint = _validated_scene(first)[2]
        found = cache.find_snapshot(first['revision'],fingerprint)
        self.assertEqual(found,first)
        found['meshes'][0]['name']='mutated return'
        self.assertEqual(cache.find_snapshot(first['revision'],fingerprint),first)
        self.assertIsNone(cache.find_snapshot(first['revision'],'0'*64))


if __name__=='__main__':unittest.main()
