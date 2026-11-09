"""One-source host/template/delta/client/service/MCP chain on fake bpy.

The transport only replaces _exchange with in-process execution. Production
request generation, host capture/delta, response validation, delta decode,
ReadContext, geometry and MCP encoding remain real. No socket or Blender.
"""
from __future__ import annotations

import ast
import builtins
from contextlib import ExitStack, redirect_stdout
import copy
import hashlib
import io
import itertools
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from human_eye_plugin import auto_router, live_service as service_module, task_query
from human_eye_plugin import live_spatial_mcp as mcp, mcp_transport as wire
from human_eye_plugin.blender_mcp_host import BlenderMCPHost, RPC_PREFIX
from human_eye_plugin.runtime_identity import runtime_identity
from verification.arch_resident_001 import test_residency_contract as fixture

RECORDS=[]

def compact(value):
    return json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf8')

def forbidden(*a,**kw):
    raise AssertionError('No network, subprocess, Blender or action-state work')

def without_trace(value):
    return {key:item for key,item in value.items() if key!='trace_id'}

class InProcessClient(BlenderMCPHost):
    def __init__(self,bpy):
        self.bpy=bpy
        self.exchanges=[]
        self.decoded=[]
        self.explicit_source_compiles=[]
        super().__init__(ROOT,timeout_s=10.)
        self._old_slot=sys.modules.pop(self._resident_slot,None)
        self._old_helper=sys.modules.get('_human_eye_scene_residency')
        original=self._scene_decoder.apply
        def decode(packet):
            result=original(packet)
            self.decoded.append(copy.deepcopy(result))
            return result
        self._scene_decoder.apply=decode

    @property
    def backend(self):
        return sys.modules[self._resident_slot]._mcp_resident_host

    def _exchange(self,payload):
        request=json.loads(payload)
        code=request['params']['code']
        prefix='_request = _json.loads('
        literal=next(line[len(prefix):-1] for line in code.splitlines() if line.startswith(prefix))
        inner=json.loads(ast.literal_eval(literal))
        stream=io.StringIO()
        original=builtins.compile
        def compile_source(source,filename,*a,**kw):
            if filename in (str(ROOT/'human_eye_plugin/blender_host.py'),str(ROOT/'human_eye_plugin/scene_residency.py')):
                self.explicit_source_compiles.append(filename)
            return original(source,filename,*a,**kw)
        with patch.object(builtins,'compile',side_effect=compile_source),redirect_stdout(stream):
            exec(code,{'bpy':self.bpy})
        output=stream.getvalue()
        envelope=json.loads(output[len(RPC_PREFIX):])
        result=envelope.get('result')
        self.exchanges.append({'command':inner['command'],'request_bytes':len(payload),
            'envelope':copy.deepcopy(envelope),'response_bytes':len(output.encode('utf8')),
            'resource_count':len(result.get('resources',[])) if isinstance(result,dict) else None})
        return {'status':'success','result':{'executed':True,'result':output}}

    def cleanup(self):
        module=sys.modules.pop(self._resident_slot,None)
        if module is not None:
            backend=getattr(module,'_mcp_resident_host',None)
            if backend is not None:backend.close_residency()
        if self._old_slot is not None:sys.modules[self._resident_slot]=self._old_slot
        if self._old_helper is None:sys.modules.pop('_human_eye_scene_residency',None)
        else:sys.modules['_human_eye_scene_residency']=self._old_helper
        self.close()

