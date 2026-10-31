"""Execute the shipped worker, with fake bpy and the real scene helper.

The worker itself is never replaced by a protocol double. Actual Blender is
verified separately. Runtime and test roots are obtained from imported files,
so these tests can run against an isolated wheel with Python -I.
"""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from human_eye_plugin import blender_host as host_module
from human_eye_plugin.blender_process import BlenderProcessHost, HostTransportError
from human_eye_plugin.host_runtime import GuardedHostRuntime
from verification.test_host_precision_preflight import digest


RUNTIME_ROOT = Path(host_module.__file__).resolve().parents[1]
TEST_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_WORKER = Path(host_module.__file__).resolve().with_name('blender_worker.py')
NONCE = 'a' * 32

LAUNCHER = '''import json,runpy,sys
from pathlib import Path
from types import SimpleNamespace
runtime_root,test_root,worker,host_root=map(Path,sys.argv[1:])
sys.path.insert(0,str(test_root));sys.path.insert(0,str(runtime_root))
from verification.test_host_precision_preflight import fixture,Float32Matrix
engine,focal,reference=fixture()
engine.bpy.app=SimpleNamespace(version_string='fake-bpy-worker-protocol-test')
sys.modules['bpy']=engine.bpy
sys.modules['mathutils']=SimpleNamespace(Matrix=Float32Matrix)
sys.argv=[str(worker),'--',str(host_root)]
try:runpy.run_path(str(worker),run_name='__main__')
finally:
 print('WORKER_TEST_COUNTERS:'+json.dumps({'assignments':focal.assignments}),file=sys.stderr,flush=True)
'''


class BlenderWorkerProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.launcher = self.base/'launch_actual_worker.py'
        self.launcher.write_text(LAUNCHER, encoding='utf-8')
        self.blend = self.base/'fake-bpy-fixture.blend'
        self.blend.write_bytes(b'protocol fixture; never opened by Blender')
        self.original_popen = subprocess.Popen
        self.commands = []

    def host(self, *, worker_path=None):
        def launch(command, **kwargs):
            self.commands.append(command)
            worker = command[command.index('--python')+1]
            root = command[command.index('--')+1]
            return self.original_popen([sys.executable,'-I','-B',str(self.launcher),
                str(RUNTIME_ROOT),str(TEST_ROOT),worker,root], **kwargs)
        with patch('human_eye_plugin.blender_process.subprocess.Popen', side_effect=launch):
            host = BlenderProcessHost(sys.executable,self.blend,worker_path=worker_path,
                                      startup_timeout=5.,timeout=5.)
        self.addCleanup(host.close)
        return host

    def action(self, scene, delta):
        focal = next(mesh for mesh in scene['meshes'] if mesh['name']=='PrecisionPart')
        reference = next(mesh for mesh in scene['meshes'] if mesh['name']=='PrecisionBase')
        return dict(focal_id=focal['object_id'],reference_id=reference['object_id'],translation=delta)

    def counters(self, host):
        host.close()
        values = [line.split('WORKER_TEST_COUNTERS:',1)[1] for line in host.diagnostics
                  if 'WORKER_TEST_COUNTERS:' in line]
        self.assertEqual(len(values),1,host.diagnostics)
        return json.loads(values[0])

    def test_default_worker_is_packaged_sibling_and_does_not_require_examples(self):
        host = self.host()
        selected = Path(self.commands[0][self.commands[0].index('--python')+1])
        self.assertEqual(selected,CANONICAL_WORKER)
        self.assertEqual(selected.parent,Path(host_module.__file__).resolve().parent)
        self.assertTrue(host.capabilities()['persistent'])
        self.assertEqual(self.counters(host)['assignments'],0)

    def test_actual_worker_forwards_nonce_and_refuses_without_assigning(self):
        host = self.host()
        before = host.capture_scene()
        result = host.apply_transform(self.action(before,[.001,0,0]),before['revision'],
                                      digest(before),request_nonce=NONCE)
        self.assertEqual(result['status'],'rejected_before_mutation')
        self.assertEqual(result['rejection']['request_nonce'],NONCE)
        self.assertEqual(host.capture_scene(),before)
        self.assertTrue(host.is_alive)
        self.assertEqual(self.counters(host)['assignments'],0)

    def test_real_worker_runtime_chain_clears_known_refusal_then_executes_fresh_step(self):
        host = self.host()
        before = host.capture_scene()
        action = self.action(before,[.001,0,0])
        runtime = GuardedHostRuntime(host,quad_size=64,require_execution_capability=True)
        def prepare():
            return runtime.before_model(session_id='s',task_instruction='Measure Blender part clearance.',
                focal_id=action['focal_id'],reference_id=action['reference_id'],messages=[],include_image=False)
        prepare()
        refused = runtime.execute_action(session_id='s',action={'translation':[.001,0,0]})
        self.assertEqual(refused['status'],'blocked')
        self.assertIs(refused['host_mutation_started'],False)
        self.assertFalse(runtime.status['quarantined'])
        self.assertEqual(host.capture_scene(),before)
        prepare()
        accepted = runtime.execute_action(session_id='s',action={'translation':[.0625,0,0]})
        self.assertTrue(accepted['execution_verified'],accepted)
        self.assertEqual(self.counters(host)['assignments'],1)

    def test_explicit_compatibility_worker_has_same_nonce_protocol(self):
        example = RUNTIME_ROOT/'examples/blender_worker.py'
        if not example.is_file():
            # A wheel carries the canonical worker; exercise an explicit copy.
            example = self.base/'compatibility_worker.py'
            example.write_bytes(CANONICAL_WORKER.read_bytes())
        host = self.host(worker_path=example)
        before = host.capture_scene()
        result = host.apply_transform(self.action(before,[.001,0,0]),before['revision'],
                                      digest(before),request_nonce=NONCE)
        self.assertEqual(result['status'],'rejected_before_mutation')
        self.assertEqual(self.counters(host)['assignments'],0)

    def test_legacy_without_nonce_keeps_old_uncertainty_path(self):
        host = self.host()
        before = host.capture_scene()
        with self.assertRaisesRegex(HostTransportError,'mutation could not be verified'):
            host.apply_transform(self.action(before,[.001,0,0]),before['revision'],digest(before))
        self.assertFalse(host.is_alive)

    def stub_worker(self, helper, params):
        root = self.base/'standalone_source'
        folder = root/'human_eye_plugin';folder.mkdir(parents=True)
        (folder/'blender_host.py').write_text(helper,encoding='utf-8')
        requests = [dict(id=1,command='capabilities',params={}),
                    dict(id=2,command='apply',params=params),dict(id=3,command='shutdown',params={})]
        result = subprocess.run([sys.executable,'-I','-B',str(self.launcher),str(RUNTIME_ROOT),
            str(TEST_ROOT),str(CANONICAL_WORKER),str(root)],
            input=''.join(json.dumps(item)+'\n' for item in requests),capture_output=True,text=True,timeout=8)
        self.assertEqual(result.returncode,0,result.stderr)
        return [json.loads(line[len('HUMAN_EYE_RPC:'):]) for line in result.stdout.splitlines()
                if line.startswith('HUMAN_EYE_RPC:')]

    def test_absent_nonce_is_omitted_for_a_legacy_helper_signature(self):
        helper='''class BlenderSceneHost:
 def __init__(self,execution_metadata=False):pass
 def apply_transform(self,action,expected_revision,expected_fingerprint=None):
  return {'legacy_signature':True,'revision':expected_revision,'fingerprint':expected_fingerprint}
'''
        rows = self.stub_worker(helper,dict(action={'translation':[0,0,0]},
            expected_revision='r1',expected_fingerprint='f'*64))
        self.assertEqual(rows[1]['result'],dict(legacy_signature=True,revision='r1',fingerprint='f'*64))
        self.assertTrue(rows[2]['result']['closed'])

    def test_explicit_nonce_reaches_a_required_helper_parameter(self):
        helper='''class BlenderSceneHost:
 def __init__(self,execution_metadata=False):pass
 def apply_transform(self,action,expected_revision,expected_fingerprint=None,*,request_nonce):
  return {'nonce':request_nonce}
'''
        rows = self.stub_worker(helper,dict(action={'translation':[0,0,0]},
            expected_revision='r1',expected_fingerprint='f'*64,request_nonce=NONCE))
        self.assertEqual(rows[1]['result'],{'nonce':NONCE})

    def test_actual_worker_apply_exception_preserves_uncertainty(self):
        helper='''class BlenderSceneHost:
 def __init__(self,execution_metadata=False):pass
 def apply_transform(self,*args,**kwargs):raise RuntimeError('unknown assignment outcome')
'''
        rows = self.stub_worker(helper,dict(action={'translation':[0,0,0]},
            expected_revision='r1',expected_fingerprint='f'*64,request_nonce=NONCE))
        self.assertEqual(len(rows),2)
        self.assertIs(rows[1]['error']['mutation_uncertain'],True)
        self.assertEqual(rows[1]['error']['type'],'RuntimeError')

    def test_canonical_worker_is_standalone_and_example_copy_matches_when_present(self):
        code='import runpy,sys;runpy.run_path(sys.argv[1]);print(any(x in sys.modules for x in ("numpy","PIL","bpy","human_eye_plugin")))'
        result=subprocess.run([sys.executable,'-I','-B','-c',code,str(CANONICAL_WORKER)],
                              capture_output=True,text=True,timeout=8)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.strip(),'False')
        example=RUNTIME_ROOT/'examples/blender_worker.py'
        if example.is_file():
            self.assertEqual(example.read_bytes(),CANONICAL_WORKER.read_bytes())


if __name__=='__main__':
    unittest.main()
