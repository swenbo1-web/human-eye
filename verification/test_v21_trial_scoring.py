"""Authored delivered-evidence adversaries; no asset, historical truth or model."""
import copy
import unittest
from verification import v21_trial_scoring as scorer


def fixture():
    sources={}
    for index,label in enumerate(('one','two'),1):
        sources[label]=dict(source_ref=dict(scene_sha256=str(index)*64,rig_object_id='rig',mesh_object_id='mesh',
            frame=dict(number=index,subframe=0.)),source_observation_sha256=str(index+2)*64,
            original_topology_sha256='a'*64,anchor_id='head-'+label,core_half_extents_m=[.5]*3)
    contract=dict(schema=scorer.CONTRACT_SCHEMA,task_sha256='b'*64,run_nonce='c'*32,consumer_id='anonymous',
        thresholds=dict(high=1.1,low=.9),sources=sources)
    facts=[dict(triangle=0,state='measured',reason=None,principal_stretches=[1.2,.8],area_ratio=.96),
        dict(triangle=1,state='measured',reason=None,principal_stretches=[1.3,.98],area_ratio=1.274),
        dict(triangle=2,state='measured',reason=None,principal_stretches=[1.02,.7],area_ratio=.714),
        dict(triangle=3,state='unknown',reason='metric_resolution_insufficient',principal_stretches=None,area_ratio=None),
        dict(triangle=4,state='measured',reason=None,principal_stretches=[1.25,.8],area_ratio=1.)]
    reference=dict(frames=[dict(label=label,source_ref=source['source_ref'],anchor_id=source['anchor_id'],
        members=[0,1,2,4],facts=copy.deepcopy(facts),acceptable_witnesses=[0,4],
        global_states=dict(measured=4,collapsed=0,unknown=1)) for label,source in sources.items()])
    frames=[dict(label=label,**copy.deepcopy(source),core_states=dict(measured=4,collapsed=0,unknown=0),
        global_states=dict(measured=4,collapsed=0,unknown=1),rows=[dict(row,in_core=row['triangle']!=3) for row in facts])
        for label,source in sources.items()]
    payload=dict(schema=scorer.PAYLOAD_SCHEMA,**{key:contract[key] for key in scorer.IDENTITY_FIELDS},
        channel='initial_report',frames=frames,raw_report={'ordinary':'authored report'})
    record=dict(**{key:contract[key] for key in scorer.IDENTITY_FIELDS},event_id='event1',request_id='initial',
        transport_event_id='actual-tool-stdout1',delivered=True,payload=payload,payload_sha256=scorer.digest(payload))
    answer=dict(task_sha256=contract['task_sha256'],selected_triangle=0,frames=[dict(label=label,
        file_sha256=source['source_ref']['scene_sha256'],principal_stretches=[1.2,.8],area_ratio=.96,state='measured',reason=None,
        in_core=True,has_confirmed_mixed_witness=True) for label,source in sources.items()],
        interpretation='The local reliable witness does not remove global unknowns; these static moments do not certify damage or animation.')
    return contract,reference,[record],answer


