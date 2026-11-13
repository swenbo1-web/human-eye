"""Independent anonymous content audit. Public package only; no author scorer import."""
import ast
from collections import Counter
from fractions import Fraction
import hashlib
import itertools
import json
from pathlib import Path
import re

PUBLIC=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_surface_scan_continuous_consumption_001/quality/public')
OUT=Path(__file__).resolve().parent
inputs={};assertions=[]
def raw(path):
    assert path.is_relative_to(PUBLIC)
    value=path.read_bytes();inputs[str(path.relative_to(PUBLIC))]={'bytes':len(value),'sha256':hashlib.sha256(value).hexdigest()};return value
def load(path):return json.loads(raw(path))
def check(label,condition):assertions.append({'label':label,'passed':bool(condition)})
def rational(row):return Fraction(int(row['numerator']),int(row['denominator']))
def pair(a,b):return tuple(sorted((a,b)))
index=load(PUBLIC/'INDEX.json')
contract=load(PUBLIC/'scoring/SCORING_CONTRACT.json')
base_contract=load(PUBLIC/'scoring/BASE_SCORING_CONTRACT.json')
truths={state:load(PUBLIC/'scoring'/(state+'_TRUTH.json')) for state in ['BASE','EDIT']}
snapshots={state:load(PUBLIC/'scoring'/(state+'_SNAPSHOT.json')) for state in ['BASE','EDIT']}
for name,sha in index['fixed_quality_materials'].items():
    if name.endswith('score_answer.py'):continue
    check('frozen_public_hash:'+name,hashlib.sha256(raw(PUBLIC/name)).hexdigest()==sha)
oracle={state:{pair(r['object_a'],r['object_b']):r for r in truth['pairs']} for state,truth in truths.items()}
threshold=Fraction.from_float(.002)**2
for state,rows in oracle.items():
    check(state+':full_276_truth_pairs',len(rows)==276)
    for key,row in rows.items():check(state+':exact_membership:'+str(key),row['matches_threshold']==(rational(row['exact_squared_distance_m2'])<=threshold))
expected={state:{key for key,row in rows.items() if row['matches_threshold']} for state,rows in oracle.items()}
tolerance=Fraction(contract['distance_tolerance_mm'])
TABLE=re.compile(r'^\|\s*(Obj_\d{3})\s*\|\s*(Obj_\d{3})\s*\|\s*([0-9]+(?:\.[0-9]+)?)\s*\|\s*$',re.M)
TEXT_PAIR=re.compile(r'^\s*(Obj_\d{3})\s*(?:\|\s*|\s+)(Obj_\d{3})\s*(?:\|\s*|\s+)([0-9]+(?:\.[0-9]+)?)(?:\s+mm)?\s*$',re.M)
def assess_rows(rows,state):
    found={};dupes=[];bad_distance=[];zero_errors=[];precision=[]
    for a,b,value in rows:
        key=pair(a,b)
        if key in found:dupes.append(key)
        found[key]=value
        if key not in oracle[state]:bad_distance.append({'pair':key,'reason':'unknown_object_pair'});continue
        d=Fraction(value);q=rational(oracle[state][key]['exact_squared_distance_m2'])*1000000
        lower=max(Fraction(0),d-tolerance);upper=d+tolerance
        if not lower*lower<=q<=upper*upper:bad_distance.append({'pair':key,'distance_mm':value,'reason':'outside_exact_squared_tolerance_interval'})
        if d==0 and q!=0:zero_errors.append(key)
        if d!=0 and ('.' not in value or len(value.split('.')[1])<3):precision.append(key)
    return {'found':found,'TP':len(set(found)&expected[state]),'FP':sorted(set(found)-expected[state]),'FN':sorted(expected[state]-set(found)),
      'duplicates':dupes,'distance_errors':bad_distance,'false_exact_zero':zero_errors,'presentation_incomplete':precision}
def good_numeric(result):return not any(result[k] for k in ['FP','FN','duplicates','distance_errors','false_exact_zero','presentation_incomplete'])
def content_texts(result):return [v['text'] for v in result.get('content',[]) if v.get('type')=='text']
def facts_from_text(text):
    try:value=json.loads(text)
    except (ValueError,TypeError):return TEXT_PAIR.findall(text),text,None
    if isinstance(value,dict) and value.get('result_kind')=='surface_scan':
        return [(r[0],r[1],str(r[5])) for r in value['matches']],None,value
    stdout=value.get('result',{}).get('result') if isinstance(value,dict) else None
    return (TEXT_PAIR.findall(stdout),stdout,None) if isinstance(stdout,str) else ([],None,None)

