"""Counterexamples for negotiated, scene-bound zero-write precision refusals.

The fake Matrix models binary32 storage only; actual Blender remains a separate
integration acceptance. All fixture paths are temporary or imported modules.
"""
from contextlib import contextmanager
import ast
import copy
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from human_eye_plugin import blender_host as host_module
from human_eye_plugin.blender_host import (
    BlenderSceneHost, BlenderHostError, PREWRITE_REFUSAL_PROTOCOL,
    validate_prewrite_refusal,
)
from human_eye_plugin.blender_process import BlenderProcessHost, HostTransportError
from human_eye_plugin.blender_mcp_host import BlenderMCPHost, RPC_PREFIX
from human_eye_plugin.host_runtime import GuardedHostRuntime


NONCE = 'a' * 32

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()

class Float32Matrix(list):
    def __init__(self, rows):
        super().__init__([[struct.unpack('!f', struct.pack('!f', x))[0] for x in row] for row in rows])

class Object:
    def __init__(self, name, origin):
        self.name = self.name_full = name
        self.type, self.instance_type, self.mode = 'MESH', 'NONE', 'OBJECT'
        self.is_instancer = False
        self.library = self.parent = self.animation_data = self.rigid_body = self.rigid_body_constraint = None
        self.children, self.constraints, self.modifiers = [], [], []
        self.lock_location = self.lock_rotation = self.lock_scale = (False, False, False)
        self.hide_viewport = self.hide_render = False
        self.color = (.5, .2, .9, 1.)
        self.data = NS(vertices=[NS(co=p) for p in ((0,0,0),(1,0,0),(0,1,0),(0,0,1))],
            loop_triangles=[NS(vertices=f) for f in ((0,2,1),(0,1,3),(0,3,2),(1,2,3))],
            shape_keys=None, animation_data=None, calc_loop_triangles=lambda: None)
        self._matrix_world = [[1.,0.,0.,origin[0]],[0.,1.,0.,origin[1]],[0.,0.,1.,origin[2]],[0.,0.,0.,1.]]
        self.assignments = 0

    @property
    def matrix_world(self):
        return self._matrix_world

    @matrix_world.setter
    def matrix_world(self, value):
        self.assignments += 1
        self._matrix_world = [list(row) for row in value]

    def evaluated_get(self, graph):
        return self

    def to_mesh(self):
        return self.data

    def to_mesh_clear(self):
        pass

def fixture(*, origin=(1e6, 0., 3.), scale=1.):
    focal, reference = Object('PrecisionPart', origin), Object('PrecisionBase', (0.,0.,-5.))
    graph = NS(object_instances=[])
    layer = NS(update=lambda: None, depsgraph=graph, objects=NS(active=focal))
    scene = NS(objects=[focal, reference], unit_settings=NS(scale_length=scale), frame_current=1, view_layers=[layer])
    graph.scene_eval = NS(original=scene)
    bpy = NS(context=NS(scene=scene, view_layer=layer, evaluated_depsgraph_get=lambda: graph))
    return BlenderSceneHost(bpy, execution_metadata=True), focal, reference

@contextmanager
def binary32():
    with patch.dict(sys.modules, {'mathutils': NS(Matrix=Float32Matrix)}):
        yield

def refusal_fixture():
    host, focal, _ = fixture()
    scene = host.capture_scene()
    action = {'focal_id': host.object_id(focal), 'translation': [.001,0,0]}
    with binary32():
        result = host.apply_transform(action, scene['revision'], digest(scene), request_nonce=NONCE)
    return result, action, scene['revision'], digest(scene)

def rebind_refusal(template, params):
    value = copy.deepcopy(template)
    rejection = value['rejection']
    rejection.update(request_nonce=params.get('request_nonce'),
        expected_revision=params['expected_revision'], scene_revision=params['expected_revision'],
        expected_fingerprint=params['expected_fingerprint'], scene_fingerprint=params['expected_fingerprint'],
        action_sha256=digest(params['action']), focal_id=params['action']['focal_id'])
    return value


