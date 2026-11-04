"""Public contract tests on authored task headers, no private data or model."""
import copy,hashlib,itertools,json,math,unittest
from verification import visual004_contract as c

CASES={
    'V01':(['target','reference','occluder'],['relation','minimum_gap_m','direction','closest_region']),
    'V02':(['target','reference','occluder'],['relation','minimum_gap_m','direction','closest_region']),
    'V03':(['target','reference'],['containment','relation','minimum_gap_m','direction']),
    'V04':(['target','reference'],['relation','minimum_gap_m','direction','opposite_gap_m']),
    'V05':(['target','reference','third'],['centroid_direction','vertical_clearance_m','vertical_is_not_euclidean']),
    'V06':(['target','reference'],['relation','minimum_gap_m','direction','visual_visibility'])}

def task(case='V01'):
    roles,facts=CASES[case]
    return dict(schema='visual004-public-task-v1',case_id=case,question='Authored shape/space question, not the frozen asset answer.',
        required_roles=roles[:],required_fact_ids=facts[:],units='metres')

def definition(case,fact):return c.public_supplement(task(case))['facts'][fact]


class PublicContractTests(unittest.TestCase):
    def test_all_six_roles_facts_and_ten_kinds_have_public_definitions(self):
        kinds=set()
        for case,(roles,facts) in CASES.items():
            supplement=c.public_supplement(task(case))
            self.assertEqual(supplement['schema'],'visual004-public-semantics-v1');self.assertEqual(supplement['version'],'004A-R1')
            self.assertEqual(set(supplement['roles']),set(roles));self.assertEqual(set(supplement['facts']),set(facts))
            for row in supplement['facts'].values():
                self.assertEqual(set(row),{'kind','value_type','domain','unit','predicate','direction_semantics','description'})
                kinds.add(row['kind'])
        self.assertEqual(len(kinds),10)
    def test_role_descriptions_fix_V04_subject_reference_order(self):
        roles=c.public_supplement(task('V04'))['roles']
        self.assertIn('white octagonal post',roles['target']);self.assertIn('green U-shaped bracket',roles['reference'])
        self.assertNotIn('white',roles['reference'])
    def test_existing_minimal_portable_V01_subset_is_supported(self):
        public=dict(schema='visual004-public-task-v1',case_id='V01',question='Identify two shapes.',
            required_roles=['target','reference'],required_fact_ids=['minimum_gap_m'])
        supplement=c.public_supplement(public)
        self.assertEqual(set(supplement['facts']),{'minimum_gap_m'});self.assertNotIn('occluder',supplement['roles'])
    def test_no_correct_names_values_tolerances_or_views_in_public_supplement(self):
        for case in CASES:
            data=c.public_supplement(task(case));raw=json.dumps(data)
            for forbidden in ('Object_','"expected_objects":','"accepted_values":','"tolerance":','"best_view":','"support_result":','"png_sha256":'):
                self.assertNotIn(forbidden,raw,case)
            for row in data['facts'].values():self.assertNotIn('value',row)
    def test_complete_relation_and_containment_domains_not_only_correct_choices(self):
        self.assertEqual(definition('V01','relation')['domain'],['separated','contact','penetration'])
        self.assertEqual(definition('V03','containment')['domain'],['inside_hole_without_contact','inside_hole_contact','intersects_ring_material','outside_hole'])
    def test_V06_true_is_NOT_visible_and_false_is_not_normal_visibility_false(self):
        fact=definition('V06','visual_visibility');self.assertEqual(fact['value_type'],'boolean')
        self.assertEqual(fact['domain'],[False,True]);self.assertIn('NOT visible',fact['predicate']['true_means'])
        self.assertIn('not an ordinary visibility=false',fact['predicate']['false_means'])
        self.assertIs(c.normalize_value(True,fact),True);self.assertIs(c.normalize_value(False,fact),False)
    def test_task_digest_exact_ascii_sorted_compact_terminal_LF(self):
        public=task();public['question']='中文 question'
        raw=json.dumps(public,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')+b'\n'
        self.assertEqual(c.public_supplement(public)['task_sha256'],hashlib.sha256(raw).hexdigest())
    def test_digest_is_not_semantic_authority_after_self_rehashed_enum_tamper(self):
        public=task('V03');changed=c.public_supplement(public)
        changed['facts']['containment']['domain'].append('inside_hole')
        with self.assertRaisesRegex(ValueError,'template_mismatch'):
            c.validate_supplement(changed,public,c.supplement_sha256(changed))
    def test_self_rehashed_role_predicate_kind_and_unit_changes_are_rejected(self):
        public=task('V06');original=c.public_supplement(public)
        for change in ('role','predicate','kind','unit','extra'):
            with self.subTest(change=change):
                altered=copy.deepcopy(original)
                if change=='role':altered['roles']['target']='the reference shell'
                elif change=='predicate':altered['facts']['visual_visibility']['predicate']['true_means']='visible'
                elif change=='kind':altered['facts']['direction']['kind']='unadvertised_kind'
                elif change=='unit':altered['facts']['minimum_gap_m']['unit']='mm'
                else:altered['correct_answer']='hidden'
                with self.assertRaisesRegex(ValueError,'template_mismatch'):
                    c.validate_supplement(altered,public,c.supplement_sha256(altered))
    def test_wrong_expected_digest_and_wrong_public_question_are_rejected(self):
        public=task();supplement=c.public_supplement(public);digest=c.supplement_sha256(supplement)
        with self.assertRaisesRegex(ValueError,'supplement_digest_binding'):c.validate_supplement(supplement,public,'0'*64)
        changed=copy.deepcopy(public);changed['question']+=' changed'
        with self.assertRaisesRegex(ValueError,'template_mismatch'):c.validate_supplement(supplement,changed,digest)
        for invalid in (None,True,'x'*64,'a'*63,'A'*64):
            with self.subTest(invalid=invalid),self.assertRaisesRegex(ValueError,'expected_digest'):
                c.validate_supplement(supplement,public,invalid)
    def test_validation_and_generation_return_deep_copies(self):
        public=task('V03');original=c.public_supplement(public);saved=c.supplement_sha256(original)
        validated=c.validate_supplement(original,public,saved);validated['facts']['containment']['domain'].clear()
        self.assertEqual(c.supplement_sha256(original),saved)
        original['roles']['target']='mutated';self.assertNotEqual(c.public_supplement(public)['roles']['target'],'mutated')
    def test_unknown_case_role_fact_and_foreign_case_fact_are_rejected(self):
        for field,value in [('case_id','V07'),('required_roles',['focal']),('required_fact_ids',['unknown_fact']),
            ('required_fact_ids',['containment'])]:
            public=task();public[field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):c.public_supplement(public)
    def test_bad_public_shape_duplicates_extra_answers_and_units_rejected(self):
        for change in (dict(question=' '),dict(question=True),dict(required_roles=['target','target']),
            dict(required_fact_ids=[]),dict(units='mm'),dict(expected_objects={'target':'Object_01'})):
            public=dict(task(),**change)
            with self.subTest(change=change),self.assertRaises(ValueError):c.public_supplement(public)
    def test_strict_enum_accepts_full_domains_but_no_inside_hole_alias(self):
        fact=definition('V03','containment')
        for value in fact['domain']:self.assertEqual(c.normalize_value(value,fact),value)
        for wrong in ('inside_hole','inside hole','Inside_Hole_Without_Contact','inside_hole_contact ',True,None):
            with self.subTest(wrong=wrong),self.assertRaisesRegex(ValueError,'enum_value'):c.normalize_value(wrong,fact)
    def test_number_is_metres_finite_exact_nonbool_and_not_numeric_text(self):
        fact=definition('V01','minimum_gap_m');self.assertEqual(fact['unit'],'m')
        self.assertIs(type(c.normalize_value(2,fact)),float);self.assertEqual(c.normalize_value(2,fact),2.)
        self.assertEqual(c.normalize_value(.37,fact),.37)
        for wrong in (True,False,'0.37','37mm',None,float('nan'),float('inf'),-float('inf'),-1.,10**1000):
            with self.subTest(wrong=type(wrong).__name__),self.assertRaisesRegex(ValueError,'number_value'):c.normalize_value(wrong,fact)
    def test_signed_vertical_and_opposite_clearances_do_not_leak_positive_answer(self):
        for case,fact_id in [('V05','vertical_clearance_m'),('V04','opposite_gap_m')]:
            fact=definition(case,fact_id);self.assertIsNone(fact['domain']['minimum'])
            self.assertEqual(c.normalize_value(-.25,fact),-.25)
    def test_negative_zero_canonicalizes_to_positive_float_zero(self):
        zero=c.normalize_value(-0.,definition('V01','minimum_gap_m'))
        self.assertEqual(zero,0.);self.assertEqual(math.copysign(1.,zero),1.)
    def test_booleans_reject_numbers_strings_and_null_for_both_predicates(self):
        for fact in (definition('V05','vertical_is_not_euclidean'),definition('V06','visual_visibility')):
            for wrong in (0,1,'true','false',None):
                with self.subTest(kind=fact['kind'],wrong=wrong),self.assertRaisesRegex(ValueError,'boolean_value'):c.normalize_value(wrong,fact)
    def test_six_world_axes_are_exact_and_nearest_direction_not_center_sign(self):
        fact=definition('V01','direction');self.assertEqual(set(fact['domain']),{'+X','-X','+Y','-Y','+Z','-Z'})
        self.assertIn('nearest target surface',fact['direction_semantics'])
        for axis in fact['domain']:self.assertEqual(c.normalize_value(axis,fact),axis)
        for wrong in ('left','x+','+x','0',[1,0,0],None):
            with self.subTest(wrong=wrong),self.assertRaisesRegex(ValueError,'enum_value'):c.normalize_value(wrong,fact)
    def test_AABB_vector_has_per_axis_domains_and_target_minus_reference(self):
        fact=definition('V05','centroid_direction');self.assertIn('target AABB center - reference',fact['direction_semantics'])
        self.assertEqual(c.normalize_value(['-X','0','+Z'],fact),['-X','0','+Z'])
        for wrong in (['+Y','-X','+Z'],['+X','-Y'],['+X','-Y',0],['+X','-Y','Z'],('+X','-Y','+Z'),None):
            with self.subTest(wrong=wrong),self.assertRaisesRegex(ValueError,'axis_vector_value'):c.normalize_value(wrong,fact)
    def test_AABB_complete_27_value_domain_not_a_single_answer_vector(self):
        fact=definition('V05','centroid_direction');vectors=list(itertools.product(*fact['domain']))
        self.assertEqual(len(vectors),27)
        for vector in vectors:self.assertEqual(c.normalize_value(list(vector),fact),list(vector))
    def test_free_region_prose_is_syntax_only_and_never_an_answer_enum(self):
        fact=definition('V01','closest_region');self.assertEqual(fact['value_type'],'text')
        text='另一种局部描述; independent blind review must judge this'
        self.assertEqual(c.normalize_value(text,fact),text)
        self.assertNotIn('right arm',fact['description'])
        for wrong in ('',' \t\n','nul\x00here','a'*4097,[],None):
            with self.subTest(wrong=type(wrong).__name__),self.assertRaisesRegex(ValueError,'text_value'):c.normalize_value(wrong,fact)
    def test_normalization_rejects_unknown_or_self_modified_fact_definition(self):
        original=definition('V01','minimum_gap_m')
        for altered in (dict(original,kind='unknown_kind'),dict(original,unit='mm'),
            dict(original,domain=dict(original['domain'],minimum=-1)),dict(original,value_type='enum')):
            with self.subTest(altered=altered),self.assertRaises(ValueError):c.normalize_value(0,altered)
    def test_null_is_never_silently_promoted_into_known_value(self):
        for case in CASES:
            for fact in c.public_supplement(task(case))['facts'].values():
                with self.subTest(kind=fact['kind']),self.assertRaises(ValueError):c.normalize_value(None,fact)

if __name__=='__main__':unittest.main()
