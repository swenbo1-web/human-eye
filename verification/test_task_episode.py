"""Episode semantics use explicit contract fixtures, not human/native proof."""
import copy
import hashlib
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
from unittest.mock import patch

from human_eye_plugin.task_episode import (TaskEpisode, approval_decision, task_event_id,
                                           validate_episode, summarize_episodes, archive_episode, read_episode)
from human_eye_plugin.task_authority import ClearanceTaskSpec


class TaskEpisodeTests(unittest.TestCase):
    def seed(self, request_id=7):
        self.task = ClearanceTaskSpec('part','base').to_dict()
        self.resolved = copy.deepcopy(self.task)
        self.resolved['reference_triangle_index'] = 2
        self.scope = dict(initial_native_sha256='a'*64, initial_capture_sha256='b'*64,
                          engine_build_id='sha256:'+'c'*64, connector_config_sha256='d'*64,
                          clock_domain='contract-clock',reference_triangle_index=2, process_id=123,
                          host_identity=dict(schema_version='1.0',capture_scope='complete_scene_meshes',
                              document_epoch='e'*64,object_instances={'part':'instance-part','base':'instance-base'}))
        self.arguments = dict(focal_id='part', reference_id='base')
        e = TaskEpisode('connection-fixture', request_id, self.arguments, 100.)
        e.proposed(self.task)
        self.e = e
        return e

    def accepted(self):
        e = self.seed()
        e.bind(self.resolved, self.scope, 'form-1')
        self.response = dict(jsonrpc='2.0', id='form-1', result={'action':'accept','content':{'approve':True}})
        e.response(self.response, 'accept_true')
        self.admission = dict(scope=copy.deepcopy(self.scope), event_id=task_event_id('connection-fixture',7),
            authorization_id='form-1', original_started_monotonic=100., original_deadline_monotonic=130.,
            persistence='committed', current_scene_revalidated=True, live_registration_available=True,
            goal_id='goal-1', limits=copy.deepcopy(self.task['limits']))
        e.admitted(self.admission)
        e.execution_started()
        self.result = dict(status='completed', task_succeeded=True, physical_task_succeeded=True,
            host_closed=True, execution_phase='physical_completion_verified', completion_persistence='committed',
            new_setter_count=4, engine_confirmed_steps=4, goal_id='goal-1',
            budget=dict(confirmed_steps=4, started_monotonic=100., deadline_monotonic=130.))
        return e

    def rehash(self, value):
        value.pop('sha256', None)
        value['sha256'] = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
            ensure_ascii=True, allow_nan=False).encode('utf8')).hexdigest()
        return value

    def test_success_is_only_a_candidate_without_human_or_training_claim(self):
        value=self.accepted().finish(self.result,101.)
        self.assertEqual(value['derived']['outcome'],'succeeded')
        self.assertTrue(value['derived']['success_candidate'])
        self.assertFalse(value['derived']['human_UI_verified'])
        self.assertFalse(value['derived']['training_positive'])
        self.assertIsNone(value['conclusions']['independent_support_count'])
        self.assertEqual(validate_episode(json.loads(json.dumps(value))),value)

    def test_receive_identity_and_all_layers_detach_from_mutable_inputs(self):
        e=self.accepted()
        self.arguments['focal_id']='changed';self.task['limits']['max_duration_s']=99
        self.resolved['direction_world'][2]=-1;self.scope['process_id']=999
        self.response['result']['content']['approve']=False;self.admission['scope'].clear()
        value=e.finish(self.result,101.);self.result['new_setter_count']=999
        self.assertEqual(value['raw_evidence']['proposal']['limits']['max_duration_s'],30)
        self.assertEqual(value['raw_evidence']['binding']['scope']['process_id'],123)
        self.assertEqual(value['raw_evidence']['result']['new_setter_count'],4)
        self.assertTrue(value['derived']['success_candidate'])

    def test_one_time_freeze_prevents_rebinding_and_sealed_reuse(self):
        e=self.accepted()
        for action in (lambda:e.proposed(self.task),lambda:e.bind(self.resolved,self.scope,'form-2'),
                       lambda:e.response(self.response,'accept_true'),lambda:e.admitted(self.admission)):
            with self.assertRaises(ValueError):action()
        value=e.finish(self.result,101.)
        value['raw_evidence']['request_id']=999
        with self.assertRaises(ValueError):e.finish(self.result,102.)
        with self.assertRaises(ValueError):e.execution_started()

    def test_unknown_physical_count_is_not_zero_or_success(self):
        e=self.accepted();self.result.update(status='review_required',task_succeeded=False,
            physical_task_succeeded=None,new_setter_count=None,execution_phase='dispatch_started')
        value=e.finish(self.result,101.)['derived']
        self.assertEqual(value['outcome'],'unknown');self.assertIsNone(value['new_setter_count'])
        self.assertFalse(value['success_candidate'])

    def test_physical_completion_and_save_ack_loss_stay_separate(self):
        e=self.accepted();self.result.update(status='review_required',task_succeeded=False,completion_persistence='unknown')
        d=e.finish(self.result,101.)['derived']
        self.assertEqual(d['outcome'],'unknown');self.assertTrue(d['physical_task_succeeded'])
        self.assertEqual(d['new_setter_count'],4);self.assertEqual(d['completion_persistence'],'unknown')
        self.assertFalse(d['success_candidate'])

    def test_known_partial_stop_is_not_success_or_replay_permission(self):
        e=self.accepted();self.result.update(status='review_required',task_succeeded=False,
            physical_task_succeeded=False,new_setter_count=1,execution_phase='reconciled')
        d=e.finish(self.result,101.)['derived']
        self.assertEqual(d['outcome'],'stopped_or_failed');self.assertEqual(d['new_setter_count'],1)
        self.assertFalse(d['retry_authorized']);self.assertFalse(d['execution_authority'])

    def test_decline_cancel_error_wrong_id_and_numeric_boolean_are_distinct(self):
        answers=[({'id':'form','result':{'action':'decline'}},'decline','client_declined'),
                 ({'id':'form','result':{'action':'cancel'}},'cancel','client_cancelled'),
                 ({'id':'form','error':{'code':-1}},'rpc_error','not_admitted'),
                 ({'id':'other','result':{'action':'accept','content':{'approve':True}}},'wrong_id','not_admitted'),
                 ({'id':'form','result':{'action':'accept','content':{'approve':1}}},'invalid_or_false','not_admitted')]
        for answer,decision,outcome in answers:
            with self.subTest(decision=decision):
                e=self.seed();e.bind(self.resolved,self.scope,'form')
                self.assertEqual(approval_decision(answer,'form'),decision)
                e.response(answer,decision)
                d=e.finish(dict(status='goal_not_admitted_or_review_required',new_setter_count=0),101.)['derived']
                self.assertEqual(d['outcome'],outcome);self.assertEqual(d['new_setter_count'],0)
                self.assertFalse(d['human_UI_verified'])

    def test_missing_response_is_not_fabricated_decline(self):
        e=self.seed();e.bind(self.resolved,self.scope,'form')
        value=e.finish({'status':'goal_not_admitted_or_review_required','new_setter_count':0},101.)
        self.assertEqual(value['raw_evidence']['approval']['decision'],'requested_no_valid_response')
        self.assertEqual(value['derived']['outcome'],'not_admitted')

    def test_missing_binding_cannot_turn_a_completed_string_into_success(self):
        self.accepted();e=TaskEpisode('other',1,{},100.);e.execution_started()
        d=e.finish(self.result,101.)['derived']
        self.assertEqual(d['outcome'],'unknown');self.assertFalse(d['binding_complete'])

    def test_incomplete_or_invalid_source_never_claims_complete_binding(self):
        for field in ('initial_native_sha256','initial_capture_sha256','host_identity','clock_domain','engine_build_id'):
            e=self.accepted();value=e.finish(self.result,101.)
            value['raw_evidence']['binding']['scope'].pop(field)
            value['raw_evidence']['admission']['scope'].pop(field)
            with self.assertRaisesRegex(ValueError,'derivation'):validate_episode(self.rehash(value))
        e=self.seed();self.scope['host_identity']['object_instances']={'other':'instance'}
        e.bind(self.resolved,self.scope,'form');e.execution_started()
        self.result=dict(status='completed',task_succeeded=True,physical_task_succeeded=True,new_setter_count=4)
        d=e.finish(self.result,101.)['derived'];self.assertFalse(d['binding_complete'])

    def test_goal_budget_event_or_scope_mismatch_prevents_success(self):
        cases=[lambda:self.admission.update(event_id='other'),lambda:self.admission.update(authorization_id='other'),
               lambda:self.admission['scope'].update(process_id=999),lambda:self.result.update(goal_id='other'),
               lambda:self.result['budget'].update(deadline_monotonic=160.),
               lambda:self.admission.update(original_started_monotonic=99.)]
        for change in cases:
            e=self.accepted();value=e.finish(self.result,101.);change()
            # Model corruption of an exported document is checked again by the
            # consumer, even after it recomputes a non-authenticating digest.
            value['raw_evidence']['admission']=copy.deepcopy(self.admission)
            value['raw_evidence']['result']=copy.deepcopy(self.result)
            with self.assertRaises(ValueError):validate_episode(self.rehash(value))

    def test_missing_or_boolean_counts_cannot_become_success(self):
        for field in ('new_setter_count','engine_confirmed_steps'):
            e=self.accepted();self.result[field]=True
            self.assertFalse(e.finish(self.result,101.)['derived']['success_candidate'])
        e=self.accepted();self.result['budget']['confirmed_steps']=True
        self.assertFalse(e.finish(self.result,101.)['derived']['success_candidate'])

    def test_historical_receipt_does_not_count_as_a_new_success(self):
        e=self.accepted();self.result.update(historical_receipt=True,replayed=True,new_setter_count=0)
        d=e.finish(self.result,101.)['derived']
        self.assertEqual(d['outcome'],'historical_receipt');self.assertFalse(d['success_candidate'])

    def test_digest_corruption_and_rehashed_conclusion_injection_are_rejected(self):
        value=self.accepted().finish(self.result,101.)
        bad=copy.deepcopy(value);bad['raw_evidence']['result']['new_setter_count']=8
        with self.assertRaises(ValueError):validate_episode(bad)
        bad=copy.deepcopy(value);bad['derived']['training_positive']=True
        with self.assertRaises(ValueError):validate_episode(self.rehash(bad))
        bad=copy.deepcopy(value);bad['raw_evidence']['origin']='human_UI_verified'
        with self.assertRaises(ValueError):validate_episode(self.rehash(bad))

    def test_a_hundred_copies_are_one_recorded_event_not_independent_support(self):
        value=self.accepted().finish(self.result,101.)
        result=summarize_episodes([copy.deepcopy(value) for _ in range(100)])
        self.assertEqual(result['distinct_recorded_events'],1);self.assertEqual(result['duplicate_records'],99)
        self.assertEqual(result['success_candidates'],1);self.assertEqual(result['training_positives'],0)
        self.assertIsNone(result['independent_support_count'])

    def test_conflicting_records_for_same_event_are_not_silently_selected(self):
        a=self.accepted().finish(self.result,101.)
        e=self.accepted();self.result.update(status='review_required',new_setter_count=None,task_succeeded=False)
        b=e.finish(self.result,101.)
        with self.assertRaisesRegex(ValueError,'conflicting'):summarize_episodes([a,b])

    def test_bad_times_stay_unknown_evidence_without_nan_json(self):
        for received in (float('nan'),float('inf'),True,-1.):
            e=TaskEpisode('connection',1,{},received)
            value=e.finish(dict(status='goal_not_admitted_or_review_required',new_setter_count=0),101.)
            self.assertIsNone(value['raw_evidence']['received_monotonic'])
            self.assertFalse(value['derived']['timing_valid']);validate_episode(value)

    def test_request_ids_are_typed_bounded_and_do_not_alias(self):
        self.assertNotEqual(task_event_id('connection',7),task_event_id('connection','7'))
        for value in (True,None,-1,2**53,'','x'*129):
            with self.assertRaises(ValueError):task_event_id('connection',value)

    def test_request_document_and_collection_budgets_are_finite(self):
        with self.assertRaises(ValueError):TaskEpisode('connection',1,{'payload':'x'*262144},100.)
        with self.assertRaises(ValueError):summarize_episodes([{}]*1025)

    def test_archive_round_trip_and_duplicate_preserve_the_original_bytes(self):
        value=self.accepted().finish(self.result,101.)
        with tempfile.TemporaryDirectory() as folder:
            first=archive_episode(value,folder);before=Path(first['path']).read_bytes()
            again=archive_episode(value,folder)
            self.assertFalse(first['deduplicated']);self.assertTrue(again['deduplicated'])
            self.assertTrue(first['file_flushed']);self.assertFalse(first['directory_metadata_flushed'])
            self.assertEqual(Path(first['path']).read_bytes(),before)
            self.assertEqual(read_episode(first['path']),value)
            self.assertEqual(len(list(Path(folder).iterdir())),1)

    def test_archive_publication_failure_cleans_only_its_temporary_and_never_replaces(self):
        value=self.accepted().finish(self.result,101.)
        with tempfile.TemporaryDirectory() as folder:
            sentinel=Path(folder)/'sentinel';sentinel.write_text('keep')
            with patch('human_eye_plugin.task_episode.os.link',side_effect=OSError('injected link failure')):
                with self.assertRaises(OSError):archive_episode(value,folder)
            self.assertEqual([p.name for p in Path(folder).iterdir()],['sentinel'])
            self.assertEqual(sentinel.read_text(),'keep')

    def test_archive_corrupt_preexisting_file_is_not_overwritten_or_trusted(self):
        value=self.accepted().finish(self.result,101.)
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/(value['sha256']+'.json');target.write_text('{broken')
            with self.assertRaises(ValueError):archive_episode(value,folder)
            self.assertEqual(target.read_text(),'{broken')
            with self.assertRaises(ValueError):read_episode(target)

    def test_two_archive_consumers_publish_one_complete_record(self):
        value=self.accepted().finish(self.result,101.)
        with tempfile.TemporaryDirectory() as folder:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(lambda _:archive_episode(value,folder),range(2)))
            self.assertEqual(sum(r['deduplicated'] for r in results),1)
            self.assertEqual(read_episode(results[0]['path']),value)
            self.assertEqual(len(list(Path(folder).iterdir())),1)


if __name__=='__main__':unittest.main()
