"""Fixed evidence template compatibility and actual shared-host execution."""
import ast
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import unittest

from human_eye_plugin.blender_mcp_host import BlenderMCPHost, RPC_PREFIX
from verification.test_blender_mcp_host import _server, _reply
from verification.test_blender_native_evidence import fixture

ROOT=Path(__file__).resolve().parents[1]


class HostEvidenceTransportTests(unittest.TestCase):
    def test_legacy_fixed_templates_match_frozen_before_exactly(self):
        source=ROOT/'verification/fixes/20261030_v21_host_evidence/before/human_eye_plugin/blender_mcp_host.py'
        tree=ast.parse(source.read_text(encoding='utf-8'))
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='BlenderMCPHost')
        method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_code')
        namespace={'json':json,'RPC_PREFIX':RPC_PREFIX}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[])),str(source),'exec'),namespace)
        host=BlenderMCPHost(ROOT)
        for command,params in [('capture',{}),('apply',{'action':{'focal_id':'quoted"零件',
            'translation':[0.,0.,.0005]},'expected_revision':'r1','expected_fingerprint':'f'*64})]:
            self.assertEqual(host._code(command,params,'a'*32),namespace['_code'](host,command,params,'a'*32))

    def execute(self, command, params):
        output=io.StringIO()
        with redirect_stdout(output):
            exec(self.remote._code(command,params,'b'*32),{'bpy':self.local.bpy})
        text=output.getvalue()
        self.assertTrue(text.startswith(RPC_PREFIX))
        return json.loads(text[len(RPC_PREFIX):])

    def setUp(self):
        self.local,self.part,self.base,_=fixture()
        self.remote=BlenderMCPHost(ROOT)
        self.pair={'focal_id':self.local.object_id(self.part),'reference_id':self.local.object_id(self.base)}

    def test_new_fixed_capture_evidence_executes_only_a_read(self):
        packet=self.execute('capture_evidence',{})
        self.assertEqual(packet['result']['protocol'],'native-pose-evidence-v1-20261030')
        self.assertEqual(packet['result']['capture'],self.local.capture_scene())
        self.assertEqual(self.part.assignments+self.base.assignments,0)

    def test_shared_namespace_registration_status_and_end_never_promote_coverage(self):
        begin=self.execute('motion_begin',{'goal_id':'shared-goal',**self.pair,'limits':None})
        self.assertFalse(begin['result']['all_channels_complete'])
        status=self.execute('motion_status',{'goal_id':'shared-goal','after_event_count':0})['result']
        self.assertTrue(status['registered_events_complete'])
        self.assertFalse(status['physical_meter']['complete'])
        self.assertFalse(status['goal_budget_eligible'])
        end=self.execute('motion_end',{'goal_id':'shared-goal'})['result']
        self.assertTrue(end['closed'])
        self.assertEqual(self.part.assignments+self.base.assignments,0)

    def test_extra_or_injected_arguments_cannot_become_code(self):
        reply=self.execute('capture_evidence',{'code':'raise RuntimeError("unexpected")'})
        self.assertIn('error',reply)
        self.assertFalse(reply['error']['mutation_uncertain'])
        reply=self.execute('motion_begin',{'goal_id':'x\");raise RuntimeError("unexpected");#',**self.pair,'limits':None})
        self.assertIn('error',reply)
        self.assertNotIn('unexpected',reply['error']['message'])
        self.assertEqual(self.part.assignments+self.base.assignments,0)

    def test_public_python_methods_send_only_the_typed_commands(self):
        with _server(lambda request:_reply(request,{'command':request['command'],'params':request['params']}),
                     connections=4) as (port,requests):
            host=BlenderMCPHost(ROOT,port=port)
            self.assertEqual(host.capture_evidence()['command'],'capture_evidence')
            self.assertEqual(host.begin_motion_goal('goal',**self.pair)['params'],
                             {'goal_id':'goal',**self.pair,'limits':None})
            self.assertEqual(host.motion_goal_status('goal',2)['params'],{'goal_id':'goal','after_event_count':2})
            self.assertEqual(host.end_motion_goal('goal')['command'],'motion_end')
            self.assertEqual(len(requests),4)


if __name__=='__main__':unittest.main()
