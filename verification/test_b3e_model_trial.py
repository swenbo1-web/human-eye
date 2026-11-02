"""No Google requests, credentials or Blender; local finite-budget doubles."""
import copy,hashlib,json,os,sqlite3,subprocess,sys,tempfile,time,unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from verification.model_trial import b3e_spend as spend,b3e_gemini as gemini
from verification.model_trial import b3e_contract as contract
from verification.model_trial.deadline import EpisodeDeadline


def response():
    return dict(modelVersion='gemini-4-argon',responseId='test-response',
        candidates=[dict(content=dict(parts=[dict(text='{"status":"unknown"}')]),finishReason='STOP')],
        usageMetadata=dict(promptTokenCount=100,candidatesTokenCount=10,thoughtsTokenCount=20,totalTokenCount=130))


def receipt():
    return dict(response_sha256='b'*64,price_sha256=gemini.PRICE_SHA256,model_version=gemini.MODEL,usage=response()['usageMetadata'])


class B3eBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
        self.ledger=spend.CampaignLedger.create(self.root/'campaign.sqlite3','trial','a'*64)

    def test_integer_money_and_single_total_cap(self):
        for value in (True,1.0,-1,20_000_001):
            with self.subTest(value=value),self.assertRaises(ValueError):spend.money(value)
        with self.ledger.attempt('ordinary','r1','1'*64,15_000_000) as permit:permit.settle(15_000_000,receipt())
        for episode in ('core','native','scoring'):
            with self.subTest(episode=episode),self.assertRaisesRegex(ValueError,'campaign_cap'):
                with self.ledger.attempt(episode,'r-'+episode,'1'*64,5_000_001):pass
        self.assertEqual(self.ledger.snapshot()['remaining_micro_usd'],5_000_000)

    def test_complete_settlement_retains_original_upper_event_and_releases_only_unused_bound(self):
        with self.ledger.attempt('core','r1','1'*64,2_100_000) as permit:permit.settle(500,receipt())
        state=self.ledger.snapshot();self.assertEqual(state['known_charge_micro_usd'],500);self.assertEqual(state['exposure_micro_usd'],500)
        self.assertEqual(state['reservations']['r1']['upper_micro_usd'],2_100_000)
        with closing(sqlite3.connect(self.ledger.path)) as db,db:
            rows=db.execute('SELECT kind,payload FROM events ORDER BY seq').fetchall();self.assertEqual([r[0] for r in rows],['reserve','settle'])
            with self.assertRaises(sqlite3.DatabaseError):db.execute('UPDATE events SET payload=?',('{}',))
            with self.assertRaises(sqlite3.DatabaseError):db.execute('DELETE FROM events')
        reopened=spend.CampaignLedger(self.ledger.path,'trial','a'*64);self.assertEqual(reopened.snapshot(),state)

    def test_unknown_preserves_full_upper_and_permanently_stops_batch_without_retry(self):
        with self.assertRaises(TimeoutError):
            with self.ledger.attempt('core','r1','1'*64,2_100_000):raise TimeoutError('unknown provider')
        for ident in ('r1','new-id'):
            with self.subTest(ident=ident),self.assertRaisesRegex(ValueError,'stopped'):
                with spend.CampaignLedger(self.ledger.path,'trial','a'*64).attempt('native',ident,'2'*64,1):pass
        state=self.ledger.snapshot();self.assertEqual(state['exposure_micro_usd'],2_100_000);self.assertEqual(state['known_charge_micro_usd'],0)

    def test_committed_settlement_then_lost_ack_is_recoverable_without_resending_old_id(self):
        settle=spend._Attempt.settle
        def lost(self,*a,**k):settle(self,*a,**k);raise OSError('lost local ack')
        with patch.object(spend._Attempt,'settle',lost),self.assertRaises(OSError):
            with self.ledger.attempt('core','r1','1'*64,2_100_000) as permit:permit.settle(500,receipt())
        state=self.ledger.snapshot();self.assertIsNone(state['stopped']);self.assertEqual(state['exposure_micro_usd'],500)
        with self.assertRaisesRegex(ValueError,'request_id_reused'):
            with self.ledger.attempt('core','r1','1'*64,2_100_000):pass

    def test_legacy_handoff_retains_two_unknowns_and_never_creates_another_twenty(self):
        legacy=dict(source_sha256='c'*64,campaign_id='same-campaign',known_charge_micro_usd=0,pending_upper_micro_usd=20_000,
            unknown_requests=['external-smoke-1','external-smoke-2'])
        path=self.root/'import.sqlite3';ledger=spend.CampaignLedger.create(path,'same-campaign','d'*64,legacy=legacy)
        state=ledger.snapshot();self.assertEqual(state['cap_micro_usd'],20_000_000);self.assertEqual(state['remaining_micro_usd'],19_980_000)
        self.assertEqual(state['legacy'],legacy);self.assertEqual(state['stopped'],'legacy_unknown_request')
        with self.assertRaisesRegex(ValueError,'legacy_unknown'):
            with ledger.attempt('native','r3','e'*64,100):pass
        with self.assertRaises(FileExistsError):spend.CampaignLedger.create(path,'same-campaign','d'*64,legacy=legacy)

    def test_missing_replaced_or_mismatched_ledger_never_auto_reinitializes(self):
        for args in ((self.root/'absent','trial','a'*64),(self.ledger.path,'different','a'*64),(self.ledger.path,'trial','f'*64)):
            with self.subTest(args=args),self.assertRaises(ValueError):spend.CampaignLedger(*args).snapshot()

    def test_crashed_process_after_durable_reserve_is_stopped_on_next_attempt(self):
        script='''import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from verification.model_trial.b3e_spend import CampaignLedger
ledger=CampaignLedger(Path(sys.argv[2]),'trial','a'*64)
with ledger.attempt('native','crash','1'*64,2100000):os._exit(7)
'''
        run=subprocess.run([sys.executable,'-I','-B','-c',script,str(Path(__file__).resolve().parents[1]),str(self.ledger.path)],capture_output=True,timeout=15)
        self.assertEqual(run.returncode,7)
        with self.assertRaisesRegex(ValueError,'prior_request_unreconciled'):
            with self.ledger.attempt('core','later','2'*64,1):pass
        self.assertEqual(self.ledger.snapshot()['exposure_micro_usd'],2_100_000)
        self.assertEqual(self.ledger.snapshot()['stopped'],'prior_request_unreconciled')

    def test_concurrent_processes_share_one_twenty_dollar_allowance(self):
        script='''import json,sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from verification.model_trial.b3e_spend import CampaignLedger
ledger=CampaignLedger(Path(sys.argv[2]),'trial','a'*64)
try:
 with ledger.attempt('arm-'+sys.argv[3],'request-'+sys.argv[3],'1'*64,4000000,timeout=10) as permit:
  time.sleep(.05)
  permit.settle(4000000,dict(response_sha256='b'*64,price_sha256='c'*64,model_version='gemini-4-argon',usage={}))
 result={'ok':True}
except ValueError as exc:result={'ok':False,'error':str(exc)}
print(json.dumps(result))
'''
        children=[]
        try:
            for i in range(6):children.append(subprocess.Popen([sys.executable,'-I','-B','-c',script,str(Path(__file__).resolve().parents[1]),str(self.ledger.path),str(i)],stdout=subprocess.PIPE,stderr=subprocess.PIPE))
            rows=[]
            for child in children:
                stdout,stderr=child.communicate(timeout=20);self.assertEqual(child.returncode,0,stderr);rows.append(json.loads(stdout))
            self.assertEqual(sum(r['ok'] for r in rows),5);self.assertEqual(sum(not r['ok'] and 'campaign_cap' in r['error'] for r in rows),1)
            self.assertEqual(self.ledger.snapshot()['exposure_micro_usd'],20_000_000)
        finally:
            for child in children:
                if child.poll() is None:child.kill();child.communicate(timeout=5)


