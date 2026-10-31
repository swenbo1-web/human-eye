"""Compact selectors cross observation transports without geometry or authority loss."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from human_eye_plugin.auto_router import _validated_scene
from human_eye_plugin.hook_context import compact_hook_summary, _expand_local
from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.live_spatial_mcp import LIVE_MCP_TOOLS_SCHEMA, LiveSpatialMCPServer, _tool_result
from human_eye_plugin.query_policy import validate_query
from human_eye_plugin.task_brief import project_task_brief
from verification.test_live_service import SelfLockingHost
from verification.test_support_plane_candidate import tilted_scene
from verification.test_host_runtime import mesh


def expand_discovery_metadata(value):
    """Decode the documented same-tool value codec, preserving context string."""
    if 'support_plane_value_encoding' not in value:
        return copy.deepcopy(value)
    document=copy.deepcopy(value)
    document['context_projection']={'reference_encoding':'local_pointer_with_object_id'}
    body=copy.deepcopy(value);body.pop('support_plane_value_encoding')
    result=_expand_local(document,body)
    if 'context_text' in result.get('routing',{}):
        facts=json.loads(body['routing']['context_text'])
        result['routing']['context_text']=json.dumps(_expand_local(document,facts),
            ensure_ascii=False,allow_nan=False)
    return result


class SupportPlaneDiscoveryTransportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name); self.config = self.folder/'config.json'
        self.config.write_text(json.dumps({'schema_version':'1.0',
            'project_root':str(Path(__file__).resolve().parents[1]),
            'state_file':'state.json','audit_file':'audit.jsonl','quad_size':64}),encoding='utf-8')
        self.host = SelfLockingHost(); self.host.scene = tilted_scene()
        self.initial = copy.deepcopy(self.host.scene)
        self.service = LiveSpatialService(self.config,host=self.host)
        self.server = LiveSpatialMCPServer(self.service,default_session_id='discovery-transport')

    @staticmethod
    def args(**changes):
        value = {'focal_id':'part','reference_id':'base','include_image':False,
            'query':{'alignment_evidence':False,'support_plane_discovery':{}}}
        value.update(changes); return value

    @staticmethod
    def body(wire):
        return json.loads(next(c['text'] for c in wire['content'] if c['type']=='text'))

    @staticmethod
    def facts(body):
        return body.get('observation') or json.loads(body['routing']['context_text'])

    def call(self,arguments):
        result = self.server.handle_jsonrpc_message({'jsonrpc':'2.0','id':1,'method':'tools/call',
            'params':{'name':'human_eye_scene_observe','arguments':arguments}})['result']
        return result,self.body(result)

    def assert_discovery(self,body):
        discovery = body['support_plane_discovery']
        self.assertEqual(discovery['status'],'complete',discovery)
        self.assertEqual(len(discovery['candidates']),1,discovery)
        self.assertIs(discovery['execution_authority'],False)
        selector = discovery['candidates'][0]['selector']
        binding = selector['selection_binding']
        _,_,fingerprint = _validated_scene(self.host.scene)
        self.assertEqual(binding,{'scene_revision':self.host.scene['revision'],
            'scene_fingerprint':fingerprint,'focal_id':'part','reference_id':'base'})
        self.assertEqual(body['routing']['support_plane_discovery_ref'],'#/support_plane_discovery')
        self.assertEqual(self.facts(body)['support_plane_discovery_ref'],'#/support_plane_discovery')
        self.assertEqual(body['support_plane_reference_encoding'],'same_tool_result_metadata_json_pointer')
        self.assertNotIn('scene_transport',body)
        self.assertEqual(self.host.calls,0)
        return discovery

    def test_schema_declares_optional_bounded_discovery_and_keeps_four_tools(self):
        self.assertEqual(len(LIVE_MCP_TOOLS_SCHEMA),4)
        query = LIVE_MCP_TOOLS_SCHEMA[0]['inputSchema']['properties']['query']
        schema = query['properties']['support_plane_discovery']
        self.assertFalse(schema['additionalProperties'])
        self.assertEqual(schema['properties']['max_candidates']['maximum'],6)
        self.assertNotIn('support_plane_discovery',query.get('required',[]))

    def test_query_normalization_is_detached_idempotent_and_no_direction_invented(self):
        query={'support_plane_discovery':{}}
        value=validate_query(query)
        self.assertEqual(value['support_plane_discovery'],{'max_candidates':4})
        self.assertEqual(validate_query(value),value)
        self.assertEqual(query,{'support_plane_discovery':{}})
        value['support_plane_discovery']['max_candidates']=2
        self.assertEqual(query,{'support_plane_discovery':{}})
        vector={'support_plane_discovery':{'direction_world':[3,0,7]}}
        result=validate_query(vector)
        self.assertEqual(result['support_plane_discovery']['direction_world'],[3.,0.,7.])
        self.assertEqual(validate_query(result),result)

    def test_bad_discovery_options_reject_before_capture(self):
        invalid=[None,False,[],{'force':True},{'max_candidates':0},{'max_candidates':7},
            {'max_candidates':True},{'direction_world':[0,0,0]},
            {'direction_world':[0,False,1]},{'direction_world':[0,0,float('inf')]},
            {'direction_world':[0,0,float('nan')]},{'direction_world':[0,1]},
            {'direction_world':['0',0,1]}]
        for value in invalid:
            with self.subTest(value=value):
                wire,_=self.call(self.args(query={'support_plane_discovery':value}))
                self.assertTrue(wire['isError'])
        self.assertEqual(self.host.captures,0);self.assertEqual(self.host.calls,0)

    def test_default_observation_does_not_run_or_emit_discovery(self):
        with patch('human_eye_plugin.support_plane_discovery.discover_support_planes',
                   side_effect=AssertionError('default observation ran optional discovery')) as discover:
            wire,body=self.call(self.args(query={'alignment_evidence':False}))
        self.assertFalse(wire['isError'],body);discover.assert_not_called()
        self.assertNotIn('support_plane_discovery',body)
        self.assertNotIn('support_plane_discovery',self.facts(body))

    def test_full_brief_keep_single_canonical_bound_selector_without_mesh_payload(self):
        for detail in ('full','brief'):
            with self.subTest(detail=detail):
                wire,body=self.call(self.args(response_detail=detail))
                self.assertFalse(wire['isError'],body)
                self.assert_discovery(body)
                self.assertFalse(any(c['type']=='image' for c in wire['content']))
                text=wire['content'][0]['text']
                self.assertEqual(text.count('"selection_binding"'),1)
                self.assertNotIn('"vertices"',text)
                self.assertNotIn('"faces"',text)
        self.assertEqual(self.host.captures,2)

    def test_sdk_keeps_detached_full_evidence_in_all_three_locations(self):
        body=self.service.observe('sdk',**self.args())
        facts=json.loads(body['routing']['context_text'])
        self.assertEqual(body['support_plane_discovery'],facts['support_plane_discovery'])
        self.assertEqual(body['support_plane_discovery'],body['routing']['support_plane_discovery'])
        body['support_plane_discovery']['candidates'].clear()
        self.assertEqual(len(facts['support_plane_discovery']['candidates']),1)
        self.assertEqual(len(body['routing']['support_plane_discovery']['candidates']),1)

    def test_cache_hit_still_captures_current_scene_and_new_revision_invalidates(self):
        _,first=self.call(self.args());_,second=self.call(self.args())
        self.assertTrue(second['routing']['cache_hit'])
        self.assertEqual(first['support_plane_discovery'],second['support_plane_discovery'])
        self.host.scene['revision']='revision-after-observation'
        _,third=self.call(self.args())
        self.assertFalse(third['routing']['cache_hit'])
        self.assert_discovery(third)
        self.assertNotEqual(first['support_plane_discovery']['scene_revision'],third['support_plane_discovery']['scene_revision'])
        self.assertEqual(self.host.captures,3)

    def test_direction_or_limit_query_change_cannot_reuse_wrong_discovery(self):
        _,first=self.call(self.args())
        _,parallel=self.call(self.args(query={'alignment_evidence':False,
            'support_plane_discovery':{'direction_world':[1,0,0]}}))
        self.assertFalse(parallel['routing']['cache_hit'])
        self.assertEqual(parallel['support_plane_discovery']['candidates'],[])
        _,limited=self.call(self.args(query={'alignment_evidence':False,
            'support_plane_discovery':{'max_candidates':1}}))
        self.assertFalse(limited['routing']['cache_hit'])
        self.assertEqual(len(limited['support_plane_discovery']['candidates']),1)
        self.assertEqual(self.host.scene,self.initial)

    def test_unpaired_overview_explicitly_reports_no_selector(self):
        self.host.scene['meshes']=self.host.scene['meshes'][:1]
        wire,body=self.call({'include_image':False,'query':{'support_plane_discovery':{}}})
        self.assertFalse(wire['isError'],body)
        d=body['support_plane_discovery']
        self.assertEqual(d['status'],'unsupported')
        self.assertEqual(d['candidates'],[])
        self.assertIn('target_pair_not_established',d['reason_codes'])

    def test_unrelated_open_mesh_keeps_partial_scene_and_pair_discovery_distinct(self):
        unknown=mesh('open',[.5,0,0],[.1,.1,.1]);unknown['faces']=unknown['faces'][:1];unknown['edges']=[]
        self.host.scene['meshes'].append(unknown)
        wire,body=self.call(self.args())
        self.assertFalse(wire['isError'],body)
        self.assertEqual(body['observation_status'],'partial')
        self.assertIsNone(body['routing']['observation_id'])
        self.assertIs(body['routing']['allow_action'],False)
        self.assertEqual(body['support_plane_discovery']['status'],'complete')
        self.assertIs(body['support_plane_discovery']['execution_authority'],False)

    def test_optional_discovery_exception_keeps_strict_measurement_and_no_selector(self):
        with patch('human_eye_plugin.support_plane_discovery.discover_support_planes',side_effect=RuntimeError('injected discovery failure')):
            wire,body=self.call(self.args())
        self.assertFalse(wire['isError'],body)
        facts=self.facts(body)
        self.assertTrue(facts['measurement']['measurement_valid'])
        d=body['support_plane_discovery']
        self.assertEqual(d['status'],'unknown');self.assertEqual(d['candidates'],[])
        self.assertIsNone(d['total_candidate_count']);self.assertIsNone(d['ambiguous'])
        self.assertEqual(d['error_type'],'RuntimeError')

    def test_valid_pair_but_blocked_observation_does_not_silently_drop_requested_discovery(self):
        self.host.scene['meshes'][1]['faces']=self.host.scene['meshes'][1]['faces'][:1]
        self.host.scene['meshes'][1]['edges']=[]
        wire,body=self.call(self.args())
        self.assertTrue(wire['isError'],body)
        self.assertEqual(body['support_plane_discovery']['status'],'unknown')
        self.assertEqual(body['support_plane_discovery']['candidates'],[])
        self.assertIn('observation_pipeline_blocked',body['support_plane_discovery']['reason_codes'])

    def test_hook_projection_preserves_full_selector_and_false_authority(self):
        body=self.service.observe('hook',**self.args());route=body['routing']
        summary={'human_eye_live':'observed','observation':route['context_text'],
            'reason_codes':route['reason_codes'],'allow_action':route['allow_action']}
        projected=compact_hook_summary(summary,body,route,correlation={'source':'private_test'},identity={})
        expanded=_expand_local(projected,projected)
        self.assertEqual(expanded['observation']['support_plane_discovery'],body['support_plane_discovery'])
        self.assertIs(expanded['observation']['support_plane_discovery']['execution_authority'],False)

    def test_mismatched_sdk_copies_are_not_aliased_or_briefed_away(self):
        original=self.service.observe('contradiction',**self.args())
        for location in ('routing','facts'):
            changed=copy.deepcopy(original)
            if location=='routing':changed['routing']['support_plane_discovery']['status']='unknown'
            else:
                facts=json.loads(changed['routing']['context_text'])
                facts['support_plane_discovery']['status']='unknown'
                changed['routing']['context_text']=json.dumps(facts)
            wire=_tool_result(changed,is_error=False,response_detail='brief',compact_support_planes=True);body=self.body(wire)
            self.assertNotIn('response_detail',body)
            self.assertNotIn('support_plane_reference_encoding',body)
            self.assertEqual(body['support_plane_discovery']['status'],'complete')
            self.assertIn('support_plane_discovery',body['routing'])
            self.assertIn('support_plane_discovery',self.facts(body))

    def test_major_fact_codec_expands_to_exact_precodec_full_and_brief_values(self):
        original=self.service.observe('codec-roundtrip',**self.args())
        for detail in ('full','brief'):
            plain=_tool_result(original,is_error=False,response_detail=detail)
            compact=_tool_result(original,is_error=False,response_detail=detail,compact_support_planes=True)
            encoded=self.body(compact)
            self.assertIn('support_plane_value_encoding',encoded)
            self.assertEqual(expand_discovery_metadata(encoded),self.body(plain))
            self.assertEqual(encoded['support_plane_discovery'],original['support_plane_discovery'])
            self.assertEqual(len(encoded['support_plane_discovery']['candidates'][0]['selector']['selection_binding']),4)
            self.assertLess(len(compact['content'][0]['text'].encode()),len(plain['content'][0]['text'].encode()))

    def test_major_fact_codec_preserves_unknown_nulls_and_literal_reserved_keys(self):
        with patch('human_eye_plugin.support_plane_discovery.discover_support_planes',side_effect=ValueError('injected')):
            original=self.service.observe('codec-unknown',**self.args())
        compact=self.body(_tool_result(original,is_error=False,compact_support_planes=True))
        plain=self.body(_tool_result(original,is_error=False))
        self.assertEqual(expand_discovery_metadata(compact),plain)
        self.assertIsNone(compact['support_plane_discovery']['total_candidate_count'])
        literal=copy.deepcopy(original);literal['future_reserved']={'$ref':'literal-user-value'}
        encoded=self.body(_tool_result(literal,is_error=False,compact_support_planes=True))
        self.assertNotIn('support_plane_value_encoding',encoded)
        self.assertEqual(encoded['future_reserved'],{'$ref':'literal-user-value'})

    def test_major_fact_references_only_target_preceding_physical_metadata(self):
        original=self.service.observe('codec-scope',**self.args())
        for detail in ('full','brief'):
            value=self.body(_tool_result(original,is_error=False,response_detail=detail,compact_support_planes=True))
            seen=set();references=[]
            def walk(item,path,physical=True):
                if isinstance(item,dict):
                    if '$ref' in item:
                        self.assertIn(item['$ref'],seen)
                        references.append(item['$ref'])
                    elif physical:seen.add(path)
                    for key,child in item.items():
                        childpath=path+'/'+key.replace('~','~0').replace('/','~1')
                        if key=='context_text':walk(json.loads(child),childpath,False)
                        else:walk(child,childpath,physical)
                elif isinstance(item,list):
                    for i,child in enumerate(item):walk(child,path+'/'+str(i),physical)
            walk(value,'#')
            self.assertTrue(references)
            self.assertFalse(any('/decoded_context_text' in ref or '/context_text/' in ref for ref in references))
            self.assertEqual(expand_discovery_metadata(value),self.body(_tool_result(original,is_error=False,response_detail=detail)))

    def test_nonopted_tool_results_do_not_enable_new_value_codec(self):
        original=self.service.observe('nonopted',focal_id='part',reference_id='base',include_image=False)
        plain=_tool_result(original,is_error=False)
        attempted=_tool_result(original,is_error=False,compact_support_planes=True)
        self.assertEqual(plain,attempted)

    def test_discovery_does_not_change_native_image_bytes(self):
        plain=self.service.observe('plain',focal_id='part',reference_id='base')
        found=self.service.observe('found',focal_id='part',reference_id='base',query={'support_plane_discovery':{}})
        self.assertEqual(plain['routing']['image'],found['routing']['image'])
        self.assertEqual(self.host.calls,0);self.assertEqual(self.host.scene,self.initial)

    def test_compact_full_reply_is_smaller_than_full_geometry_transport(self):
        compact_wire,compact=self.call(self.args(response_detail='brief'))
        full_wire,full=self.call(self.args(query={'alignment_evidence':False},response_detail='brief',scene_delta={}))
        self.assertIn('scene_transport',full)
        self.assert_discovery(compact)
        self.assertLess(len(compact_wire['content'][0]['text'].encode('utf-8')),
                        len(full_wire['content'][0]['text'].encode('utf-8')))


if __name__=='__main__':unittest.main()
