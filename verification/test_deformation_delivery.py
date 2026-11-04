"""Protocol failure injection is separate from real owned-source acceptance."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from human_eye_plugin import deformation_context as context
from human_eye_plugin import deformation_delivery as delivery
from verification.test_deformation_task_view import task_fixture


class Clock:
    def __init__(self):self.now=time.perf_counter_ns()
    def __call__(self):return self.now
    def advance(self,n):self.now+=n


class Snapshot(dict):
    def __call__(self):return dict(self)


class FakeQualifiedReader:
    """Authored finite reader, not a source-admission or performance claim."""
    supported_read_kinds=('facts','targeted','joint_supplement')
    def __init__(self,spec,frames,*,task_deadline_ns):
        self.task_deadline_ns=task_deadline_ns
        self.frames={f['label']:f for f in frames};self.calls=[];self.closed=False;self.close_calls=0
        self.read_fault=None;self.close_fault=None;self.read_hook=None;self.close_hook=None
        self.snapshot_costs=Snapshot(physical_inspect_requests=2,B2_rows_passes=0,
            source_validation_calls=2,owned_process_starts=2,owned_process_closes=0,
            logical_directory_reads=2,task_deadline_ns=task_deadline_ns)
        self.directory_receipts={label:dict(label=label,source_ref=copy.deepcopy(source['source_ref']),
            catalog_sha256=source['catalog_sha256'],anchor_id=source['anchor_id'],
            profile_sha256=source['profile_sha256'],core_half_extents_m=source['core_half_extents_m'][:],
            status='ok',fresh=True,task_deadline_ns=task_deadline_ns,logical_directory_reads=1,
            costs=dict(physical_inspect_requests=1,B2_rows_passes=0))
            for label,source in spec['sources'].items()}

    def read(self,request):
        self.calls.append(copy.deepcopy(request));self.snapshot_costs['physical_inspect_requests']+=1
        self.snapshot_costs['B2_rows_passes']+=1;self.snapshot_costs['source_validation_calls']+=1
        if self.read_hook:self.read_hook(request)
        if self.read_fault=='raise':raise OSError('injected lost receipt after read')
        label=request['label'];bundle=copy.deepcopy(self.frames[label])
        receipt={key:copy.deepcopy(request[key]) for key in ('request_id','run_nonce','condition_id','task_sha256','label','source_ref',
            'selection','kind','deadline_ns','task_deadline_ns')}
        receipt.update(status='ok',fresh=True,source_sha256=bundle['proof']['source_sha256'],
            costs=dict(physical_inspect_requests=1,B2_rows_passes=1))
        if self.read_fault=='unknown':receipt['status']='unknown'
        elif self.read_fault=='failed':receipt['status']='failed'
        elif self.read_fault=='wrong_run':receipt['run_nonce']='b'*32
        elif self.read_fault=='wrong_source':receipt['source_ref']['frame']['number']+=1
        elif self.read_fault=='wrong_task':receipt['task_sha256']='0'*64
        elif self.read_fault=='wrong_selection':receipt['selection']['core_half_extents_m']=[.25]*3
        elif self.read_fault=='wrong_subdeadline':receipt['deadline_ns']+=1
        elif self.read_fault=='wrong_taskdeadline':receipt['task_deadline_ns']+=1
        elif self.read_fault=='stale':receipt['fresh']=False
        if request['kind']=='targeted':receipt['targeted_triangle_indices']=copy.deepcopy(request['targeted_triangle_indices'])
        if self.read_fault=='wrong_targeted':receipt['targeted_triangle_indices']=[99]
        return dict(bundle=bundle,receipt=receipt)

    def verify_and_close(self):
        self.close_calls+=1
        self.closed=True;self.snapshot_costs['owned_process_closes']=self.snapshot_costs['owned_process_starts']
        if self.close_hook:self.close_hook()
        if self.close_fault:raise OSError('injected close/source verification failure')
        return dict(sources_unchanged=True,all_owned_closed=True,original_deadline_preserved=True)


class DeliveryProtocolTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.task,self.frames=task_fixture()
        self.clock=Clock();self.deadline=self.clock()+30_000_000_000
        self.reader=FakeQualifiedReader(self.task['spec'],self.frames,task_deadline_ns=self.deadline)

    def session(self,**changes):
        kwargs=dict(run_nonce=self.task['run_nonce'],condition_id=self.task['condition_id'],
            deadline_ns=self.deadline,store=self.root,reader=self.reader,
            prior_usage=dict(directories=2,facts=0,native_supplements=0),clock_ns=self.clock)
        kwargs.update(changes)
        return delivery.DeliverySession(self.task['spec'],**kwargs)

    def ledger(self,session):
        return json.loads((session.store_path/'LEDGER.json').read_bytes())

    def test_real_persisted_reference_is_resolvable_only_after_publication(self):
        session=self.session();published=session.request('request-one');reference=published['reference']
        self.assertTrue(published['published']);self.assertFalse(published['delivered']);self.assertFalse(published['model_received'])
        ledger=self.ledger(session)
        self.assertEqual(ledger['state'],'published')
        self.assertEqual(ledger['usage']['directories'],2)
        self.assertEqual(ledger['usage']['facts'],2)
        self.assertEqual(ledger['usage']['physical_inspect_requests'],4)
        self.assertEqual(ledger['usage']['B2_rows_passes'],2)
        self.assertEqual(len(self.reader.calls),2);self.assertTrue(self.reader.closed)
        resolved=session.resolve(reference,'');evidence=resolved['value']
        self.assertIsInstance(evidence,dict)
        self.assertIn('frames',evidence)
        delivered=session.deliver(reference,'delivery-one')
        self.assertTrue(delivered['delivered']);self.assertFalse(delivered['model_received'])
        self.assertEqual(self.ledger(session)['state'],'delivered')

    def test_duplicate_request_is_rejected_without_second_read_or_budget_reset(self):
        session=self.session();session.request('same-id')
        before=self.ledger(session)['usage'].copy()
        with self.assertRaisesRegex(delivery.DeliveryError,'duplicate_request'):
            session.request('same-id')
        self.assertEqual(len(self.reader.calls),2)
        self.assertEqual(self.ledger(session)['usage'],before)

    def test_new_request_after_success_cannot_redo_source_work(self):
        session=self.session();session.request('first')
        with self.assertRaisesRegex(delivery.DeliveryError,'terminal|session_state'):
            session.request('second')
        self.assertEqual(len(self.reader.calls),2)

    def test_reopening_same_task_with_new_nonce_does_not_reset_usage(self):
        session=self.session();session.request('first');before=self.ledger(session)['usage'].copy()
        with self.assertRaisesRegex(delivery.DeliveryError,'existing|run_binding|resume|already'):
            self.session(run_nonce='c'*32)
        self.assertEqual(self.ledger(session)['usage'],before)
        self.assertEqual(len(self.reader.calls),2)

    def test_non_hex_nonce_is_rejected_before_creating_a_session_slot(self):
        for nonce in ('not-a-run','g'*32,'a'*31):
            with self.subTest(nonce=nonce),self.assertRaisesRegex(delivery.DeliveryError,'^deformation_delivery_run_binding$'):
                self.session(run_nonce=nonce)
        self.assertEqual(list(self.root.iterdir()),[])

    def test_bad_directory_binding_retains_spent_directory_work_and_cleans_up(self):
        self.reader.directory_receipts['source_left']['core_half_extents_m']=[.1]*3
        with self.assertRaisesRegex(delivery.DeliveryError,'directory_binding'):
            self.session()
        ledger=json.loads((self.root/self.task['task_sha256']/'LEDGER.json').read_bytes())
        self.assertEqual(ledger['usage']['directories'],2);self.assertEqual(ledger['usage']['facts'],0)
        self.assertEqual(ledger['usage']['physical_inspect_requests'],2)
        self.assertEqual(ledger['state'],'failed');self.assertTrue(self.reader.closed)

    def test_wrong_directory_deadline_is_not_a_new_task_allowance(self):
        self.reader.directory_receipts['source_left']['task_deadline_ns']+=1
        with self.assertRaisesRegex(delivery.DeliveryError,'directory_binding'):
            self.session()
        ledger=json.loads((self.root/self.task['task_sha256']/'LEDGER.json').read_bytes())
        self.assertEqual(ledger['usage']['directories'],2);self.assertEqual(ledger['usage']['facts'],0)
        self.assertTrue(self.reader.closed)

    def test_constructor_persistence_failure_keeps_directory_consumption(self):
        original=delivery._persist_blob
        def fail_spec(path,blob):
            if Path(path).name=='SPEC.json':raise OSError('injected spec write failure')
            return original(path,blob)
        with patch.object(delivery,'_persist_blob',side_effect=fail_spec):
            with self.assertRaisesRegex(delivery.DeliveryError,'^deformation_delivery_initialization_failed$'):
                self.session()
        ledger=json.loads((self.root/self.task['task_sha256']/'LEDGER.json').read_bytes())
        self.assertEqual(ledger['usage']['directories'],2);self.assertEqual(ledger['usage']['facts'],0)
        self.assertEqual(ledger['state'],'failed');self.assertTrue(self.reader.closed)

    def test_existing_consumption_leaves_insufficient_fact_budget(self):
        session=self.session(prior_usage=dict(directories=2,facts=3,native_supplements=0))
        with self.assertRaisesRegex(delivery.DeliveryError,'^deformation_delivery_budget_exhausted$'):
            session.request('cannot-afford-two')
        self.assertEqual(self.ledger(session)['usage']['facts'],3)
        self.assertEqual(self.reader.calls,[])

    def test_joint_supplement_mapping_is_distinct_from_per_source_facts(self):
        session=self.session();published=session.request('mock-joint',kind='joint_supplement')
        usage=self.ledger(session)['usage']
        self.assertEqual(usage['facts'],0);self.assertEqual(usage['native_supplements'],1)
        self.assertEqual(usage['logical_source_read_attempts'],2)
        self.assertEqual(usage['physical_inspect_requests'],4)
        self.assertTrue(published['published'])
        # This exercises only the explicit protocol double; the production
        # reader declares joint_supplement unsupported and makes no such claim.

    def test_unsupported_read_kind_is_not_disguised_as_free_or_native_work(self):
        self.reader.supported_read_kinds=('facts',)
        session=self.session()
        with self.assertRaisesRegex(delivery.DeliveryError,'^deformation_delivery_unsupported_read_kind$'):
            session.request('no-native-domain',kind='joint_supplement')
        usage=self.ledger(session)['usage']
        self.assertEqual((usage['facts'],usage['native_supplements']),(0,0))
        self.assertEqual(self.reader.calls,[])

    def test_targeted_receipt_binds_the_actual_requested_face_indices(self):
        session=self.session();ids={label:[0] for label in self.task['spec']['sources']}
        published=session.request('targeted',kind='targeted',explicit_candidates_by_label=ids)
        receipts=json.loads((session.store_path/'READ_RECEIPTS.json').read_bytes())
        self.assertEqual(len(receipts),2)
        for row in receipts:self.assertEqual(row['targeted_triangle_indices'],[0])
        self.assertEqual(self.ledger(session)['usage']['facts'],2)
        self.assertTrue(published['published'])

    def test_wrong_targeted_receipt_is_rejected_after_only_the_actual_first_read(self):
        self.reader.read_fault='wrong_targeted';session=self.session()
        with self.assertRaisesRegex(delivery.DeliveryError,'^deformation_delivery_targeted_receipt$'):
            session.request('wrong-targeted',kind='targeted',explicit_candidates_by_label={label:[0] for label in self.task['spec']['sources']})
        self.assertEqual(len(self.reader.calls),1);self.assertEqual(self.ledger(session)['usage']['facts'],1)

    def test_candidate_budget_failure_keeps_both_already_completed_source_reads(self):
        session=self.session()
        with self.assertRaisesRegex(delivery.DeliveryError,'^deformation_delivery_execution_failed$'):
            session.request('no-candidate-slot',max_candidates=0)
        ledger=self.ledger(session)
        self.assertIn('deformation_task_view_candidate_budget',ledger['error']['message'])
        self.assertEqual(ledger['usage']['facts'],2);self.assertEqual(len(self.reader.calls),2)
        self.assertFalse(ledger['published'])

    def test_cancel_before_dispatch_prevents_reads_and_later_requests(self):
        session=self.session();session.cancel('operator cancelled')
        with self.assertRaisesRegex(delivery.DeliveryError,'cancelled|terminal|session_state'):
            session.request('after-cancel')
        self.assertEqual(self.reader.calls,[])
        self.assertEqual(self.ledger(session)['state'],'cancelled')

    def test_cancel_after_first_actual_read_retains_spent_and_stops_second(self):
        session=self.session();self.reader.read_hook=lambda request:session.cancel('during-read')
        with self.assertRaisesRegex(delivery.DeliveryError,'cancelled|terminal|session_state'):
            session.request('cancel-in-read')
        self.assertEqual(len(self.reader.calls),1)
        self.assertEqual(self.ledger(session)['usage']['facts'],1)
        self.assertEqual(self.ledger(session)['state'],'cancelled')

    def test_missing_or_failed_receipt_never_refunds_or_automatically_retries(self):
        for fault in ('raise','unknown','failed'):
            with self.subTest(fault=fault):
                with tempfile.TemporaryDirectory() as tmp:
                    self.reader=FakeQualifiedReader(self.task['spec'],self.frames,task_deadline_ns=self.deadline);self.reader.read_fault=fault
                    session=self.session(store=Path(tmp))
                    with self.assertRaisesRegex(delivery.DeliveryError,'^deformation_delivery_receipt_unknown$'):
                        session.request('failed-read')
                    ledger=self.ledger(session)
                    self.assertEqual(ledger['usage']['facts'],1)
                    self.assertEqual(len(self.reader.calls),1)
                    with self.assertRaisesRegex(delivery.DeliveryError,'^deformation_delivery_terminal_no_retry$'):
                        session.request('another-id')
                    self.assertEqual(len(self.reader.calls),1)

    def test_wrong_receipt_task_run_or_source_rejects_after_charging(self):
        for fault in ('wrong_task','wrong_run','wrong_source','wrong_selection','wrong_subdeadline','wrong_taskdeadline'):
            with self.subTest(fault=fault):
                with tempfile.TemporaryDirectory() as tmp:
                    self.reader=FakeQualifiedReader(self.task['spec'],self.frames,task_deadline_ns=self.deadline);self.reader.read_fault=fault
                    session=self.session(store=Path(tmp))
                    with self.assertRaisesRegex(delivery.DeliveryError,'^deformation_delivery_receipt_binding$'):
                        session.request('wrong-receipt')
                    self.assertEqual(self.ledger(session)['usage']['facts'],1)
                    self.assertEqual(len(self.reader.calls),1)

    def test_original_deadline_expires_before_any_read(self):
        session=self.session();self.clock.now=self.deadline
        with self.assertRaisesRegex(delivery.DeliveryError,'deadline'):
            session.request('expired')
        self.assertEqual(self.reader.calls,[])

    def test_expiry_after_real_first_read_retains_fact_and_blocks_second(self):
        session=self.session();self.reader.read_hook=lambda request:setattr(self.clock,'now',self.deadline)
        with self.assertRaisesRegex(delivery.DeliveryError,'deadline'):
            session.request('expires-during-read')
        self.assertEqual(len(self.reader.calls),1)
        self.assertEqual(self.ledger(session)['usage']['facts'],1)

    def test_original_task_time_cannot_hide_an_expired_child_read_deadline(self):
        self.deadline=self.clock()+60_000_000_000
        self.reader=FakeQualifiedReader(self.task['spec'],self.frames,task_deadline_ns=self.deadline)
        session=self.session()
        self.reader.read_hook=lambda request:setattr(self.clock,'now',request['deadline_ns'])
        with self.assertRaisesRegex(delivery.DeliveryError,'^deformation_delivery_read_deadline$'):
            session.request('child-expired')
        self.assertLess(self.clock(),self.deadline)
        self.assertEqual(self.ledger(session)['usage']['facts'],1);self.assertEqual(len(self.reader.calls),1)

    def test_close_failure_preserves_consumed_work_and_cannot_publish(self):
        session=self.session();self.reader.close_fault=True
        with self.assertRaisesRegex(delivery.DeliveryError,'execution_failed'):
            session.request('close-fails')
        ledger=self.ledger(session)
        self.assertEqual(ledger['usage']['facts'],2)
        self.assertNotEqual(ledger['state'],'published')
        self.assertFalse(ledger.get('published',False))
        self.assertIn('injected close/source verification failure',ledger['error']['message'])
        self.assertEqual(self.reader.close_calls,1,'A failed close receipt must not silently retry source verification')

    def test_expiry_at_close_does_not_publish_previously_constructed_view(self):
        session=self.session();self.reader.close_hook=lambda:setattr(self.clock,'now',self.deadline)
        with self.assertRaisesRegex(delivery.DeliveryError,'deadline'):
            session.request('expires-at-close')
        self.assertEqual(self.ledger(session)['usage']['facts'],2)
        self.assertNotEqual(self.ledger(session)['state'],'published')

    def test_serialization_and_persistence_failures_are_terminal_without_refund(self):
        for fault in ('serialize','persist'):
            with self.subTest(fault=fault):
                with tempfile.TemporaryDirectory() as tmp:
                    self.reader=FakeQualifiedReader(self.task['spec'],self.frames,task_deadline_ns=self.deadline)
                    session=self.session(store=Path(tmp))
                    target='human_eye_plugin.deformation_delivery._persist_blob'
                    original=delivery._persist_blob
                    def fail_evidence(path,blob):
                        if Path(path).name!='LEDGER.json':raise OSError('injected persistence failure')
                        return original(path,blob)
                    if fault=='persist':
                        with patch(target,side_effect=fail_evidence):
                            with self.assertRaisesRegex(delivery.DeliveryError,'^deformation_delivery_execution_failed$'):
                                session.request('cannot-persist')
                    else:
                        # Ordinary bound input is valid; the producer return alone
                        # is corrupted, so source reads have already been consumed.
                        actual=delivery.producer.produce
                        def bad_producer(*args,**kwargs):
                            view,audit=actual(*args,**kwargs);audit['evidence_sidecar']['invalid']=object();return view,audit
                        with patch.object(delivery.producer,'produce',side_effect=bad_producer):
                            with self.assertRaisesRegex(delivery.DeliveryError,'^deformation_delivery_execution_failed$'):
                                session.request('cannot-serialize')
                    self.assertEqual(self.ledger(session)['usage']['facts'],2)
                    self.assertNotEqual(self.ledger(session)['state'],'published')
                    self.assertEqual(self.ledger(session)['error']['reason'],'OSError' if fault=='persist' else 'TypeError')

    def test_expiry_during_evidence_persistence_cannot_publish(self):
        session=self.session();actual=delivery._persist_blob
        def expire_after_evidence(path,blob):
            actual(path,blob)
            if Path(path).name=='EVIDENCE.json':self.clock.now=self.deadline
        with patch.object(delivery,'_persist_blob',side_effect=expire_after_evidence):
            with self.assertRaisesRegex(delivery.DeliveryError,'original_deadline'):
                session.request('expires-while-persisting')
        self.assertEqual(self.ledger(session)['usage']['facts'],2)
        self.assertEqual(self.ledger(session)['state'],'deadline_exceeded')
        self.assertFalse(self.ledger(session)['published'])

    def test_producer_cannot_publish_a_different_self_consistent_task(self):
        for target in ('view','evidence'):
            with self.subTest(target=target):
                with tempfile.TemporaryDirectory() as tmp:
                    self.reader=FakeQualifiedReader(self.task['spec'],self.frames,task_deadline_ns=self.deadline)
                    session=self.session(store=Path(tmp));actual=delivery.producer.produce
                    def rebind(*args,**kwargs):
                        view,audit=actual(*args,**kwargs)
                        if target=='view':view['task_binding']['run_nonce']='f'*32
                        else:audit['evidence_sidecar']['request_task']['run_nonce']='f'*32
                        evidence=context.publication_bytes(audit['evidence_sidecar'])
                        view['evidence_ref']['sha256']=hashlib.sha256(evidence).hexdigest()
                        view['evidence_ref']['bytes']=len(evidence)
                        audit['evidence_sidecar_sha256']=view['evidence_ref']['sha256']
                        audit['evidence_sidecar_bytes']=len(evidence)
                        payload=context.publication_bytes(view)
                        audit['published_publication_sha256']=hashlib.sha256(payload).hexdigest()
                        audit['published_publication_bytes']=len(payload)
                        return view,audit
                    with patch.object(delivery.producer,'produce',side_effect=rebind):
                        with self.assertRaisesRegex(delivery.DeliveryError,'produced.*binding|producer.*binding|task_binding'):
                            session.request('wrong-produced-task')
                    self.assertEqual(self.ledger(session)['usage']['facts'],2)
                    self.assertFalse(self.ledger(session)['published'])

    def test_unpublished_or_modified_evidence_is_not_resolvable(self):
        session=self.session()
        fake=dict(schema='deformation-evidence-reference-v1',run_nonce=self.task['run_nonce'],
            condition_id=self.task['condition_id'],task_sha256=self.task['task_sha256'],
            evidence_sha256='0'*64,view_sha256='0'*64,evidence_version=2)
        with self.assertRaisesRegex(delivery.DeliveryError,'unpublished_reference'):
            session.resolve(fake,'')
        reference=session.request('publish-then-tamper')['reference']
        (session.store_path/'EVIDENCE.json').write_bytes(b'{}\n')
        with self.assertRaisesRegex(delivery.DeliveryError,'artifact_digest'):
            session.resolve(reference,'')

    def test_resolver_rejects_wrong_run_wrong_hash_or_arbitrary_path(self):
        session=self.session();ref=session.request('published-once')['reference']
        self.assertIn('frames',session.resolve(ref,'')['value'])
        for edits in (dict(run_nonce='d'*32),dict(task_sha256='0'*64),dict(evidence_sha256='0'*64)):
            with self.subTest(edits=edits),self.assertRaisesRegex(delivery.DeliveryError,'reference'):
                session.resolve(dict(ref,**edits),'')
        for pointer in ('../../private.json','D:/hefe/secret','/../../secret'):
            with self.subTest(pointer=pointer),self.assertRaisesRegex(delivery.DeliveryError,'pointer|reference'):
                session.resolve(ref,pointer)

    def test_duplicate_delivery_id_is_not_model_consumption(self):
        session=self.session();ref=session.request('one')['reference']
        receipt=session.deliver(ref,'delivery-one')
        self.assertFalse(receipt['model_received'])
        with self.assertRaisesRegex(delivery.DeliveryError,'duplicate_delivery|delivered|terminal'):
            session.deliver(ref,'delivery-one')

    def test_delivery_persist_failure_or_expiry_cannot_claim_first_delivery_succeeded(self):
        for fault in ('failed','expired'):
            with self.subTest(fault=fault):
                with tempfile.TemporaryDirectory() as tmp:
                    self.reader=FakeQualifiedReader(self.task['spec'],self.frames,task_deadline_ns=self.deadline)
                    session=self.session(store=Path(tmp));ref=session.request('publish')['reference'];actual=delivery._persist_blob
                    tripped=[False]
                    def fail_delivered(path,blob):
                        state=json.loads(blob) if Path(path).name=='LEDGER.json' else {}
                        if state.get('state')=='delivered' and not tripped[0]:
                            tripped[0]=True
                            if fault=='failed':raise OSError('injected delivery ledger failure')
                            actual(path,blob);self.clock.now=self.deadline;return
                        return actual(path,blob)
                    with patch.object(delivery,'_persist_blob',side_effect=fail_delivered):
                        with self.assertRaisesRegex(delivery.DeliveryError,'delivery|original_deadline'):
                            session.deliver(ref,'failed-delivery')
                    ledger=self.ledger(session)
                    self.assertFalse(ledger['delivered']);self.assertFalse(ledger['model_received'])
                    self.assertEqual(len(self.reader.calls),2)

    def test_request_reply_copy_expiry_cannot_return_a_completed_publication(self):
        session=self.session();actual=copy.deepcopy;tripped=[]
        def expire_returned_view(value,*args,**kwargs):
            result=actual(value,*args,**kwargs)
            if (type(value) is dict and value.get('schema')=='surface-deformation-task-witness-view-v2'
                    and session.ledger['state']=='published'):
                tripped.append(True);self.clock.now=self.deadline
            return result
        with patch.object(delivery.copy,'deepcopy',side_effect=expire_returned_view):
            with self.assertRaisesRegex(delivery.DeliveryError,'^deformation_delivery_original_deadline$'):
                session.request('expires-constructing-reply')
        self.assertEqual(len(tripped),1,'Expire specifically in the final reply copy, after artifact publication')
        ledger=self.ledger(session)
        self.assertEqual(ledger['state'],'deadline_exceeded')
        self.assertFalse(ledger['published']);self.assertFalse(session._publication_completed)
        self.assertFalse(ledger['model_received']);self.assertEqual(ledger['usage']['facts'],2)
        self.assertEqual(len(self.reader.calls),2)

    def test_resolve_reply_copy_expiry_does_not_return_a_published_value(self):
        session=self.session();reference=session.request('publish-before-resolution')['reference']
        actual=copy.deepcopy;tripped=[]
        def expire_returned_evidence(value,*args,**kwargs):
            result=actual(value,*args,**kwargs)
            if type(value) is dict and value.get('schema')=='surface-deformation-task-witness-evidence-v2':
                tripped.append(True);self.clock.now=self.deadline
            return result
        with patch.object(delivery.copy,'deepcopy',side_effect=expire_returned_evidence):
            with self.assertRaisesRegex(delivery.DeliveryError,'^deformation_delivery_evidence_delivery_unknown$'):
                session.resolve(reference,'')
        self.assertEqual(len(tripped),1,'Expire in the returned evidence copy, after persisted receipt validation')
        ledger=self.ledger(session)
        self.assertEqual(ledger['state'],'evidence_delivery_unknown')
        self.assertFalse(ledger['delivered']);self.assertFalse(ledger['model_received'])
        self.assertEqual(ledger['usage']['facts'],2);self.assertEqual(len(self.reader.calls),2)

    def test_deliver_reply_copy_expiry_does_not_claim_first_delivery(self):
        session=self.session();reference=session.request('publish-before-delivery')['reference']
        actual=copy.deepcopy;tripped=[]
        def expire_returned_reference(value,*args,**kwargs):
            result=actual(value,*args,**kwargs)
            if type(value) is dict and value==reference and session.ledger['state']=='delivered':
                tripped.append(True);self.clock.now=self.deadline
            return result
        with patch.object(delivery.copy,'deepcopy',side_effect=expire_returned_reference):
            with self.assertRaisesRegex(delivery.DeliveryError,'^deformation_delivery_delivery_unknown$'):
                session.deliver(reference,'expires-constructing-delivery-reply')
        self.assertEqual(len(tripped),1,'Expire after the delivery-ledger commit but before reply return')
        ledger=self.ledger(session)
        self.assertEqual(ledger['state'],'delivery_unknown')
        self.assertFalse(ledger['delivered']);self.assertFalse(ledger['model_received'])
        self.assertEqual(ledger['usage']['facts'],2);self.assertEqual(len(self.reader.calls),2)

    def test_missing_audit_or_read_receipts_blocks_both_resolution_and_delivery(self):
        for name in ('AUDIT.json','READ_RECEIPTS.json'):
            for operation in ('resolve','deliver'):
                with self.subTest(artifact=name,operation=operation),tempfile.TemporaryDirectory() as tmp:
                    self.reader=FakeQualifiedReader(self.task['spec'],self.frames,task_deadline_ns=self.deadline)
                    session=self.session(store=Path(tmp));reference=session.request('publish-complete-artifacts')['reference']
                    (session.store_path/name).unlink()
                    with self.assertRaisesRegex(delivery.DeliveryError,'^deformation_delivery_artifact_unavailable$'):
                        if operation=='resolve':session.resolve(reference,'')
                        else:session.deliver(reference,'must-not-deliver-missing-evidence')
                    self.assertFalse(self.ledger(session)['delivered'])
                    self.assertEqual(len(self.reader.calls),2)

    def test_tampered_audit_or_read_receipts_blocks_both_resolution_and_delivery(self):
        for name in ('AUDIT.json','READ_RECEIPTS.json'):
            for operation in ('resolve','deliver'):
                with self.subTest(artifact=name,operation=operation),tempfile.TemporaryDirectory() as tmp:
                    self.reader=FakeQualifiedReader(self.task['spec'],self.frames,task_deadline_ns=self.deadline)
                    session=self.session(store=Path(tmp));reference=session.request('publish-complete-artifacts')['reference']
                    (session.store_path/name).write_bytes(b'{}\n')
                    with self.assertRaisesRegex(delivery.DeliveryError,'^deformation_delivery_artifact_digest$'):
                        if operation=='resolve':session.resolve(reference,'')
                        else:session.deliver(reference,'must-not-deliver-tampered-evidence')
                    self.assertFalse(self.ledger(session)['delivered'])
                    self.assertEqual(len(self.reader.calls),2)


if __name__=='__main__':unittest.main()
