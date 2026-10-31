"""Read-only unchanged-state reuse preserves durable mutation journals."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from human_eye_plugin import live_service as ls
from human_eye_plugin.live_service import LiveSpatialService, RequestBudgetError
from verification.test_live_service import SelfLockingHost
from verification.test_request_wait_budget import Clock


def compact(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')


class ObservationNoopPersistTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.state = self.folder/'state.json'
        self.config = self.folder/'config.json'
        self.config.write_text(json.dumps({'schema_version':'1.0',
            'project_root':str(Path(ls.__file__).resolve().parents[1]),
            'state_file':str(self.state),'audit_file':str(self.folder/'audit.jsonl'),
            'quad_size':128,'max_sessions':4,'request_budget_s':1.,'enabled':True}),encoding='utf-8')
        self.host = SelfLockingHost()
        self.service = LiveSpatialService(self.config,host=self.host)

    def observe(self, sid='s', *, service=None, include_image=False):
        return (service or self.service).observe(sid,focal_id='part',reference_id='base',include_image=include_image)

    def fixture(self, old_runtime, new_runtime, *, old_extra=None, new_extra=None, baseline=True):
        old = {'schema_version':'1.0','config_fingerprint':self.service.config_fingerprint,
               'runtime':copy.deepcopy(old_runtime),'inflight':None,**(old_extra or {})}
        self.state.write_bytes(compact(old))
        value = copy.deepcopy(old)
        value.update(copy.deepcopy(new_extra or {}))
        runtime = SimpleNamespace(router=SimpleNamespace(scene_cache=object()),
            export_state=lambda:copy.deepcopy(new_runtime))
        writer = ls._atomic_write
        with patch.object(ls,'_atomic_write',wraps=writer) as calls:
            self.service._save(value,runtime,_observation_baseline=old if baseline else None)
        return old,value,calls.call_count

    def test_first_observation_writes_then_unchanged_text_reuses_exact_bytes(self):
        original = ls._atomic_write
        with patch.object(ls,'_atomic_write',wraps=original) as writer:
            first = self.observe()
            self.assertEqual(writer.call_count,1)
            data = self.state.read_bytes()
            writer.reset_mock()
            second = self.observe()
        self.assertFalse(first['routing']['cache_hit'])
        self.assertTrue(second['routing']['cache_hit'])
        self.assertEqual(writer.call_count,0)
        self.assertEqual(self.state.read_bytes(),data)
        self.assertEqual((self.host.captures,self.host.calls),(2,0))
        events = [json.loads(line) for line in (self.folder/'audit.jsonl').read_text().splitlines()]
        traces = [row['trace'] for row in events if row.get('event')=='request_trace']
        self.assertEqual(len(traces),2)
        names = [row['name'] for row in traces[-1]['spans']]
        self.assertIn('state.persist.compare',names)
        self.assertIn('state.persist.skip_unchanged',names)
        self.assertNotIn('state.persist.atomic_write',names)

    def test_unchanged_image_reuses_bytes_and_restart_retains_observation(self):
        self.observe(include_image=True)
        before = self.state.read_bytes()
        restarted = LiveSpatialService(self.config,host=self.host)
        with patch.object(ls,'_atomic_write',side_effect=AssertionError('unchanged observation must not write')):
            result = self.observe(service=restarted,include_image=True)
        self.assertTrue(result['routing']['cache_hit'])
        self.assertIsNotNone(result['routing']['image'])
        self.assertEqual(self.state.read_bytes(),before)
        self.assertEqual(self.host.calls,0)

    def test_imported_lists_and_exported_tuples_have_same_json_semantics(self):
        old,new,count = self.fixture({'sessions':[['s',{'id':'1'}]]},{'sessions':[('s',{'id':'1'})]})
        self.assertEqual(count,0)
        self.assertEqual(self.state.read_bytes(),compact(old))
        self.assertEqual(compact(old),compact(new))

    def test_equal_python_values_with_different_json_numeric_spelling_must_write(self):
        for old,new in ((False,0),(True,1),(1,1.0),(0.0,-0.0),(-0.0,0.0)):
            with self.subTest(old=repr(old),new=repr(new)):
                self.assertEqual(old,new)
                _,after,count = self.fixture({'value':old},{'value':new})
                self.assertEqual(count,1)
                self.assertEqual(self.state.read_bytes(),compact(after))

    def test_dictionary_order_and_complete_envelope_changes_are_not_skipped(self):
        _,_,count = self.fixture({'a':1,'b':2},{'b':2,'a':1})
        self.assertEqual(count,1)
        for extra in ({'schema_version':'different'}, {'config_fingerprint':'changed'},
                      {'goal_segments':{'schema_version':'1.0','records':{}}},
                      {'inflight':{'operation_id':'pending'}}):
            with self.subTest(extra=extra):
                _,after,count = self.fixture({'same':True},{'same':True},new_extra=extra)
                self.assertEqual(count,1)
                self.assertEqual(self.state.read_bytes(),compact(after))

    def test_inflight_state_is_never_a_skip_even_when_identical(self):
        pending = {'inflight':{'operation_id':'same','session_id':'s','started':1.}}
        _,_,count = self.fixture({'same':True},{'same':True},old_extra=pending,new_extra=pending)
        self.assertEqual(count,1)

    def test_default_save_force_writes_even_equal_state(self):
        _,_,count = self.fixture({'same':True},{'same':True},baseline=False)
        self.assertEqual(count,1)

    def test_session_lru_change_writes_but_subsequent_same_order_does_not(self):
        self.observe('first');self.observe('second')
        original = ls._atomic_write
        with patch.object(ls,'_atomic_write',wraps=original) as writer:
            result = self.observe('first')
            self.assertTrue(result['routing']['cache_hit'])
            self.assertEqual(writer.call_count,1)
            writer.reset_mock()
            self.assertTrue(self.observe('first')['routing']['cache_hit'])
            self.assertEqual(writer.call_count,0)
        state=json.loads(self.state.read_bytes())
        self.assertEqual([row[0] for row in state['runtime']['sessions']],['second','first'])

    def test_expired_other_session_cleanup_writes_even_when_current_cache_hits(self):
        self.observe('old');self.observe('current')
        value=json.loads(self.state.read_bytes())
        value['runtime']['router']['sessions'][0][1]['observation']['created']-=1000
        self.state.write_bytes(compact(value))
        original=ls._atomic_write
        with patch.object(ls,'_atomic_write',wraps=original) as writer:
            result=self.observe('current')
        self.assertTrue(result['routing']['cache_hit'])
        self.assertEqual(writer.call_count,1)
        restored=json.loads(self.state.read_bytes())
        self.assertIsNone(restored['runtime']['router']['sessions'][0][1]['observation'])

    def test_changed_scene_and_reset_state_are_not_skipped(self):
        self.observe()
        self.host.scene['meshes'][1]['name']='renamed-part'
        original=ls._atomic_write
        with patch.object(ls,'_atomic_write',wraps=original) as writer:
            changed=self.observe()
        self.assertFalse(changed['routing']['cache_hit']);self.assertEqual(writer.call_count,1)
        self.state.unlink()
        with patch.object(ls,'_atomic_write',wraps=original) as writer:
            reset=self.observe()
        self.assertFalse(reset['routing']['cache_hit']);self.assertEqual(writer.call_count,1)

    def test_deleted_file_during_capture_is_recreated_even_for_cache_hit(self):
        self.observe()
        capture=self.host.capture_scene
        def remove():
            result=capture();self.state.unlink();return result
        original=ls._atomic_write
        with patch.object(self.host,'capture_scene',side_effect=remove),patch.object(ls,'_atomic_write',wraps=original) as writer:
            result=self.observe()
        self.assertTrue(result['routing']['cache_hit']);self.assertEqual(writer.call_count,1)
        self.assertTrue(self.state.is_file())

    def test_nonruntime_envelope_snapshot_is_detached_before_observation(self):
        self.observe()
        value=json.loads(self.state.read_bytes())
        value['metadata']={'checkpoint':1}
        self.state.write_bytes(compact(value))
        save=self.service._save
        def changed(value,runtime,**kwargs):
            value['metadata']['checkpoint']=2
            self.assertEqual(kwargs['_observation_baseline']['metadata']['checkpoint'],1)
            return save(value,runtime,**kwargs)
        original=ls._atomic_write
        with patch.object(self.service,'_save',side_effect=changed),patch.object(ls,'_atomic_write',wraps=original) as writer:
            self.assertTrue(self.observe()['routing']['cache_hit'])
        self.assertEqual(writer.call_count,1)
        self.assertEqual(json.loads(self.state.read_bytes())['metadata']['checkpoint'],2)

    def test_loaded_runtime_is_detached_from_live_import(self):
        self.observe()
        with self.service._locked() as (value,runtime):
            before=compact(value['runtime'])
            runtime._sessions['s']['task_instruction']='live-only-change'
            runtime.router._sessions['s']['observation']=None
            self.assertEqual(compact(value['runtime']),before)

    def test_transform_keeps_both_durable_journal_writes(self):
        self.observe()
        original=ls._atomic_write
        writes=[]
        def save(path,value,**kwargs):
            writes.append(copy.deepcopy(value));return original(path,value,**kwargs)
        with patch.object(ls,'_atomic_write',side_effect=save):
            result=self.service.transform('s',{'focal_id':'part','reference_id':'base','translation':[0,0,.05]})
        self.assertTrue(result['verified']);self.assertEqual(self.host.calls,1)
        self.assertEqual(len(writes),2)
        self.assertIsNotNone(writes[0]['inflight']);self.assertIsNone(writes[1]['inflight'])

    def test_comparison_expiry_stops_before_writer_or_skip(self):
        value={'schema_version':'1.0','config_fingerprint':self.service.config_fingerprint,
               'runtime':{'same':True},'inflight':None}
        baseline=copy.deepcopy(value)
        self.state.write_bytes(compact(value))
        runtime=SimpleNamespace(router=SimpleNamespace(scene_cache=object()),export_state=lambda:{'same':True})
        original=json.dumps;clock=Clock()
        def delayed(value,*args,**kwargs):
            result=original(value,*args,**kwargs)
            if value is baseline:clock.expire()
            return result
        with patch.object(ls,'time',clock),self.service._request_budget(),patch.object(ls.json,'dumps',side_effect=delayed),patch.object(ls,'_atomic_write') as writer:
            with self.assertRaises(RequestBudgetError) as caught:
                self.service._save(value,runtime,_observation_baseline=baseline)
        self.assertEqual(caught.exception.to_error_fields()['budget_stage'],'before_atomic_state_write')
        writer.assert_not_called()
        self.assertEqual(self.state.read_bytes(),compact(baseline))

    def test_size_and_nonfinite_checks_precede_noop_comparison(self):
        for payload,error in (('x'*(32*1024*1024),ValueError),(float('nan'),ValueError)):
            value={'runtime':{'payload':payload},'inflight':None}
            runtime=SimpleNamespace(router=SimpleNamespace(scene_cache=object()),export_state=lambda:{'payload':payload})
            self.state.write_bytes(b'original')
            with patch.object(ls,'_atomic_write') as writer,self.assertRaises(error):
                self.service._save(value,runtime,_observation_baseline=copy.deepcopy(value))
            writer.assert_not_called();self.assertEqual(self.state.read_bytes(),b'original')


if __name__=='__main__':unittest.main()
