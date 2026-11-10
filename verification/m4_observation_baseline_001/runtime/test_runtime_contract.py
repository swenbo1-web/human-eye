"""Small no-model adapter checks. No backend, CLI consumer or solver runs."""
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
BATCH=HERE.parent


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


class RuntimeContractTests(unittest.TestCase):
    def test_one_actual_image_argument_is_common_and_text_budget_is_separate(self):
        transport=load('_m4_test_transport',HERE/'consumer_transport.py')
        inputs={'image':'input/INITIAL.png','image_sha256':'42466e241a4239552fa418b7f79bf1fd73c10092f174c3e87444ed5e93cbed0a','image_bytes':1185069}
        image=transport.initial_image_metadata({'inputs':inputs,'image_count':1,'new_images':0})
        self.assertEqual((image['width'],image['height']),(1200,900))
        self.assertGreater(image['bytes'],1048576)  # common input, not tool text
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);cell=root/'cell.json'
            for group in ('N','P'):
                cell.write_text(json.dumps({'endpoint':str(root/'ENDPOINT.json'),'group':group}),encoding='utf8')
                args=transport.argv_for('dependency-python',cell,root,root/'final.txt',group,initial_image=image['path'])
                self.assertEqual(args.count('--image'),1)
                self.assertEqual(args[args.index('--image')+1],image['path'])
                self.assertIn('--ignore-user-config',args)
                self.assertEqual(args[-1],'-')
        self.assertEqual(set(transport.TOOLS_BY_GROUP),{'N','P'})
        self.assertEqual(len(transport.TOOLS_BY_GROUP['N']),1)
        self.assertEqual(len(transport.TOOLS_BY_GROUP['P']),3)
        self.assertFalse(transport.settings()['features.view_image'])
        self.assertEqual(transport.settings()['forced_login_method'],'chatgpt')

    def test_previous_cycle_GO_cannot_reach_a_consumer(self):
        driver=load('_m4_test_driver',HERE/'driver.py')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'GO.json').write_text(json.dumps({'task':'M1-TASK-ENTRY-001_EVAL','authorized':True}),encoding='utf8')
            (root/'PLAN.json').write_text('{}',encoding='utf8')
            with patch.object(driver,'HERE',root),patch.object(driver.subprocess,'Popen',side_effect=AssertionError('unexpected process')) as launch:
                with self.assertRaises(AssertionError):driver.run_models()
                launch.assert_not_called()
            self.assertFalse((root/'STARTED.json').exists())

    def test_original_helper_construction_evidence_refuses_and_stops_tools(self):
        actor=load('_m4_test_actor',HERE/'actor.py')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'native').mkdir()
            log=root/'native/WORKER_EVENTS.jsonl'
            log.write_text(json.dumps({'event':'render_started','at_ns':1})+'\n',encoding='utf8')
            owner=actor.Owner.__new__(actor.Owner)
            owner.out=root;owner.calls=0;owner.bytes=0;owner.logs=[];owner.peer=None
            owner.read_names=frozenset();owner.image_construction_violation=False
            executions=[]
            def run(code,timeout_s):
                executions.append(code)
                return {'response':{'status':'success','result':{'result':'read-only output'}}}
            owner.native=types.SimpleNamespace(run=run)
            request={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'execute_blender_code','arguments':{'code':'pass'}}}
            first=owner.handle(request)
            self.assertTrue(first['result']['isError']);self.assertTrue(owner.image_construction_violation)
            second=owner.handle(dict(request,id=2))
            self.assertTrue(second['result']['isError']);self.assertEqual(executions,['pass'])
            self.assertEqual(owner.calls,2)
            self.assertTrue((root/'tool_01/ATTEMPT.json').exists())
            self.assertEqual(owner.image_construction_status()['status'],'observed')

    def test_missing_native_image_ledger_stays_unknown(self):
        actor=load('_m4_test_actor_unknown',HERE/'actor.py')
        with tempfile.TemporaryDirectory() as directory:
            owner=actor.Owner.__new__(actor.Owner);owner.out=Path(directory)
            status=owner.image_construction_status()
            self.assertEqual(status['status'],'unknown')
            self.assertFalse(status['observed'])


if __name__=='__main__':unittest.main(verbosity=2)
