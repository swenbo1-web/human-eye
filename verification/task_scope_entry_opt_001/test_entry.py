"""Bounded entry tests: original parser, native schema cases and memory routing."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import unittest

from human_eye_plugin import live_spatial_mcp as mcp, mcp_transport as wire
from human_eye_plugin.task_query import SELECTOR_SCHEMA
from verification.task_scope_impl_001 import test_scope as prior
from verification.test_concave_geometry import box

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
prior.OUT=OUT  # record() must never overwrite the preceding fixed evidence.


def example():
    text=mcp.LIVE_MCP_TOOLS_SCHEMA[0]['description']
    value,_=json.JSONDecoder().raw_decode(text[text.index('{'):])
    return value


def cases():
    old=json.loads((ROOT/'verification/tool_affordance_001/offline_04/parser_results.json').read_bytes())['candidate']
    rows=[dict(name='old_'+r['name'],arguments=r['arguments'],expected=True) for r in old if r['expected_accepted']]
    sample=example()
    rows.append(dict(name='callable_example',arguments=sample,expected=True))
    triple=copy.deepcopy(sample);triple['query']['candidates']=[{'name':x} for x in ('B','C','D')]
    triple['query']['requested_facts'].append('aabb')
    rows.append(dict(name='three_candidates_with_aabb',arguments=triple,expected=True))
    rows.append(dict(name='old_four_aabb',arguments={'include_image':False,'query':{'mode':'task',
        'objects':[{'id':x} for x in ('a','b','c','d')],'requested_facts':['aabb']}},expected=True))
    modes=[None]+[mode for mode in mcp._QUERY_SCHEMA['properties']['mode']['enum'] if mode!='task']
    for mode in modes:
        for fields in ('both','target_only','candidates_only'):
            value=copy.deepcopy(sample);query=value['query']
            if mode is None:query.pop('mode')
            else:query['mode']=mode
            if fields=='target_only':query.pop('candidates')
            if fields=='candidates_only':query.pop('target')
            rows.append(dict(name=str(mode)+'_'+fields,arguments=value,expected=False))
    mutations=[('task_target_only',lambda q:q.pop('candidates')),
        ('task_candidates_only',lambda q:q.pop('target')),
        ('mixed_objects',lambda q:q.update(objects=[{'name':'A'},{'name':'B'}])),
        ('extra_object_ids',lambda q:q.update(object_ids=['B'])),
        ('extra_pair_budget',lambda q:q.update(max_exact_pairs=1)),
        ('empty_candidates',lambda q:q.update(candidates=[])),
        ('four_candidates',lambda q:q.update(candidates=[{'id':str(i)} for i in range(4)])),
        ('missing_fact',lambda q:q.update(requested_facts=['surface_proximity'])),
        ('unsupported_fact',lambda q:q['requested_facts'].append('pair_relation')),
        ('dual_selector',lambda q:q['target'].update(id='A'))]
    for name,mutate in mutations:
        value=copy.deepcopy(sample);mutate(value['query'])
        rows.append(dict(name=name,arguments=value,expected=False))
    return rows


def stripped(value):
    if isinstance(value,dict):return {k:stripped(v) for k,v in value.items() if k!='description'}
    if isinstance(value,list):return [stripped(v) for v in value]
    return value


class EntryChecks(unittest.TestCase):
    def test_actual_catalogue_once_and_unchanged_other_tools(self):
        class NoHost:
            def __getattr__(self,name):raise AssertionError('unexpected host access: '+name)
        response=mcp.LiveSpatialMCPServer(NoHost()).handle_jsonrpc_message({'jsonrpc':'2.0','id':1,'method':'tools/list'})
        raw=wire.encode_response(response).encode('utf8')
        baseline=json.loads((ROOT/'verification/task_scope_impl_001/catalogue_response.json').read_bytes())
        old_tools=baseline['result']['tools'];tools=response['result']['tools']
        self.assertEqual(tools[1:],old_tools[1:])
        self.assertEqual([t['name'] for t in tools],[t['name'] for t in old_tools])
        old,new=stripped(old_tools),stripped(tools)
        old_query=old[0]['inputSchema']['properties']['query'];new_query=new[0]['inputSchema']['properties']['query']
        self.assertEqual(old_query['allOf'][0],new_query['allOf'][0])
        old_query.pop('allOf');new_query.pop('allOf')
        self.assertEqual(old,new)
        for key in ('objects','target','candidates'):
            value=mcp._QUERY_SCHEMA['properties'][key]
            if key!='target':value=value['items']
            self.assertEqual(value,SELECTOR_SCHEMA)
        self.assertNotIn('$ref',json.dumps(mcp._QUERY_SCHEMA['allOf'][1]))
        (OUT/'catalogue_response.json').write_bytes(raw)
        (OUT/'public_schema.json').write_bytes(json.dumps(tools[0]['inputSchema']).encode())
        (OUT/'public_cases.json').write_bytes((json.dumps(cases(),indent=2)+'\n').encode())
        (OUT/'BYTE_RESULT.json').write_bytes((json.dumps(dict(
            baseline_full_catalogue_bytes=len(wire.encode_response(baseline).encode()),
            candidate_full_catalogue_bytes=len(raw),evaluation_point_bytes=20254,
            target_met=len(raw)<=20254,other_three_tools_identical=True,
            selector_structures_identical=True,only_non_description_change='task routing condition',
            example=example()),indent=2)+'\n').encode())
    def test_original_parser_positive_negative_matrix(self):
        results=[]
        for row in cases():
            try:mcp._validate_arguments('human_eye_scene_observe',copy.deepcopy(row['arguments']))
            except ValueError as error:accepted=False;reason=str(error)
            else:accepted=True;reason=None
            with self.subTest(case=row['name']):self.assertEqual(accepted,row['expected'])
            results.append(dict(**row,actual=accepted,reason=reason))
        (OUT/'parser_results.json').write_bytes((json.dumps(dict(passed=True,checks=len(results),rows=results),indent=2)+'\n').encode())
    def test_no_runtime_function_or_other_module_change(self):
        old=ast.parse((OUT/'SOURCE.before.py.txt').read_bytes())
        new=ast.parse((ROOT/'human_eye_plugin/live_spatial_mcp.py').read_bytes())
        def implementation(tree):
            return ast.dump(ast.Module(body=[node for node in tree.body if not (isinstance(node,ast.Assign)
                and any(isinstance(target,ast.Name) and target.id in {'_QUERY_SCHEMA','LIVE_MCP_TOOLS_SCHEMA'}
                        for target in node.targets))],type_ignores=[]),include_attributes=False)
        self.assertEqual(implementation(old),implementation(new))
        (OUT/'IMPLEMENTATION_PROOF.json').write_bytes((json.dumps(dict(non_schema_module_AST_equal=True,
            normalized_AST_sha256=hashlib.sha256(implementation(new).encode()).hexdigest()),indent=2)+'\n').encode())


class RoutingChecks(unittest.TestCase):
    setUp=prior.ScopeTests.setUp
    arrange=prior.ScopeTests.arrange
    work=prior.ScopeTests.work
    def test_literal_example_runs_once_in_memory(self):
        self.arrange([box((0,0,0),(2,2,2),'A'),box((4,0,0),(2,2,2),'B')])
        response=self.server.handle_jsonrpc_message({'jsonrpc':'2.0','id':1,'method':'tools/call',
            'params':{'name':'human_eye_scene_observe','arguments':example()}})
        self.assertFalse(response['result']['isError'])
        value=json.loads(response['result']['content'][0]['text'])
        self.assertEqual(value['summary']['nearest_separated_ids'],['B'])
        self.assertEqual(len(self.host.selected_calls),1)
        self.assertEqual(value['schema_version'],'task-query-set-v1')
        (OUT/'example_result.json').write_bytes((json.dumps(value,indent=2)+'\n').encode())
    def test_missing_or_wrong_mode_rejected_before_capture(self):
        self.arrange()
        for mode in (None,'overview'):
            value=example()
            if mode is None:value['query'].pop('mode')
            else:value['query']['mode']=mode
            response=self.server.handle_jsonrpc_message({'jsonrpc':'2.0','id':1,'method':'tools/call',
                'params':{'name':'human_eye_scene_observe','arguments':value}})
            self.assertTrue(response['result']['isError'])
        self.assertEqual(self.host.selected_calls,[])


if __name__=='__main__':unittest.main()
