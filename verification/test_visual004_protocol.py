import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from verification import visual004_protocol as p

def task():return dict(schema='visual004-public-task-v1',case_id='V01',question='Identify the two shapes and explain the local relation.',
    required_roles=['target','reference'],required_fact_ids=['minimum_gap_m'])

class ProtocolTests(unittest.TestCase):
    def test_balanced_fixed_pairs_include_all_six_cases(self):
        self.assertEqual([case for case,_ in p.PAIR_ORDER],['V01','V02','V03','V04','V05','V06'])
        self.assertEqual(sum(order[0]=='P' for _,order in p.PAIR_ORDER),3)
        self.assertTrue(all(set(order)=={'P','N'} and len(order)==2 for _,order in p.PAIR_ORDER))
    def test_contract_exact_source_task_and_unique_run(self):
        a=p.task_contract(task(),'a'*64);b=p.task_contract(task(),'a'*64)
        self.assertEqual(a['task_sha256'],hashlib.sha256(p.encoded(task())).hexdigest())
        self.assertEqual(a['asset_sha256'],'a'*64);self.assertNotEqual(a['task_run_id'],b['task_run_id'])
    def test_changed_question_invalidates_old_public_input(self):
        public=task();contract=p.task_contract(public,'a'*64);public['question']+=' changed'
        with self.assertRaisesRegex(ValueError,'public_binding'):p.consumer_input(public,contract,'N')
    def test_no_private_object_pair_or_solver_in_shared_input(self):
        public=task();contract=p.task_contract(public,'a'*64)
        for condition in ('P','N'):
            data=p.consumer_input(public,contract,condition)
            self.assertEqual(data['task'],public);self.assertNotIn('expected_objects',data)
            self.assertNotIn('focal_id',data);self.assertNotIn('reference_id',data)
            self.assertNotIn('private_truth',data);self.assertNotIn('solver',data)
    def test_both_conditions_have_equal_original_budgets(self):
        public=task();contract=p.task_contract(public,'a'*64)
        left=p.consumer_input(public,contract,'P');right=p.consumer_input(public,contract,'N')
        for key in ('task','contract','public_contract','formal_entry_policy','rules','evidence_reference_rules','answer_schema','task_window_seconds','image_budget','text_budget','max_public_calls'):
            self.assertEqual(left[key],right[key],key)
        self.assertEqual(left['task_window_seconds'],600);self.assertEqual(left['max_public_calls'],48)
        self.assertEqual(left['text_budget']['max_total_wire_bytes'],360448)
    def test_fixed_visual_choices_do_not_turn_projection_into_xy_selector(self):
        self.assertEqual(p.P_MODES,[dict(mode='auto',view=v) for v in ('SCENE','XY','XZ')]+[dict(mode='projection',view='SCENE')])
        self.assertIn('fixed Q1-Q4',p.P_RULES)
    def test_common_initial_code_is_neutral_and_no_task_or_object_selection(self):
        code=p.COMMON_INITIAL_CODE
        self.assertNotIn('human_eye',code);self.assertNotIn('target',code);self.assertNotIn('reference',code)
        self.assertNotIn('Object_',code);self.assertIn('bpy.ops.render.render',code)
        self.assertIn('768',code);self.assertIn('camera_matrix_world',code)
    def test_invalid_case_or_hash_rejected(self):
        public=task();public['case_id']='other'
        with self.assertRaisesRegex(ValueError,'case_id'):p.task_contract(public,'a'*64)
        for digest in ('a'*63,'g'*64,True):
            with self.subTest(digest=digest),self.assertRaisesRegex(ValueError,'asset_sha256'):p.task_contract(task(),digest)
    def image(self):return dict(width=768,height=768,pixels=768**2,reservation_id='r1',path='own/image.png',sha256='a'*64)
    def test_valid_image_ref_requires_spent_reservation(self):
        row=self.image();self.assertEqual(p.validate_image_ref(row),row)
        del row['reservation_id']
        with self.assertRaisesRegex(ValueError,'reserved_image_required'):p.validate_image_ref(row)
    def test_wide_equal_area_image_exceeds_dimension_gate(self):
        row=dict(self.image(),width=2048,height=512,pixels=1024**2)
        with self.assertRaisesRegex(ValueError,'single_image_dimensions'):p.validate_image_ref(row)
    def test_dimensions_cannot_be_boolean_or_false_area(self):
        for change in (dict(width=True),dict(pixels=1),dict(height=0)):
            with self.subTest(change=change),self.assertRaises(ValueError):p.validate_image_ref(dict(self.image(),**change))
    def test_non_hex_digest_rejected(self):
        with self.assertRaisesRegex(ValueError,'image_digest'):p.validate_image_ref(dict(self.image(),sha256='g'*64))
    def reply(self):
        return dict(request_id='inspect-1',ok=True,result=dict(image_refs=[dict(self.image(),image_id='image-3',reservation_id='delivery-2')]))
    def test_evidence_symbols_use_identifiers_visible_to_consumer(self):
        self.assertEqual(p.public_evidence_ids(self.reply()),dict(text='text:inspect-1',images=['image:inspect-1:delivery-2:image-3']))
    def test_redisplay_is_new_evidence_even_when_png_bytes_same(self):
        first=self.reply();second=copy.deepcopy(first);second['request_id']='redisplay-1';second['result']['image_refs'][0]['reservation_id']='delivery-3'
        self.assertNotEqual(p.public_evidence_ids(first)['images'],p.public_evidence_ids(second)['images'])
    def test_failed_reply_has_only_text_symbol_even_if_private_images_present(self):
        row=self.reply();row['ok']=False
        self.assertEqual(p.public_evidence_ids(row),dict(text='text:inspect-1',images=[]))
    def test_reference_proposal_does_not_attest_delivery(self):
        row=p.public_evidence_ids(self.reply())
        self.assertNotIn('delivered',row);self.assertNotIn('actual_host_event_id',row)
        self.assertIn('do not attest delivery',p.EVIDENCE_REFERENCE_RULES)
    def test_public_reference_rejects_ambiguous_or_unbounded_identifiers(self):
        for request in ('x:y','white space','a'*65,'中文','',None):
            with self.subTest(request=request),self.assertRaisesRegex(ValueError,'public_request_id'):
                p.public_evidence_ids(dict(self.reply(),request_id=request))
        row=self.reply();row['result']['image_refs'][0]['image_id']='image:3'
        with self.assertRaisesRegex(ValueError,'public_image_identifiers'):p.public_evidence_ids(row)
    def test_duplicate_reference_and_oversized_image_are_rejected(self):
        row=self.reply();row['result']['image_refs']*=2
        with self.assertRaisesRegex(ValueError,'duplicate_public_image_reference'):p.public_evidence_ids(row)
        row=self.reply();row['result']['image_refs'][0].update(width=2048,height=512,pixels=1024**2)
        with self.assertRaisesRegex(ValueError,'single_image_dimensions'):p.public_evidence_ids(row)
    def test_versioned_plan_verification_keeps_old_generation_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);new=root/'final_protocol';new.mkdir()
            old=root/'FORMAL_PLAN.json';old.write_bytes(b'old sealed generation\n')
            plan=dict(schema='visual004-frozen-paired-plan-v2',script_pins=[],cases=[],public_contract_policy=p.PUBLIC_CONTRACT_POLICY,
                score_contract_schema=p.BOUND_CONTRACT_SCHEMA,formal_entry_policy=p.FORMAL_ENTRY_POLICY);raw=p.encoded(plan)
            (new/'FORMAL_PLAN.json').write_bytes(raw)
            (new/'FORMAL_PLAN_SEAL.json').write_bytes(p.encoded(dict(sha256=hashlib.sha256(raw).hexdigest())))
            self.assertEqual(p.verify_plan(root,output_dir=new),plan)
            self.assertEqual(old.read_bytes(),b'old sealed generation\n')
            (new/'FORMAL_PLAN.json').write_bytes(raw+b' ')
            with self.assertRaisesRegex(ValueError,'plan_changed'):p.verify_plan(root,output_dir=new)
    def test_formal_input_binds_public_semantics_and_v2_answer(self):
        public=task();contract=p.task_contract(public,'a'*64)
        data=p.consumer_input(public,contract,'N')
        self.assertEqual(contract['schema'],'visual004-score-contract-v2')
        self.assertEqual(data['schema'],'visual004-public-consumer-input-v2')
        self.assertEqual(data['answer_schema']['schema'],'visual004-answer-v2')
        self.assertIn('public_contract_sha256',data['answer_schema']['bindings'])
        self.assertEqual(contract['public_contract_sha256'],p.supplement_sha256(data['public_contract']))
    def test_formal_input_rejects_old_unbound_schema(self):
        public=task();contract=p.task_contract(public,'a'*64);contract['schema']='visual004-score-contract-v1';contract.pop('public_contract_sha256')
        with self.assertRaisesRegex(ValueError,'formal_bound_contract_required'):p.consumer_input(public,contract,'P')
    def test_public_supplement_mismatch_and_self_rehashed_tamper_rejected(self):
        public=task();contract=p.task_contract(public,'a'*64);supplement=p.public_supplement(public)
        supplement['roles']['target']='A different role selected after looking at an answer'
        with self.assertRaises(ValueError):p.consumer_input(public,contract,'P',public_contract=supplement)
        contract['public_contract_sha256']=p.supplement_sha256(supplement)
        with self.assertRaises(ValueError):p.consumer_input(public,contract,'N',public_contract=supplement)
    def test_formal_entry_is_broker_only_and_deviations_retain_original_sample(self):
        policy=p.consumer_input(task(),p.task_contract(task(),'a'*64),'N')['formal_entry_policy']
        self.assertEqual(policy['consumer_cli'],'verification/visual004_session.py --workspace <own workspace> --requestJSON <owned request JSON>')
        self.assertNotIn('observe',policy['allowed_operations']['N']);self.assertIn('observe',policy['allowed_operations']['P'])
        self.assertIn('visual004_native.py --script',policy['coordinator_only'])
        self.assertEqual(policy['public_call_limit'],48)
        self.assertTrue(policy['internal_worker_limit_is_not_extra_public_allowance'])
        self.assertIn('no replacement or restart',policy['deviation'])
    def test_utf8_code_limit_does_not_promise_unicode_json_fits(self):
        from verification.visual004_session import REQUEST_LIMIT
        from verification.visual004_native import MAX_CODE
        code='#'+'\u4e2d'*60000
        self.assertLess(len(code.encode('utf8')),MAX_CODE)
        broker=p.encoded(dict(request_id='unicode-1',operation='native_run',args=dict(code=code)))
        worker=p.encoded(dict(type='execute_code',params=dict(code=code)))
        self.assertGreater(len(broker),REQUEST_LIMIT)
        self.assertGreater(len(worker),MAX_CODE+4096)
        self.assertEqual(REQUEST_LIMIT,p.FORMAL_ENTRY_POLICY['serialized_broker_request_limit_bytes'])
        self.assertEqual(MAX_CODE+4096,p.FORMAL_ENTRY_POLICY['serialized_worker_request_limit_bytes'])
    def plan_fixture(self,root):
        destination=root/'final_protocol';asset=root/'assets/V01';asset.mkdir(parents=True)
        supplement=p.public_supplement(task());supplement_path=destination/'public_contracts/V01.json'
        supplement_path.parent.mkdir(parents=True);supplement_path.write_bytes(p.encoded(supplement))
        for name,value in [('scene.blend',b'authored fixture, not a Blender run'),('PUBLIC_TASK.json',p.encoded(task())),('PRIVATE_TRUTH.json',b'authored private placeholder')]:
            (asset/name).write_bytes(value)
        row=dict(case_id='V01',asset_sha256=p.sha(asset/'scene.blend'),public_task_sha256=p.sha(asset/'PUBLIC_TASK.json'),private_truth_sha256=p.sha(asset/'PRIVATE_TRUTH.json'),
            public_contract_path='public_contracts/V01.json',public_contract_sha256=p.supplement_sha256(supplement),public_contract_version=supplement['version'])
        plan=dict(schema='visual004-frozen-paired-plan-v2',script_pins=[],cases=[row],public_contract_policy=p.PUBLIC_CONTRACT_POLICY,score_contract_schema=p.BOUND_CONTRACT_SCHEMA,formal_entry_policy=p.FORMAL_ENTRY_POLICY)
        self.write_plan(destination,plan)
        return destination,plan,supplement,supplement_path
    def write_plan(self,destination,plan):
        raw=p.encoded(plan);(destination/'FORMAL_PLAN.json').write_bytes(raw)
        (destination/'FORMAL_PLAN_SEAL.json').write_bytes(p.encoded(dict(sha256=hashlib.sha256(raw).hexdigest())))
    def test_materialized_plan_rejects_rehashed_supplement_tamper(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);destination,plan,supplement,path=self.plan_fixture(root)
            self.assertEqual(p.verify_plan(root,output_dir=destination),plan)
            supplement['roles']['target']='Substituted target';path.write_bytes(p.encoded(supplement))
            plan['cases'][0]['public_contract_sha256']=p.supplement_sha256(supplement);self.write_plan(destination,plan)
            with self.assertRaises(ValueError):p.verify_plan(root,output_dir=destination)
    def test_materialized_plan_rejects_wrong_public_contract_version(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);destination,plan,supplement,path=self.plan_fixture(root)
            plan['cases'][0]['public_contract_version']='unreviewed-version';self.write_plan(destination,plan)
            with self.assertRaisesRegex(ValueError,'public_contract_version'):p.verify_plan(root,output_dir=destination)
    def test_missing_policy_cannot_downgrade_bound_plan_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);destination,plan,supplement,path=self.plan_fixture(root)
            del plan['public_contract_policy'];self.write_plan(destination,plan)
            with self.assertRaisesRegex(ValueError,'formal_entry_contract'):p.verify_plan(root,output_dir=destination)
    def test_legacy_schema_cannot_select_an_unbound_plan_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);destination,plan,supplement,path=self.plan_fixture(root)
            plan['schema']='visual004-frozen-paired-plan-v1';self.write_plan(destination,plan)
            with self.assertRaisesRegex(ValueError,'formal_entry_contract'):p.verify_plan(root,output_dir=destination)

if __name__=='__main__':unittest.main()
