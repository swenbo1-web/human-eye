"""Durable live service tests: fresh scenes, crash journal and inner gate."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from human_eye_plugin.live_service import LiveSpatialService
from verification.test_host_runtime import MutableHost


class SelfLockingHost(MutableHost):
    def capture_scene(self):
        if self.in_transaction:return super().capture_scene()
        with self.transaction():return super().capture_scene()


class LiveServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.config_path=self.base/'live.json'
        self.config={'schema_version':'1.0','project_root':str(Path(__file__).resolve().parents[1]),
                     'state_file':'state.json','audit_file':'events.jsonl','quad_size':64,'max_sessions':4,
                     'enabled':True}
        self.config_path.write_text(json.dumps(self.config),encoding='utf-8')
        self.host=SelfLockingHost();self.service=LiveSpatialService(self.config_path,host=self.host)
        self.action={'focal_id':'part','reference_id':'base','translation':[0,0,.05]}

    def observe(self,service=None,**changes):
        return (service or self.service).observe('s',focal_id='part',reference_id='base',**changes)

    def state(self):return json.loads((self.base/'state.json').read_text(encoding='utf-8'))

    def test_auto_observe_and_actual_inner_gate_without_prior_tool_choice(self):
        result=self.service.transform('s',self.action)
        self.assertTrue(result['verified'],result);self.assertEqual(self.host.calls,1)
        self.assertIsNone(self.state()['inflight'])

    def test_cross_instance_persistence_and_preview_does_not_execute(self):
        preview=self.service.preview_action('s',self.action)
        self.assertTrue(preview['allow_action']);self.assertEqual(self.host.calls,0)
        other=LiveSpatialService(self.config_path,host=self.host)
        self.assertTrue(other.transform('s',self.action)['verified'])

    def test_preview_does_not_eliminate_fresh_execution_check(self):
        self.assertTrue(self.service.preview_action('s',self.action)['allow_action'])
        bad={**self.action,'translation':[0,0,-.15]}
        result=self.service.transform('s',bad)
        self.assertEqual(result['status'],'blocked');self.assertEqual(self.host.calls,0)
        self.assertIsNone(self.state()['inflight'])

    def test_failed_or_partial_mutation_persists_connector_wide_quarantine(self):
        self.host.mode='partial_failure'
        result=self.service.transform('s',self.action)
        self.assertFalse(result['verified']);self.assertIsNotNone(self.state()['inflight'])
        other=LiveSpatialService(self.config_path,host=self.host)
        self.assertEqual(other.transform('other',self.action)['status'],'host_quarantined')
        self.assertEqual(other.observe('other')['status'],'host_quarantined')
        self.assertEqual(self.host.calls,1)

    def test_final_state_write_failure_leaves_original_uncertainty_journal(self):
        from human_eye_plugin.live_service import _atomic_write
        calls=[]
        def fail_final(path,data,**kwargs):
            calls.append(copy.deepcopy(data))
            if len(calls)==2:raise OSError('simulated crash before commit')
            return _atomic_write(path,data,**kwargs)
        with patch('human_eye_plugin.live_service._atomic_write',side_effect=fail_final):
            with self.assertRaises(OSError):self.service.transform('s',self.action)
        self.assertEqual(self.host.calls,1);self.assertIsNotNone(self.state()['inflight'])
        other=LiveSpatialService(self.config_path,host=self.host)
        self.assertEqual(other.transform('new',self.action)['status'],'host_quarantined')
        self.assertEqual(self.host.calls,1)

    def test_initial_journal_write_failure_never_calls_host_mutation(self):
        with patch('human_eye_plugin.live_service._atomic_write',side_effect=OSError('cannot journal')):
            with self.assertRaises(OSError):self.service.transform('s',self.action)
        self.assertEqual(self.host.calls,0)

    def test_corrupt_or_incomplete_state_is_not_reset(self):
        self.observe();state=self.state()
        for field,value in (('runtime',{}),('runtime',None),('runtime',False),('inflight',False),('inflight',{})):
            bad=copy.deepcopy(state);bad[field]=value
            (self.base/'state.json').write_text(json.dumps(bad),encoding='utf-8')
            with self.assertRaises((ValueError,KeyError)):self.service.transform('s',self.action)
        self.assertEqual(self.host.calls,0)

    def test_configuration_change_requires_host_review(self):
        self.observe();self.config['quad_size']=128
        self.config_path.write_text(json.dumps(self.config),encoding='utf-8')
        other=LiveSpatialService(self.config_path,host=self.host)
        with self.assertRaises(ValueError):other.transform('s',self.action)

    def test_disabled_service_never_reads_or_mutates_blender(self):
        self.config['enabled']=False;self.config_path.write_text(json.dumps(self.config),encoding='utf-8')
        disabled=LiveSpatialService(self.config_path,host=self.host)
        self.assertEqual(disabled.observe('s')['status'],'disabled')
        self.assertFalse(disabled.preview_action('s',self.action)['allow_action'])
        self.assertFalse(disabled.transform('s',self.action)['verified'])
        self.assertEqual(self.host.captures,0);self.assertEqual(self.host.calls,0)

    def test_unpaired_scene_has_real_overview_but_no_action_qualification(self):
        self.host.scene['meshes']=self.host.scene['meshes'][1:]
        result=self.service.observe('s')
        self.assertEqual(result['status'],'overview');route=result['routing']
        self.assertEqual(route['execution_scope'],'scene_overview_only')
        self.assertIsNone(route['observation_id']);self.assertIsNotNone(route['image'])
        self.assertEqual(self.state()['runtime']['sessions'],[])

    def test_bad_objects_and_unknown_operations_fail_closed(self):
        for action in ({'translation':[0,0,.1]}, {**self.action,'scale':[1,1,1]},
                       {**self.action,'focal_id':'missing'}):
            try:result=self.service.transform('s',action)
            except ValueError:continue
            self.assertFalse(result['verified'])
        self.assertEqual(self.host.calls,0)

    def test_audit_failure_does_not_change_verified_mutation_to_retryable_error(self):
        with patch('human_eye_plugin.live_service.LiveSpatialService.record_event',return_value=False):
            result=self.service.transform('s',self.action)
        self.assertTrue(result['verified']);self.assertEqual(self.host.calls,1)


if __name__=='__main__':unittest.main()
