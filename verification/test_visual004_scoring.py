"""Authored scoring counterexamples; no Blender, private assets or consumers."""
import copy,json,unittest
from verification import visual004_scoring as s

def fixture():
    contract=dict(schema=s.CONTRACT_SCHEMA,case_id='authored_case',task_run_id='new-run-01',asset_sha256='a'*64,task_sha256='b'*64)
    public=dict(case_id=contract['case_id'],required_roles=['target','reference','occluder'],
        required_fact_ids=['relation','minimum_gap_m','direction','closest_region'])
    truth=dict(case_id=contract['case_id'],expected_objects=dict(target='Object_07',reference='Object_09',occluder='Object_02'),
        facts=dict(relation=dict(kind='separation_class',value='separated',accepted_values=['separated']),
            minimum_gap_m=dict(kind='minimum_surface_distance_m',value=.002,tolerance=.0001),
            direction=dict(kind='target_to_reference_world_axis',value='+X',accepted_values=['+X']),
            closest_region=dict(kind='closest_local_region',value='short arm right face',accepted_values=['short arm right face'])))
    def evidence(identity,kind,payload,host=None,slot=0):
        return dict(evidence_id=identity,actual_host_event_id=host or 'actual-'+identity,host_block_index=slot,
            **{key:contract[key] for key in s.BINDINGS},kind=kind,delivered=True,payload=payload,payload_sha256=s.digest(payload))
    deliveries=[evidence('mesh-event','geometry',dict(data={'original_vertices':[[0,0,0]],'matrix':'authored read'}))]
    image=evidence('image-event','image',dict(png_sha256='c'*64,width=384,height=384))
    answer=dict(schema=s.ANSWER_SCHEMA,**{key:contract[key] for key in s.BINDINGS},objects=copy.deepcopy(truth['expected_objects']),
        identity_evidence_refs=['mesh-event'],facts={key:dict(status='known',value=copy.deepcopy(value['value']),
            evidence_refs=['mesh-event'],uncertainty=dict(basis='geometry',physical_metrology=False,note='Frozen mesh calculation; not physical metrology'))
            for key,value in truth['facts'].items()},visual_evidence_used=False,
        interpretation='Objects are separated; the nearest original surfaces face +X. Visibility of the patch is distinct from numeric full-geometry evidence.')
    return contract,public,truth,deliveries,image,answer