class HostPrecisionPreflightTests(unittest.TestCase):
    def apply(self, host, focal, action, *, nonce=NONCE):
        action = dict(action, focal_id=host.object_id(focal))
        scene = host.capture_scene()
        return host.apply_transform(action, scene['revision'], digest(scene), request_nonce=nonce)

    def test_far_millimetre_is_refused_without_assignment_or_rollback(self):
        host, focal, _ = fixture()
        before = host.capture_scene()
        with binary32():
            result = self.apply(host, focal, {'translation':[.001,0,0]})
        self.assertEqual(result['status'], 'rejected_before_mutation')
        self.assertEqual(focal.assignments, 0)
        self.assertEqual(host.capture_scene(), before)
        self.assertGreater(result['rejection']['precision']['absolute_error_m'][0], 1e-6)

    def test_representable_far_step_still_executes_and_reads_back(self):
        host, focal, _ = fixture()
        with binary32():
            result = self.apply(host, focal, {'translation':[.0625,0,0]})
        self.assertTrue(result['receipt']['host_execution_verified'])
        self.assertEqual(focal.assignments, 1)
        self.assertEqual(focal.matrix_world[0][3], 1e6 + .0625)

    def test_near_millimetre_and_large_xy_small_z_are_not_overblocked(self):
        for origin in ((2.,0.,3.), (1e6,0.,3.)):
            with self.subTest(origin=origin):
                host, focal, _ = fixture(origin=origin)
                with binary32():
                    result = self.apply(host, focal, {'translation':[0,0,.001]})
                self.assertTrue(result['receipt']['host_execution_verified'])
                self.assertEqual(focal.assignments, 1)

    def test_scene_units_are_applied_to_minimum_storage_error(self):
        for scale, origin in ((.001,(1e9,0.,3.)), (1000.,(1000.,0.,3.))):
            with self.subTest(scale=scale):
                host, focal, _ = fixture(origin=origin, scale=scale)
                with binary32():
                    result = self.apply(host, focal, {'translation':[.001,0,0]})
                self.assertEqual(result['status'], 'rejected_before_mutation')
                self.assertEqual(focal.assignments, 0)
                self.assertEqual(result['rejection']['precision']['unit_scale_m'], scale)

    def test_small_rotation_keeps_actual_readback_gate(self):
        host, focal, _ = fixture(origin=(2.,0.,3.))
        with binary32():
            result = self.apply(host, focal, {'rotation_euler_deg':[13.,-29.,47.]})
        self.assertTrue(result['receipt']['host_execution_verified'])
        self.assertEqual(focal.assignments, 1)

    def test_rotation_rounding_not_proven_by_pivot_preflight_still_rolls_back(self):
        host, focal, _ = fixture(origin=(2.,0.,3.))
        for vertex in focal.data.vertices:
            vertex.co = tuple(x * 10000 for x in vertex.co)
        before = host.capture_scene()
        with binary32(), self.assertRaisesRegex(BlenderHostError, 'rollback_verified=True'):
            self.apply(host, focal, {'rotation_euler_deg':[13.,-29.,47.]})
        self.assertEqual(focal.assignments, 2)
        self.assertEqual(host.capture_scene(), before)

    def test_error_threshold_does_not_replace_existing_tolerance(self):
        for delta, rejected in ((.5e-6, False), (2e-6, True)):
            with self.subTest(delta=delta):
                host, focal, _ = fixture(origin=(64.,0.,3.))
                with binary32():
                    result = self.apply(host, focal, {'translation':[delta,0,0]})
                self.assertEqual(result.get('status') == 'rejected_before_mutation', rejected)
                self.assertEqual(focal.assignments, 0 if rejected else 1)

    def test_legacy_no_nonce_keeps_uncertain_failure_contract(self):
        host, focal, _ = fixture()
        with binary32(), self.assertRaisesRegex(BlenderHostError, 'rollback_verified=True'):
            self.apply(host, focal, {'translation':[.001,0,0]}, nonce=None)
        self.assertEqual(focal.assignments, 2)

    def test_stale_revision_or_fingerprint_never_issues_refusal(self):
        host, focal, _ = fixture()
        scene = host.capture_scene()
        action = {'focal_id':host.object_id(focal), 'translation':[.001,0,0]}
        for revision, fingerprint in (('stale',digest(scene)), (scene['revision'],'0'*64)):
            with binary32(), self.assertRaises(BlenderHostError):
                host.apply_transform(action, revision, fingerprint, request_nonce=NONCE)
        self.assertEqual(focal.assignments, 0)

    def test_nonce_requires_exact_lowercase_hex_binding(self):
        host, focal, _ = fixture()
        for nonce in ('', 'A'*32, 'a'*31, True, 42):
            with self.subTest(nonce=nonce), binary32(), self.assertRaises(BlenderHostError):
                self.apply(host, focal, {'translation':[.001,0,0]}, nonce=nonce)
        self.assertEqual(focal.assignments, 0)

    def test_standalone_boundary_still_imports_without_engine_dependencies(self):
        source = Path(host_module.__file__).resolve()
        code = 'import runpy,sys;runpy.run_path(sys.argv[1]);print(any(x in sys.modules for x in ("numpy","PIL","bpy","human_eye_plugin")))'
        result = subprocess.run([sys.executable,'-I','-B','-c',code,str(source)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'False')

    def test_validator_rejects_binding_scope_type_and_proof_tampering(self):
        template, action, revision, fingerprint = refusal_fixture()
        cases = []
        for key, value in [('contract_revision','old'),('source','agent'),('code','safe'),
                ('request_nonce','b'*32),('expected_revision','stale'),('scene_revision','stale'),
                ('expected_fingerprint','0'*64),('scene_fingerprint','0'*64),('action_sha256','0'*64),
                ('focal_id','other'),('mutation_started',0),('scene_unchanged',1),('reason_codes',[])]:
            variant = copy.deepcopy(template);variant['rejection'][key]=value;cases.append(variant)
        for key, value in [('scope','all_execution'),('storage_kind','guessed'),('coordinate_tolerance_m',1e-5),
                ('unit_scale_m',True),('absolute_error_m',[0.,0.,0.]),('exceeded_axes',[True]),
                ('before_pivot_world_m',[0.,0.,0.]),('absolute_error_m',[float('nan'),0.,0.]),
                ('requested_pivot_world_m',[0.,0.,0.]),('nearest_translation_host_units',[0.,0.,0.]),
                ('preflight_authorizes_execution',True)]:
            variant = copy.deepcopy(template);variant['rejection']['precision'][key]=value;cases.append(variant)
        variant = copy.deepcopy(template);variant['extra']=True;cases.append(variant)
        variant = copy.deepcopy(template);variant['rejection']['extra']=True;cases.append(variant)
        variant = copy.deepcopy(template);del variant['rejection']['source'];cases.append(variant)
        for index, value in enumerate(cases):
            with self.subTest(index=index), self.assertRaises((ValueError, TypeError)):
                validate_prewrite_refusal(value, action=action, expected_revision=revision,
                    expected_fingerprint=fingerprint, request_nonce=NONCE)


class RuntimePrecisionRefusalTests(unittest.TestCase):
    def prepare(self, host, focal, reference):
        runtime = GuardedHostRuntime(host, quad_size=64, require_execution_capability=True)
        runtime.before_model(session_id='s', task_instruction='Measure Blender clearance',
            focal_id=host.object_id(focal), reference_id=host.object_id(reference), messages=[], include_image=False)
        return runtime

    def test_valid_refusal_does_not_quarantine_and_next_fresh_request_can_execute(self):
        host, focal, reference = fixture()
        runtime = self.prepare(host, focal, reference)
        before = host.capture_scene()
        with binary32():
            result = runtime.execute_action(session_id='s', action={'translation':[.001,0,0]})
        self.assertEqual(result['status'], 'blocked')
        self.assertIs(result['executed'], False)
        self.assertIs(result['host_mutation_started'], False)
        self.assertFalse(runtime.status['quarantined'])
        self.assertEqual(focal.assignments, 0)
        self.assertEqual(host.capture_scene(), before)
        self.assertEqual(runtime.execute_action(session_id='s', action={'translation':[0,0,.001]})['status'], 'observation_required')
        runtime = self.prepare(host, focal, reference)
        with binary32():
            result = runtime.execute_action(session_id='s', action={'translation':[0,0,.001]})
        self.assertTrue(result['execution_verified'])
        self.assertEqual(focal.assignments, 1)

    def test_malformed_or_unnegotiated_refusal_remains_uncertain(self):
        for mode in ('nonce','fingerprint','action','extra','legacy','generic'):
            with self.subTest(mode=mode):
                host, focal, reference = fixture()
                original = host.apply_transform
                def damaged(action, expected_revision, expected_fingerprint=None, request_nonce=None):
                    if mode == 'generic':
                        raise RuntimeError('No write, trust me')
                    result = original(action, expected_revision, expected_fingerprint,
                                      request_nonce=request_nonce or NONCE)
                    if mode == 'nonce': result['rejection']['request_nonce']='f'*32
                    if mode == 'fingerprint': result['rejection']['scene_fingerprint']='f'*64
                    if mode == 'action': result['rejection']['action_sha256']='f'*64
                    if mode == 'extra': result['rejection']['executed']=False
                    return result
                host.apply_transform = damaged
                if mode == 'legacy': host.prewrite_refusal_protocol=None
                runtime = self.prepare(host, focal, reference)
                with binary32():
                    result = runtime.execute_action(session_id='s', action={'translation':[.001,0,0]})
                self.assertEqual(result['status'], 'host_execution_uncertain')
                self.assertIsNone(result['executed'])
                self.assertTrue(runtime.status['quarantined'])
                self.assertEqual(focal.assignments, 0)

    def test_consistent_proof_rebound_to_other_pivot_is_still_uncertain(self):
        host, focal, reference = fixture()
        original = host.apply_transform
        validated = []
        def rebound(action, expected_revision, expected_fingerprint=None, request_nonce=None):
            result = original(action, expected_revision, expected_fingerprint, request_nonce=request_nonce)
            precision = result['rejection']['precision']
            for key in ('before_pivot_world_m','requested_pivot_world_m','nearest_pivot_world_m',
                        'requested_translation_host_units','nearest_translation_host_units'):
                precision[key][0] += 64.
            # All invocation bindings and the numeric proof still agree. The
            # runtime must additionally compare its own actual capture.
            validate_prewrite_refusal(result,action=action,expected_revision=expected_revision,
                expected_fingerprint=expected_fingerprint,request_nonce=request_nonce)
            validated.append(True)
            return result
        host.apply_transform = rebound
        runtime = self.prepare(host, focal, reference)
        before = host.capture_scene()
        with binary32():
            result = runtime.execute_action(session_id='s',action={'translation':[.001,0,0]})
        self.assertEqual(validated,[True])
        self.assertEqual(result['status'],'host_execution_uncertain')
        self.assertIsNone(result['executed'])
        self.assertTrue(runtime.status['quarantined'])
        self.assertNotIn('host_prewrite_refusal',result)
        self.assertEqual(focal.assignments,0)
        self.assertEqual(host.capture_scene(),before)


class PrecisionBridgeTests(unittest.TestCase):
    def setUp(self):
        self.template, self.action, self.revision, self.fingerprint = refusal_fixture()

    def test_MCP_refusal_validates_transport_and_inner_nonce_then_remains_live(self):
        host = BlenderMCPHost(Path(host_module.__file__).resolve().parents[1])
        def response(payload):
            code = json.loads(payload)['params']['code']
            line = next(x for x in code.splitlines() if x.startswith('_request = _json.loads('))
            request = json.loads(ast.literal_eval(line[len('_request = _json.loads('):-1]))
            result = rebind_refusal(self.template, request['params'])
            return {'status':'success','result':{'executed':True,'result':RPC_PREFIX+json.dumps(
                {'protocol_version':'1.0','id':request['id'],'result':result})+'\n'}}
        with patch.object(host, '_exchange', side_effect=response):
            result = host.apply_transform(self.action,self.revision,self.fingerprint,request_nonce=NONCE)
        self.assertEqual(result['status'],'rejected_before_mutation')
        self.assertTrue(host.is_alive)

    def test_MCP_wrong_inner_or_outer_nonce_invalidates_without_retry(self):
        for mode in ('inner','outer','extra'):
            with self.subTest(mode=mode):
                host = BlenderMCPHost(Path(host_module.__file__).resolve().parents[1])
                def response(payload):
                    code = json.loads(payload)['params']['code']
                    line = next(x for x in code.splitlines() if x.startswith('_request = _json.loads('))
                    request = json.loads(ast.literal_eval(line[len('_request = _json.loads('):-1]))
                    result = rebind_refusal(self.template, request['params'])
                    if mode == 'inner': result['rejection']['request_nonce']='b'*32
                    if mode == 'extra': result['rejection']['extra']=False
                    envelope={'protocol_version':'1.0','id':'old' if mode=='outer' else request['id'],'result':result}
                    return {'status':'success','result':{'executed':True,'result':RPC_PREFIX+json.dumps(envelope)+'\n'}}
                with patch.object(host,'_exchange',side_effect=response) as exchange, self.assertRaises(HostTransportError):
                    host.apply_transform(self.action,self.revision,self.fingerprint,request_nonce=NONCE)
                self.assertEqual(exchange.call_count,1)
                self.assertFalse(host.is_alive)

    def test_stdio_generic_apply_error_and_duplicate_keys_remain_unknown(self):
        worker = '''import json,sys
mode=sys.argv[1]
for line in sys.stdin:
 r=json.loads(line)
 if r['command']=='capabilities': print('HUMAN_EYE_RPC:'+json.dumps({'id':r['id'],'result':{'protocol_version':'1.0'}}),flush=True)
 elif r['command']=='apply':
  if mode=='duplicate': print('HUMAN_EYE_RPC:{"id":'+str(r['id'])+',"result":{},"result":{"status":"rejected_before_mutation"}}',flush=True)
  else: print('HUMAN_EYE_RPC:'+json.dumps({'id':r['id'],'error':{'type':'PrewriteRefusal','message':'no write claimed','mutation_uncertain':False}}),flush=True)
 else: break
'''
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary);blend=base/'fixture.blend';blend.write_bytes(b'protocol fixture')
            path=base/'worker.py';path.write_text(worker,encoding='utf-8')
            original=subprocess.Popen
            for mode in ('generic','duplicate'):
                with self.subTest(mode=mode):
                    def launch(command,**kwargs):
                        return original([sys.executable,'-I','-B',str(path),mode],**kwargs)
                    with patch('human_eye_plugin.blender_process.subprocess.Popen',side_effect=launch):
                        host=BlenderProcessHost(sys.executable,blend,worker_path=path,startup_timeout=3.,timeout=3.)
                    try:
                        with self.assertRaises(HostTransportError):
                            host.apply_transform(self.action,self.revision,self.fingerprint,request_nonce=NONCE)
                        self.assertFalse(host.is_alive)
                    finally:host.close()

    def test_stdio_valid_and_forged_refusals_use_real_isolated_protocol_process(self):
        template = json.dumps(self.template)
        worker = '''import json,sys,hashlib
template=json.loads(TEMPLATE)
mode=sys.argv[1]
for line in sys.stdin:
 r=json.loads(line); command=r['command']; params=r['params']
 if command=='capabilities': value={'protocol_version':'1.0'}
 elif command=='shutdown':
  print('HUMAN_EYE_RPC:'+json.dumps({'id':r['id'],'result':{'closed':True}}),flush=True);break
 else:
  value=json.loads(json.dumps(template)); d=value['rejection']
  d.update(request_nonce=params.get('request_nonce'),expected_revision=params['expected_revision'],scene_revision=params['expected_revision'],expected_fingerprint=params['expected_fingerprint'],scene_fingerprint=params['expected_fingerprint'],focal_id=params['action']['focal_id'],action_sha256=hashlib.sha256(json.dumps(params['action'],sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest())
  if mode=='nonce':d['request_nonce']='b'*32
  if mode=='revision':d['scene_revision']='old'
  if mode=='fingerprint':d['scene_fingerprint']='f'*64
  if mode=='extra':d['extra']=False
 print('HUMAN_EYE_RPC:'+json.dumps({'id':r['id']+1 if mode=='outer' and command=='apply' else r['id'],'result':value}),flush=True)
'''.replace('TEMPLATE', repr(template))
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary); blend=base/'fixture.blend';blend.write_bytes(b'isolated protocol fixture')
            path=base/'worker.py';path.write_text(worker,encoding='utf-8')
            original=subprocess.Popen
            for mode in ('valid','nonce','revision','fingerprint','extra','outer'):
                with self.subTest(mode=mode):
                    def launch(command,**kwargs):
                        return original([sys.executable,'-I','-B',str(path),mode],**kwargs)
                    with patch('human_eye_plugin.blender_process.subprocess.Popen',side_effect=launch):
                        host=BlenderProcessHost(sys.executable,blend,worker_path=path,startup_timeout=3.,timeout=3.)
                    try:
                        if mode=='valid':
                            result=host.apply_transform(self.action,self.revision,self.fingerprint,request_nonce=NONCE)
                            self.assertEqual(result['status'],'rejected_before_mutation');self.assertTrue(host.is_alive)
                        else:
                            with self.assertRaises(HostTransportError):
                                host.apply_transform(self.action,self.revision,self.fingerprint,request_nonce=NONCE)
                            self.assertFalse(host.is_alive)
                    finally:host.close()


