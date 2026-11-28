"""Reader telemetry faults are independent of source/geometry correctness.

All execution here is the public protocol's authored finite reader. No Blender,
asset, provider or oracle is read. The old-commit reproduction is explicit.
"""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

from human_eye_plugin import deformation_delivery as delivery
from verification.test_deformation_delivery import Clock,Snapshot,FakeQualifiedReader
from verification.test_deformation_task_view import task_fixture
from verification.test_deformation_reader import authored_reader


BASELINE='78f1faaab1c29293afded62fe0e317ac9d1650fc'
PRIMARY=('physical_inspect_requests','B2_rows_passes')


class ControlledSnapshot(Snapshot):
    """Change only the telemetry channel; the fake read still executes once."""
    def __init__(self,value,reader):
        super().__init__(value);self.reader=reader;self.fault=None;self.attempts=0

    def __call__(self):
        self.attempts+=1
        fault=self.fault(self) if callable(self.fault) else self.fault
        if isinstance(fault,BaseException):raise fault
        if fault=='raise':raise OSError('read succeeded, cost telemetry unavailable')
        if fault is not None:return fault
        return dict(self)


def baseline_reproducer(output):
    """Actually execute the exact 78f1faa module, even after HEAD is fixed."""
    root=Path(__file__).resolve().parents[1]
    raw=subprocess.check_output(['git','show',BASELINE+':human_eye_plugin/deformation_delivery.py'],cwd=root)
    module=types.ModuleType('human_eye_plugin._cost_snapshot_baseline')
    module.__package__='human_eye_plugin'
    exec(compile(raw,'git:'+BASELINE+':deformation_delivery.py','exec'),module.__dict__)
    task,frames=task_fixture();clock=Clock();deadline=clock()+30_000_000_000
    reader=FakeQualifiedReader(task['spec'],frames,task_deadline_ns=deadline)
    class FaultSnapshot(Snapshot):
        def __call__(self):
            if reader.calls:raise OSError('read succeeded, cost telemetry unavailable')
            return dict(self)
    reader.snapshot_costs=FaultSnapshot(reader.snapshot_costs)
    with tempfile.TemporaryDirectory() as folder:
        session=module.DeliverySession(task['spec'],run_nonce=task['run_nonce'],condition_id=task['condition_id'],
            deadline_ns=deadline,store=Path(folder),reader=reader,
            prior_usage=dict(directories=2,facts=0,native_supplements=0),clock_ns=clock)
        reply=session.request('exact-regression')
        ledger=json.loads((session.store_path/'LEDGER.json').read_bytes())
        result=dict(schema='cost-snapshot-baseline-reproduction-v1',baseline_commit=BASELINE,
            executed_source_sha256=hashlib.sha256(raw).hexdigest(),mode='authored_protocol_reader_no_real_source',
            actual_reader_counters=dict(reader.snapshot_costs),actual_reader_calls=len(reader.calls),
            actual_close_calls=reader.close_calls,published=reply['status']=='published',
            returned_usage=reply['usage'],returned_cost_error=reply.get('cost_snapshot_error'),
            persisted_cost_error=ledger.get('cost_snapshot_error'),
            defect_reproduced=(reply['usage']['physical_inspect_requests']==2
                and reply['usage']['B2_rows_passes']==0
                and reader.snapshot_costs['physical_inspect_requests']==4
                and reader.snapshot_costs['B2_rows_passes']==2),
            physical_asset_reads=0,provider_calls=0)
    if not result['defect_reproduced']:raise AssertionError(result)
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
    return result


class CostSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.task,self.frames=task_fixture()
        self.clock=Clock();self.deadline=self.clock()+30_000_000_000
        self.reset_reader()
        self.session_number=0

    def reset_reader(self):
        self.reader=FakeQualifiedReader(self.task['spec'],self.frames,task_deadline_ns=self.deadline)
        self.telemetry=ControlledSnapshot(self.reader.snapshot_costs,self.reader)
        self.reader.snapshot_costs=self.telemetry

    def session(self,**changes):
        self.session_number+=1
        values=dict(run_nonce=self.task['run_nonce'],condition_id=self.task['condition_id'],
            deadline_ns=self.deadline,store=self.root/str(self.session_number),reader=self.reader,
            prior_usage=dict(directories=2,facts=0,native_supplements=0),clock_ns=self.clock)
        values.update(changes)
        return delivery.DeliverySession(self.task['spec'],**values)

    def ledger(self,session):return json.loads((session.store_path/'LEDGER.json').read_bytes())

    def assert_integrity(self,value,state,*,physical=None,passes=None):
        info=value['cost_integrity'];self.assertEqual(info['state'],state)
        self.assertIsInstance(info['schema'],str)
        self.assertGreater(info['snapshot_sequence'],0)
        self.assertEqual(info['sampled_at_ns'],self.clock())
        self.assertEqual(set(info['counter_fields']),set(info['current']))
        self.assertEqual(set(info['unknown_fields']),{key for key,count in info['current'].items() if count is None})
        for key,expected in zip(PRIMARY,(physical,passes)):
            self.assertEqual(value['usage'][key],expected)
            self.assertEqual(info['current'][key],expected)
        for field in ('event_sequence_through','logical_source_read_attempts_through','close_attempted','close_completed'):
            self.assertIn(field,info)
        for key,known in info['last_known'].items():
            self.assertIs(type(known['value']),int,key)
            self.assertGreaterEqual(known['value'],0,key)
            self.assertLessEqual(known['snapshot_sequence'],info['snapshot_sequence'])
            for field in ('sampled_at_ns','event_sequence_through','logical_source_read_attempts_through','close_attempted','close_completed'):
                self.assertIn(field,known,key)
        self.assertEqual(value['usage']['directories'],2)
        self.assertEqual(value['usage']['native_supplements'],0)
        return info

    def assert_persisted_receipt(self,session,receipt,state,*,physical=None,passes=None):
        ledger=self.ledger(session)
        self.assertEqual(receipt['usage'],ledger['usage'])
        self.assertEqual(receipt['cost_integrity'],ledger['cost_integrity'])
        self.assertEqual(session.ledger['cost_integrity'],ledger['cost_integrity'])
        info=self.assert_integrity(receipt,state,physical=physical,passes=passes)
        for key,value in info['current'].items():
            self.assertEqual(ledger['reader_costs'].get(key),value,key)
        return info

    def assert_read_once(self,session,*,reads=2,published=True):
        self.assertEqual(len(self.reader.calls),reads)
        self.assertEqual(self.reader.close_calls,1)
        self.assertTrue(self.reader.closed)
        self.assertEqual(session.ledger['usage']['facts'],reads)
        self.assertEqual(session.ledger['usage'].get('logical_source_read_attempts',0),reads)
        self.assertEqual(session.ledger['published'],published)
        self.assertFalse(session.ledger['model_received'])
        self.assertEqual(dict(self.telemetry)['physical_inspect_requests'],2+reads)
        self.assertEqual(dict(self.telemetry)['B2_rows_passes'],reads)

    def test_exact_fault_snapshot_reproduces_missing_telemetry_not_false_current(self):
        reader=self.reader;initial_sample_at=self.clock()
        reader.read_hook=lambda request:self.clock.advance(1_000_000)
        class FaultSnapshot(Snapshot):
            def __call__(self):
                if reader.calls:raise OSError('read succeeded, cost telemetry unavailable')
                return dict(self)
        self.telemetry=FaultSnapshot(self.telemetry);self.reader.snapshot_costs=self.telemetry
        session=self.session();receipt=session.request('exact-regression')
        info=self.assert_persisted_receipt(session,receipt,'unknown')
        self.assertEqual(receipt['status'],'published')
        self.assertEqual(info['last_known']['physical_inspect_requests']['value'],2)
        self.assertEqual(info['last_known']['B2_rows_passes']['value'],0)
        self.assertEqual(info['last_known']['physical_inspect_requests']['logical_source_read_attempts_through'],0)
        self.assertEqual(info['last_known']['physical_inspect_requests']['sampled_at_ns'],initial_sample_at)
        self.assertEqual(info['sampled_at_ns'],initial_sample_at+2_000_000)
        self.assertTrue(info['history']);self.assertEqual(info['issues'],{'_snapshot':'OSError'})
        self.assertTrue(all(value is None for value in info['current'].values()))
        self.assert_read_once(session)

    def test_constructor_missing_snapshot_preserves_verified_directories_and_can_recover(self):
        self.telemetry.fault='raise';session=self.session()
        initial=self.ledger(session)
        self.assert_integrity(initial,'unknown')
        self.assertEqual(initial['usage']['facts'],0)
        self.assertEqual(initial['cost_integrity']['last_known'],{})
        history=copy.deepcopy(initial['cost_integrity']['history']);self.assertTrue(history)
        self.assertEqual(len(self.reader.calls),0);self.assertEqual(self.reader.close_calls,0)
        self.telemetry.fault=None
        receipt=session.request('complete-cumulative-recovery')
        info=self.assert_persisted_receipt(session,receipt,'complete',physical=4,passes=2)
        self.assertEqual(info['history'][:len(history)],history)
        self.assert_read_once(session)

    def test_valid_directory_counter_disagreement_still_rejects_initialization(self):
        self.telemetry['logical_directory_reads']=3
        with self.assertRaisesRegex(delivery.DeliveryError,'^deformation_delivery_prior_directory_costs$'):
            self.session()
        self.assertEqual(len(self.reader.calls),0);self.assertEqual(self.reader.close_calls,1)

    def test_healthy_snapshots_are_complete_and_have_no_gap_history(self):
        session=self.session();receipt=session.request('healthy')
        info=self.assert_persisted_receipt(session,receipt,'complete',physical=4,passes=2)
        self.assertEqual(info['history'],[])
        self.assertEqual(info['unknown_fields'],[])
        self.assertEqual(info['issues'],{})
        self.assertTrue(info['close_attempted']);self.assertTrue(info['close_completed'])
        self.assert_read_once(session)

    def test_first_source_missing_snapshot_recovers_from_second_cumulative_snapshot(self):
        session=self.session()
        self.telemetry.fault=lambda snap:'raise' if len(self.reader.calls)==1 else None
        receipt=session.request('one-gap')
        info=self.assert_persisted_receipt(session,receipt,'complete',physical=4,passes=2)
        self.assertTrue(info['history'])
        self.assertTrue(any(gap['logical_source_read_attempts_through']==1 for gap in info['history']))
        self.assert_read_once(session)

    def test_two_source_missing_snapshots_never_reuse_baseline_counts(self):
        session=self.session();self.telemetry.fault=lambda snap:'raise' if self.reader.calls else None
        receipt=session.request('two-gaps')
        info=self.assert_persisted_receipt(session,receipt,'unknown')
        self.assertEqual(info['logical_source_read_attempts_through'],2)
        self.assert_read_once(session)

    def test_close_snapshot_missing_does_not_change_successful_close_or_publication(self):
        session=self.session();self.telemetry.fault=lambda snap:'raise' if self.reader.closed else None
        receipt=session.request('close-cost-gap')
        info=self.assert_persisted_receipt(session,receipt,'unknown')
        self.assertEqual(info['last_known']['physical_inspect_requests']['value'],4)
        self.assertEqual(info['last_known']['B2_rows_passes']['value'],2)
        self.assertFalse(info['last_known']['physical_inspect_requests']['close_completed'])
        self.assertTrue(info['close_completed'])
        self.assertTrue(session.ledger['close_receipt']['sources_unchanged'])
        self.assert_read_once(session)

    def test_final_publication_snapshot_missing_is_in_returned_receipt_and_ledger(self):
        session=self.session();persist=delivery._persist_blob
        def fault_after_marker(path,blob):
            result=persist(path,blob)
            if Path(path).name=='PUBLISHED.json':self.telemetry.fault='raise'
            return result
        with patch.object(delivery,'_persist_blob',side_effect=fault_after_marker):
            receipt=session.request('final-cost-gap')
        info=self.assert_persisted_receipt(session,receipt,'unknown')
        self.assertEqual(info['last_known']['physical_inspect_requests']['value'],4)
        self.assertTrue(info['last_known']['physical_inspect_requests']['close_completed'])
        self.assertTrue((session.store_path/'PUBLISHED.json').exists())
        self.assert_read_once(session)

    def test_missing_required_counter_reports_partial_and_valid_peer_stays_current(self):
        for missing in PRIMARY:
            with self.subTest(missing=missing):
                self.reset_reader();session=self.session()
                def omit(snap):
                    current=dict(snap);current.pop(missing);return current
                self.telemetry.fault=omit
                receipt=session.request('missing-'+missing)
                expected=dict(physical=None if missing==PRIMARY[0] else 4,passes=None if missing==PRIMARY[1] else 2)
                info=self.assert_persisted_receipt(session,receipt,'partial',**expected)
                self.assertIn(missing,info['unknown_fields'])
                self.assertEqual(info['issues'][missing],'missing')
                self.assert_read_once(session)

    def test_invalid_counter_values_never_become_measured_current(self):
        for invalid in (None,True,False,-1,1.25,'4',[],{}):
            with self.subTest(invalid=invalid):
                self.reset_reader();session=self.session()
                self.telemetry.fault=lambda snap:dict(snap,physical_inspect_requests=invalid)
                receipt=session.request('invalid-count')
                info=self.assert_persisted_receipt(session,receipt,'partial',passes=2)
                self.assertEqual(info['issues'][PRIMARY[0]],'invalid_counter')
                self.assertEqual(info['last_known'][PRIMARY[0]]['value'],2)
                self.assert_read_once(session)

    def test_missing_both_primary_counts_is_not_complete_even_if_other_counters_known(self):
        session=self.session()
        def omit(snap):return {key:value for key,value in snap.items() if key not in PRIMARY}
        self.telemetry.fault=omit;receipt=session.request('both-primary-missing')
        info=self.assert_persisted_receipt(session,receipt,'partial')
        self.assertTrue(set(PRIMARY)<=set(info['unknown_fields']))
        self.assert_read_once(session)

    def test_non_mapping_snapshot_is_unknown_instead_of_failing_geometry_publication(self):
        for invalid in ('bad',[1],7):
            with self.subTest(invalid=invalid):
                self.reset_reader();session=self.session();self.telemetry.fault=invalid
                receipt=session.request('invalid-snapshot')
                info=self.assert_persisted_receipt(session,receipt,'unknown')
                self.assertEqual(info['issues']['_snapshot'],'ValueError')
                self.assert_read_once(session)

    def test_seen_optional_counter_omission_cannot_silently_revert_to_complete(self):
        session=self.session()
        def omit(snap):
            current=dict(snap);current.pop('source_validation_calls');return current
        self.telemetry.fault=omit;receipt=session.request('missing-optional')
        info=self.assert_persisted_receipt(session,receipt,'partial',physical=4,passes=2)
        self.assertIn('source_validation_calls',info['unknown_fields'])
        self.assertIsNone(info['current']['source_validation_calls'])
        self.assertEqual(info['issues']['source_validation_calls'],'missing')
        self.assert_read_once(session)

    def test_first_snapshot_invalid_optional_counter_is_tracked(self):
        for invalid in (None,-1,True):
            with self.subTest(invalid=invalid):
                self.reset_reader()
                self.telemetry.fault=lambda snap:dict(snap,source_validation_calls=invalid)
                session=self.session();initial=self.ledger(session)
                info=self.assert_integrity(initial,'partial',physical=2,passes=0)
                self.assertIn('source_validation_calls',info['unknown_fields'])
                self.assertEqual(info['issues']['source_validation_calls'],'invalid_counter')
                receipt=session.request('initial-invalid-optional')
                self.assert_persisted_receipt(session,receipt,'partial',physical=4,passes=2)
                self.assert_read_once(session)

    def test_initial_invalid_optional_counter_recovers_only_on_new_complete_sample(self):
        self.telemetry.fault=lambda snap:dict(snap,source_validation_calls=None)
        session=self.session();initial=self.ledger(session)
        self.assert_integrity(initial,'partial',physical=2,passes=0)
        self.assertNotIn('source_validation_calls',initial['cost_integrity']['last_known'])
        history=copy.deepcopy(initial['cost_integrity']['history'])
        self.telemetry.fault=None
        published=session.request('initial-optional-recovery')
        info=self.assert_persisted_receipt(session,published,'complete',physical=4,passes=2)
        self.assertEqual(info['current']['source_validation_calls'],4)
        self.assertEqual(info['last_known']['source_validation_calls']['value'],4)
        self.assertEqual(info['history'],history)
        self.assert_read_once(session)

    def test_metadata_copy_failure_is_unknown_without_failing_geometry_or_reusing_counts(self):
        class NoCopy:
            def __deepcopy__(self,memo):raise OSError('metadata cannot be frozen')
        session=self.session();self.telemetry.fault=lambda snap:dict(snap,events=[NoCopy()])
        published=session.request('copy-failure')
        info=self.assert_persisted_receipt(session,published,'unknown')
        self.assertEqual(info['issues']['_snapshot'],'OSError')
        self.assert_read_once(session)

    def test_metadata_json_failures_are_unknown_without_failing_geometry_publication(self):
        circular=[];circular.append(circular)
        for metadata in (float('nan'),float('inf'),{1,2},circular):
            with self.subTest(kind=type(metadata).__name__):
                self.reset_reader();session=self.session()
                self.telemetry.fault=lambda snap:dict(snap,events=metadata)
                published=session.request('json-failure')
                self.assert_persisted_receipt(session,published,'unknown')
                self.assert_read_once(session)

    def test_nested_mixed_metadata_keys_are_unknown_before_canonical_ledger_serialization(self):
        session=self.session()
        self.telemetry.fault=lambda snap:dict(snap,events=[{1:'a','x':'b'}])
        published=session.request('mixed-json-keys')
        info=self.assert_persisted_receipt(session,published,'unknown')
        self.assertEqual(info['issues']['_snapshot'],'TypeError')
        self.assert_read_once(session)

    def test_counter_decrease_is_unknown_for_that_field_until_cumulative_recovers(self):
        session=self.session()
        self.telemetry.fault=lambda snap:dict(snap,physical_inspect_requests=1)
        receipt=session.request('decreasing-count')
        info=self.assert_persisted_receipt(session,receipt,'partial',passes=2)
        self.assertEqual(info['last_known'][PRIMARY[0]]['value'],2)
        self.assertEqual(info['issues'][PRIMARY[0]],'counter_regression')
        history=copy.deepcopy(info['history']);self.assertTrue(history)
        self.telemetry.fault=None
        resolved=session.resolve(receipt['reference'],'')
        recovered=self.assert_persisted_receipt(session,resolved,'complete',physical=4,passes=2)
        self.assertEqual(recovered['history'][:len(history)],history)
        self.assert_read_once(session)

    def test_partial_valid_field_advances_highwater_before_later_regression(self):
        session=self.session()
        def high_then_low(snap):
            count=len(self.reader.calls)
            if count==1:return dict(snap,physical_inspect_requests=8,B2_rows_passes=None)
            return dict(snap,physical_inspect_requests=4)
        self.telemetry.fault=high_then_low
        receipt=session.request('partial-highwater')
        info=self.assert_persisted_receipt(session,receipt,'partial',passes=2)
        self.assertEqual(info['last_known'][PRIMARY[0]]['value'],8)
        self.assertEqual(info['last_known'][PRIMARY[0]]['logical_source_read_attempts_through'],1)
        self.assertEqual(info['issues'][PRIMARY[0]],'counter_regression')
        self.assert_read_once(session)

    def test_snapshot_metadata_is_not_mistaken_for_cumulative_counters(self):
        session=self.session()
        def metadata(snap):
            return dict(snap,started_ns=self.clock(),elapsed_ns=100-len(self.reader.calls),
                events=[{'sequence':len(self.reader.calls)}],actor_sequences={'one':2},
                worker_processes={'one':{'pid':17,'closed':self.reader.closed}},
                spans_are_inclusive_and_not_additive=True)
        self.telemetry.fault=metadata
        receipt=session.request('metadata')
        info=self.assert_persisted_receipt(session,receipt,'complete',physical=4,passes=2)
        for field in ('started_ns','elapsed_ns','events','actor_sequences','worker_processes','task_deadline_ns','spans_are_inclusive_and_not_additive'):
            self.assertNotIn(field,info['counter_fields'])
        self.assert_read_once(session)

    def test_known_started_epoch_change_blocks_false_cumulative_recovery(self):
        self.telemetry['started_ns']=self.clock();session=self.session()
        self.telemetry['started_ns']+=1
        receipt=session.request('different-epoch')
        info=self.assert_persisted_receipt(session,receipt,'unknown')
        self.assertEqual(info['issues']['_epoch'],'cumulative_epoch_unverified');self.assertTrue(info['history'])
        self.telemetry['started_ns']-=1
        resolved=session.resolve(receipt['reference'],'')
        self.assert_persisted_receipt(session,resolved,'unknown')
        self.assert_read_once(session)

    def test_known_started_epoch_omission_blocks_false_cumulative_recovery(self):
        self.telemetry['started_ns']=self.clock();session=self.session()
        def omit(snap):
            current=dict(snap);current.pop('started_ns');return current
        self.telemetry.fault=omit
        receipt=session.request('missing-epoch')
        self.assert_persisted_receipt(session,receipt,'unknown')
        self.telemetry.fault=None
        delivered=session.deliver(receipt['reference'],'epoch-still-unknown')
        self.assert_persisted_receipt(session,delivered,'unknown')
        self.assert_read_once(session)

    def test_resolve_and_deliver_refresh_unknown_usage_without_new_source_work(self):
        session=self.session();published=session.request('publish');reference=published['reference']
        self.telemetry.fault='raise'
        resolved=session.resolve(reference,'')
        self.assertIn('frames',resolved['value'])
        self.assert_persisted_receipt(session,resolved,'unknown')
        delivered=session.deliver(reference,'deliver-during-gap')
        self.assertTrue(delivered['delivered']);self.assertFalse(delivered['model_received'])
        self.assert_persisted_receipt(session,delivered,'unknown')
        self.assert_read_once(session)

    def test_later_complete_resolve_and_delivery_recover_counts_preserving_gap_history(self):
        session=self.session();self.telemetry.fault=lambda snap:'raise' if self.reader.calls else None
        published=session.request('publish-during-gap');history=copy.deepcopy(published['cost_integrity']['history'])
        self.telemetry.fault=None
        resolved=session.resolve(published['reference'],'')
        info=self.assert_persisted_receipt(session,resolved,'complete',physical=4,passes=2)
        self.assertEqual(info['history'],history)
        delivered=session.deliver(published['reference'],'deliver-after-recovery')
        self.assert_persisted_receipt(session,delivered,'complete',physical=4,passes=2)
        self.assertEqual(delivered['cost_integrity']['history'],history)
        self.assert_read_once(session)

    def test_returned_cost_objects_do_not_mutate_current_ledger_or_future_receipts(self):
        session=self.session();published=session.request('immutable-cost-receipt')
        published['usage'][PRIMARY[0]]=99
        published['cost_integrity']['current'][PRIMARY[0]]=99
        published['cost_integrity']['last_known'][PRIMARY[0]]['value']=99
        published['cost_integrity']['history'].append({'forged':True})
        resolved=session.resolve(published['reference'],'')
        self.assert_persisted_receipt(session,resolved,'complete',physical=4,passes=2)
        self.assertEqual(resolved['cost_integrity']['last_known'][PRIMARY[0]]['value'],4)
        self.assertEqual(resolved['cost_integrity']['history'],[])
        self.assert_read_once(session)

    def test_failed_read_cleanup_preserves_original_failure_and_unknown_costs(self):
        session=self.session();self.reader.read_fault='raise'
        self.telemetry.fault=lambda snap:'raise' if self.reader.calls else None
        with self.assertRaisesRegex(delivery.DeliveryError,'^deformation_delivery_receipt_unknown$'):
            session.request('lost-receipt-and-telemetry')
        ledger=self.ledger(session);self.assert_integrity(ledger,'unknown')
        self.assertEqual(ledger['state'],'receipt_unknown')
        self.assertEqual(ledger['error']['reason'],'receipt_unknown')
        self.assert_read_once(session,reads=1,published=False)
        with self.assertRaisesRegex(delivery.DeliveryError,'^deformation_delivery_terminal_no_retry$'):
            session.request('no-hidden-retry')
        self.assertEqual(len(self.reader.calls),1)

    def test_failed_close_keeps_source_failure_separate_from_cost_missing(self):
        session=self.session();self.reader.close_fault=True
        self.telemetry.fault=lambda snap:'raise' if self.reader.closed else None
        with self.assertRaisesRegex(delivery.DeliveryError,'^deformation_delivery_execution_failed$'):
            session.request('failed-close-with-telemetry-gap')
        ledger=self.ledger(session);info=self.assert_integrity(ledger,'unknown')
        self.assertFalse(info['close_completed']);self.assertTrue(info['close_attempted'])
        self.assertIsNone(ledger['close_receipt'])
        self.assert_read_once(session,published=False)

    def test_close_cost_sampling_past_deadline_cannot_publish_or_refund(self):
        session=self.session();tripped=[]
        def late_close(snap):
            if self.reader.closed:
                if not tripped:self.clock.advance(31_000_000_000);tripped.append(True)
                return 'raise'
            return None
        self.telemetry.fault=late_close
        with self.assertRaisesRegex(delivery.DeliveryError,'^deformation_delivery_original_deadline$'):
            session.request('late-close-costs')
        ledger=self.ledger(session);self.assert_integrity(ledger,'unknown')
        self.assertEqual(ledger['state'],'deadline_exceeded')
        self.assertEqual(ledger['error']['reason'],'original_deadline')
        self.assert_read_once(session,published=False)

    def test_final_cost_sampling_past_deadline_cannot_return_published_success(self):
        session=self.session();persist=delivery._persist_blob;tripped=[]
        def late_final(snap):
            if not tripped:self.clock.advance(31_000_000_000);tripped.append(True)
            return 'raise'
        def select_final(path,blob):
            result=persist(path,blob)
            if Path(path).name=='PUBLISHED.json':self.telemetry.fault=late_final
            return result
        with patch.object(delivery,'_persist_blob',side_effect=select_final):
            with self.assertRaisesRegex(delivery.DeliveryError,'^deformation_delivery_original_deadline$'):
                session.request('late-final-costs')
        ledger=self.ledger(session);self.assert_integrity(ledger,'unknown')
        self.assertEqual(ledger['state'],'deadline_exceeded')
        self.assert_read_once(session,published=False)

    def test_resolve_cost_sampling_past_deadline_is_unknown_without_source_retry(self):
        session=self.session();published=session.request('before-resolve-deadline')
        def late_sample(snap):
            self.clock.advance(31_000_000_000)
            return 'raise'
        self.telemetry.fault=late_sample
        with self.assertRaisesRegex(delivery.DeliveryError,'^deformation_delivery_evidence_delivery_unknown$'):
            session.resolve(published['reference'],'')
        ledger=self.ledger(session);self.assert_integrity(ledger,'unknown')
        self.assertEqual(ledger['state'],'evidence_delivery_unknown')
        self.assertFalse(ledger['delivered'])
        self.assert_read_once(session)

    def test_delivery_cost_sampling_past_deadline_cannot_acknowledge_first_delivery(self):
        session=self.session();published=session.request('before-delivery-deadline')
        def late_sample(snap):
            self.clock.advance(31_000_000_000)
            return 'raise'
        self.telemetry.fault=late_sample
        with self.assertRaisesRegex(delivery.DeliveryError,'^deformation_delivery_delivery_unknown$'):
            session.deliver(published['reference'],'late-cost-snapshot')
        ledger=self.ledger(session);self.assert_integrity(ledger,'unknown')
        self.assertEqual(ledger['state'],'delivery_unknown')
        self.assertFalse(ledger['delivered'])
        self.assert_read_once(session)

    def test_real_reader_close_telemetry_failure_keeps_verified_zero_exit_facts(self):
        backend=authored_reader(self.clock,self.deadline)
        with patch.object(backend,'snapshot_costs',side_effect=OSError('cost telemetry unavailable')):
            receipt=backend.verify_and_close()
        self.assertTrue(receipt['sources_unchanged']);self.assertTrue(receipt['all_owned_closed'])
        self.assertTrue(receipt['original_deadline_preserved'])
        self.assertIsNone(receipt['costs'])
        self.assertEqual(receipt['cost_snapshot_error'],'OSError')
        self.assertTrue(all(actor.closed for actor in backend.actors.values()))
        self.assertTrue(all(actor.process.poll()==0 for actor in backend.actors.values()))
        self.assertTrue(all(actor.verify_calls==2 for actor in backend.actors.values()))

    def test_real_reader_source_or_exit_failure_cannot_be_hidden_by_telemetry_fault(self):
        for exit_code,verify_failure in ((73,False),(0,True)):
            with self.subTest(exit_code=exit_code,verify_failure=verify_failure):
                backend=authored_reader(self.clock,self.deadline,exit_code=exit_code,verify_failure=verify_failure)
                with patch.object(backend,'snapshot_costs',side_effect=OSError('telemetry unavailable')) as snapshot:
                    with self.assertRaises(ValueError):backend.verify_and_close()
                self.assertIsNone(backend.close_receipt)
                self.assertEqual(snapshot.call_count,0)
                self.assertTrue(all(actor.closed for actor in backend.actors.values()))

    def test_real_reader_close_telemetry_fault_after_deadline_never_claims_valid_close(self):
        backend=authored_reader(self.clock,self.deadline)
        def fail_after_deadline():
            self.clock.advance(31_000_000_000)
            raise OSError('late telemetry unavailable')
        with patch.object(backend,'snapshot_costs',side_effect=fail_after_deadline):
            with self.assertRaises(ValueError):backend.verify_and_close()
        self.assertIsNone(backend.close_receipt)
        self.assertTrue(all(actor.closed for actor in backend.actors.values()))

    def test_real_reader_close_bad_cost_metadata_keeps_only_verified_close_facts(self):
        class NoCopy:
            def __deepcopy__(self,memo):raise OSError('bad metadata copy')
        circular=[];circular.append(circular)
        cases=([{1:'a','x':'b'}],float('nan'),circular,[NoCopy()])
        for metadata in cases:
            with self.subTest(metadata_type=type(metadata).__name__):
                backend=authored_reader(self.clock,self.deadline)
                original=backend.snapshot_costs
                with patch.object(backend,'snapshot_costs',side_effect=lambda:dict(original(),events=metadata)):
                    receipt=backend.verify_and_close()
                self.assertTrue(receipt['sources_unchanged']);self.assertTrue(receipt['all_owned_closed'])
                self.assertTrue(receipt['original_deadline_preserved'])
                self.assertIsNone(receipt['costs']);self.assertIn('cost_snapshot_error',receipt)
                self.assertTrue(all(actor.verify_calls==2 for actor in backend.actors.values()))
                self.assertTrue(all(actor.process.poll()==0 for actor in backend.actors.values()))

    def test_real_reader_cost_freeze_crossing_deadline_cannot_set_close_receipt(self):
        clock=self.clock
        class SlowFreeze:
            def __deepcopy__(self,memo):clock.advance(31_000_000_000);return None
        backend=authored_reader(self.clock,self.deadline)
        original=backend.snapshot_costs
        with patch.object(backend,'snapshot_costs',side_effect=lambda:dict(original(),events=[SlowFreeze()])):
            with self.assertRaises(ValueError):backend.verify_and_close()
        self.assertIsNone(backend.close_receipt)
        self.assertTrue(all(actor.process.poll()==0 for actor in backend.actors.values()))

    def test_real_reader_receipt_copy_crossing_deadline_cannot_set_close_receipt(self):
        backend=authored_reader(self.clock,self.deadline);deepcopy=copy.deepcopy;tripped=[]
        def late_receipt_copy(value,*args,**kwargs):
            result=deepcopy(value,*args,**kwargs)
            if type(value) is dict and value.get('schema')=='deformation-reader-close-v1':
                self.clock.advance(31_000_000_000);tripped.append(True)
            return result
        with patch('human_eye_plugin.deformation_reader.copy.deepcopy',side_effect=late_receipt_copy):
            with self.assertRaises(ValueError):backend.verify_and_close()
        self.assertEqual(tripped,[True]);self.assertIsNone(backend.close_receipt)
        self.assertTrue(all(actor.process.poll()==0 for actor in backend.actors.values()))


if __name__=='__main__':unittest.main()
