"""An incompatible visual engine must refuse before touching the scene."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer
from human_eye_plugin.live_hooks import route_live_hook
from verification.test_live_service import SelfLockingHost


class ObservationIdentityGateTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.config=self.root/'connector.json'
        self.host=SelfLockingHost()
        self.host.capture_scene=Mock(side_effect=AssertionError('Identity gate contacted host'))
        self.host.native_observation_capabilities=Mock(side_effect=AssertionError('Identity gate probed host'))
        self.host.observe_readonly_native=Mock(side_effect=AssertionError('Identity gate rendered host'))

    def service(self,expected=None):
        config={'schema_version':'1.0','enabled':True,'observe_on_prompt':True,
            'project_root':str(Path(__file__).resolve().parents[1]),'state_file':'state.json',
            'audit_file':'audit.jsonl','quad_size':64}
        if expected is not None:config['expected_identity']=expected
        self.config.write_text(json.dumps(config),encoding='utf8')
        return LiveSpatialService(self.config,host=self.host)

    def assert_no_scene_or_state_work(self):
        self.host.capture_scene.assert_not_called()
        self.host.native_observation_capabilities.assert_not_called()
        self.host.observe_readonly_native.assert_not_called()
        self.assertEqual(self.host.calls,0)
        self.assertFalse((self.root/'state.json').exists())

    def test_wrong_identity_blocks_text_projection_native_and_hook_before_host(self):
        for expected in ({'build_id':'sha256:'+'0'*64},
                         {'implementation_revision':'unavailable-revision'},
                         {'source_kind':'installed_distribution'}):
            service=self.service(expected)
            for include_image,mode in ((False,'auto'),(True,'auto'),(True,'projection'),(True,'multiscale')):
                with self.subTest(expected=expected,mode=mode,image=include_image):
                    result=service.observe('pin-test',focal_id='part',reference_id='base',
                        include_image=include_image,query={'native_visual':{'mode':mode}})
                    self.assertEqual(result['status'],'implementation_mismatch')
                    self.assertFalse(result['executed']);self.assertFalse(result['allow_action'])
            reply=LiveSpatialMCPServer(service).handle_jsonrpc_message({
                'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'human_eye_scene_observe',
                'arguments':{'session_id':'mcp-pin-test','include_image':False}}})['result']
            self.assertTrue(reply['isError'])
            self.assertEqual([block['type'] for block in reply['content']],['text'])
            output=route_live_hook({'hook_event_name':'UserPromptSubmit','session_id':'hook-pin',
                'turn_id':'turn','prompt':'检查 Blender 中 "part" 与 "base" 的间隙，只观察，不移动。'},
                service,agent='codex',invocation_source='hook_command')
            summary=json.loads(output['hookSpecificOutput']['additionalContext'])
            self.assertEqual(summary['human_eye_live'],'implementation_mismatch')
            diagnostic=service.status()
            self.assertFalse(diagnostic['runtime_identity']['identity_check']['compatible'])
            self.assert_no_scene_or_state_work()

    def test_production_source_drift_rejects_observation_but_status_remains_diagnostic(self):
        service=self.service();service.production_mode=True
        with patch('human_eye_plugin.live_service.check_source_drift',return_value={
                'compatible':False,'reasons':['source_bytes_changed']}) as check:
            result=service.observe('drift-test',focal_id='part',reference_id='base',include_image=False)
            self.assertEqual(result['status'],'implementation_mismatch')
            self.assertEqual(result['reason_codes'],['source_bytes_changed'])
            self.assertFalse(result['executed']);self.assertFalse(result['allow_action'])
            check.assert_called_once()
            diagnostic=service.status()
            self.assertIn('runtime_identity',diagnostic)
            self.assertEqual(check.call_count,1)
        self.assert_no_scene_or_state_work()


if __name__=='__main__':unittest.main()
