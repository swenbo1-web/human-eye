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
        for key in ('task','contract','rules','evidence_reference_rules','answer_schema','task_window_seconds','image_budget','text_budget','max_public_calls'):
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
            plan=dict(script_pins=[],cases=[]);raw=p.encoded(plan)
            (new/'FORMAL_PLAN.json').write_bytes(raw)
            (new/'FORMAL_PLAN_SEAL.json').write_bytes(p.encoded(dict(sha256=hashlib.sha256(raw).hexdigest())))
            self.assertEqual(p.verify_plan(root,output_dir=new),plan)
            self.assertEqual(old.read_bytes(),b'old sealed generation\n')
            (new/'FORMAL_PLAN.json').write_bytes(raw+b' ')
            with self.assertRaisesRegex(ValueError,'plan_changed'):p.verify_plan(root,output_dir=new)

if __name__=='__main__':unittest.main()