class DeliveredWitnessScoring(unittest.TestCase):
    def setUp(self):self.contract,self.reference,self.deliveries,self.answer=fixture()
    def grade(self):return scorer.grade(self.answer,self.contract,self.reference,self.deliveries)
    def refreeze(self):
        for record in self.deliveries:record['payload_sha256']=scorer.digest(record['payload'])
    def expect(self,reason):
        result=self.grade();self.assertFalse(result['mechanical_complete']);self.assertEqual(result['issues'],[reason]);return result

    def test_real_delivered_rows_pass_without_claiming_worker_targeted(self):
        result=self.grade();self.assertTrue(result['mechanical_complete']);self.assertTrue(all(result['checks'].values()))
        self.assertEqual(result['worker_targeted_query']['status'],'not_applicable')
        self.assertEqual(result['selected_row_delivery_events'],{'one':['event1'],'two':['event1']})

    def test_all_acceptable_faces_not_one_hardcoded_face(self):
        for face in (0,4):
            self.answer['selected_triangle']=face
            for row in self.answer['frames']:
                row['principal_stretches']=[1.2,.8] if face==0 else [1.25,.8];row['area_ratio']=.96 if face==0 else 1.
            self.assertTrue(self.grade()['mechanical_complete'])

    def test_different_faces_cannot_join_thresholds(self):
        self.answer['selected_triangle']=1;self.expect('answer_no_acceptable_same_face')

    def test_unacceptable_face_outside_core_fails(self):
        for frame in self.reference['frames']:
            frame['members']=[1,2];frame['acceptable_witnesses']=[]
        self.deliveries=[];self.expect('answer_no_acceptable_same_face')

    def test_candidate_list_cannot_replace_delivered_rows(self):
        for frame in self.deliveries[0]['payload']['frames']:frame['rows']=[]
        self.deliveries[0]['payload']['candidate_triangle_indices']=[0,4]
        self.deliveries[0]['payload']['targeted_triangle_indices']=[0,4]
        self.refreeze();self.expect('same_face_not_delivered')

    def test_one_source_row_missing_is_not_dual_evidence(self):
        self.deliveries[0]['payload']['frames'][1]['rows']=[]
        self.refreeze();self.expect('same_face_not_delivered')

    def test_non_delivered_prepared_payload_rejected(self):
        self.deliveries[0]['delivered']=False;self.expect('evidence_not_delivered')

    def test_payload_digest_tamper_rejected_before_content(self):
        self.deliveries[0]['payload']['raw_report']['ordinary']='changed';self.expect('delivery_payload_digest')

    def test_wrong_source_saved_frame_anchor_observation_and_topology(self):
        for field in scorer.SOURCE_FIELDS:
            self.setUp();frame=self.deliveries[0]['payload']['frames'][0]
            frame[field]=None;self.refreeze()
            with self.subTest(field=field):self.expect('delivery_source_binding')

    def test_boolean_frame_number_and_subframe_cannot_match_numeric_identity(self):
        for field,value in (('number',True),('subframe',False)):
            self.setUp();self.deliveries[0]['payload']['frames'][0]['source_ref']['frame'][field]=value
            self.refreeze()
            with self.subTest(field=field):self.expect('delivery_source_binding')

    def test_cross_run_task_and_consumer_delivery_references_rejected(self):
        for field in scorer.IDENTITY_FIELDS:
            self.setUp();self.deliveries[0][field]='wrong'
            with self.subTest(field=field):self.expect('delivery_identity_binding')

    def test_payload_cross_run_binding_cannot_be_self_hashed_away(self):
        self.deliveries[0]['payload']['run_nonce']='d'*32;self.refreeze();self.expect('payload_identity_binding')

    def test_duplicate_event_request_or_transport_references_rejected(self):
        for field in ('event_id','request_id','transport_event_id'):
            self.setUp();other=copy.deepcopy(self.deliveries[0])
            for key in ('event_id','request_id','transport_event_id'):other[key]+='-new'
            other[field]=self.deliveries[0][field];self.deliveries.append(other)
            with self.subTest(field=field):self.expect('duplicate_delivery_reference')

    def test_same_fact_really_delivered_twice_is_counted_as_two_events(self):
        other=copy.deepcopy(self.deliveries[0])
        other.update(event_id='event2',request_id='lookup1',transport_event_id='stdout2')
        other['payload']['channel']='snapshot_lookup';self.deliveries.append(other);self.refreeze()
        result=self.grade();self.assertTrue(result['mechanical_complete'])
        self.assertEqual(result['selected_row_delivery_events']['one'],['event1','event2'])

    def test_snapshot_lookup_can_supply_rows_omitted_by_initial_report(self):
        lookup=copy.deepcopy(self.deliveries[0]);lookup.update(event_id='lookup',request_id='lookup',transport_event_id='stdout2')
        lookup['payload']['channel']='snapshot_lookup'
        for frame in self.deliveries[0]['payload']['frames']:frame['rows']=[]
        self.deliveries.append(lookup);self.refreeze();self.assertTrue(self.grade()['mechanical_complete'])

    def test_lookup_wrong_original_index_not_corrected(self):
        self.deliveries[0]['payload']['frames'][0]['rows'][0]['triangle']=99
        self.refreeze();self.expect('delivery_original_triangle')

    def test_duplicate_rows_and_labels_rejected(self):
        self.deliveries[0]['payload']['frames'][0]['rows'].append(copy.deepcopy(self.deliveries[0]['payload']['frames'][0]['rows'][0]))
        self.refreeze();self.expect('delivery_original_triangle')
        self.setUp();self.deliveries[0]['payload']['frames'][1]['label']='one';self.refreeze();self.expect('delivery_frame_labels')

    def test_delivered_numbers_cannot_be_fabricated_then_rehashed(self):
        self.deliveries[0]['payload']['frames'][0]['rows'][0]['principal_stretches'][0]=9
        self.refreeze();self.expect('delivery_metric_mismatch')

    def test_unknown_delivered_as_measured_is_rejected(self):
        self.deliveries[0]['payload']['frames'][0]['rows'][3].update(state='measured',reason=None,principal_stretches=[1,1],area_ratio=1)
        self.refreeze();self.expect('delivery_metric_mismatch')

    def test_wrong_core_member_delivery_rejected(self):
        self.deliveries[0]['payload']['frames'][0]['rows'][0]['in_core']=False
        self.refreeze();self.expect('delivery_core_membership')

    def test_wrong_task_source_answer_and_boolean_face_rejected(self):
        self.answer['task_sha256']='d'*64;self.expect('answer_task_binding')
        self.setUp();self.answer['frames'][0]['file_sha256']='d'*64;self.expect('answer_source_binding')
        self.setUp();self.answer['selected_triangle']=False;self.expect('answer_no_acceptable_same_face')

    def test_answer_extra_and_duplicate_rows_rejected(self):
        self.answer['frames'].append(copy.deepcopy(self.answer['frames'][0]));self.expect('answer_rows')
        self.setUp();self.answer['frames'][1]['label']='one';self.expect('answer_labels')

    def test_answer_values_are_finite_exact_numeric_shape(self):
        for value in (True,float('nan'),float('inf'),'1.2'):
            self.setUp();self.answer['frames'][0]['principal_stretches'][0]=value
            with self.subTest(value=value):self.expect('answer_numbers')

    def test_numeric_tolerance_is_fixed_and_independent(self):
        self.answer['frames'][0]['principal_stretches'][0]+=1e-10;self.assertTrue(self.grade()['mechanical_complete'])
        self.answer['frames'][0]['principal_stretches'][0]+=1e-6;self.expect('answer_numbers')

    def test_reference_acceptable_set_must_be_complete(self):
        self.reference['frames'][0]['acceptable_witnesses']=[0];self.expect('reference_acceptable_set')

    def test_reference_complete_facts_cannot_be_a_summary(self):
        self.reference['frames'][0]['facts'].pop(2);self.expect('reference_original_triangle')

    def test_reference_cannot_rebind_source_or_anchor(self):
        self.reference['frames'][0]['source_ref']=None;self.expect('reference_source_binding')
        self.setUp();self.reference['frames'][0]['anchor_id']='other';self.expect('reference_anchor_binding')

    def test_malformed_legacy_anchor_record_does_not_throw_or_override_explicit_anchor(self):
        self.reference['frames'][0]['anchor']=None
        self.assertTrue(self.grade()['mechanical_complete'])
        self.reference['frames'][0].pop('anchor_id');self.expect('reference_anchor_binding')

    def test_boolean_reference_original_triangle_is_rejected(self):
        self.reference['frames'][0]['facts'][0]['triangle']=False;self.expect('reference_original_triangle')

    def test_core_states_count_does_not_prove_no_same_face_witness(self):
        # Make one frame genuinely negative while the other retains the witness.
        self.reference['frames'][0]['members']=[1,2];self.reference['frames'][0]['acceptable_witnesses']=[]
        frame=self.deliveries[0]['payload']['frames'][0];frame['rows']=[dict(frame['rows'][0],in_core=False)]
        frame['core_states']=dict(measured=2,collapsed=0,unknown=0)
        self.answer['frames'][0]['in_core']=False;self.answer['frames'][0]['has_confirmed_mixed_witness']=False
        self.refreeze();self.expect('insufficient_scope_evidence')
        frame['core_confirmation']=False;self.refreeze();self.assertTrue(self.grade()['mechanical_complete'])

    def test_core_unknown_is_not_a_false_negative(self):
        source=self.reference['frames'][0];source['members']=[1,2,3];source['acceptable_witnesses']=[]
        delivered=self.deliveries[0]['payload']['frames'][0]
        delivered['core_states']=dict(measured=2,collapsed=0,unknown=1)
        for row in delivered['rows']:row['in_core']=row['triangle'] in source['members']
        self.answer['frames'][0]['in_core']=False;self.answer['frames'][0]['has_confirmed_mixed_witness']=False
        self.refreeze();self.expect('answer_confirmation_scope')
        self.answer['frames'][0]['has_confirmed_mixed_witness']=None;self.assertTrue(self.grade()['mechanical_complete'])

    def excluded_high(self,unknown=False):
        frame=self.reference['frames'][0]
        for index in (0,1,2,4):
            row=frame['facts'][index];row['principal_stretches'][0]=1.05;row['area_ratio']=1.05*row['principal_stretches'][1]
        frame['acceptable_witnesses']=[]
        if unknown:frame['members']=[0,1,2,3,4]
        delivered=self.deliveries[0]['payload']['frames'][0]
        delivered['rows']=[dict(frame['facts'][0],in_core=True)]
        delivered['core_states']=dict(measured=4,collapsed=0,unknown=int(unknown))
        delivered['core_extrema']=dict(max_principal_stretch=1.05,min_principal_stretch=.7,
            min_area_ratio=.735,max_area_ratio=1.029)
        self.answer['frames'][0].update(principal_stretches=[1.05,.8],area_ratio=.84,
            has_confirmed_mixed_witness=None if unknown else False)
        self.refreeze();return delivered

    def test_complete_core_maximum_can_prove_false_without_all_rows(self):
        delivered=self.excluded_high();self.assertTrue(self.grade()['mechanical_complete'])
        delivered['core_extrema']={'max_principal_stretch':1.05}
        self.refreeze();self.assertTrue(self.grade()['mechanical_complete'])

    def test_complete_core_minimum_can_prove_false_without_all_rows(self):
        frame=self.reference['frames'][0]
        for index in (0,1,2,4):
            row=frame['facts'][index];row['principal_stretches'][1]=.95;row['area_ratio']=.95*row['principal_stretches'][0]
        frame['acceptable_witnesses']=[]
        delivered=self.deliveries[0]['payload']['frames'][0]
        delivered['rows']=[dict(frame['facts'][0],in_core=True)]
        delivered['core_extrema']={'min_principal_stretch':.95}
        self.answer['frames'][0].update(principal_stretches=[1.2,.95],area_ratio=1.14,has_confirmed_mixed_witness=False)
        self.refreeze();self.assertTrue(self.grade()['mechanical_complete'])

    def test_excluding_extrema_with_core_unknown_proves_unknown_not_false(self):
        self.excluded_high(unknown=True);self.assertTrue(self.grade()['mechanical_complete'])
        self.answer['frames'][0]['has_confirmed_mixed_witness']=False;self.expect('answer_confirmation_scope')

    def test_separate_threshold_extrema_do_not_prove_same_face_or_absence(self):
        self.reference['frames'][0]['members']=[1,2];self.reference['frames'][0]['acceptable_witnesses']=[]
        delivered=self.deliveries[0]['payload']['frames'][0]
        delivered['rows']=[dict(delivered['rows'][0],in_core=False)]
        delivered['core_states']=dict(measured=2,collapsed=0,unknown=0)
        delivered['core_extrema']={'max_principal_stretch':1.3,'min_principal_stretch':.7}
        self.answer['frames'][0].update(in_core=False,has_confirmed_mixed_witness=False)
        self.refreeze();self.expect('insufficient_scope_evidence')
        self.answer['frames'][0]['has_confirmed_mixed_witness']=True;self.expect('answer_confirmation_scope')

    def test_extrema_without_complete_core_counts_do_not_prove_absence(self):
        delivered=self.excluded_high();del delivered['core_states']
        self.refreeze();self.expect('insufficient_scope_evidence')

    def test_area_extrema_alone_do_not_prove_direction_threshold_exclusion(self):
        delivered=self.excluded_high();delivered['core_extrema']={'min_area_ratio':.735,'max_area_ratio':1.029}
        self.refreeze();self.expect('insufficient_scope_evidence')

    def test_wrong_or_nonfinite_extrema_cannot_be_rehashed_into_evidence(self):
        for value in (1.04,True,float('inf'),'1.05'):
            self.setUp();delivered=self.excluded_high();delivered['core_extrema']['max_principal_stretch']=value
            if value==float('inf'):
                self.deliveries[0]['payload_sha256']='not-valid-json';self.expect('malformed_input')
            else:
                self.refreeze();self.expect('delivery_core_extrema')

    def test_extrema_threshold_equality_and_tolerance_crossing_do_not_exclude(self):
        frame=self.reference['frames'][0];frame['members']=[1,2];frame['acceptable_witnesses']=[]
        frame['facts'][1].update(principal_stretches=[1.1,.98],area_ratio=1.078)
        delivered=self.deliveries[0]['payload']['frames'][0]
        delivered['rows']=[dict(delivered['rows'][0],in_core=False)]
        delivered['core_states']=dict(measured=2,collapsed=0,unknown=0)
        self.answer['frames'][0].update(in_core=False,has_confirmed_mixed_witness=False)
        for maximum in (1.1,1.1-1e-10):
            delivered['core_extrema']={'max_principal_stretch':maximum}
            self.refreeze();self.expect('insufficient_scope_evidence')

    def test_global_unknown_counts_must_have_been_delivered(self):
        del self.deliveries[0]['payload']['frames'][0]['global_states'];self.refreeze();self.expect('insufficient_scope_evidence')
        self.setUp();self.deliveries[0]['payload']['frames'][0]['global_states']['unknown']=0
        self.refreeze();self.expect('delivery_global_states')

    def test_absent_optional_core_summary_does_not_stop_positive_row_inference(self):
        for frame in self.deliveries[0]['payload']['frames']:
            frame.pop('core_states');frame['rows']=[frame['rows'][0]]
        self.refreeze();self.assertTrue(self.grade()['mechanical_complete'])

    def test_malformed_inputs_fail_closed_without_throwing(self):
        for value in (None,[],True):
            self.assertFalse(scorer.grade(value,self.contract,self.reference,self.deliveries)['mechanical_complete'])
        self.contract['sources']['two']['original_topology_sha256']='d'*64;self.expect('contract_original_topology')

    def test_row_order_has_no_effect_and_inputs_are_not_mutated(self):
        self.answer['frames'].reverse();self.reference['frames'].reverse()
        for frame in self.deliveries[0]['payload']['frames']:frame['rows'].reverse()
        self.refreeze();before=copy.deepcopy((self.contract,self.reference,self.deliveries,self.answer))
        self.assertTrue(self.grade()['mechanical_complete'])
        self.assertEqual((self.contract,self.reference,self.deliveries,self.answer),before)


if __name__=='__main__':unittest.main()
