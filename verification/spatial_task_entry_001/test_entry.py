"""Dedicated task entry contracts; memory hosts, StringIO and mocked launchers."""
import copy
import io
import json
import time
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np

from human_eye_plugin import live_spatial_mcp as mcp, live_service, production_server
from human_eye_plugin import task_query, telemetry
from verification.task_scope_impl_001 import test_scope as prior
from verification import test_live_spatial_mcp as old_mcp
from verification.test_concave_geometry import box, entity

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
NAME='human_eye_spatial_relations'
prior.OUT=OUT

def compact(value):return json.dumps(value,ensure_ascii=True,allow_nan=False,separators=(',',':')).encode()
def save(name,value):(OUT/name).write_bytes((json.dumps(value,indent=2,allow_nan=False)+'\n').encode())
def args(candidates=('b','c','d'),aabb=False):
    return {'target':{'id':'a'},'candidates':[{'id':oid} for oid in candidates],**({'include_aabb':True} if aabb else {})}

def cases():
    rows=[]
    def add(label,tool,value,expected):rows.append(dict(name=label,tool=tool,arguments=value,expected=expected,
        schema='dedicated' if tool==NAME else 'legacy'))
    add('new_minimum',NAME,args(),True)
    add('new_one_aabb',NAME,args(('b',),True),True)
    for key,value in (('include_image',False),('query',{}),('mode','task'),('requested_facts',[]),
                      ('session_id','x'),('task_context',{})):
        add('new_extra_'+key,NAME,{**args(),key:value},False)
    for value in (0,1,None,'false'):add('new_aabb_'+repr(value),NAME,{**args(),'include_aabb':value},False)
    for label,value in [('zero',[]),('four',[{'id':str(i)} for i in range(4)]),('none',None)]:
        add('new_candidates_'+label,NAME,{**args(),'candidates':value},False)
    add('new_dual_selector',NAME,{**args(),'target':{'name':'a','id':'a'}},False)
    add('new_missing_target',NAME,{'candidates':[{'id':'b'}]},False)
    add('new_missing_candidates',NAME,{'target':{'id':'a'}},False)
    frozen=json.loads(Path('D:/hefe/verification/fixes/20261109_adoption_entry/FROZEN_ENTRY_AUDIT.json').read_bytes())
    for row in frozen['cases']:add('frozen_'+row['label'],'human_eye_scene_observe',row['args'],row['runtime_task_shape_supported'])
    base={'query':{'mode':'task','target':{'id':'a'},'candidates':[{'id':'b'}],
                   'requested_facts':['closed_solid_relation','surface_proximity']},'include_image':False}
    for key,value in [('focal_id','a'),('reference_id','b'),('goal',{'target_clearance_m':1.,'clearance_tolerance_m':0.}),('scene_delta',{})]:
        add('task_'+key,'human_eye_scene_observe',{**base,key:value},False)
        add('task_null_'+key,'human_eye_scene_observe',{**base,key:None},False)
        add('overview_'+key,'human_eye_scene_observe',{'query':{'mode':'overview'},key:value},True)
        add('overview_null_'+key,'human_eye_scene_observe',{'query':{'mode':'overview'},key:None},False)
    add('legacy_pair_valid','human_eye_scene_observe',{'query':{'mode':'task','objects':[{'id':'a'},{'id':'b'}],
        'requested_facts':['pair_relation']},'include_image':False},True)
    add('overview_default_image','human_eye_scene_observe',{'query':{'mode':'overview'}},True)
    return rows


