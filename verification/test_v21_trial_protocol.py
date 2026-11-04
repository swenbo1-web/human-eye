"""Finite transport guards: static lookups are not live targeted inspections."""
import contextlib,copy,hashlib,io,json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from verification import v21_trial_protocol as p

class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.frame=dict(source_ref={'scene_sha256':'a'*64},source_observation_sha256='b'*64,anchor_id='anchor',
            rows=[dict(triangle=i,state='measured',reason=None,principal_stretches=[1.2,.8],area_ratio=.96) for i in range(6)],
            members=[0,1],initial_row_indices=[0],initial_summary=dict(core_states=dict(measured=2,collapsed=0,unknown=0),
                global_states=dict(measured=6,collapsed=0,unknown=0)))
        common=dict(sources={label:dict(core_half_extents_m=[.5]*3) for label in ('l','r')})
        p.save(self.root/'COMMON.json',common);p.save(self.root/'A/REPORT.json',dict(schema='ordinary',details=[0]))
        backend=dict(task_sha256='t',run_nonce='n',original_topology_sha256='c'*64,
            report_sha256=p.sha(self.root/'A/REPORT.json'),frames={label:copy.deepcopy(self.frame) for label in ('l','r')})
        p.save(self.root/'A/BACKEND.json',backend)
        self.reg=dict(mapping={'x':'A'},registered_ns=time.perf_counter_ns(),execution_window_seconds=2400,
            consumer_window_seconds=600,task_sha256='t',run_nonce='n',script_pins=[],members=[dict(path=name,sha256=p.sha(self.root/name))
                for name in ('COMMON.json','A/REPORT.json','A/BACKEND.json')])
        p.save(self.root/'PREREGISTERED.json',self.reg)
        p.save(self.root/'PREREGISTERED_SEAL.json',dict(sha256=p.sha(self.root/'PREREGISTERED.json')))
        p.start(self.root,'x')
    def session(self):return p.load(self.root/'consumers/x/SESSION.json')
    def emit(self,indices=None):
        output=io.StringIO()
        with contextlib.redirect_stdout(output):p.emit(self.root,'x',indices)
        return json.loads(output.getvalue()),output.getvalue().encode('ascii')
    def test_stdout_matches_sealed_bytes_and_is_not_a_model_receipt(self):
        payload,raw=self.emit();event=self.session()['events'][0]
        saved=self.root/'consumers/x'/('x-event-1_PAYLOAD.json')
        self.assertEqual(raw,saved.read_bytes());self.assertEqual(hashlib.sha256(raw).hexdigest(),event['payload_sha256'])
        self.assertEqual(event['state'],'stdout_written_host_receipt_required')
        self.assertTrue(payload['provenance']['helper_stdout_is_not_model_consumption_proof'])
        self.assertEqual(payload['provenance']['extra_source_reads'],0)
        self.assertEqual([row['triangle'] for row in payload['frames'][0]['rows']],[0])
        self.assertNotIn('core_confirmation',payload['frames'][0])
    def test_initial_read_cannot_be_repeated_or_session_restarted(self):
        self.emit()
        with self.assertRaisesRegex(ValueError,'initial_read_state'):self.emit()
        with self.assertRaises(FileExistsError):p.start(self.root,'x')
        self.assertEqual(self.session()['initial_attempts'],1)
    def test_lookup_before_initial_read_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'initial_read_state'):self.emit([0])
        self.assertEqual(self.session()['lookup_attempts'],0)
    def test_two_optional_dual_source_lookups_and_hard_budget(self):
        self.emit();first,_=self.emit([3]);second,_=self.emit([4,5])
        self.assertEqual(len(first['frames']),2)
        self.assertTrue(all(f['rows'][0]['triangle']==3 and f['rows'][0]['in_core'] is False for f in first['frames']))
        self.assertEqual([r['triangle'] for r in second['frames'][1]['rows']],[4,5])
        with self.assertRaisesRegex(ValueError,'lookup_budget'):self.emit([0])
        self.assertEqual(self.session()['lookup_attempts'],2)
    def test_out_of_domain_lookup_spends_attempt_and_never_repairs_face(self):
        self.emit()
        with self.assertRaisesRegex(ValueError,'lookup_domain'):self.emit([999])
        session=self.session();self.assertEqual(session['lookup_attempts'],1)
        self.assertEqual(session['events'][-1]['requested_indices'],[999])
        self.assertEqual(session['events'][-1]['state'],'failed_or_unknown')
    def test_duplicate_boolean_and_oversize_indices_rejected_without_work(self):
        self.emit()
        for indices in ([1,1],[True],list(range(5)),[],[-1]):
            with self.subTest(indices=indices),self.assertRaisesRegex(ValueError,'lookup_indices'):self.emit(indices)
        self.assertEqual(self.session()['lookup_attempts'],0)
    def test_registration_or_static_input_tampering_is_rejected(self):
        (self.root/'A/REPORT.json').write_bytes(b'{}\n')
        with self.assertRaisesRegex(ValueError,'static_input_changed'):self.emit()
        self.assertEqual(self.session()['initial_attempts'],0)
    def test_expired_consumer_never_extends_original_window(self):
        session=self.session();session['deadline_ns']=time.perf_counter_ns()-1
        p.replace(self.root/'consumers/x/SESSION.json',session)
        with self.assertRaisesRegex(ValueError,'consumer_deadline'):self.emit()
        self.assertEqual(self.session()['initial_attempts'],0)
    def test_new_consumer_requires_full_window_inside_global_deadline(self):
        reg=p.load(self.root/'PREREGISTERED.json')
        reg['registered_ns']=time.perf_counter_ns()-1_900_000_000_000
        p.replace(self.root/'PREREGISTERED.json',reg)
        p.replace(self.root/'PREREGISTERED_SEAL.json',dict(sha256=p.sha(self.root/'PREREGISTERED.json')))
        with self.assertRaisesRegex(ValueError,'insufficient_global_window'):p.start(self.root,'x')
    def test_expiry_after_reservation_has_no_stdout_and_keeps_spent_attempt(self):
        session=self.session();before=session['deadline_ns']-100;after=session['deadline_ns']+1
        # frozen check, session gate, event start, gate after payload persistence.
        output=io.StringIO()
        with patch.object(p.time,'perf_counter_ns',side_effect=[before,before,before,after,after]),contextlib.redirect_stdout(output):
            with self.assertRaisesRegex(ValueError,'consumer_deadline'):p.emit(self.root,'x')
        self.assertEqual(output.getvalue(),'');self.assertEqual(self.session()['initial_attempts'],1)
        self.assertEqual(self.session()['events'][-1]['state'],'failed_or_unknown')
    def test_expiry_after_stdout_preserves_emitted_evidence_but_not_valid_completion(self):
        session=self.session();before=session['deadline_ns']-100;after=session['deadline_ns']+1;output=io.StringIO()
        with patch.object(p.time,'perf_counter_ns',side_effect=[before,before,before,before,before,after,after]),contextlib.redirect_stdout(output):
            with self.assertRaisesRegex(ValueError,'consumer_deadline'):p.emit(self.root,'x')
        self.assertIn('v21-delivered-facts-v1',output.getvalue())
        self.assertEqual(self.session()['events'][-1]['state'],'failed_or_unknown')
        self.assertEqual(self.session()['initial_attempts'],1)
    def test_failed_stdout_keeps_attempt_and_releases_transport_lock(self):
        class Broken(io.StringIO):
            def write(self,value):raise OSError('broken transport')
        with contextlib.redirect_stdout(Broken()),self.assertRaises(OSError):p.emit(self.root,'x')
        self.assertEqual(self.session()['initial_attempts'],1)
        self.assertEqual(self.session()['events'][-1]['state'],'failed_or_unknown')
        self.assertFalse((self.root/'consumers/x/ACTIVE').exists())
    def test_paused_request_before_lock_cannot_overwrite_newly_spent_read(self):
        original=Path.mkdir;injected=False
        def first_completes_before_second_lock(path,*args,**kwargs):
            nonlocal injected
            if path.name=='ACTIVE' and not injected:
                injected=True;self.emit()
            return original(path,*args,**kwargs)
        with patch.object(Path,'mkdir',new=first_completes_before_second_lock):
            with self.assertRaisesRegex(ValueError,'initial_read_state'):self.emit()
        session=self.session();self.assertEqual(session['initial_attempts'],1)
        self.assertEqual(len(session['events']),1)
        self.assertEqual(session['events'][0]['state'],'stdout_written_host_receipt_required')
    def test_successful_lookup_then_paused_failed_lookup_both_spend_budget(self):
        self.emit();original=Path.mkdir;injected=False
        def inner_finishes_before_outer_lock(path,*args,**kwargs):
            nonlocal injected
            if path.name=='ACTIVE' and not injected:
                injected=True;self.emit([3])
            return original(path,*args,**kwargs)
        with patch.object(Path,'mkdir',new=inner_finishes_before_outer_lock):
            with self.assertRaisesRegex(ValueError,'lookup_domain'):self.emit([999])
        session=self.session();self.assertEqual(session['lookup_attempts'],2)
        self.assertEqual(len(session['events']),3)
        self.assertEqual(session['events'][1]['requested_indices'],[3])
        self.assertEqual(session['events'][2]['requested_indices'],[999])
        with self.assertRaisesRegex(ValueError,'lookup_budget'):self.emit([4])

if __name__=='__main__':unittest.main()
