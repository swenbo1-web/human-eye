"""Apply the unchanged seven-item rubric to sealed raw answers and closed originals."""

import argparse
from fractions import Fraction
import json
from math import sqrt
from pathlib import Path
import re
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from evidence import (NS, OLD, LABELS, TRUTH, closed_answer, closed_source, dependency_paths, digest,
                      evaluated_facts, exact, formal_wires, read, require, write)


TARGETS = {'S021','S034','S055'}
VIEWS = {'SCENE','TOP','LEFT','RIGHT','FRONT','BACK'}
TOLERANCE = Fraction(1,20000)
MARKDOWN = re.compile(r'\]\(\s*(?:<([^<>\n]+)>|([^\s()<>]+))(?:\s+["\'][^"\'\n]*["\'])?\s*\)')


def links(answer):
    return {a or b for a,b in MARKDOWN.findall(answer)}


def quoted(answer, claim):
    value=claim.get('quote')
    require(type(value) is str and bool(value.strip()) and value in answer, 'transcription_missing_exact_original_quote')


def number(value):
    require(type(value) in (int,float,str,Fraction), 'expected_numerical_fact')
    return Fraction(str(value))


def nearby(actual, expected):
    return len(actual)==len(expected) and all(abs(number(a)-number(b))<=TOLERANCE for a,b in zip(actual,expected))


def source_ids(claim, name, aliases):
    fields={'source_triangle_indices','source_triangle_index_ranges','source_roi_id'} & claim.keys()
    require(len(fields)==1,'missing_or_ambiguous_source_reference')
    key,=fields
    if key=='source_roi_id':
        known=aliases.get(name,{}).get(claim[key],[])
        require(len(known)==1,'roi_not_uniquely_recoverable_in_this_slot')
        return known[0]
    if key=='source_triangle_indices':
        rows=claim[key]
        require(all(type(index) is int and index>=0 for index in rows) and len(rows)==len(set(rows)),
                'invalid_or_duplicate_source_index')
        return sorted(rows)
    ranges=claim[key]
    require(all(type(a) is int and type(b) is int and 0<=a<=b<6162 for a,b in ranges),'invalid_source_triangle_range')
    rows=[i for lo,hi in ranges for i in range(lo,hi+1)]
    require(len(rows)==len(set(rows)),'overlapping_source_triangle_ranges')
    return sorted(rows)


def on_triangle_xy(vertex, triangle):
    """Project the rounded point to its horizontal candidate triangle and check edge distances."""
    if (len({v[2] for v in triangle})!=1 or abs(vertex[2]-triangle[0][2])>TOLERANCE):
        return False
    crosses=[]
    for i,j in ((0,1),(1,2),(2,0)):
        a,b=triangle[i],triangle[j]
        dx,dy=b[0]-a[0],b[1]-a[1]
        cross=dx*(vertex[1]-a[1])-dy*(vertex[0]-a[0])
        crosses.append((cross,dx*dx+dy*dy))
    return any(all(sign*c>=0 or c*c<=TOLERANCE*TOLERANCE*side for c,side in crosses) for sign in (-1,1))


def measured(measurement, geometry, source):
    expected=geometry['measurement']
    require(measurement['reference']==expected['reference'] and measurement['object_name']==expected['object']
            and measurement.get('wrong_scope',False) is False,'wrong_measured_selection_or_reference_scope')
    aim=measurement['direction_world']
    require(nearby(aim,expected['direction_world']), 'surface_direction_not_world_positive_Z')
    points=[tuple(map(number,measurement[name])) for name in ('a','b')]
    require(all(len(p)==3 for p in points), 'nearest_point_coordinate_dimension')
    vertices={r['name']:r['evaluated'] for r in source['objects']}
    for point,name,ids in zip(points,(expected['object'],expected['reference']),
                              (expected['source_triangle_indices'],expected['attaining_reference_triangles']),strict=True):
        target=vertices[name]
        positions=[tuple(map(number,p)) for p in target['vertices_world_m']]
        # Both cap triangles attain the global minimum, including ties on their shared diagonal.
        face_ids=ids if name==expected['object'] else (
            i for i,ix in enumerate(target['triangles']) if all(positions[k][2]==2 for k in ix))
        require(any(on_triangle_xy(point,[positions[k] for k in target['triangles'][i]]) for i in face_ids),
                'reported_point_not_on_corresponding_current_triangle_surface/'+name)
    a,b=points
    distance=number(measurement['distance_m'])
    delta=tuple(y-x for x,y in zip(a,b,strict=True))
    require(distance>0 and abs(distance-number(expected['distance_exact_m']))<=TOLERANCE and
            nearby(delta,[0,0,expected['distance_exact_m']]) and
            abs(sqrt(sum(x*x for x in delta))-float(distance))<=float(TOLERANCE),
            'reported_pair_does_not_attain_whole_reference_minimum')
    return {'distance_m':str(distance),'direction_world':aim,'point_pair':[measurement['a'],measurement['b']]}


