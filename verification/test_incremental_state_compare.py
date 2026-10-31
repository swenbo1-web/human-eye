"""Strict JSON parity, error validation and durable-write boundaries."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from human_eye_plugin import live_service as ls
from human_eye_plugin.live_service import LiveSpatialService, RequestBudgetError
from verification.test_live_service import SelfLockingHost


class IncrementalCompareTests(unittest.TestCase):
    def matches(self,new,old):
        encoded=json.dumps(new,ensure_ascii=True,allow_nan=False)
        with patch.object(ls,'_STATE_WRITE_BUFFER_LIMIT',0):
            return ls._state_json_matches(encoded,old)

    def test_numeric_types_and_signed_zero_follow_ascii_json_not_python_equality(self):
        values=[False,True,0,1,0.,-0.,1.,1e-300,1e300,None]
        for a in values:
            for b in values:
                with self.subTest(a=repr(a),b=repr(b)):
                    self.assertEqual(self.matches({'x':a},{'x':b}),json.dumps({'x':a})==json.dumps({'x':b}))

    def test_unicode_and_surrogate_representations_follow_standard_ascii_encoder(self):
        pairs=[('中文\n\\"','中文\n\\"'),('\U0001f600','\ud83d\ude00'),
            ('\U0001f600\ud83d\ude01','\ud83d\ude00\U0001f601'),('\ud800','\ud800'),
            ('\ud800','\ud801'),('e\u0301','é')]
        for a,b in pairs:
            with self.subTest(a=repr(a),b=repr(b)):
                self.assertEqual(self.matches({'x':a},{'x':b}),json.dumps({'x':a})==json.dumps({'x':b}))

    def test_dict_order_and_list_tuple_json_semantics(self):
        self.assertTrue(self.matches({'x':[(1,2)]},{'x':[[1,2]]}))
        self.assertFalse(self.matches({'a':1,'b':2},{'b':2,'a':1}))
        self.assertTrue(self.matches({'1':False},{1:False}))
        self.assertFalse(self.matches({'x':[1,2]},{'x':[2,1]}))

    def test_prefix_differences_do_not_match(self):
        for a,b in [([1],[1,2]),('a','ab'),({'a':1},{'a':1,'b':2}),('',None)]:
            self.assertFalse(self.matches(a,b))

    def test_mismatch_does_not_hide_trailing_nonfinite_or_unsupported_values(self):
        for invalid,error in [(float('nan'),ValueError),(float('inf'),ValueError),({1,2},TypeError)]:
            with self.subTest(value=repr(invalid)):
                with self.assertRaises(error):
                    self.matches({'first':'new','tail':0},{'first':'old','tail':invalid})

    def test_mismatch_does_not_hide_trailing_circular_state(self):
        circular=[];circular.append(circular)
        with self.assertRaisesRegex(ValueError,'Circular reference'):
            self.matches({'first':'new'},{'first':'old','tail':circular})

    def test_large_single_string_stream_does_not_build_a_joined_old_document(self):
        old={'runtime':{'payload':'x'*(1024*1024)},'inflight':None}
        encoded=json.dumps(old,ensure_ascii=True,allow_nan=False)
        with patch.object(ls.json,'dumps',side_effect=AssertionError('joined old document')):
            self.assertTrue(ls._state_json_matches(encoded,old))

    def test_token_heavy_state_uses_original_encoder_after_bounded_probe(self):
        old={'rows':list(range(20000)),'payload':'x'*(1024*1024)}
        encoded=json.dumps(old);original=json.dumps;checks=[]
        with patch.object(ls.json,'dumps',wraps=original) as fallback:
            self.assertTrue(ls._state_json_matches(encoded,old,checkpoint=lambda:checks.append(True)))
        self.assertEqual(fallback.call_count,1)
        self.assertLessEqual(len(checks),1+ls._STATE_COMPARE_STREAM_CHUNKS//16)

    def test_bounded_probe_fallback_still_validates_invalid_late_values(self):
        old={'rows':list(range(20000))+[float('nan')],'payload':'x'*(1024*1024)}
        with self.assertRaises(ValueError):self.matches({'first':'changed'},old)

    def test_small_state_retains_original_c_encoder_comparison(self):
        old={'a':[1,False,-0.]};encoded=json.dumps(old)
        original_iter=json.JSONEncoder.iterencode
        def only_c(encoder,value,_one_shot=False):
            self.assertTrue(_one_shot)
            return original_iter(encoder,value,_one_shot=_one_shot)
        with patch.object(ls.json.JSONEncoder,'iterencode',only_c):
            self.assertTrue(ls._state_json_matches(encoded,old))


class IncrementalSaveIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.state=self.root/'state.json'
        config=self.root/'config.json'
        config.write_text(json.dumps({'schema_version':'1.0','enabled':True,
            'project_root':str(Path(ls.__file__).resolve().parents[1]),'state_file':str(self.state),
            'audit_file':str(self.root/'audit.jsonl'),'quad_size':128}),encoding='utf-8')
        self.service=LiveSpatialService(config,host=SelfLockingHost())

    def fixture(self):
        old={'schema_version':'1.0','config_fingerprint':self.service.config_fingerprint,
            'runtime':{'payload':'x'*(1024*1024),'generation':0},'inflight':None}
        self.state.write_text(json.dumps(old,separators=(',',':')),encoding='utf-8')
        runtime=SimpleNamespace(router=SimpleNamespace(scene_cache=None),export_state=lambda:copy.deepcopy(old['runtime']))
        return old,runtime

    def test_large_noop_keeps_original_durable_bytes_and_changed_state_writes(self):
        old,runtime=self.fixture();before=self.state.read_bytes();original=ls._atomic_write
        with patch.object(ls,'_atomic_write',wraps=original) as writes:
            self.service._save(copy.deepcopy(old),runtime,_observation_baseline=old)
        writes.assert_not_called();self.assertEqual(self.state.read_bytes(),before)
        changed=copy.deepcopy(old['runtime']);changed['generation']=1;runtime.export_state=lambda:changed
        with patch.object(ls,'_atomic_write',wraps=original) as writes:
            self.service._save(copy.deepcopy(old),runtime,_observation_baseline=old)
        self.assertEqual(writes.call_count,1)
        self.assertEqual(json.loads(self.state.read_bytes())['runtime']['generation'],1)

    def test_stream_budget_expiry_neither_skips_nor_writes(self):
        old,runtime=self.fixture();before=self.state.read_bytes();original=self.service._check_request_budget
        def expire(stage):
            if stage=='during_state_comparison':raise RequestBudgetError('expired',stage)
            return original(stage)
        with (patch.object(self.service,'_check_request_budget',side_effect=expire),
              patch.object(ls,'_atomic_write') as writes,self.assertRaises(RequestBudgetError)):
            self.service._save(copy.deepcopy(old),runtime,_observation_baseline=old)
        writes.assert_not_called();self.assertEqual(self.state.read_bytes(),before)

    def test_public_large_cache_hit_uses_stream_and_preserves_complete_state(self):
        self.service.observe('s',focal_id='part',reference_id='base',include_image=False)
        old=json.loads(self.state.read_bytes());old['diagnostics']={'payload':'x'*(1024*1024)}
        self.state.write_text(json.dumps(old,separators=(',',':')),encoding='utf-8')
        before=self.state.read_bytes()
        with patch.object(ls,'_atomic_write',side_effect=AssertionError('unchanged public observation wrote')):
            result=self.service.observe('s',focal_id='part',reference_id='base',include_image=False)
        self.assertTrue(result['routing']['cache_hit']);self.assertEqual(self.state.read_bytes(),before)
        events=[json.loads(x) for x in (self.root/'audit.jsonl').read_text().splitlines()]
        trace=[x['trace'] for x in events if x.get('event')=='request_trace'][-1]
        names=[s['name'] for s in trace['spans']]
        self.assertIn('state.persist.compare_stream',names)
        self.assertNotIn('state.persist.compare_fallback',names)
        self.assertIn('state.persist.skip_unchanged',names)

    def test_oversized_current_state_stops_before_old_compare(self):
        old,runtime=self.fixture();before=self.state.read_bytes()
        runtime.export_state=lambda:{'payload':'x'*(32*1024*1024)}
        with (patch.object(ls,'_state_json_matches',side_effect=AssertionError('size gate bypassed')),
              patch.object(ls,'_atomic_write') as writes,self.assertRaisesRegex(ValueError,'32 MiB')):
            self.service._save(copy.deepcopy(old),runtime,_observation_baseline=old)
        writes.assert_not_called();self.assertEqual(self.state.read_bytes(),before)


if __name__=='__main__':unittest.main()