# Independent checks supporting optional deterministic final claims.
snapshot=snapshots['BASE'];objects=snapshot['objects']
triangle_total=sum(len(r['faces']) for r in objects)
triangle_pairs=sum(len(a['faces'])*len(b['faces']) for a,b in itertools.combinations(objects,2))
zero_count=sum(rational(row['exact_squared_distance_m2'])==0 for row in oracle['BASE'].values())
nonmatches={p:rational(r['exact_squared_distance_m2']) for p,r in oracle['BASE'].items() if not r['matches_threshold']}
nearest_negative=min(nonmatches,key=nonmatches.get)
degenerate=[]
for obj in objects:
    vertices=[[Fraction(v) for v in p] for p in obj['vertices_local']]
    for ordinal,face in enumerate(obj['faces']):
        a,b,c=[vertices[i] for i in face];u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)]
        cross=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
        if all(x==0 for x in cross):degenerate.append([obj['name'],ordinal])
check('extra_truth_978_triangles_436640_cross_object_triangle_pairs',triangle_total==978 and triangle_pairs==436640)
check('extra_truth_43_exact_zero_and_nearest_negative_002_008',zero_count==43 and nearest_negative==('Obj_002','Obj_008'))
nearest_display=Fraction('2.249999')
check('extra_nearest_negative_display_distance', (nearest_display-tolerance)**2<=nonmatches[nearest_negative]*1000000<=(nearest_display+tolerance)**2)
retained_count=sum(r['api_AABB_Linf_retained'] for r in oracle['BASE'].values())
check('extra_164_41_71_partition_agrees_with_fixed_bound_truth',retained_count==112 and len(oracle['BASE'])-retained_count==164 and retained_count-len(expected['BASE'])==41)
check('extra_truth_no_degenerate_faces',degenerate==[])

results=[];semantic_notes={
 'episode_019ced26c1ce4747':'Explicit full 71-row table, six decimal mm and exact-zero distinction; 164/41/71 partition, no unknown, surface/solid distinction supported by current business facts.',
 'episode_a4a392599cd543ab':'Explicit full table; optional 978 triangles, 436640 exhaustive triangle pairs, nearest excluded 002/008 at 2.249999mm, frame1 and no instances/modifiers are supported by actual current reads/full-check stdout and fixed geometry.',
 'episode_a6aad01907aa45e1':'Explicit full table; current evaluated mesh read, all-pair full check, 43 exact zeros, no empty/degenerate meshes or instances and 1000mm/unit supported by public code/output and fixed geometry.',
 'episode_d9b21bbabe0249e1':'Explicit full table and complete 164/41/71 partition; no unknown and surface/solid distinction supported by current business facts.',
 'episode_d9e9b94ffbfc41f8':'Explicit full table and complete 164/41/71 partition; raw-distance threshold and exact-zero distinction supported; no extra solid conclusion.',
 'episode_db42cda275fa496f':'Explicit full table; evaluated world geometry, finite/nondegenerate triangles, object coverage and point-face/edge-edge/bidirectional edge-face code support the current answer. Extra 205 nonmatches and absent 023/024 matches agree with truth.'}
