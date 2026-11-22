"""Preflight the unchanged rubric against retained closed originals and rejection cases."""

from copy import deepcopy
from pathlib import Path
import sys


HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from evidence import (OLD, closed_answer, closed_source, dependency_paths, digest, exact, formal_wires, frame_deliveries,
                      publication, read, require, retained, score_frame, write)
from score import LABELS, grade, score_answer


def actual_formal():
    done=[]
    for baseline,label in (('he_perf050_source_scope_rank_transfer_recovery_001','N1'),
                           ('he_perf050_source_scope_rank_transfer_recovery_001','P1'),
                           ('he_m4_dense_panel_sweep_formal_001','P3')):
        slot=Path('D:/')/baseline/'slots'/label
        raw,pub=publication(slot)
        final=closed_answer(slot,raw)
        require(final is not None and raw['model_consumers']==1, 'historical_actual_formal_consumer_missing')
        ledger=formal_wires(slot,pub)
        require(ledger['attempts'], 'archived_actual_formal_wire_missing')
        checked=frame_deliveries(slot,read(slot/'DEVICE_EVIDENCE.json')['frames'],ledger)
        if label=='P3':
            require(pub['status']=='failed' and not raw['consumer']['valid_completion'],
                    'failed_real_formal_answer_reclassified_completed')
        else:
            require(pub['status']=='completed' and raw['consumer']['valid_completion']
                    and any(item['named_local_path'] for rows in checked.values() for item in rows),
                    'historical_current_path_image_delivery_missing')
        done.append({'archive':baseline,'label':label,'status':pub['status'],
                     'result':exact(slot/'SLOT_RESULT.json',slot),
                     'published':exact(slot/'SLOT_PUBLICATION.json',slot),
                     'actual_final':{key:value for key,value in final.items() if key!='text'},
                     'business_attempts':len(ledger['attempts']),
                     'frame_delivery_count':sum(map(len,checked.values()))})
    return done


def original_micro_ui():
    slot=Path('D:/he_perf050_dense_micro_surface_holdout_001/slots/QN')
    raw,pub=publication(slot)
    require(pub['status']=='completed' and closed_answer(slot,raw) is None,
            'original_micro_QN_is_zero_model_without_answer')
    source,state=closed_source(slot,raw)
    geometry=retained(OLD/'qualification/native.py')['certify_geometry'](source)
    device=read(slot/'DEVICE_EVIDENCE.json')
    rows=device['frames']
    old=read(OLD/'evidence/QN_CLOSED_IMAGES.json')['reopened']
    proofs={}
    clauses=[]
    claims={'rows':[],'witnesses':{},'extra_assertions':[]}
    for name,row in sorted(geometry['regions'].items()):
        quote=f"{name} source 0, 1, center {row['center_world_m']}"
        clauses.append(quote)
        claims['rows'].append({'object_name':name,'source_triangle_indices':[0,1],
                              'center_world_m':row['center_world_m'],'quote':quote})
    for key,expected in old.items():
        frame,=[r for r in rows if r['ref']==expected['ref']]
        name=expected['object_name']
        proof=score_frame(slot,frame,source,name,{},geometry)
        require((proof['selected_surface_pixels'],proof['contrasting_boundary_pixels'],proof['complete'])==
                (expected['selected_surface_pixels'],expected['contrasting_boundary_pixels'],expected['complete']),
                'retained_actual_micro_images_changed')
        proofs[key]=proof
        if proof['complete']:
            link=proof['path']
            quote=f"{name} [original](<{link}>)"
            clauses.append(quote)
            claims['witnesses'][name]=[{'link':link,'quote':quote}]
    facts={'geometry':geometry,'linked_originals':{proof['path']:{'targets':{proof['object_name']:proof},
           'deliveries':[]} for proof in proofs.values()}}
    cover='S034 is blocked by the overhead reference cover in all six directions.'
    distance='S034 to M4_Far_00 is 0.125 m towards +Z with endpoints (1.53,0.53,1.875) and (1.53,0.53,2).'
    claims['occlusion']={'quote':cover,'object_name':'S034','all_six':True,'reason':'reference_cover'}
    claims['measurement']={'quote':distance,'object_name':'S034','reference':'M4_Far_00','distance_m':'1/8',
                           'direction_world':[0,0,1],'a':[1.53,0.53,1.875],'b':[1.53,0.53,2]}
    answer='\n'.join(clauses+[cover,distance])
    scored=score_answer(answer,claims,facts,source)
    require(scored['all_items_passed'],'same_rubric_rejects_equivalent_points_or_natural_omissions')
    controls={}
    for false_item,edit,expected in (
            ('wrong_image',lambda copy:copy['witnesses'].update(S055=copy['witnesses']['S021']),'original_png_S055'),
            ('outside_reference',lambda copy:copy['measurement'].update(b=[1.53,1.02,2]),'surface_measurement'),
            ('wrong_direction',lambda copy:copy['measurement'].update(direction_world=[0,0,-1]),'surface_measurement'),
            ('insufficient_unknown',lambda copy:copy['occlusion'].update(all_six=False),'six_direction_occlusion'),
            ('extra_object',lambda copy:copy['rows'].append(dict(copy['rows'][0],object_name='S019')),'discovery')):
        wrong=deepcopy(claims)
        edit(wrong)
        check=score_answer(answer,wrong,facts,source)
        require(not check['items'][expected]['passed'], 'wrong_case_scored/' + false_item)
        controls[false_item]=True
    return {'actual_zero_model_source':state,'actual_original_image_proofs':proofs,
            'synthetic_answer_scored_for_preflight_only':scored['score'],'rejection_controls':controls}


def main():
    dependency_paths()
    formal=actual_formal()
    micro=original_micro_ui()
    statuses={'N1':'failed'}
    ledger={'slots':[{'label':label,'arm':label[0],'status':statuses.get(label,'unrun'),'blind_id':None} for label in LABELS]}
    report=grade(ledger,{}, {})
    require(report['formal_denominator']==6 and report['quality_complete_counts']=={'N':0,'P':0}
            and all(row['score'] is None for row in report['slots']),
            'failed_or_unrun_formal_slots_credited')
    old_qp=Path('D:/he_perf050_dense_micro_surface_holdout_001/slots/QP')
    result,pub=publication(old_qp)
    require(pub['status']=='failed' and result['model_consumers']==0 and closed_answer(old_qp,result) is None,
            'old_QP_early_stop_no_longer_preserved')
    write(HERE/'SCORER_PREFLIGHT.json', {'passed':True,'formal_slots':list(LABELS),'actual_Blender_starts':0,
          'actual_model_starts':0,'retained_archived_formal_controls':formal,'retained_micro-QN':micro,
          'failed_unrun_original_denominator_preserved':True,'original_QP_retains_failure':True,
          'source_pins':[{'path':str(path),'sha256':digest(path),'bytes':path.stat().st_size}
                         for path in (HERE/'evidence.py',HERE/'score.py',Path(__file__),OLD/'qualification/rubric.md')]})
    print('Formal evidence and all seven rubric items preflight passed')


if __name__=='__main__':
    main()