class PublicContracts(unittest.TestCase):
    def test_catalogues_size_and_default_four_tools(self):
        service=old_mcp.FakeService()
        response=mcp.LiveSpatialMCPServer(service,spatial_task_only=True).handle_jsonrpc_message(
            {'jsonrpc':'2.0','id':1,'method':'tools/list'})
        default=mcp.LiveSpatialMCPServer(service).handle_jsonrpc_message({'jsonrpc':'2.0','id':1,'method':'tools/list'})
        self.assertEqual([r['name'] for r in response['result']['tools']],[NAME])
        self.assertEqual(default['result']['tools'],mcp.LIVE_MCP_TOOLS_SCHEMA)
        self.assertEqual(len(default['result']['tools']),4)
        baseline=json.loads((ROOT/'verification/task_scope_entry_opt_001/catalogue_response.json').read_bytes())
        self.assertEqual(default['result']['tools'][1:],baseline['result']['tools'][1:])
        self.assertLessEqual(len(compact(response)),1536)
        self.assertLessEqual(len(compact(response)),19204*.08)
        self.assertEqual(service.calls,[])
        (OUT/'dedicated_catalogue.json').write_bytes(compact(response))
        (OUT/'default_catalogue.json').write_bytes(compact(default))
        save('dedicated_schema.json',response['result']['tools'][0]['inputSchema'])
        save('legacy_schema.json',default['result']['tools'][0]['inputSchema'])
        save('schema_cases.json',cases())
        save('BYTES.json',dict(compact_ascii_JSONRPC_id=1,frozen_catalogue_B=19204,
            frozen_observe_descriptor_B=10118,dedicated_catalogue_B=len(compact(response)),
            dedicated_descriptor_B=len(compact(response['result']['tools'][0])),
            default_catalogue_B=len(compact(default)),catalogue_reduction_fraction=1-len(compact(response))/19204))
    def test_original_validators_match_schema_case_expectations(self):
        results=[]
        for row in cases():
            try:mcp._validate_arguments(row['tool'],copy.deepcopy(row['arguments']))
            except ValueError as error:actual=False;reason=str(error)
            else:actual=True;reason=None
            with self.subTest(case=row['name']):self.assertEqual(actual,row['expected'])
            results.append(dict(**row,actual=actual,reason=reason))
        save('parser_results.json',dict(checks=len(results),rows=results,passed=True))
    def test_mode_gates_unpublished_tools_and_strict_boolean(self):
        service=old_mcp.FakeService()
        for bad in (1,'true',None):
            with self.assertRaises(ValueError):mcp.LiveSpatialMCPServer(service,spatial_task_only=bad)
        for only,names in ((True,[t['name'] for t in mcp.LIVE_MCP_TOOLS_SCHEMA]+['other']), (False,[NAME])):
            server=mcp.LiveSpatialMCPServer(service,spatial_task_only=only)
            for name in names:
                reply=server.handle_jsonrpc_message({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':name,'arguments':{}}})
                self.assertTrue(reply['result']['isError'])
                self.assertIn('not exposed',reply['result']['content'][0]['text'])
        self.assertEqual(service.calls,[])
    def test_repeated_validation_preserves_inputs_and_set_normalization(self):
        for candidates in (('b',),('b','c','d')):
            value=args(candidates);before=copy.deepcopy(value)
            for _ in range(2):mcp._validate_arguments(NAME,value)
            normalized=mcp.validate_query(mcp._spatial_task_query(value))
            self.assertEqual(normalized['scope'],task_query.SET_SCOPE)
            self.assertEqual(mcp.validate_query(json.loads(json.dumps(normalized))),normalized)
            self.assertEqual(value,before)


class AliasRoutes(unittest.TestCase):
    setUp=prior.ScopeTests.setUp
    query=prior.ScopeTests.query
    work=prior.ScopeTests.work
    def arrange(self,*a,**kw):
        prior.ScopeTests.arrange(self,*a,**kw)
        self.server=mcp.LiveSpatialMCPServer(self.service,'scope-test',spatial_task_only=True)
    def call(self,query=None):
        query=query or self.query()
        arguments={'target':query['target'],'candidates':query['candidates'],
                   'include_aabb':'aabb' in query['requested_facts']}
        response=self.server.handle_jsonrpc_message({'jsonrpc':'2.0','id':7,'method':'tools/call',
            'params':{'name':NAME,'arguments':arguments}})
        return response,json.loads(response['result']['content'][0]['text'])
    def observe(self,query=None):return self.call(query)[1]
    test_one_capture_four_meshes=prior.ScopeTests.test_one_capture_validate_full_binding_four_entities_three_helpers_one_rank
    test_cache_and_local_changes=prior.ScopeTests.test_cold_hot_and_geometry_changes_aggregate_counts
    test_duplicate_missing_self=prior.ScopeTests.test_duplicates_alias_self_and_missing_preserve_all_rows
    test_ambiguity_unknown_target=prior.ScopeTests.test_ambiguous_candidate_and_missing_target_keep_other_evidence
    test_containment=prior.ScopeTests.test_containment_positive_surface_distance_is_not_separation_gap
    test_contact_and_ties=prior.ScopeTests.test_touching_and_exact_ties
    test_open_shell=prior.ScopeTests.test_relation_unknown_does_not_become_complete_by_filtering
    test_exact_order_same_display=prior.ScopeTests.test_exact_rank_distinguishes_equal_float_displays
    def test_one_public_observe_no_image_and_same_legacy_result(self):
        self.arrange();arguments=args(aabb=True);query=mcp._spatial_task_query(arguments)
        with patch.object(self.service,'observe',wraps=self.service.observe) as observe, \
             patch.object(mcp,'_tool_result',wraps=mcp._tool_result) as encoded:
            response=self.server.handle_jsonrpc_message({'jsonrpc':'2.0','id':'caller-17','method':'tools/call',
                'params':{'name':NAME,'arguments':arguments}})
        self.assertEqual(observe.call_count,1);self.assertEqual(encoded.call_count,1)
        self.assertFalse(observe.call_args.kwargs['include_image'])
        self.assertEqual(observe.call_args.kwargs['query'],query)
        result=json.loads(response['result']['content'][0]['text']);result.pop('trace_id')
        old=self.service.observe('scope-test',query=query,include_image=False);old.pop('trace_id')
        self.assertEqual(result,old)
        self.assertEqual(len(response['result']['content']),1)
        save('alias_result.json',response)
    def test_domain_refusal_retains_unknown(self):
        a=box(identity='a');b=box((4,0,0),identity='b')
        self.arrange([a,entity('b',b.vertices,np.tile(b.faces,(420,1)))])
        response,value=self.call(self.query(('b',),aabb=False))
        self.assertTrue(response['result']['isError']);self.assertEqual(value['status'],'unknown')
        self.assertFalse(value['summary']['nearest_separated_complete'])
    def test_trace_maps_to_observe_and_image_false_with_caller_id(self):
        self.arrange();self.call()
        rows=[json.loads(line) for line in self.service.audit_path.read_text().splitlines()]
        traces=[row['trace'] for row in rows if row['event']=='request_trace']
        self.assertEqual(len(traces),1)
        trace=traces[0]
        self.assertEqual(trace['operation'],'mcp.observe')
        self.assertIs(trace['annotations']['include_image'],False)
        self.assertEqual(trace['annotations']['mcp_request_id'],7)
        self.assertEqual(trace['annotations']['mcp_request_id_type'],'integer')
        self.assertEqual(trace['annotations']['mcp_native_image_block_count'],0)
        save('trace.json',trace)
    def test_publication_deadline_kept(self):
        self.arrange();check=self.service._check_request_budget
        def expire(stage,*a,**kw):
            if stage=='before_task_publication':raise live_service.RequestBudgetError('late','publication')
            return check(stage,*a,**kw)
        with patch.object(self.service,'_check_request_budget',side_effect=expire):
            response,_=self.call();self.assertTrue(response['result']['isError'])
    def test_encoding_budget_is_the_original_request_deadline(self):
        self.arrange();encode=mcp._tool_result
        def expire(*a,**kw):
            if not kw.get('is_error'):
                budget=live_service._REQUEST_BUDGET.get();self.assertIsNotNone(budget)
                budget['deadline']=time.monotonic()-1
            return encode(*a,**kw)
        with patch.object(mcp,'_tool_result',side_effect=expire):
            response,_=self.call()
        self.assertTrue(response['result']['isError']);self.assertEqual(response['id'],7)
        save('encoding_deadline_result.json',response)
    def test_rejected_image_argument_still_has_no_image_trace_or_capture(self):
        self.arrange()
        response=self.server.handle_jsonrpc_message({'jsonrpc':'2.0','id':1,'method':'tools/call',
            'params':{'name':NAME,'arguments':{**args(),'include_image':True}}})
        self.assertTrue(response['result']['isError']);self.assertEqual(self.host.selected_calls,[])
        traces=[json.loads(line)['trace'] for line in self.service.audit_path.read_text().splitlines()
                if json.loads(line)['event']=='request_trace']
        self.assertEqual(len(traces),1);self.assertIs(traces[0]['annotations']['include_image'],False)
    def test_direct_service_none_and_legacy_mcp_null_contract(self):
        self.arrange();query=self.query(('b',))
        value=self.service.observe('direct',query=query,include_image=False,
            focal_id=None,reference_id=None,goal=None,scene_delta=None)
        self.assertEqual(value['summary']['nearest_separated_ids'],['b'])
        server=mcp.LiveSpatialMCPServer(self.service)
        for key in ('focal_id','reference_id','goal','scene_delta'):
            response=server.handle_jsonrpc_message({'jsonrpc':'2.0','id':1,'method':'tools/call',
                'params':{'name':'human_eye_scene_observe','arguments':{'query':query,'include_image':False,key:None}}})
            self.assertTrue(response['result']['isError'])
        self.assertEqual(len(self.host.selected_calls),1)
        with self.assertRaisesRegex(ValueError,'query.target/query.candidates'):
            self.service.observe('bad',query=query,include_image=True)


class StdioAndLaunch(unittest.TestCase):
    setUp=AliasRoutes.setUp
    arrange=AliasRoutes.arrange
    def test_stdio_sequence_recovers_and_uses_single_trace_per_call(self):
        self.arrange()
        requests=[{'jsonrpc':'2.0','id':1,'method':'initialize'}, {'jsonrpc':'2.0','id':2,'method':'tools/list'},
            {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':NAME,'arguments':args()}},
            {'jsonrpc':'2.0','id':4,'method':'tools/call','params':{'name':'human_eye_transform','arguments':{}}},
            {'jsonrpc':'2.0','id':5,'method':'ping'},
            {'jsonrpc':'2.0','id':6,'method':'tools/call','params':{'name':NAME,'arguments':args(('b',))}}]
        incoming=io.StringIO('\n'.join(json.dumps(r) for r in requests[:4])+'\n{broken\n'+'\n'.join(json.dumps(r) for r in requests[4:])+'\n')
        outgoing=io.StringIO()
        mcp.run_stdio_mcp_server(self.service,incoming,outgoing,spatial_task_only=True)
        lines=[json.loads(line) for line in outgoing.getvalue().splitlines()]
        self.assertEqual(len(lines),7);self.assertEqual(lines[1]['result']['tools'][0]['name'],NAME)
        self.assertFalse(lines[2]['result']['isError']);self.assertTrue(lines[3]['result']['isError'])
        self.assertEqual(lines[4]['error']['code'],-32700);self.assertEqual(lines[5]['result'],{})
        self.assertFalse(lines[6]['result']['isError']);self.assertEqual(len(self.host.selected_calls),2)
        traces=[json.loads(line)['trace'] for line in self.service.audit_path.read_text().splitlines() if json.loads(line)['event']=='request_trace']
        self.assertEqual(len(traces),3)
        for trace in (traces[0],traces[2]):self.assertIs(trace['annotations']['include_image'],False)
        save('stdio.json',dict(requests=requests,responses=lines,UTF8_input_B=len(incoming.getvalue().encode()),UTF8_output_B=len(outgoing.getvalue().encode())))
    def test_stdio_deadline_before_write(self):
        self.arrange();check=self.service._check_request_budget
        def expire(stage,*a,**kw):
            if stage=='before_stdio_write':raise live_service.RequestBudgetError('late','stdio')
            return check(stage,*a,**kw)
        request={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':NAME,'arguments':args()}}
        output=io.StringIO()
        with patch.object(self.service,'_check_request_budget',side_effect=expire):
            mcp.run_stdio_mcp_server(self.service,io.StringIO(json.dumps(request)+'\n'),output,spatial_task_only=True)
        self.assertTrue(json.loads(output.getvalue())['result']['isError'])
    def test_live_cli_keyword_and_flag_passthrough(self):
        token=object()
        for flags,keyword in (([],False),(['--spatial-task-only'],False),([],True)):
            with patch.object(mcp,'_configure_utf8_stdio'),patch.object(live_service,'LiveSpatialService',return_value=token) as made,patch.object(mcp,'run_stdio_mcp_server') as run:
                self.assertEqual(mcp.main(['--config','not-opened.json',*flags],spatial_task_only=keyword),0)
            made.assert_called_once_with('not-opened.json',production_mode=True)
            run.assert_called_once_with(token,**({'spatial_task_only':True} if flags or keyword else {}))
    def test_production_cli_and_demo_rejection(self):
        token=object()
        for flags,keyword in (([],False),(['--spatial-task-only'],False),([],True)):
            with patch.object(production_server,'resolve_config',return_value=Path('trusted.json')),patch.object(production_server,'construct_live_service',return_value=token),patch.object(mcp,'run_stdio_mcp_server') as run,patch('sys.stdout',new=io.StringIO()),patch('sys.stderr',new=io.StringIO()):
                self.assertEqual(production_server.main(flags,spatial_task_only=keyword),0)
            run.assert_called_once_with(token,**({'spatial_task_only':True} if flags or keyword else {}))
        with patch.object(production_server,'run_demo_stdio') as demo,patch('sys.stderr',new=io.StringIO()),self.assertRaises(SystemExit) as caught:
            production_server.main(['--demo','--spatial-task-only'])
        self.assertEqual(caught.exception.code,2);demo.assert_not_called()


if __name__=='__main__':unittest.main()
