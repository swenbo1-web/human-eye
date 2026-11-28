"""Run the component scorer on closed originals and focused raw-packet mutations."""
import copy
import importlib.util
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
ROOT=Path(sys.argv[1]).resolve(strict=True)
OLD=ROOT.parent/'M4-NEAREST-SURFACE-TASK-INTENT-001'
PRE=ROOT/'preflight'
OUT=PRE/'SCORE_CONTROLS.json'

spec=importlib.util.spec_from_file_location('component_formal_scorer',HERE/'score_public.py')
score=importlib.util.module_from_spec(spec)
spec.loader.exec_module(score)
need,read,pin=score.need,score.read,score.pin


def write(path,value):
    with Path(path).open('x',encoding='utf8',newline='\n') as f:
        json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False)
        f.write('\n')


def archived_controls():
    freeze=read(OLD/'preflight/FROZEN_EXECUTION.json')
    fixture=freeze['fixture']
    truth,geometry=(read(score.intent.checked_pin(fixture[k])) for k in ('truth','source'))
    annotations=read(OLD/'postflight/NATURAL_ANSWER_ANNOTATIONS.json')
    cases={}
    pins=[OLD/name for name in ('preflight/FROZEN_EXECUTION.json','postflight/NATURAL_ANSWER_ANNOTATIONS.json',
                                'FORMAL_SCORE.json','sealed/RAW_INDEX.json')]
    pins.extend(score.intent.checked_pin(fixture[k]) for k in ('truth','source'))
    for slot in score.ORDER:
        folder=OLD/'slots'/slot
        payload=score.slot_score(folder,freeze,geometry,truth,slot,annotations[slot])
        work=payload['attribution']
        expected_far=8 if slot=='A2' else 7
        need(payload['status']=='observed' and payload['quality_passed'] and payload['product_nearest_first_raster']
             and not payload['component_measured_delivered'] and len(work['full_target_mesh_reads'])==1
             and len(work['near_distance_followups'])==1
             and work['near_distance_followups'][0]['kind']=='near_new_scope_same_distance'
             and work['far_first_measurement']['ordinal']==expected_far,'archived_A_reference_regression/'+slot)
        for name in ('post_capture.json','closed.json','wire/INDEX.jsonl','consumer/stdout.raw.bin',
                     'consumer/final.txt','frames.jsonl','physical_frames.jsonl','CONSUMER_DELIVERY.json'):
            pins.append(folder/name)
        for wire in score.intent.json_lines(folder/'wire/INDEX.jsonl'):
            pins.extend(score.intent.checked_pin(wire[side]) for side in ('tx','rx'))
        for image in payload['images']:
            pins.extend(folder/image[k] for k in ('png','npz'))
        cases[slot]=payload
    k=copy.deepcopy(annotations['B1'])
    k['distances']=[]
    k_score=score.slot_score(OLD/'slots/B1',freeze,geometry,truth,'B1',k)
    need(k_score['quality_passed'] and not k_score['distances_required']
         and k_score['voluntary_K_gap_count']==0,'K_candidate_arm_incorrectly_requires_both_distances')
    t=copy.deepcopy(annotations['A2'])
    t['distances']=t['distances'][:1]
    t_score=score.slot_score(OLD/'slots/A2',freeze,geometry,truth,'A2',t)
    need(not t_score['quality_passed'] and t_score['distances_required'] and t_score['single_image_common_quality'],
         'T_baseline_arm_accepted_missing_second_distance')
    bad=copy.deepcopy(annotations['A1'])
    bad['pixel']['source_triangle_index']+=1
    invalid=score.slot_score(OLD/'slots/A1',freeze,geometry,truth,'A1',bad)
    need(not invalid['quality_passed'] and invalid['answer']['original_png_link']
         and not invalid['answer']['same_frame_pixel_in_nearest_piece'],
         'declared_wrong_source_pixel_accepted')
    details={'historical_all_four':{slot:{
          'artifacts_closed':item['strict_closure'],
          'first_product_raster':item['product_nearest_first_raster'],
          'one_target_mesh_and_near_repeat':True,
          'far_measurement_ordinal':item['attribution']['far_first_measurement']['ordinal']} for slot,item in cases.items()},
        'K_without_voluntary_distances_passes':True,'T_missing_other_piece_fails':True,
        'actual_PNG_with_wrong_claimed_source_fails':True}
    return details,cases,list(map(pin,dict.fromkeys(pins))),truth,geometry