def score_answer(answer, claims, facts, source):
    geometry = facts['geometry']
    rows=claims.get('rows',[])
    names=[row['object_name'] for row in rows]
    status={}
    def item(name,run):
        try:
            value=run()
            require(bool(value), 'missing_or_incorrect_answer_fact')
            status[name]={'passed':True,'verified':value}
        except (ValueError,KeyError,IndexError,TypeError,ZeroDivisionError) as error:
            status[name]={'passed':False,'reason':str(error)}
    for row in rows:
        quoted(answer,row)
    def roster():
        require(len(names)==len(TARGETS) and set(names)==TARGETS,'incorrect_or_incomplete_scene_roster')
        for row in rows:
            if 'area_m2' in row:
                require(abs(number(row['area_m2'])-Fraction(1,256))<=TOLERANCE,'wrong_claimed_target_area')
            if 'unit_normal_world' in row:
                require(nearby(row['unit_normal_world'],[0,0,1]),'wrong_claimed_oriented_normal')
        return names
    def sources():
        require(len(names)==3 and set(names)==TARGETS,'source_items_missing_or_extra')
        accepted={}
        for row in rows:
            name=row['object_name']
            ids=source_ids(row,name,facts.get('roi_aliases',{}))
            require(ids==geometry['regions'][name]['source_triangle_indices'],'wrong_current_source_triangles/'+name)
            accepted[name]=ids
        return accepted
    item('discovery',roster)
    item('source_triangles',sources)
    item('centers',lambda:len(names)==3 and set(names)==TARGETS and
         all(nearby(row['center_world_m'],geometry['regions'][row['object_name']]['center_world_m']) for row in rows))
    for name in ('S021','S055'):
        def witness():
            offered=claims.get('witnesses',{}).get(name,[])
            proof=[]
            for candidate in offered:
                quoted(answer,candidate)
                link=candidate['link']
                require(link in links(answer) and link in links(candidate['quote']),
                        'claimed_original_needs_openable_original_Markdown_reference')
                resolved=facts['linked_originals'].get(link,{}).get('targets',{}).get(name)
                require(resolved and resolved['complete'],'quoted_image_lacks_current_complete_pixel_witness')
                proof.append({'link':link,'proof':resolved,'deliveries':facts['linked_originals'][link]['deliveries']})
            return proof
        item('original_png_'+name,witness)
    def occlusion():
        row=claims.get('occlusion',{})
        quoted(answer,row)
        cover=geometry['strict_covering']['S034']
        require(row['object_name']=='S034' and row['all_six'] is True and row['reason']=='reference_cover'
                and set(cover)==VIEWS and all(z['cover_object_name']=='M4_Far_00' for z in cover.values())
                and row.get('blocker_object_name','M4_Far_00')=='M4_Far_00','unsupported_six_direction_occlusion_reason')
        if 'blocker_triangles' in row:
            require(set(row['blocker_triangles']) and set(row['blocker_triangles'])<={512,513},
                    'quoted_claim_names_invalid_cover_triangles')
        return cover
    item('six_direction_occlusion',occlusion)
    def measurement():
        claim=claims.get('measurement',{})
        quoted(answer,claim)
        return measured(claim,geometry,source)
    item('surface_measurement',measurement)
    extra=claims.get('extra_assertions',[])
    for row in extra:
        quoted(answer,row)
        require(type(row['issue']) is str and row['issue'].strip(),'unsupported_assertion_missing_explanation')
    score=sum(checked['passed'] for checked in status.values())
    return {'score':score,'max':7,'all_items_passed':score==7 and not extra,'items':status,'extra_assertions':extra}


def extract(runtime):
    sys.path.insert(0,str(NS/'harness'))
    from common import EXTERNAL
    from admission import publication,verify_freeze,verify_qp_gate

    require(runtime.resolve()==EXTERNAL.resolve(),'unregistered_formal_runtime_root')
    frozen=verify_freeze()
    have_formal=any((runtime/'slots'/label).exists() for label in LABELS)
    gate_path=runtime/'preflight/QP_CLOSED_GATE.json'
    gate_sha=None
    if have_formal:
        qp,receipt=publication('QP',frozen)
        verify_qp_gate(runtime,frozen,qp,receipt)
        gate_sha=digest(gate_path)
    dependency_paths()
    rows=[]
    masked={}
    for label in LABELS:
        slot=runtime/'slots'/label
        row={'label':label,'arm':label[0],'status':'unrun','blind_id':None}
        rows.append(row)
        if not slot.exists():
            continue
        row['status']='unconfirmed'
        try:
            original,pub=publication(label,frozen)
            require(original['phase']=='formal' and original['group']==label[0],'registered_formal_arm_changed')
            row.update(status=pub['status'],published_result=exact(slot/'SLOT_RESULT.json',slot),
                       publication=exact(slot/'SLOT_PUBLICATION.json',slot),
                       consumer_count=original.get('model_consumers',0))
            final=closed_answer(slot,original)
            if final:
                blind_id=final['sha256']
                require(blind_id not in masked,'duplicate_final_original_bytes')
                masked[blind_id]=final['text']
                row['blind_id']=blind_id
                row['answer']={key:value for key,value in final.items() if key!='text'}
            if original['status']!=pub['status'] or pub['status']!='completed':
                row['recorded_errors']=original.get('errors',[])
                continue
            require(original['model_consumers']==1 and original['consumer']['valid_completion'] is True
                    and final,'missing_actual_formal_consumer_completion')
            source,current=closed_source(slot,original)
            row['closed_source']=current
            tools=formal_wires(slot,pub)
            row['facts']=evaluated_facts(slot,source,tools,links(final['text']))
        except (OSError,KeyError,ValueError,TypeError,IndexError,ImportError) as error:
            row['evidence_error']={'type':type(error).__name__,'reason':str(error)}
    ledger={'schema':'perf050-micro-formal-original-evidence-v1','rubric_sha256':digest(OLD/'qualification/rubric.md'),
            'freeze_sha256':frozen,'closed_qp_gate_sha256':gate_sha,
            'truth_sha256':digest(TRUTH),'formal_denominator':len(LABELS),'slots':rows}
    return json.loads(json.dumps(ledger,allow_nan=False)),dict(sorted(masked.items()))