class ServicePipelineTests(unittest.TestCase):
    def setUp(self):
        initial,self.focal,self.reference,self.graph=fixture.make_host()
        self.bpy=initial.bpy
        initial.close_residency()
        self.focal._matrix_world=fixture.fixture.matrix((0,0,0))
        self.reference._matrix_world=fixture.fixture.matrix((3,0,0))
        self.far=fixture.prepare_object(fixture.fixture.FakeObject('Far',(8,0,0)),103)
        self.bpy.context.scene.objects.append(self.far)
        self.temp=tempfile.TemporaryDirectory(prefix='service_pipeline_')
        self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.config=self.base/'connector.json'
        self.config.write_bytes(compact({'schema_version':'1.0','enabled':True,'quad_size':64,
            'project_root':str(ROOT),'state_file':'actions.json','audit_file':'audit.jsonl'}))
        self.client=InProcessClient(self.bpy)
        self.addCleanup(self.client.cleanup)
        self.service=service_module.LiveSpatialService(self.config,host=self.client,production_mode=True)
        self.service.state_path.write_bytes(b'opaque pending/committed/quarantine action bytes')
        self.ledger=self.service.state_path.read_bytes()
        self.narrow=mcp.LiveSpatialMCPServer(self.service,'integration',spatial_task_only=True)
        self.ordinary=mcp.LiveSpatialMCPServer(self.service,'integration')
        self.addCleanup(self.record)

    def record(self):
        RECORDS.append({'test':self.id(),'source_sha256':runtime_identity()['source_sha256'],
            'exchanges':self.client.exchanges,'explicit_source_compiles':self.client.explicit_source_compiles,
            'host_stats':self.client.backend.residency_work() if self.client._resident_slot in sys.modules else {}})
        OUT.mkdir(parents=True,exist_ok=True)
        (OUT/'service_pipeline_records.json').write_text(json.dumps(RECORDS,indent=2)+'\n',encoding='utf8')

    def call(self,candidates=('Reference',),*,target='Focal',nearest=False):
        name='human_eye_scene_observe' if nearest else 'human_eye_spatial_relations'
        arguments=({'session_id':'integration','include_image':False,'query':{'mode':'surface_nearest','objects':[{'name':target}]}}
            if nearest else {'target':{'name':target},'candidates':[{'name':item} for item in candidates], 'include_aabb':True})
        with ExitStack() as stack:
            for method in ('_locked','_save','_runtime'):
                stack.enter_context(patch.object(self.service,method,side_effect=forbidden))
            reply=(self.ordinary if nearest else self.narrow).handle_jsonrpc_message({'jsonrpc':'2.0','id':7,
                'method':'tools/call','params':{'name':name,'arguments':arguments}})
        encoded=wire.encode_response(reply)
        self.assertFalse(reply['result']['isError'],reply)
        self.assertEqual(reply['id'],7)
        self.assertEqual([item['type'] for item in reply['result']['content']],['text'])
        body=json.loads(json.loads(encoded)['result']['content'][0]['text'])
        for internal in ('capture_state','_scene_resource','vertices_local','live_resources','scene-resource-delta'):
            self.assertNotIn(internal,encoded)
        self.assertEqual(self.service.state_path.read_bytes(),self.ledger)
        return body

    def token(self):
        logical=self.client.decoded[-1]
        return (logical.get('capture') or logical)['capture_state']

    def assert_current_source(self,body):
        binding=body.get('context',body.get('binding'))
        self.assertEqual(binding['runtime_source_sha256'],runtime_identity()['source_sha256'])
        host_sha=next(row['sha256'] for row in runtime_identity()['source_files'] if row['path']=='human_eye_plugin/blender_host.py')
        self.assertEqual(self.client._readonly_host_source_sha256,host_sha)
        self.assertEqual(self.client.backend.__class__.__module__,self.client._resident_slot)

    def test_cold_and_warm_selected_chain_consumes_token_before_normalization(self):
        original=service_module._validated_scene
        tokens=[]
        def validate(raw,*a,**kw):
            self.assertIn('capture_state',raw)
            tokens.append(dict(raw['capture_state']))
            result=original(raw,*a,**kw)
            self.assertNotIn('capture_state',result[0])
            return result
        with patch.object(service_module,'_validated_scene',side_effect=validate) as normalized:
            cold=self.call()
        self.assertEqual(normalized.call_count,1)
        self.assertEqual(cold['sets']['nearest_separated']['distance_m'],2.)
        self.assertEqual(cold['candidates'][0]['closed_solid_relation']['value'],'separated')
        self.assert_current_source(cold)
        self.assertEqual(self.client.exchanges[0]['resource_count'],2)
        stats=self.client.backend.residency_work()
        compiles=len(self.client.explicit_source_compiles)
        with patch.object(service_module,'_validated_scene',side_effect=forbidden), \
             patch.object(task_query,'task_result',side_effect=forbidden), \
             patch.object(auto_router.MeshEntity3D,'from_dict',side_effect=forbidden):
            warm=self.call()
        self.assertEqual(without_trace(cold),without_trace(warm))
        self.assertEqual(tokens[-1],self.token())
        self.assertEqual(self.client.exchanges[-1]['resource_count'],0)
        for key in ('to_mesh','triangulations','resource_builds'):
            self.assertEqual(self.client.backend.residency_work()[key],stats[key])
        self.assertEqual(len(self.client.explicit_source_compiles),compiles)
        self.assertEqual(compiles,2)
        self.assertLess(self.client.exchanges[1]['request_bytes'],self.client.exchanges[0]['request_bytes'])

    def test_selection_switch_reuses_old_normalized_and_facts(self):
        with patch.object(service_module,'_validated_scene',wraps=service_module._validated_scene) as normalize, \
             patch.object(task_query,'task_result',wraps=task_query.task_result) as task:
            first=self.call(('Reference',))
            other=self.call(('Far',))
            again=self.call(('Reference',))
        self.assertEqual(normalize.call_count,2)
        self.assertEqual(task.call_count,2)
        self.assertEqual(without_trace(first),without_trace(again))
        self.assertEqual(other['sets']['nearest_separated']['distance_m'],7.)
        self.assertEqual([row['resource_count'] for row in self.client.exchanges],[2,1,0])

    def test_nearest_warm_uses_real_delta_and_no_repeated_summarizer(self):
        with patch.object(service_module,'_validated_scene',wraps=service_module._validated_scene) as normalize:
            cold=self.call(nearest=True)
        self.assertEqual(normalize.call_count,1)
        token=self.token()
        self.assertEqual(cold['nearest_objects'][0]['name'],'Reference')
        self.assertEqual(cold['distance_m'],2.)
        self.assert_current_source(cold)
        with patch.object(service_module,'_validated_scene',side_effect=forbidden), \
             patch.object(task_query,'surface_nearest_result',side_effect=forbidden):
            warm=self.call(nearest=True)
        self.assertEqual(without_trace(cold),without_trace(warm))
        self.assertEqual(self.token(),token)
        self.assertEqual(self.client.exchanges[-1]['resource_count'],0)

    def test_metadata_pose_and_mesh_updates_reach_current_facts(self):
        first=self.call();before=self.token();stats=self.client.backend.residency_work()
        self.focal.color=(.1,.2,.3,1.)
        with patch.object(service_module,'_validated_scene',wraps=service_module._validated_scene) as normalize:
            colored=self.call()
        self.assertEqual(normalize.call_count,1)
        self.assertNotEqual(self.token(),before)
        self.assertEqual(colored['sets'],first['sets'])
        self.assertEqual(self.client.backend.residency_work()['to_mesh'],stats['to_mesh'])
        self.assertEqual(self.client.exchanges[-1]['resource_count'],0)
        before=self.token();self.reference._matrix_world[0][3]+=1.
        moved=self.call()
        self.assertNotEqual(self.token(),before)
        self.assertEqual(moved['sets']['nearest_separated']['distance_m'],3.)
        self.assertEqual(self.client.exchanges[-1]['resource_count'],0)
        self.assertEqual(self.client.backend.residency_work()['to_mesh'],stats['to_mesh'])
        self.focal.data.vertices[1].co=(1.5,0.,0.)
        self.focal.bound_box=list(itertools.product((0.,1.5),(0.,1.),(0.,1.)))
        fixture.notify_geometry(self.client.backend,self.graph,self.focal,via_data=True)
        changed=self.call()
        self.assertEqual(changed['target']['aabb']['value']['max'][0],1.5)
        self.assertEqual(changed['sets']['nearest_separated']['distance_m'],2.5)
        self.assertEqual(self.client.exchanges[-1]['resource_count'],1)

    def test_names_units_frame_and_epoch_invalidate_context(self):
        initial=self.call();before=self.token()
        self.reference.name=self.reference.name_full='Renamed'
        renamed=self.call(('Renamed',))
        self.assertNotEqual(before,self.token())
        self.assertEqual(renamed['candidates'][0]['name'],'Renamed')
        self.assertNotEqual(initial['candidates'][0]['object_id'],renamed['candidates'][0]['object_id'])
        before=self.token();self.bpy.context.scene.unit_settings.scale_length=.01
        scaled=self.call(('Renamed',))
        self.assertNotEqual(before,self.token())
        self.assertAlmostEqual(scaled['sets']['nearest_separated']['distance_m'],.02,places=14)
        before=self.token();self.bpy.context.scene.frame_current+=1
        framed=self.call(('Renamed',))
        self.assertNotEqual(before,self.token())
        self.assertEqual(framed['sets'],scaled['sets'])
        for kind in ('undo_post','redo_post','load_post'):
            before=self.token()
            callbacks=tuple(getattr(self.bpy.app.handlers,kind))
            self.assertTrue(callbacks)
            for callback in callbacks:callback(None)
            with patch.object(service_module,'_validated_scene',wraps=service_module._validated_scene) as normalize:
                current=self.call(('Renamed',))
            self.assertEqual(normalize.call_count,1)
            self.assertNotEqual(before['epoch'],self.token()['epoch'])
            self.assertEqual(current['sets'],scaled['sets'])
            self.assertGreater(self.client.exchanges[-1]['resource_count'],0)

    def test_task_and_nearest_coexist_without_cross_binding(self):
        with patch.object(service_module,'_validated_scene',wraps=service_module._validated_scene) as normalize, \
             patch.object(task_query,'task_result',wraps=task_query.task_result) as task, \
             patch.object(task_query,'surface_nearest_result',wraps=task_query.surface_nearest_result) as nearest:
            task_first=self.call();near_first=self.call(nearest=True)
            task_again=self.call();near_again=self.call(nearest=True)
        self.assertEqual((normalize.call_count,task.call_count,nearest.call_count),(2,1,1))
        self.assertEqual(task_first['sets'],task_again['sets'])
        self.assertEqual(near_first['nearest_objects'],near_again['nearest_objects'])
        self.assertEqual(len(self.service._read_context._selections),2)

if __name__=='__main__':
    with patch.object(socket,'socket',side_effect=forbidden), \
         patch.object(socket,'create_connection',side_effect=forbidden), \
         patch.object(subprocess,'Popen',side_effect=forbidden):
        unittest.main(verbosity=2)