class B3eGeminiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()

    def ledger(self,index='one'):return spend.CampaignLedger.create(self.root/(index+'.sqlite3'),'trial','a'*64)
    def budget(self):
        budget=EpisodeDeadline(30.);self.addCleanup(budget.close);return budget
    def call(self,ledger,transport,**kwargs):return gemini.generate_once(ledger,transport,episode_id='core',request_id='r1',system_prompt='same system',user_prompt='same task',budget=self.budget(),**kwargs)

    def test_exact_model_settings_text_only_and_full_count_payload(self):
        body=gemini.build_request('sys','user',max_output_tokens=512,thinking_level='LOW')
        self.assertEqual(set(body),{'contents','systemInstruction','generationConfig','serviceTier','store'})
        self.assertEqual(body['generationConfig'],dict(candidateCount=1,maxOutputTokens=512,thinkingConfig=dict(thinkingLevel='LOW',includeThoughts=False)))
        self.assertEqual(gemini.count_tokens_payload(body)['generateContentRequest']['model'],'models/gemini-4-argon')
        self.assertFalse(set(body)&{'tools','cachedContent','temperature','topP','topK'})
        for cap in (True,0,32769):
            with self.subTest(cap=cap),self.assertRaises(ValueError):gemini.build_request('s','u',max_output_tokens=cap)

    def test_complete_usage_includes_thinking_and_settles_without_cached_discount(self):
        raw=response();raw['usageMetadata']['cachedContentTokenCount']=50;seen=[]
        def transport(body,budget):seen.append(body);return raw
        value=self.call(self.ledger(),transport)
        self.assertEqual(len(seen),1);self.assertEqual(value['receipt']['charge_micro_usd'],500)
        self.assertEqual(value['reserved_micro_usd'],2_102_272)
        self.assertEqual(value['campaign']['known_charge_micro_usd'],500)
        self.assertEqual(value['receipt']['usage']['thoughtsTokenCount'],20);self.assertIsNone(value['receipt']['actual_invoice_cost'])

    def test_missing_usage_version_finish_wrong_totals_or_price_tier_stop_without_retry(self):
        changes=[lambda r:r.pop('usageMetadata'),lambda r:r.pop('modelVersion'),lambda r:r['candidates'][0].pop('finishReason'),
            lambda r:r['usageMetadata'].pop('thoughtsTokenCount'),lambda r:r['usageMetadata'].update(totalTokenCount=131),
            lambda r:r['usageMetadata'].update(serviceTier='priority'),lambda r:r['usageMetadata'].update(toolUsePromptTokenCount=1),
            lambda r:r.update(modelVersion='other-model'),lambda r:r['usageMetadata'].update(candidatesTokenCount=True)]
        for i,change in enumerate(changes):
            with self.subTest(i=i):
                ledger=self.ledger(str(i));raw=response();change(raw);calls=[]
                def transport(body,budget):calls.append(1);return raw
                with self.assertRaises(ValueError):self.call(ledger,transport)
                self.assertEqual(ledger.snapshot()['exposure_micro_usd'],2_102_272);self.assertIsNotNone(ledger.snapshot()['stopped'])
                with self.assertRaises(ValueError):self.call(ledger,transport)
                self.assertEqual(len(calls),1)

    def test_unknown_http_failure_retains_upper_and_makes_only_one_transport_attempt(self):
        ledger=self.ledger();calls=[]
        def transport(*a):calls.append(1);raise TimeoutError('unknown')
        for _ in range(2):
            with self.assertRaises((TimeoutError,ValueError)):self.call(ledger,transport)
        self.assertEqual(len(calls),1);self.assertEqual(ledger.snapshot()['exposure_micro_usd'],2_102_272)

    def test_changed_model_version_holds_upper(self):
        with self.assertRaisesRegex(ValueError,'version_changed'):self.call(self.ledger(),lambda *a:response(),expected_model_version='gemini-4-argon-other-version')

    def test_price_expiry_and_near_boundary_fail_closed(self):
        from datetime import datetime,timezone
        gemini.price_valid(datetime(2026,11,30,23,59,0,tzinfo=timezone.utc),remaining_seconds=30)
        for date,remaining in [(datetime(2026,12,1,tzinfo=timezone.utc),0),(datetime(2026,11,30,23,59,59,tzinfo=timezone.utc),2)]:
            with self.subTest(date=date),self.assertRaisesRegex(ValueError,'price_expired'):gemini.price_valid(date,remaining_seconds=remaining)

    def test_disabled_transport_never_reads_credentials_or_reserves_money(self):
        ledger=self.ledger();transport=gemini.OfficialHTTPTransport(api_key_file=self.root/'not-created')
        with patch.object(gemini,'_load_explicit_key',side_effect=AssertionError('must not read key')),self.assertRaisesRegex(ValueError,'network_disabled'):
            self.call(ledger,transport)
        self.assertEqual(ledger.snapshot()['events'],0)

    def test_explicit_credentials_ignore_ambient_values_and_never_enter_safe_receipt(self):
        key=self.root/'dedicated-key.txt';key.write_text('dedicated_abcdefghijklmnop')
        with patch.dict(os.environ,{'GOOGLE_API_KEY':'ambient-secret','GEMINI_API_KEY':'ambient-secret','GOOGLE_APPLICATION_CREDENTIALS':'ambient-adc.json'}):
            self.assertEqual(gemini._load_explicit_key(key),'dedicated_abcdefghijklmnop')
        _,safe=gemini.normalize_response(response(),max_output_tokens=512)
        self.assertNotIn('dedicated_',json.dumps(safe));self.assertNotIn('ambient-',json.dumps(safe))


