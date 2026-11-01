import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from human_eye_plugin.task_brief import project_structure_brief,STRUCTURE_BRIEF_REVISION
from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer,_tool_result
from human_eye_plugin.structure_task import register
from verification.test_mesh_structure_service import TypedRawHost


def expand_structure(value):
    root=copy.deepcopy(value);root.pop('structure_value_encoding',None)
    def visit(node,active=()):
        if type(node) is dict and set(node)=={'$ref'}:
            ref=node['$ref']
            if not ref.startswith('#/') or ref in active:raise ValueError('invalid reference')
            target=root
            for item in ref[2:].split('/'):
                key=item.replace('~1','/').replace('~0','~')
                target=target[int(key)] if type(target) is list else target[key]
            if type(target) is not dict:raise ValueError('non-dictionary reference')
            return visit(target,active+(ref,))
        if type(node) is dict:return {k:visit(v,active) for k,v in node.items()}
        if type(node) is list:return [visit(v,active) for v in node]
        return node
    return visit(root)


class StructureBriefTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);p=Path(self.tmp.name)/'config.json'
        p.write_text(json.dumps(dict(schema_version='1.0',enabled=True,project_root=str(Path(__file__).resolve().parents[1]),
            state_file='state.json',audit_file='audit.jsonl',structure_task_file='task.json',quad_size=64,max_sessions=4)))
        register(p,'target');service=LiveSpatialService(p,host=TypedRawHost())
        with patch('human_eye_plugin.structure_task_service.counter_descriptor',return_value={'test_clock':True}):
            self.value=service.observe('s',query=dict(mode='mesh_structure',operation='diagnose',request_id='a'),include_image=False)

    def test_exact_round_trip_and_no_input_mutation(self):
        original=copy.deepcopy(self.value);brief=project_structure_brief(self.value)
        self.assertEqual(brief['structure_value_encoding']['revision'],STRUCTURE_BRIEF_REVISION)
        self.assertEqual(expand_structure(brief),original);self.assertEqual(self.value,original)
        response=_tool_result(original,is_error=False,response_detail='brief');text=response['content'][0]['text']
        self.assertEqual(expand_structure(json.loads(text)),original)
        self.assertLessEqual(len(text.encode()),len(json.dumps(original,ensure_ascii=False).encode())*.9)

    def test_partial_unknown_omission_and_future_fields_preserved(self):
        value=self.value;value['status']=value['diagnostic']['status']='partial'
        check=value['diagnostic']['report']['checks']['boundary_edges']
        check.update(state='partial',total=None,omitted=3,reason='work_budget')
        value['diagnostic']['coverage']['unclassified']={'nonmanifold_vertices':{'known':False,'missing':None}}
        value['diagnostic']['future_field']={'unknown':[False,0,None,'not_checked']}
        value['patch_references_omitted']=9
        self.assertEqual(expand_structure(project_structure_brief(value)),value)

    def test_positions_precision_and_array_order_survive(self):
        value=self.value;value['precision']={'x':1.0000000000000002,'y':-0.0,'indices':[4,1,0]}
        expanded=expand_structure(project_structure_brief(value))
        self.assertEqual(json.dumps(expanded,sort_keys=True),json.dumps(value,sort_keys=True))
        self.assertEqual(expanded['diagnostic']['patches'],value['diagnostic']['patches'])

    def test_escaped_pointer_tokens_and_nested_lists(self):
        row={'reason':'unknown'*40,'total':None,'zero':0,'false':False}
        self.value['a/b~c']=[row,copy.deepcopy(row)]
        brief=project_structure_brief(self.value)
        self.assertEqual(brief['a/b~c'][1],{'$ref':'#/a~1b~0c/0'})
        self.assertEqual(expand_structure(brief),self.value)

    def test_existing_refs_or_unknown_algorithm_keep_full(self):
        for change in (lambda v:v.update(x={'$ref':'#/elsewhere'}),
            lambda v:v['diagnostic']['algorithm'].update(revision='future'),
            lambda v:v['diagnostic'].update(protocol='future'),
            lambda v:v.update(execution_authority=True),
            lambda v:v['diagnostic'].update(status='partial')):
            value=copy.deepcopy(self.value);change(value)
            self.assertIsNone(project_structure_brief(value))
            self.assertEqual(_tool_result(value,is_error=False,response_detail='brief'),_tool_result(value,is_error=False))

    def test_original_budget_charge_and_no_new_receipt_facts(self):
        value=self.value;brief=project_structure_brief(value)
        self.assertEqual(expand_structure(brief)['task_budget'],value['task_budget'])
        value['status']='receipt';value.pop('diagnostic')
        self.assertIsNone(project_structure_brief(value))
        self.assertEqual(_tool_result(value,is_error=False,response_detail='brief'),_tool_result(value,is_error=False))

    def test_exception_or_no_savings_falls_back_full(self):
        with patch('human_eye_plugin.live_spatial_mcp.project_structure_brief',side_effect=ValueError('projection failed')):
            self.assertEqual(_tool_result(self.value,is_error=False,response_detail='brief'),_tool_result(self.value,is_error=False))
        with patch('human_eye_plugin.live_spatial_mcp.project_structure_brief',return_value=self.value):
            full=_tool_result(self.value,is_error=False);brief=_tool_result(self.value,is_error=False,response_detail='brief')
            # Compact JSON alone may clear the existing size gate; either way every value remains.
            self.assertEqual(json.loads(brief['content'][0]['text']),json.loads(full['content'][0]['text']))


if __name__=='__main__':unittest.main()