for eid in index['anonymous_episode_order']:
    episode=load(PUBLIC/eid/'EPISODE.json')
    for ordinal in range(1,4):
        folder=PUBLIC/eid/('turn_'+str(ordinal));turn=load(folder/'TURN.json');evidence=load(folder/'tool_evidence.json')
        state='EDIT' if ordinal==3 else 'BASE'
        result={'episode_id':eid,'anonymous_turn_id':turn['anonymous_turn_id'],'turn_index':ordinal,
                'execution_classification':turn['execution_state'],'valid_completion':turn['valid_completion'],
                'recorded_errors':turn['errors'],'primary_content_classification':None,
                'auxiliary_context_classification':None,'current_state_basis':None}
        if turn['execution_state']=='not_run':
            check(eid+':not_run_slot_'+str(ordinal),turn['final_present'] is False and not (folder/'answer.txt').exists() and evidence['owner_attempts']==[] and evidence['public_tool_events']==[])
            result.update(primary_content_classification='not_run',auxiliary_context_classification='not_run',current_state_basis='not_run',semantic_review='No execution or final; slot preserved, not scored as wrong geometry.')
            results.append(result);continue
        answer=raw(folder/'answer.txt').decode('utf8');rows=TABLE.findall(answer);assessment=assess_rows(rows,state)
        complete_claim=('检查完整' in answer or '检查完成' in answer or '已完成只读检查' in answer or '已完成检查' in answer)
        check(eid+':confirmed_final_retains_execution_failure',turn['final_present'] is True and turn['execution_state']=='failed' and turn['valid_completion'] is False)
        check(eid+':full_71_final_rows',len(rows)==71 and len(assessment['found'])==71)
        for key in ['FP','FN','duplicates','distance_errors','false_exact_zero','presentation_incomplete']:check(eid+':'+key,assessment[key]==[])
        check(eid+':explicit_mm_complete_and_surface_scope',complete_claim and ('mm' in answer or '毫米' in answer) and ('未判断实体' in answer or '不判断实体' in answer or '不据此判断实体' in answer or '不代表对实体' in answer))
        completed=[r['event'] for r in evidence['public_tool_events'] if r['phase']=='item.completed']
        attempts=evidence['owner_attempts'];aligned=[];business_rows=[];business_details=[]
        for attempt in attempts:
            order=attempt['order'];req=attempt['request'];args=req['params']['arguments']
            visible=[v for v in completed if v.get('arguments')==args]
            owner_values=[r['value']['result'] for r in attempt['responses'] if r['kind']=='RESPONSE.json']
            check(eid+':current_success_response_'+str(order),attempt['owner_exception'] is None and not attempt['is_error'] and len(owner_values)==1)
            owner=owner_values[0];texts=content_texts(owner)
            exact_visible=[v for v in visible if content_texts(v.get('result') or {})==texts and v.get('status')=='completed' and v.get('error') is None]
            aligned.append(bool(exact_visible));check(eid+':visible_business_text_equal_owner_'+str(order),bool(exact_visible))
            for text in texts:
                pairs,stdout,packet=facts_from_text(text)
                if pairs:
                    numerical=assess_rows(pairs,state)
                    good=good_numeric(numerical)
                    # Raw business output can carry >3 significant decimals as floats;
                    # final presentation is checked separately with its six fixed decimals.
                    good=not any(numerical[k] for k in ['FP','FN','duplicates','distance_errors','false_exact_zero'])
                    business_rows.append(good)
                    business_details.append({'attempt':order,'matching_rows':len(pairs),'exact_truth_set_and_distances':good})
                if packet is not None:
                    check(eid+':complete_current_fact_packet',packet['status']=='complete' and packet['coverage']=={'objects':24,'total_pairs':276,'bound_excluded':164,'measured_match':71,'measured_nonmatch':41,'unknown':0,'deferred':0,'catalog_scope_confirmed':True} and packet['scope_issues']==packet['unsupported_objects']==packet['unresolved']==[] and packet['delivery']['complete'] is True and packet['measurement_semantics']['solid_relation']=='not_evaluated')
        # This checks current successful business substance separately from the
        # preserved failed full-envelope binding, never overriding that failure.
        evidence_ok=bool(business_rows) and any(business_rows) and all(aligned)
        check(eid+':current_business_supports_full_answer',evidence_ok)
        content_ok=good_numeric(assessment) and complete_claim
        result.update(primary_content_classification='complete_correct' if content_ok else 'incorrect',
            auxiliary_context_classification='not_applicable_first_turn_full_list',
            current_state_basis='sufficient_current_business_facts' if evidence_ok else 'insufficient',
            final_present=True,primary_pairs=len(rows),TP=assessment['TP'],FP=assessment['FP'],FN=assessment['FN'],
            duplicates=assessment['duplicates'],distance_errors=assessment['distance_errors'],presentation_incomplete=assessment['presentation_incomplete'],
            false_exact_zero=assessment['false_exact_zero'],explicit_completeness=complete_claim,
            business_fact_checks=business_details,visible_business_text_matches_owner=all(aligned),
            execution_binding_failure_preserved=True,semantic_review=semantic_notes[eid],additional_deterministic_errors=[],manual_semantic_review_complete=True)
        results.append(result)
summary={'planned_episodes':6,'planned_turns':18,'finals_reviewed':6,
         'primary_content':dict(Counter(r['primary_content_classification'] for r in results)),
         'execution':dict(Counter(r['execution_classification'] for r in results)),
         'current_state_basis':dict(Counter(r['current_state_basis'] for r in results)),
         'completed_valid_episodes':0,'confirmed_model_resumes_tested':0,
         'reviewed_BASE_pair_memberships':6*276,'reviewed_final_matching_rows':6*71,
         'checks':len(assertions),'checks_passed':sum(r['passed'] for r in assertions),'checks_failed':sum(not r['passed'] for r in assertions)}
output={'status':'FINAL_INDEPENDENT_QUALITY_REVIEW','manual_semantic_review_pending':False,
 'scope':'Only public anonymous package and root registered plan; no private/group/cost/usage files, no author scorer execution, no product/live/model/API call.',
 'parent_task':'d5c646fe-8394-4bcd-b3a6-759bdccdaeb8','parent_revision':1,'parent_write':626,
 'own_AL_assignment':'Old assignment retained; no parent handle borrowed.',
 'summary':summary,'results':results,'assertions':assertions,
 'limitations':['No continuous second or third turn ran; contextual reference and state-change behavior remain untested.','Full CLI-result/owner binding failures remain execution failures even though visible text substance was independently matched.','Fixed exact truth was SHA-checked and used; full geometric oracle was not regenerated.','Tool contents can reveal tool route, but group mapping and all cost metrics were not consulted or reported.']}
(OUT/'RESULTS.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(OUT/'INPUT_SHA256.json').write_text(json.dumps(inputs,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(summary,ensure_ascii=False))
for row in assertions:
    if not row['passed']:print(json.dumps(row,ensure_ascii=False))
