"""Service-level read reconnect boundaries over the real socket adapter."""
import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from human_eye_plugin.blender_mcp_host import BlenderMCPHost
from human_eye_plugin.blender_process import HostTransportError
from human_eye_plugin.live_service import LiveSpatialService
from verification.test_blender_mcp_host import _server,_reply
from verification.test_blender_native_evidence import fixture

ROOT=Path(__file__).resolve().parents[1]

class ReadonlyReconnectServiceTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.config=self.root/'connector.json'
        self.config.write_text(json.dumps({'schema_version':'1.0','project_root':str(ROOT),
            'state_file':'state.json','audit_file':'audit.jsonl','quad_size':64,'enabled':True}),encoding='utf8')
        producer,part,base,_=fixture();self.capture=producer.capture_scene()
        self.pair={'focal_id':producer.object_id(part),'reference_id':producer.object_id(base)}

    def test_observe_reconnects_on_next_call_after_definite_presend_failure(self):
        with _server(lambda request:_reply(request,self.capture),connections=1) as (port,requests):
            host=BlenderMCPHost(ROOT,port=port);service=LiveSpatialService(self.config,host=host)
            with patch.object(host,'_connect',side_effect=ConnectionRefusedError('offline before any send')) as connect:
                with self.assertRaises(HostTransportError):service.observe('r',include_image=False,**self.pair)
                connect.assert_called_once()
            self.assertTrue(host.is_alive);self.assertIs(service.host,host)
            self.assertFalse((self.root/'state.json').exists())
            result=service.observe('r',include_image=False,**self.pair)
            self.assertEqual(result['status'],'observed')
            self.assertEqual([r[1]['command'] for r in requests],['capture'])
            self.assertEqual(result['visual_delivery']['capability_status'],'not_probed')

    def test_pending_operation_is_preserved_without_attempting_reconnect(self):
        with _server(lambda request:_reply(request,self.capture),connections=1) as (port,requests):
            host=BlenderMCPHost(ROOT,port=port);service=LiveSpatialService(self.config,host=host)
            service.observe('r',include_image=False,**self.pair)
            state=self.root/'state.json';value=json.loads(state.read_text())
            value['inflight']={'operation_id':'unknown-write','session_id':'r','started':time.time()}
            state.write_text(json.dumps(value),encoding='utf8');before=state.read_bytes()
            host._poisoned=True
            with patch.object(host,'_connect',side_effect=AssertionError('Unknown write must not reconnect')) as connect:
                result=service.observe('r',include_image=False,**self.pair)
                connect.assert_not_called()
            self.assertEqual(result['status'],'host_quarantined')
            self.assertEqual(state.read_bytes(),before);self.assertTrue(host._poisoned)
            self.assertEqual(len(requests),1)

    def test_bad_response_stays_poisoned_across_later_observation_scopes(self):
        with _server(lambda request:b'{broken-json',connections=1) as (port,requests):
            host=BlenderMCPHost(ROOT,port=port);service=LiveSpatialService(self.config,host=host)
            with self.assertRaises(HostTransportError):service.observe('r',include_image=False,**self.pair)
            self.assertFalse(host.is_alive)
            with patch.object(host,'_connect',side_effect=AssertionError('Poison must remain permanent')) as connect:
                with self.assertRaises(HostTransportError):service.observe('r',include_image=False,**self.pair)
                connect.assert_not_called()
            self.assertEqual(len(requests),1)

if __name__=='__main__':unittest.main()