def rehash(reference):
    reference['region_id']='source-region:'+score.intent.old.fingerprint({k:v for k,v in reference.items() if k!='region_id'})


def raised(expected,call):
    try:
        call()
    except ValueError as error:
        need(str(error)==expected,'negative_control_wrong_failure/'+str(error))
        return True
    raise ValueError('negative_control_was_accepted/'+expected)


def actual_b_component_controls(truth,geometry):
    capture_path=PRE/'SEALED_CAPTURE.json'
    capture=read(capture_path)
    domain=score.intent.bind_geometry(capture,geometry)
    by_topic={}
    records=[pin(capture_path)]
    for topic,ordinal in (('K',6),('T',7)):
        folder=PRE/'natural_cold/B/wire'/f'{ordinal:03d}'
        raw,producer=(read(folder/name) for name in ('RX.bin','PRODUCER.json'))
        need(raw['result']['isError'] is False,'candidate_real_product_control_failed')
        body=next(score.nearest._body(raw))
        target,_=score.context_by_mesh(capture,truth,topic)
        case=truth['cases'][topic]
        actual=score.verify_component_field(body,producer,domain,target,case)
        need(actual and actual['status']=='measured','actual_B_component_not_delivered/'+topic)
        raster=producer['frames'][0]
        binding=body['facts']['focus']
        need(binding['region_ref']['source_triangle_indices']==[binding['primary_source_triangle_index']]
             and raster['frame_identity']==body['frames'][0]['frame_identity'],'actual_original_singleton_or_frame_drift')
        by_topic[topic]={'evidence':{**actual,'ordinal':ordinal},'raw':body,'producer':producer,'target':target}
        records.extend(pin(folder/k) for k in ('TX.bin','RX.bin','PRODUCER.json'))
        records.extend(pin(raster[k]) for k in ('image_path','arrays_path'))
    k=by_topic['K']

    def check(body,prod):
        return score.verify_component_field(body,prod,domain,k['target'],truth['cases']['K'])

    def mutate_both(mutator):
        body,producer=copy.deepcopy(k['raw']),copy.deepcopy(k['producer'])
        mutator(body['facts']['focus'])
        mutator(producer['facts']['focus'])
        return check(body,producer)

    def subset(focus):
        ref=focus['nearest_surface']['component']['region_ref']
        ref['source_triangle_indices']=[focus['primary_source_triangle_index']]
        rehash(ref)

    truncated=raised('wrong_current_component_or_single_face_reference',lambda:mutate_both(subset))

    def stale(focus):
        ref=focus['nearest_surface']['component']['region_ref']
        ref['capture_generation']['revision']+=1
        rehash(ref)

    generation=raised('wrong_current_component_or_single_face_reference',lambda:mutate_both(stale))

    def wrong_instance(focus):
        ref=focus['nearest_surface']['component']['region_ref']
        ref['instance_id']+='-different'
        rehash(ref)

    instance=raised('wrong_current_component_or_single_face_reference',lambda:mutate_both(wrong_instance))

    def moved_frame_scope(focus):
        focus['region_ref']=copy.deepcopy(focus['nearest_surface']['component']['region_ref'])

    frame_scope=raised('wrong_current_component_or_single_face_reference',lambda:mutate_both(moved_frame_scope))

    changed=copy.deepcopy(k['raw'])
    changed['facts']['focus']['nearest_surface'].pop('component')
    mismatch=raised('public_component_or_single_face_does_not_match_producer',lambda:check(changed,k['producer']))
    isolated=score.shared_vertex_component([[0,1,2],[3,4,5],[2,6,7],[8,9,7]],0)
    need(isolated==[0,2,3],'noncontiguous_point_connected_rows_not_exact')
    return by_topic,records,{'actual_B_exact_component_controls':2,
        'truncating_and_rehashing_component_fails':truncated,'stale_reference_fails':generation,
        'wrong_instance_fails':instance,'using_component_as_frame_scope_fails':frame_scope,
        'producer_public_mismatch_fails':mismatch,'noncontiguous_only_shared_vertex_rows':isolated}


