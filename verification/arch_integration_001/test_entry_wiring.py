"""Source and owned composition checks; no actual Blender process or socket."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock,patch
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(OUT))
from human_eye_plugin.blender_mcp_host import BlenderMCPHost
from human_eye_plugin import live_service as ls
from human_eye_plugin.runtime_identity import runtime_identity
from verification.arch_resident_001.test_residency_contract import make_host
from verification.test_blender_process_residency import client as owned_client
from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer
import owned_service_stdio as launcher
from prepare_entry import prepare

def forbidden(*a,**kw):raise AssertionError('Unexpected connection or Blender process')

class Wiring(unittest.TestCase):
    def config(self,folder):return Path(prepare(folder,65432)[0]['owned'])
    def copy_root(self,folder):
        package=folder/'human_eye_plugin';package.mkdir(parents=True)
        for name in ('blender_host.py','scene_residency.py'):(package/name).write_bytes((ROOT/'human_eye_plugin'/name).read_bytes())
        return folder

    def test_frozen_helper_must_match_service_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);root=self.copy_root(folder/'other')
            helper=root/'human_eye_plugin/scene_residency.py'
            helper.write_bytes(helper.read_bytes()+b'\n# different helper version\n')
            host=BlenderMCPHost(root)
            service=ls.LiveSpatialService(self.config(folder/'configs'),host=host,production_mode=True)
            with patch.object(host,'_exchange',side_effect=forbidden):
                result=service.observe('s',include_image=False,query={'mode':'task','objects':[{'name':'Focal'}], 'requested_facts':['aabb']})
            self.assertEqual(result['status'],'implementation_mismatch')
            self.assertEqual(result['reason_codes'],['host_bridge_source_mismatch'])

    def test_each_resident_host_keeps_its_frozen_helper_across_roots(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)
            a=BlenderMCPHost(self.copy_root(folder/'a'));b=BlenderMCPHost(self.copy_root(folder/'b'))
            seed,*_=make_host();bpy=seed.bpy;seed.close_residency()
            namespace={'bpy':bpy}
            saved=dict(sys.modules)
            try:
                exec('if True:\n'+'\n'.join(a._resident_setup()),namespace)
                module_a=sys.modules[a._resident_slot];host_a=module_a._mcp_resident_host
                helper_a=host_a._residency_module
                exec('if True:\n'+'\n'.join(b._resident_setup()),namespace)
                self.assertIsNot(helper_a,sys.modules['_human_eye_scene_residency'])
                with patch.object(module_a,'_scene_residency_module',side_effect=forbidden):
                    capture=host_a.capture_task_scene([{'name':'Focal'},{'name':'Reference'}])
                self.assertEqual(len(capture['meshes']),2)
                self.assertIs(host_a._residency_module,helper_a)
            finally:
                for connector in (a,b):
                    module=sys.modules.get(connector._resident_slot)
                    if module is not None:module._mcp_resident_host.close_residency()
                    sys.modules.pop(connector._resident_slot,None)
                if '_human_eye_scene_residency' in saved:sys.modules['_human_eye_scene_residency']=saved['_human_eye_scene_residency']
                else:sys.modules.pop('_human_eye_scene_residency',None)

    def test_owned_launcher_composes_existing_apis_and_closes_on_error(self):
        context=MagicMock();host=object();context.__enter__.return_value=host
        with patch.object(launcher,'BlenderProcessHost',return_value=context) as owned, \
             patch.object(launcher,'_configure_utf8_stdio') as encoding, \
             patch.object(launcher,'LiveSpatialService',return_value='service') as service, \
             patch.object(launcher,'run_stdio_mcp_server',side_effect=RuntimeError('stdio failure')) as stdio:
            with self.assertRaisesRegex(RuntimeError,'stdio failure'):
                launcher.main(['--config','isolated.json','--blender','blender.exe','--scene','fixture.blend','--timeout-s','17','--spatial-task-only'])
        owned.assert_called_once_with('blender.exe','fixture.blend',timeout=17.)
        encoding.assert_called_once_with()
        service.assert_called_once_with('isolated.json',host=host,production_mode=True)
        stdio.assert_called_once_with('service',spatial_task_only=True)
        self.assertIs(context.__exit__.call_args.args[0],RuntimeError)

    def test_owned_delta_decoder_service_and_timeout_share_same_entry(self):
        backend,focal,reference,graph=make_host();self.addCleanup(backend.close_residency)
        host=owned_client();host.timeout=17.;calls=[]
        def request(command,params,**kw):
            params=dict(params);known=params.pop('_scene_baseline')
            raw=(backend.capture_task_scene(params['selectors']) if command=='capture_task' else
                 backend.capture_nearest_candidates(**params))
            packet=backend.capture_delta(raw,known);calls.append((command,params,packet))
            return packet
        host._request=request
        with tempfile.TemporaryDirectory() as temporary:
            service=ls.LiveSpatialService(self.config(Path(temporary)),host=host,production_mode=True)
            task={'mode':'task','target':{'name':'Focal'},'candidates':[{'name':'Reference'}],
                  'requested_facts':['closed_solid_relation','surface_proximity']}
            first=service.observe('s',query=task,include_image=False)
            with patch.object(ls,'_validated_scene',side_effect=forbidden):
                warm=service.observe('s',query=task,include_image=False)
            self.assertEqual(first['pairs'],warm['pairs']);self.assertEqual(calls[-1][2]['resources'],[])
            before=ls.time.perf_counter_ns()
            nearest=service.observe('s',query={'mode':'surface_nearest','objects':[{'name':'Focal'}]},include_image=False)
            self.assertEqual(nearest['nearest_objects'][0]['name'],'Reference')
            # Service and owned host use the actual 17s timeout, rather than
            # falling back to the shared-MCP default of 10s.
            self.assertGreater(calls[-1][1]['deadline_ns']-before,15_000_000_000)
            self.assertFalse(service.state_path.exists())

    def test_production_stdio_initialize_from_pinned_isolated_config(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths,commands=prepare(Path(temporary),65432)
            code="import runpy,sys;sys.path.insert(0,"+repr(str(ROOT))+");sys.argv=['production_server','--config',"+repr(paths['mcp'])+"];runpy.run_module('human_eye_plugin.production_server',run_name='__main__')"
            process=subprocess.run([sys.executable,'-I','-B','-c',code],input=json.dumps({'jsonrpc':'2.0','id':1,'method':'initialize'})+'\n',
                text=True,capture_output=True,cwd=ROOT,timeout=20)
            self.assertEqual(process.returncode,0,process.stderr)
            reply=json.loads(process.stdout)
            self.assertEqual(reply['result']['_meta']['human_eye']['source_sha256'],runtime_identity()['source_sha256'])
            (OUT/'production_initialize_response.json').write_text(process.stdout,encoding='utf8')
            self.assertFalse((Path(paths['mcp']).parent/'actions.json').exists())
            self.assertEqual((ROOT/'examples/blender_worker.py').read_bytes(),(ROOT/'human_eye_plugin/blender_worker.py').read_bytes())

if __name__=='__main__':
    # The one production subprocess only sends initialize; no host connection.
    with patch.object(socket,'socket',side_effect=forbidden),patch.object(socket,'create_connection',side_effect=forbidden):
        unittest.main(verbosity=2)