class SpatialScoringTests(unittest.TestCase):
    def setUp(self):self.contract,self.public,self.truth,self.deliveries,self.image,self.answer=fixture()
    def grade(self):return s.grade(self.answer,self.contract,self.public,self.truth,self.deliveries)
    def test_complete_numeric_answer_has_no_visual_or_causal_claim(self):
        result=self.grade();self.assertTrue(result['mechanical_complete']);self.assertIsNone(result['final_complete'])
        self.assertEqual(result['correct_counts'],dict(objects=3,facts=4));self.assertFalse(result['host_confirmed_image_delivery'])
        self.assertFalse(result['self_declared_visual_evidence_used']);self.assertFalse(result['visual_evidence_causal_gain_proven'])
        self.assertIn('interpretation_and_evidence_sufficiency',result['needs_blind_review'])
    def test_image_delivered_but_numeric_path_does_not_force_visual_use(self):
        self.deliveries.append(self.image);result=self.grade()
        self.assertTrue(result['mechanical_complete']);self.assertTrue(result['host_confirmed_image_delivery'])
        self.assertFalse(result['self_declared_visual_evidence_used']);self.assertEqual(result['image_blocks'],1)
    def test_actual_image_reference_can_support_reviewable_visual_answer(self):
        self.deliveries.append(self.image);self.answer['visual_evidence_used']=True
        fact=self.answer['facts']['direction'];fact['evidence_refs']=['image-event'];fact['uncertainty']['basis']='image'
        result=self.grade();self.assertTrue(result['mechanical_complete'])
        self.assertIn('resolution',result['facts']['direction']['evidence_sufficiency_review'])
        self.assertFalse(result['visual_evidence_causal_gain_proven'])
    def test_claiming_visual_without_actual_image_is_rejected(self):
        self.answer['visual_evidence_used']=True
        self.assertIn('visual_claim_without_referenced_image',self.grade()['issues'])
    def test_reference_to_unavailable_image_is_not_actual_delivery(self):
        self.answer['facts']['minimum_gap_m']['evidence_refs']=['invented-image']
        self.assertIn('minimum_gap_m:evidence_not_in_actual_delivery_registry',self.grade()['issues'])
    def test_wrong_source_asset_answer_rejected(self):
        self.answer['asset_sha256']='d'*64;self.assertIn('answer_binding',self.grade()['issues'])
    def test_wrong_case_answer_rejected(self):
        self.answer['case_id']='other_case';self.assertIn('answer_binding',self.grade()['issues'])
    def test_cross_run_answer_rejected(self):
        self.answer['task_run_id']='old-run';self.assertIn('answer_binding',self.grade()['issues'])
    def test_cross_run_evidence_even_with_correct_answer_is_rejected(self):
        self.deliveries[0]['task_run_id']='other-run';self.assertIn('delivery_binding',self.grade()['issues'])
    def test_missing_actual_host_event_is_rejected(self):
        del self.deliveries[0]['actual_host_event_id'];self.assertIn('delivery_host_identity',self.grade()['issues'])
    def test_self_filled_undelivered_record_is_rejected(self):
        self.deliveries[0]['delivered']=False;self.assertIn('evidence_not_delivered',self.grade()['issues'])
    def test_changed_payload_digest_is_rejected(self):
        self.deliveries[0]['payload']['data']['matrix']='changed'
        self.assertIn('delivery_payload_digest',self.grade()['issues'])
    def test_duplicate_evidence_identity_rejected(self):
        self.deliveries.append(copy.deepcopy(self.deliveries[0]));self.assertIn('duplicate_delivery_reference',self.grade()['issues'])
    def test_duplicate_actual_host_slot_rejected(self):
        repeat=copy.deepcopy(self.deliveries[0]);repeat['evidence_id']='new-label';self.deliveries.append(repeat)
        self.assertIn('duplicate_delivery_reference',self.grade()['issues'])
    def test_same_host_different_image_blocks_are_allowed_and_counted(self):
        self.deliveries.append(self.image);second=copy.deepcopy(self.image);second.update(evidence_id='image2',host_block_index=1)
        self.deliveries.append(second);result=self.grade();self.assertTrue(result['mechanical_complete']);self.assertEqual(result['image_blocks'],2)
    def test_repeated_png_at_distinct_real_events_is_counted_twice(self):
        self.deliveries.append(self.image);second=copy.deepcopy(self.image);second.update(evidence_id='image2',actual_host_event_id='new-actual-event')
        self.deliveries.append(second);self.assertEqual(self.grade()['delivered_image_pixels'],2*384*384)
    def test_image_pixel_budget_not_fooled_by_single_composite_count(self):
        self.image['payload'].update(width=1024,height=1024);self.image['payload_sha256']=s.digest(self.image['payload'])
        for index in range(3):
            item=copy.deepcopy(self.image);item.update(evidence_id='image'+str(index),actual_host_event_id='host'+str(index));self.deliveries.append(item)
        self.assertIn('delivery_image_budget',self.grade()['issues'])
    def test_image_count_budget_is_independent_of_pixel_budget(self):
        self.image['payload'].update(width=1,height=1);self.image['payload_sha256']=s.digest(self.image['payload'])
        for index in range(9):
            item=copy.deepcopy(self.image);item.update(evidence_id='image'+str(index),actual_host_event_id='host'+str(index));self.deliveries.append(item)
        self.assertIn('delivery_image_budget',self.grade()['issues'])
    def test_oversized_png_dimensions_rejected(self):
        self.image['payload']['width']=1025;self.image['payload_sha256']=s.digest(self.image['payload']);self.deliveries.append(self.image)
        self.assertIn('delivery_image_metadata',self.grade()['issues'])
    def test_object_role_omission_keeps_original_denominator(self):
        del self.answer['objects']['occluder'];result=self.grade()
        self.assertEqual(result['denominators']['objects'],3);self.assertEqual(result['correct_counts']['objects'],2)
        self.assertIn('missing_object:occluder',result['issues']);self.assertFalse(result['mechanical_complete'])
    def test_wrong_named_object_is_separate_failure(self):
        self.answer['objects']['target']='Object_01';self.assertIn('wrong_object:target',self.grade()['issues'])
    def test_unknown_identity_is_honest_but_incomplete(self):
        self.answer['objects']['target']=None;result=self.grade()
        self.assertEqual(result['objects']['target']['status'],'unknown');self.assertFalse(result['mechanical_complete'])
    def test_required_fact_omission_keeps_original_denominator(self):
        del self.answer['facts']['minimum_gap_m'];result=self.grade()
        self.assertEqual(result['denominators']['facts'],4);self.assertEqual(result['correct_counts']['facts'],3)
        self.assertIn('missing_fact:minimum_gap_m',result['issues'])
    def test_boolean_cannot_masquerade_as_number(self):
        self.answer['facts']['minimum_gap_m']['value']=True
        self.assertIn('minimum_gap_m:numeric_fact_requires_finite_number_not_boolean',self.grade()['issues'])
    def test_nonfinite_numeric_values_rejected(self):
        for number in (float('nan'),float('inf'),-float('inf')):
            with self.subTest(number=number):
                self.answer['facts']['minimum_gap_m']['value']=number
                self.assertIn('minimum_gap_m:numeric_fact_requires_finite_number_not_boolean',self.grade()['issues'])
    def test_numeric_absolute_tolerance_uses_frozen_truth(self):
        self.answer['facts']['minimum_gap_m']['value']=.00209;self.assertTrue(self.grade()['facts']['minimum_gap_m']['correct'])
        self.answer['facts']['minimum_gap_m']['value']=.00211;self.assertFalse(self.grade()['facts']['minimum_gap_m']['correct'])
    def test_extreme_json_integer_is_rejected_as_nonfinite_numeric_fact(self):
        self.answer['facts']['minimum_gap_m']['value']=10**400
        self.assertIn('minimum_gap_m:numeric_fact_requires_finite_number_not_boolean',self.grade()['issues'])
    def test_wrong_direction_is_not_repaired(self):
        self.answer['facts']['direction']['value']='-X';self.assertIn('wrong_fact:direction',self.grade()['issues'])
    def test_physical_metrology_claim_is_rejected_even_with_right_number(self):
        self.answer['facts']['minimum_gap_m']['uncertainty']['physical_metrology']=True
        self.assertIn('minimum_gap_m:unsupported_physical_precision_claim',self.grade()['issues'])
    def test_unknown_is_safe_but_not_full_credit(self):
        fact=self.answer['facts']['minimum_gap_m'];fact.update(status='unknown',value=None,evidence_refs=[])
        fact['uncertainty'].update(basis='insufficient',note='External view does not resolve this patch.')
        result=self.grade();self.assertTrue(result['facts']['minimum_gap_m']['safe_unknown']);self.assertFalse(result['mechanical_complete'])
        self.assertEqual(result['denominators']['facts'],4);self.assertEqual(result['correct_counts']['facts'],3)
    def test_unknown_cannot_be_false(self):
        fact=self.answer['facts']['relation'];fact.update(status='unknown',value=False);fact['uncertainty']['basis']='insufficient'
        self.assertIn('relation:unknown_must_be_explicit_not_false',self.grade()['issues'])
    def test_closest_region_free_text_awaits_blind_review_not_auto_fail_or_full_credit(self):
        self.answer['facts']['closest_region']['value']='end face on the outer right of the short limb'
        result=self.grade();fact=result['facts']['closest_region']
        self.assertIsNone(fact['correct']);self.assertTrue(fact['pending_blind_review']);self.assertEqual(result['pending_region_count'],1)
        self.assertFalse(result['mechanical_complete']);self.assertEqual(result['correct_counts']['facts'],3)
    def test_geometry_claim_needs_actual_geometry_evidence(self):
        self.deliveries[0]['kind']='text'
        self.assertIn('minimum_gap_m:geometry_claim_without_geometry_evidence',self.grade()['issues'])
    def test_image_basis_without_visual_declaration_rejected(self):
        self.deliveries.append(self.image);self.answer['facts']['direction']['evidence_refs']=['image-event']
        self.answer['facts']['direction']['uncertainty']['basis']='image'
        self.assertIn('direction:visual_claim_without_referenced_image',self.grade()['issues'])
    def test_mixed_basis_requires_both_actual_modalities(self):
        self.answer['visual_evidence_used']=True;self.answer['facts']['direction']['uncertainty']['basis']='mixed'
        self.assertIn('direction:mixed_claim_without_both_modalities',self.grade()['issues'])
    def test_referencing_image_for_identity_conflicts_with_denied_visual_use(self):
        self.deliveries.append(self.image);self.answer['identity_evidence_refs']=['image-event']
        self.assertIn('visual_usage_declaration_conflicts_with_image_refs',self.grade()['issues'])
    def test_duplicate_model_evidence_refs_rejected(self):
        self.answer['facts']['direction']['evidence_refs']=['mesh-event','mesh-event']
        self.assertIn('direction:evidence_refs',self.grade()['issues'])
    def test_duplicate_answer_json_key_not_silently_overwritten(self):
        with self.assertRaisesRegex(s.ScoringError,'^duplicate_answer_key$'):s.parse_answer('{"facts":{"x":1,"x":2}}')
    def test_nonfinite_answer_json_is_rejected_before_grading(self):
        with self.assertRaisesRegex(s.ScoringError,'^nonfinite_answer_json$'):s.parse_answer('{"value":NaN}')
    def test_valid_raw_json_parser_preserves_answer(self):self.assertEqual(s.parse_answer(json.dumps(self.answer)),self.answer)
    def test_v05_direction_is_target_minus_reference_not_nearest_surface_arrow(self):
        self.public['required_fact_ids']=['centroid_direction'];self.truth['facts']=dict(centroid_direction=dict(kind='aabb_center_direction_xyz',value=['+X','-Y','-Z']))
        self.answer['facts']=dict(centroid_direction=copy.deepcopy(self.answer['facts']['direction']))
        self.answer['facts']['centroid_direction']['value']=['+X','-Y','-Z'];result=self.grade();self.assertTrue(result['mechanical_complete'])
        self.assertIn('target AABB center minus reference',result['direction_scope']['aabb_center_direction_xyz'])
    def test_v06_true_means_internal_surface_not_visible_not_seen(self):
        self.public['required_fact_ids']=['visual_visibility'];self.truth['facts']=dict(visual_visibility=dict(kind='internal_surface_not_visible_from_external_opaque_view',value=True))
        self.answer['facts']=dict(visual_visibility=copy.deepcopy(self.answer['facts']['direction']))
        self.answer['facts']['visual_visibility']['value']=True;self.assertTrue(self.grade()['mechanical_complete'])
        self.answer['facts']['visual_visibility']['value']=False;self.assertIn('wrong_fact:visual_visibility',self.grade()['issues'])
    def test_boolean_fact_does_not_accept_integer_one(self):
        self.public['required_fact_ids']=['vertical_is_not_euclidean'];self.truth['facts']=dict(vertical_is_not_euclidean=dict(kind='vertical_is_not_minimum_3d_distance',value=True))
        self.answer['facts']=dict(vertical_is_not_euclidean=copy.deepcopy(self.answer['facts']['direction']))
        self.answer['facts']['vertical_is_not_euclidean']['value']=1
        self.assertIn('vertical_is_not_euclidean:boolean_fact_requires_boolean',self.grade()['issues'])
    def test_public_schema_does_not_reveal_truth_objects_or_condition(self):
        schema=s.public_answer_schema();raw=json.dumps(schema)
        self.assertNotIn('Object_07',raw);self.assertNotIn('P/N',raw);self.assertIn('null when unknown',raw)

if __name__=='__main__':unittest.main()
