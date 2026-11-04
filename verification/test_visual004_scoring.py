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

def bound_fixture(case_id='V03'):
    """Independent authored values, not the actual task truth or HE outputs."""
    from verification.visual004_contract import public_supplement,supplement_sha256
    roles=['target','reference']
    if case_id in ('V01','V02'):roles+=['occluder']
    if case_id=='V05':roles+=['third']
    facts={
        'V01':dict(relation=('separation_class','separated'),minimum_gap_m=('minimum_surface_distance_m',.002),
            direction=('target_to_reference_world_axis','+X'),closest_region=('closest_local_region','authored short arm face')),
        'V02':dict(relation=('separation_class','separated'),minimum_gap_m=('minimum_surface_distance_m',.002),
            direction=('target_to_reference_world_axis','+X'),closest_region=('closest_local_region','authored inclined face')),
        'V03':dict(containment=('pin_location_relative_to_hole','inside_hole_without_contact'),
            relation=('separation_class','separated'),minimum_gap_m=('minimum_surface_distance_m',.003),direction=('target_to_reference_world_axis','+X')),
        'V04':dict(relation=('separation_class','separated'),minimum_gap_m=('minimum_surface_distance_m',.004),
            direction=('target_to_reference_world_axis','+X'),opposite_gap_m=('opposite_side_clearance_m',.012)),
        'V05':dict(centroid_direction=('aabb_center_direction_xyz',['+X','-Y','0']),
            vertical_clearance_m=('vertical_clearance_m',.02),vertical_is_not_euclidean=('vertical_is_not_minimum_3d_distance',True)),
        'V06':dict(relation=('separation_class','separated'),minimum_gap_m=('minimum_surface_distance_m',.004),
            direction=('target_to_reference_world_axis','+X'),visual_visibility=('internal_surface_not_visible_from_external_opaque_view',True))}[case_id]
    public=dict(schema='visual004-public-task-v1',case_id=case_id,question='Authored finite scoring case, no geometry answer is supplied.',
        required_roles=roles,required_fact_ids=list(facts),units='metres')
    supplement=public_supplement(public)
    contract=dict(schema=s.BOUND_CONTRACT_SCHEMA,case_id=case_id,task_run_id='bound-run-'+case_id,
        asset_sha256='a'*64,task_sha256=s.digest(public),public_contract_sha256=supplement_sha256(supplement))
    truth=dict(case_id=case_id,expected_objects={role:'Object_'+str(7+index).zfill(2) for index,role in enumerate(roles)},facts={})
    for key,(kind,value) in facts.items():
        row=dict(kind=kind,value=copy.deepcopy(value))
        if type(value) is float:row['tolerance']=.0001
        elif type(value) is str:row['accepted_values']=[value]
        truth['facts'][key]=row
    payload=dict(data={'source':'independent authored geometry'})
    delivery=dict(evidence_id='text:read-1',actual_host_event_id='actual-bound-event',host_block_index=0,
        **{key:contract[key] for key in s.BOUND_BINDINGS},kind='geometry',delivered=True,payload=payload,payload_sha256=s.digest(payload))
    answer=dict(schema=s.BOUND_ANSWER_SCHEMA,**{key:contract[key] for key in s.BOUND_BINDINGS},
        objects=copy.deepcopy(truth['expected_objects']),identity_evidence_refs=['text:read-1'],
        facts={key:dict(status='known',value=copy.deepcopy(row['value']),evidence_refs=['text:read-1'],
            uncertainty=dict(basis='geometry',physical_metrology=False,note='Authored geometry; no physical accuracy claim.'))
            for key,row in truth['facts'].items()},visual_evidence_used=False,
        interpretation='Geometry facts are independent of whether an opaque external image exposes the corresponding surfaces.')
    return contract,public,truth,[delivery],answer,supplement