class ServicePrecisionRefusalTests(unittest.TestCase):
    def service(self, base, host):
        from human_eye_plugin.live_service import LiveSpatialService
        path = base/'connector.json'
        path.write_text(json.dumps(dict(schema_version='1.0', enabled=True,
            project_root=str(Path(host_module.__file__).resolve().parents[1]),
            state_file='state.json', audit_file='audit.jsonl', quad_size=64,
            max_sessions=4, request_budget_s=10)), encoding='utf-8')
        return LiveSpatialService(path, host=host)

    def test_valid_refusal_durably_clears_journal_and_allows_fresh_next_action(self):
        host, focal, reference = fixture()
        action = dict(focal_id=host.object_id(focal), reference_id=host.object_id(reference), translation=[.001,0,0])
        with tempfile.TemporaryDirectory() as temporary, binary32():
            base=Path(temporary); service=self.service(base,host)
            before=host.capture_scene()
            result=service.transform('s',action)
            state=json.loads((base/'state.json').read_text(encoding='utf-8'))
            self.assertEqual(result['status'],'blocked')
            self.assertIs(result['host_mutation_started'],False)
            self.assertIsNone(state['inflight'])
            self.assertIsNone(state['runtime']['quarantine'])
            self.assertEqual(host.capture_scene(),before)
            self.assertEqual(focal.assignments,0)
            next_result=service.transform('fresh',dict(action,translation=[.0625,0,0]))
            self.assertTrue(next_result['execution_verified'])
            self.assertEqual(focal.assignments,1)
            self.assertIsNone(json.loads((base/'state.json').read_text(encoding='utf-8'))['inflight'])

    def test_invalid_refusal_retains_durable_inflight_and_quarantine(self):
        host, focal, reference = fixture()
        original=host.apply_transform
        def damaged(*args,**kwargs):
            result=original(*args,**kwargs)
            result['rejection']['request_nonce']='b'*32
            return result
        host.apply_transform=damaged
        action=dict(focal_id=host.object_id(focal),reference_id=host.object_id(reference),translation=[.001,0,0])
        with tempfile.TemporaryDirectory() as temporary,binary32():
            base=Path(temporary); service=self.service(base,host)
            result=service.transform('s',action)
            state=json.loads((base/'state.json').read_text(encoding='utf-8'))
            self.assertEqual(result['status'],'host_execution_uncertain')
            self.assertIsNone(result['executed'])
            self.assertIsNotNone(state['inflight'])
            self.assertIsNotNone(state['runtime']['quarantine'])
            self.assertEqual(focal.assignments,0)
            self.assertEqual(service.transform('fresh',action)['status'],'host_quarantined')


if __name__ == '__main__':
    unittest.main()