def text_adoptions(item, row, answer, notes, source):
    supported=[]
    mapping={'discovery':'source_triangles','occlusion':'six_direction_occlusion','measurement':'surface_measurement'}
    for note in notes:
        quoted(answer,note)
        kind=note['kind']
        require(kind in mapping and row['items'][mapping[kind]]['passed'],
                'adoption_not_present_in_scored_original_answer')
        choices=[fact for fact in item['facts']['verified_product_text_facts']
                 if fact['kind']==kind and fact['attempt']==note['attempt'] and note['object_name'] in fact['objects']]
        require(len(choices)==1,'adoption_missing_verified_product_fact_delivery')
        fact,=choices
        if kind=='measurement':
            measured(fact['measurement'],item['facts']['geometry'],source)
        supported.append({**note,'actual_delivery':fact})
    return supported


def grade(ledger, answers, claims, adoption=None):
    expected={row['blind_id'] for row in ledger['slots'] if row.get('facts')}
    require(claims.keys()==expected,'blind_claims_must_cover_all_and_only_scoreable_originals')
    require((adoption or {}).keys()<=expected,'adoption_annotation_has_no_scoreable_original')
    rows=[]
    for item in ledger['slots']:
        label=item['label']
        row={key:item[key] for key in ('label','arm','status','blind_id')}
        rows.append(row)
        if item['status']!='completed' or not item.get('facts'):
            row.update(score=None,max=7,all_items_passed=False,evidence_error=item.get('evidence_error'))
            continue
        source=read(item['closed_source']['last']['path'])
        row.update(score_answer(answers[item['blind_id']],claims[item['blind_id']],item['facts'],source))
        # A verified image link to a product frame is attributable with its original product delivery and named re-read.
        images=[e for key,score in row['items'].items() if key.startswith('original_png') and score['passed']
                for e in score['verified'] if e['proof']['origin']=='product']
        row['verified_product_image_adoption']=item['arm']=='P' and bool(images)
        notes=(adoption or {}).get(item['blind_id'],[])
        require(not notes or item['arm']=='P','ordinary_arm_product_adoption_invalid')
        row['verified_product_text_adoptions']=text_adoptions(item,row,answers[item['blind_id']],notes,source)
        row['product_facts_adopted']=row['verified_product_image_adoption'] or bool(row['verified_product_text_adoptions'])
    return {'schema':'perf050-micro-formal-independent-quality-v1','formal_denominator':6,
            'observer_provider_context':None,'observer_human_opened_image':None,'slots':rows,
            'quality_complete_counts':{arm: sum(row['all_items_passed'] for row in rows if row['arm']==arm) for arm in ('N','P')},
            'product_adoption_count':sum(row.get('product_facts_adopted',False) for row in rows if row['arm']=='P')}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('evidence','grade'))
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--claims',type=Path)
    parser.add_argument('--adoption',type=Path)
    args=parser.parse_args()
    ledger,answers=extract(args.runtime.resolve())
    if args.action=='evidence':
        write(HERE/'FORMAL_EVIDENCE.json',ledger)
        write(HERE/'BLIND_ANSWERS.json',{'raw_answers':answers,
              'masking':'No separate arm labels. Original answers are preserved and paths may reveal them.'})
    else:
        require(args.claims is not None, 'manual_semantic_claims_required')
        require(ledger==read(HERE/'FORMAL_EVIDENCE.json') and answers==read(HERE/'BLIND_ANSWERS.json')['raw_answers'],
                'formal_scoring_originals_changed')
        write(HERE/'QUALITY.json',grade(ledger,answers,read(args.claims),read(args.adoption) if args.adoption else None))


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'registered_interpreter_required')
    main()