class BoundPublicContractScoringTests(unittest.TestCase):
    def setUp(self):self.use_case('V03')
    def use_case(self,case_id):
        self.contract,self.public,self.truth,self.deliveries,self.answer,self.supplement=bound_fixture(case_id)
    def grade(self):return s.grade(self.answer,self.contract,self.public,self.truth,self.deliveries,public_contract=self.supplement)
    def rebind_supplement(self):
        from verification.visual004_contract import supplement_sha256
        digest=supplement_sha256(self.supplement);self.contract['public_contract_sha256']=digest
        self.answer['public_contract_sha256']=digest
        for row in self.deliveries:row['public_contract_sha256']=digest
    def test_all_six_authored_canonical_controls_remain_distinct_from_visual_gain(self):
        for case_id in ('V01','V02','V03','V04','V05','V06'):
            with self.subTest(case=case_id):
                self.use_case(case_id);result=self.grade();self.assertTrue(result['mechanical_complete'],result['issues'])
                self.assertEqual(result['schema'],'visual004-spatial-score-v2');self.assertIsNone(result['final_complete'])
                self.assertFalse(result['visual_evidence_causal_gain_proven'])
    def test_legacy_no_argument_public_schema_is_unchanged(self):
        self.assertEqual(s.public_answer_schema()['schema'],s.ANSWER_SCHEMA)
        self.assertEqual(s.public_answer_schema()['bindings'],list(s.BINDINGS))
    def test_bound_schema_references_single_supplied_public_semantics_without_answer(self):
        schema=s.public_answer_schema(self.supplement)
        self.assertEqual(schema['schema'],s.BOUND_ANSWER_SCHEMA);self.assertEqual(schema['bindings'],list(s.BOUND_BINDINGS))
        self.assertEqual(schema['public_contract_sha256'],self.contract['public_contract_sha256'])
        self.assertIn('public_contract.roles',schema['role_definitions']);self.assertIn('public_contract.facts',schema['fact_definitions'])
        self.assertNotIn('public_contract',schema)
        for row in self.supplement['facts'].values():
            self.assertTrue({'kind','value_type','domain','unit','predicate','direction_semantics','description'}<=set(row))
        self.assertNotIn('Object_07',json.dumps(schema));self.assertNotIn('0.003',json.dumps(schema))
    def test_missing_supplement_does_not_fall_back_to_v1(self):
        result=s.grade(self.answer,self.contract,self.public,self.truth,self.deliveries)
        self.assertIn('public_contract_required',result['issues']);self.assertFalse(result['binding_valid'])
        self.assertEqual(result['schema'],'visual004-spatial-score-v2')
    def test_v2_contract_missing_hash_is_rejected(self):
        del self.contract['public_contract_sha256'];self.assertIn('contract_schema',self.grade()['issues'])
    def test_v2_contract_malformed_hash_is_rejected(self):
        self.contract['public_contract_sha256']='a'*63;self.assertIn('contract_public_binding',self.grade()['issues'])
    def test_v2_answer_missing_hash_is_rejected(self):
        del self.answer['public_contract_sha256'];self.assertIn('answer_schema',self.grade()['issues'])
    def test_v2_answer_wrong_hash_is_rejected(self):
        self.answer['public_contract_sha256']='b'*64;self.assertIn('answer_binding',self.grade()['issues'])
    def test_v2_evidence_missing_hash_is_rejected(self):
        del self.deliveries[0]['public_contract_sha256'];self.assertIn('delivery_binding',self.grade()['issues'])
    def test_every_v2_evidence_record_needs_same_public_hash(self):
        extra=copy.deepcopy(self.deliveries[0]);extra.update(evidence_id='text:read-2',actual_host_event_id='another-event',public_contract_sha256='c'*64)
        self.deliveries.append(extra);self.assertIn('delivery_binding',self.grade()['issues'])
    def test_self_rehashed_narrowed_enum_is_not_trusted(self):
        self.supplement['facts']['containment']['domain']=['inside_hole_without_contact'];self.rebind_supplement()
        self.assertIn('public_contract_invalid',self.grade()['issues'])
    def test_self_rehashed_description_tamper_is_not_trusted(self):
        self.supplement['roles']['target']='Now means the opposite role.';self.rebind_supplement()
        self.assertIn('public_contract_invalid',self.grade()['issues'])
    def test_valid_other_case_supplement_with_matching_self_hash_still_rejected(self):
        self.supplement=bound_fixture('V04')[-1];self.rebind_supplement()
        self.assertIn('public_contract_invalid',self.grade()['issues'])
    def test_modified_public_task_without_new_external_binding_is_rejected(self):
        self.public['question']='Changed after the fixed contract.'
        self.assertIn('reference_task_binding',self.grade()['issues'])
    def test_v1_contract_cannot_sneak_supplement_into_historical_path(self):
        old=fixture();result=s.grade(old[-1],old[0],old[1],old[2],old[3],public_contract=self.supplement)
        self.assertIn('public_contract_requires_bound_v2_contract',result['issues'])
    def test_v1_answer_is_not_accepted_by_v2_contract(self):
        self.answer['schema']=s.ANSWER_SCHEMA;self.assertIn('answer_schema',self.grade()['issues'])
    def test_v03_ambiguous_inside_hole_is_rejected_instead_of_inferred_contact(self):
        self.answer['facts']['containment']['value']='inside_hole'
        self.assertIn('containment:public_fact_value_domain',self.grade()['issues'])
    def test_v03_explicit_wrong_contact_is_valid_domain_but_wrong_fact(self):
        self.answer['facts']['containment']['value']='inside_hole_contact';result=self.grade()
        self.assertFalse(result['facts']['containment']['correct']);self.assertIn('wrong_fact:containment',result['issues'])
    def test_all_v03_explicit_alternatives_are_graded_without_alias(self):
        for wrong in ('inside_hole_contact','intersects_ring_material','outside_hole'):
            with self.subTest(value=wrong):
                self.answer['facts']['containment']['value']=wrong;result=self.grade()
                self.assertEqual(result['facts']['containment']['status'],'known');self.assertFalse(result['facts']['containment']['correct'])
    def test_v06_true_and_false_keep_explicit_not_visible_predicate(self):
        self.use_case('V06');predicate=self.supplement['facts']['visual_visibility']['predicate']
        self.assertTrue(predicate['true_means']);self.assertTrue(predicate['false_means'])
        self.assertTrue(self.grade()['mechanical_complete']);self.answer['facts']['visual_visibility']['value']=False
        self.assertIn('wrong_fact:visual_visibility',self.grade()['issues'])
    def test_v06_bool_reversal_cannot_be_encoded_as_integer(self):
        self.use_case('V06');self.answer['facts']['visual_visibility']['value']=0
        self.assertIn('visual_visibility:public_fact_value_domain',self.grade()['issues'])
    def test_v04_swapped_roles_and_reversed_direction_are_not_repaired(self):
        self.use_case('V04');roles=self.answer['objects'];roles['target'],roles['reference']=roles['reference'],roles['target']
        self.answer['facts']['direction']['value']='-X';result=self.grade()
        self.assertIn('wrong_object:target',result['issues']);self.assertIn('wrong_object:reference',result['issues'])
        self.assertIn('wrong_fact:direction',result['issues'])
    def test_all_v04_wrong_facts_still_fail_with_correct_format_and_hashes(self):
        self.use_case('V04')
        for key,value in dict(relation='contact',minimum_gap_m=.04,direction='-X',opposite_gap_m=.12).items():self.answer['facts'][key]['value']=value
        result=self.grade();self.assertEqual(result['correct_counts']['facts'],0);self.assertFalse(result['mechanical_complete'])
        self.assertTrue(all('wrong_fact:'+key in result['issues'] for key in self.answer['facts']))
    def test_v2_numeric_boolean_is_rejected_before_truth_comparison(self):
        self.answer['facts']['minimum_gap_m']['value']=True
        self.assertIn('minimum_gap_m:public_fact_value_domain',self.grade()['issues'])
    def test_v2_numeric_nonfinite_is_rejected_before_truth_comparison(self):
        self.answer['facts']['minimum_gap_m']['value']=float('nan')
        self.assertIn('minimum_gap_m:public_fact_value_domain',self.grade()['issues'])
    def test_minimum_surface_distance_cannot_be_negative(self):
        self.answer['facts']['minimum_gap_m']['value']=-.003
        self.assertIn('minimum_gap_m:public_fact_value_domain',self.grade()['issues'])
    def test_numeric_error_still_uses_frozen_truth_tolerance(self):
        self.answer['facts']['minimum_gap_m']['value']=.00309;self.assertTrue(self.grade()['facts']['minimum_gap_m']['correct'])
        self.answer['facts']['minimum_gap_m']['value']=.00311;self.assertIn('wrong_fact:minimum_gap_m',self.grade()['issues'])
    def test_v2_known_fact_still_requires_actual_evidence(self):
        self.answer['facts']['minimum_gap_m']['evidence_refs']=[]
        self.assertIn('minimum_gap_m:known_fact_needs_actual_evidence',self.grade()['issues'])
    def test_v2_unknown_remains_safe_but_incomplete(self):
        row=self.answer['facts']['containment'];row.update(status='unknown',value=None,evidence_refs=[]);row['uncertainty']['basis']='insufficient'
        result=self.grade();self.assertEqual(result['safe_unknown_count'],1);self.assertFalse(result['mechanical_complete'])
    def test_v2_unknown_cannot_be_a_false_fact(self):
        row=self.answer['facts']['containment'];row.update(status='unknown',value=False);row['uncertainty']['basis']='insufficient'
        self.assertIn('containment:unknown_must_be_explicit_not_false',self.grade()['issues'])
    def test_public_vector_domain_requires_axis_order(self):
        self.use_case('V05');self.answer['facts']['centroid_direction']['value']=['+Y','-X','0']
        self.assertIn('centroid_direction:public_fact_value_domain',self.grade()['issues'])
    def test_valid_wrong_v05_vector_does_not_get_normalized_to_correct(self):
        self.use_case('V05');self.answer['facts']['centroid_direction']['value']=['-X','+Y','0']
        self.assertIn('wrong_fact:centroid_direction',self.grade()['issues'])
    def test_free_local_region_still_requires_blind_review(self):
        self.use_case('V01');self.answer['facts']['closest_region']['value']='another description requiring semantic review'
        result=self.grade();self.assertIsNone(result['facts']['closest_region']['correct']);self.assertEqual(result['pending_region_count'],1)
    def test_public_kind_disagreement_with_frozen_truth_is_rejected(self):
        self.truth['facts']['minimum_gap_m']['kind']='opposite_side_clearance_m'
        self.assertIn('public_truth_kind_mismatch',self.grade()['issues'])
    def test_frozen_truth_value_must_itself_obey_public_domain(self):
        self.truth['facts']['containment']['value']='inside_hole';self.truth['facts']['containment']['accepted_values']=['inside_hole']
        self.assertIn('public_truth_value_domain',self.grade()['issues'])
    def test_frozen_truth_accepted_values_cannot_add_ambiguous_alias(self):
        self.truth['facts']['containment']['accepted_values'].append('inside_hole')
        self.assertIn('public_truth_value_domain',self.grade()['issues'])
    def test_forged_visual_declaration_still_fails_in_bound_mode(self):
        self.answer['visual_evidence_used']=True;self.assertIn('visual_claim_without_referenced_image',self.grade()['issues'])
    def test_bound_image_registry_hash_is_required_and_not_causal_proof(self):
        payload=dict(png_sha256='c'*64,width=384,height=384)
        row=dict(evidence_id='image:read-2:delivery-1:image-1',actual_host_event_id='image-actual-event',host_block_index=1,
            **{key:self.contract[key] for key in s.BOUND_BINDINGS},kind='image',delivered=True,payload=payload,payload_sha256=s.digest(payload))
        self.deliveries.append(row);result=self.grade();self.assertTrue(result['host_confirmed_image_delivery'])
        self.assertFalse(result['self_declared_visual_evidence_used']);self.assertFalse(result['visual_evidence_causal_gain_proven'])
        del row['public_contract_sha256'];self.assertIn('delivery_binding',self.grade()['issues'])


if __name__=='__main__':unittest.main()