def scope_and_counts(cases,proof):
    k=proof['K']['evidence']
    ref=k['region_ref']
    exact='源三角 '+ '、'.join(map(str,ref['source_triangle_indices']))
    prefix={'answer':{'selected_correct_piece':True}}

    def uptake(final,claim=None,reads=(),possible=(),scope=()):
        value,=score.component_uptake(final,claim,[k],list(reads),list(possible),list(scope),prefix)
        return value

    annotated={'component_use':{'ordinal':k['ordinal'],'quote':exact}}
    need(uptake(exact,annotated)['unique_final_scope_adoption']
         and uptake(ref['region_id'])['unique_final_scope_adoption']
         and not uptake('只交了原图',annotated)['unique_final_scope_adoption'],
         'wrong_final_literal_adoption_rule')
    excluded_reads=({'ordinal':k['ordinal']+1},)
    need(not uptake(exact,annotated,reads=excluded_reads)['unique_final_scope_adoption']
         and not uptake(exact,annotated,possible=excluded_reads)['unique_final_scope_adoption'],
         'scope_not_unique_after_actual_or_unresolved_inventory')
    brought_scope={'ordinal':k['ordinal']+2,'source_rows':ref['source_triangle_indices'],'request_ref':None}
    need(not uptake(exact,annotated,scope=(brought_scope,))['unique_final_scope_adoption'],
         'duplicate_explicit_scope_counted_as_exclusive')
    reread={**brought_scope,'request_ref':ref}
    actual_ref_use=uptake(exact,annotated,scope=(reread,))
    need(actual_ref_use['unique_final_scope_adoption'] and actual_ref_use['used_exact_ref_as_query']==[reread['ordinal']],
         'same_component_requery_lost_direct_reference_adoption')
    need(score.python_target_read('s = scene_data(objects=["Item G"])','Item X')=='none'
         and score.python_target_read('s = scene_data(objects=["Item X"])','Item X')=='target'
         and score.python_target_read('s = scene_data(objects=names)','Item X')=='unknown',
         'ordinary_target_inventory_classification_failed')
    derived=copy.deepcopy(cases)
    for label in ('B1','B2'):
        work=derived[label]['attribution']
        work['full_target_mesh_reads']=[]
        work['near_distance_followups']=[]
    both=score.paired(derived)
    need(all(row['B_avoids_both_vs_A'] for row in both.values()),
         'fully_comparable_branch_not_admitted')
    one=copy.deepcopy(derived)
    one['A1']['attribution']['near_distance_followups']=[]
    absent=score.paired(one)
    need(not absent['K']['B_avoids_both_vs_A'] and absent['K']['B_used_product_first_image_and_complete_quality']
         and not absent['K']['A_baseline_had_both'],'baseline_missing_action_counted_as_gain')
    one['B2']['quality_passed']=False
    bad=score.paired(one)
    need(not bad['T']['B_used_product_first_image_and_complete_quality']
         and not bad['T']['B_avoids_both_vs_A'],'quality_failure_counted_in_eligible_pair')
    return {'controlled_rule_cases_not_formal':True,'final_quote_and_opaque_reference_positive':True,
            'mere_field_delivery_not_adoption':True,'other_source_and_full_inventory_disqualify_unique':True,
            'dependent_ref_use_stays_traceable':actual_ref_use['used_exact_ref_as_query'],
            'literal_read_and_dynamic_unknown':True,'paired_full_baseline_and_B_quality_eligibility':True}


if __name__=='__main__':
    need(sys.flags.isolated and sys.dont_write_bytecode,'fixed_isolated_interpreter')
    archive,cases,old_pins,truth,geometry=archived_controls()
    b,b_pins,mutations=actual_b_component_controls(truth,geometry)
    classification=scope_and_counts(cases,b)
    write(OUT,{'passed':True,'batch':ROOT.name,'actual_scorer':pin(HERE/'score_public.py'),'script':pin(__file__),
        'original_closed_controls':archive,'strict_B_raw_controls':mutations,'attribution_controls':classification,
        'actual_B_positive':{k:v['evidence'] for k,v in b.items()},'B_original_inputs':b_pins,
        'old_original_inputs':old_pins,'new_Blender':0,'new_models':0,
        'scope':'Closed original natural outputs, actual new installed offline packets, and marked in-memory mutations.'})