class B3eCommonContractTests(unittest.TestCase):
    def setUp(self):
        self.task=dict(schema='b3e-core-task-v1',task_id='finite-task',source_ref=dict(scene_sha256='a'*64,rig_object_id='rig',mesh_object_id='mesh',frame=dict(number=1,subframe=0.)),
            core_region=dict(kind='closed_aabb',coordinate_space='current_world_m',bounds=[[-.5]*3,[.5]*3]))
        self.facts=dict(core_status='partial',core_triangle_count=2,core_states=dict(measured=1,collapsed=0,unknown=1),core_unknown_reasons={'precision':1},
            core_extrema=dict(max_principal_stretch=1.2,min_principal_stretch=.8,min_area_ratio=.96,max_area_ratio=.96))

    def truth(self,facts=None):return contract.bind_truth(self.task,self.facts if facts is None else facts,source_observation_sha256='b'*64,independent_checker_sha256='c'*64,acquisition_receipt_sha256='d'*64)
    def answer(self):return dict(task_id=self.task['task_id'],answer_status='answered',**copy.deepcopy(self.facts),**contract.SCOPE)

    def test_common_prompt_has_same_question_and_no_arm_label_or_truth(self):
        for arm in contract.ARMS:
            prompt=contract.user_prompt(self.task,dict(public_read='same available facts'))
            self.assertNotIn(arm,prompt);self.assertNotIn('precision',prompt)
            self.assertIn('same read-only native core query',prompt)
        self.assertEqual(contract.validate_task(self.task),self.task)

    def test_complete_core_facts_pass_and_primary_extrema_cannot_substitute(self):
        truth=self.truth();answer=self.answer();self.assertTrue(contract.grade_answer(self.task,truth,answer)['complete_correct'])
        for key in contract.EXTREMA:answer['core_extrema'][key]=9.
        result=contract.grade_answer(self.task,truth,answer);self.assertFalse(result['complete_correct']);self.assertEqual(result['false_facts'],4)

    def test_insufficient_evidence_keeps_known_counts_but_is_not_answerable_coverage(self):
        answer=self.answer();answer.update(answer_status='insufficient_evidence',core_extrema=None)
        result=contract.grade_answer(self.task,self.truth(),answer)
        self.assertTrue(result['safe_incomplete']);self.assertFalse(result['complete_correct']);self.assertTrue(result['answerable']);self.assertEqual(result['missing_fields'],4)

    def test_all_unknown_and_empty_are_valid_complete_factual_answers_not_false_zeros(self):
        for count in (0,1):
            with self.subTest(count=count):
                facts=dict(core_status='partial' if count else 'empty',core_triangle_count=count,core_states=dict(measured=0,collapsed=0,unknown=count),
                    core_unknown_reasons={'precision':1} if count else {},core_extrema={key:None for key in contract.EXTREMA})
                truth=self.truth(facts);answer=dict(task_id=self.task['task_id'],answer_status='answered',**facts,**contract.SCOPE)
                self.assertTrue(contract.grade_answer(self.task,truth,answer)['complete_correct'])
                answer=copy.deepcopy(answer);answer['core_extrema']['max_area_ratio']=0.
                self.assertEqual(contract.grade_answer(self.task,truth,answer)['false_facts'],1)

    def test_damage_volume_and_speed_claims_fail_scope(self):
        for key in ('damage_conclusion','volume_conclusion','total_task_speedup'):
            with self.subTest(key=key):
                answer=self.answer();answer[key]='proved'
                result=contract.grade_answer(self.task,self.truth(),answer);self.assertFalse(result['complete_correct']);self.assertEqual(result['scope_errors'],[key])

    def test_exact_registered_rows_task_binding_and_duplicate_ids_are_checked_before_grading(self):
        registered=[dict(episode_id='anonymous1',task_id=self.task['task_id'],task_sha256=contract.digest(self.task))]
        answer=[dict(episode_id='anonymous1',task_sha256=contract.digest(self.task),answer=self.answer())]
        truth={self.task['task_id']:(self.task,self.truth())};result=contract.grade_registered(registered,truth,answer)
        self.assertEqual(result['answerable_coverage'],1.);self.assertIsNone(result['model_tokens']);self.assertIsNone(result['model_cost_usd'])
        for rows in (answer*2,[dict(answer[0],episode_id='other')],[dict(answer[0],task_sha256='f'*64)]):
            with self.subTest(rows=rows),self.assertRaises(ValueError):contract.grade_registered(registered,truth,rows)
        with self.assertRaises(ValueError):contract.grade_registered(registered*2,truth,answer*2)


if __name__=='__main__':unittest.main()
