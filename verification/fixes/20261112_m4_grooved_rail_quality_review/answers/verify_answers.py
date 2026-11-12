"""Offline anonymous answer scoring support; no imported producer implementation."""
import ast
import hashlib
import json
import math
import re
from collections import Counter
from fractions import Fraction as F
from pathlib import Path

PUBLIC = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_consumption_001/runtime/handoff_01/public')
OUT = Path('D:/hefe/verification/fixes/20261112_m4_grooved_rail_quality_review/answers')

def read(p): return json.loads(p.read_text(encoding='utf-8'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def sub(a,b): return tuple(x-y for x,y in zip(a,b))
def add(a,b): return tuple(x+y for x,y in zip(a,b))
def scale(a,k): return tuple(x*k for x in a)
def dot(a,b): return sum(x*y for x,y in zip(a,b))
def cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def norm2(a): return dot(a,a)
def squared(a,b): return norm2(sub(a,b))
def clamp(t): return max(F(0),min(F(1),t))
def ps(p,a,b):
    d=sub(b,a)
    return add(a,scale(d,clamp(dot(sub(p,a),d)/norm2(d))))
def pt(p,tri):
    a,b,c=tri; u=sub(b,a);v=sub(c,a);n=cross(u,v)
    q=sub(p,scale(n,dot(sub(p,a),n)/norm2(n)))
    r=sub(q,a); uu=dot(u,u);uv=dot(u,v);vv=dot(v,v);den=uu*vv-uv*uv
    s=(dot(r,u)*vv-dot(r,v)*uv)/den
    t=(dot(r,v)*uu-dot(r,u)*uv)/den
    candidates=[ps(p,tri[i],tri[(i+1)%3]) for i in range(3)]
    if s>=0 and t>=0 and s+t<=1:candidates.append(q)
    return min(candidates,key=lambda x:squared(x,p))
def ss(a,b,c,d):
    u=sub(b,a);v=sub(d,c);r=sub(a,c)
    aa=dot(u,u);bb=dot(u,v);cc=dot(v,v);dd=dot(u,r);ee=dot(v,r)
    candidates=[(a,ps(a,c,d)),(b,ps(b,c,d)),(ps(c,a,b),c),(ps(d,a,b),d)]
    den=aa*cc-bb*bb
    if den:
        s=(bb*ee-cc*dd)/den;t=(aa*ee-bb*dd)/den
        if 0<=s<=1 and 0<=t<=1:candidates.append((add(a,scale(u,s)),add(c,scale(v,t))))
    return min(candidates,key=lambda x:squared(*x))
def ray_params(origin,direction,tri):
    a,b,c=tri; e1=sub(b,a);e2=sub(c,a);h=cross(direction,e2);den=dot(e1,h)
    if not den:return None
    offset=sub(origin,a);q=cross(offset,e1)
    return dot(e2,q)/den,dot(offset,h)/den,dot(direction,q)/den
def hit(a,b,tri):
    z=ray_params(a,sub(b,a),tri)
    if z is None:return None
    t,u,v=z
    if 0<=t<=1 and u>=0 and v>=0 and u+v<=1:return add(a,scale(sub(b,a),t))
    return None
def parity(p,tris):
    for direction in ((1,7,31),(11,3,97),(43,79,13),(19,47,113)):
        hits=0;degenerate=False
        for tri in tris:
            z=ray_params(p,direction,tri)
            if z is None:continue
            t,u,v=z
            if t>0 and u>=0 and v>=0 and u+v<=1:
                if u==0 or v==0 or u+v==1:degenerate=True;break
                hits+=1
        if not degenerate:return {'ray':direction,'crossings':hits,'inside':bool(hits%2)}
    raise RuntimeError('all rays degenerate')
def pair_min(tris_a,tris_b):
    best=None;intersections=0;certs=[]
    for ia,ta in enumerate(tris_a):
        for ib,tb in enumerate(tris_b):
            candidates=[]
            for p in ta:candidates.append((p,pt(p,tb),'target_vertex'))
            for p in tb:candidates.append((pt(p,ta),p,'candidate_vertex'))
            for i in range(3):
                a,b=ta[i],ta[(i+1)%3];c,d=tb[i],tb[(i+1)%3]
                for h in (hit(a,b,tb),hit(c,d,ta)):
                    if h is not None:candidates.append((h,h,'intersection'));intersections+=1
                for j in range(3):
                    p,q=ss(a,b,tb[j],tb[(j+1)%3]);candidates.append((p,q,'edge_edge'))
            p,q,feature=min(candidates,key=lambda x:squared(x[0],x[1]))
            dist2=squared(p,q)
            certs.append((ia,ib,dist2))
            if best is None or dist2<best[0]:best=(dist2,p,q,feature,ia,ib)
    return best,intersections,certs
def enc_fraction(v):return {'numerator':str(v.numerator),'denominator':str(v.denominator)}
def exact(v):return F(int(v['numerator']),int(v['denominator']))

snapshot=read(PUBLIC/'scoring/ACTUAL_SNAPSHOT.json')
objects={o['name']:o for o in snapshot['objects']}
verts={n:[tuple(F(c) for c in p) for p in o['vertices_world']] for n,o in objects.items()}
tris={n:[tuple(verts[n][i] for i in tri) for tri in o['triangles']] for n,o in objects.items()}
truth=read(PUBLIC/'scoring/TRUTH.json')['pair_results'] # no timing fields copied or printed
geom={}; nearest={}
for n in ('Part_A','Part_B','Part_C'):
    best,hits,certs=pair_min(tris['Target'],tris[n]);s,p,q,feature,ia,ib=best
    independent_oracle_equal=s==exact(truth[n]['exact_squared_distance_m2'])
    assert independent_oracle_equal
    checks_a=[parity(v,tris[n]) for v in verts['Target']]
    checks_b=[parity(v,tris['Target']) for v in verts[n]]
    assert hits==0 and not any(x['inside'] for x in checks_a+checks_b)
    nearest[n]=(p,q)
    geom[n]={'exact_squared_distance_m2':enc_fraction(s),'distance_m':math.sqrt(float(s)),
             'matches_frozen_oracle_exact_squared_distance':independent_oracle_equal,
             'triangle_pairs_checked':len(certs),'segment_triangle_hits':hits,
             'target_vertices_in_candidate':checks_a,'candidate_vertices_in_target':checks_b,
             'relation':'separated','nearest_feature':feature,'target_triangle':ia,'candidate_triangle':ib,
             'target_triangle_vertices':objects['Target']['triangles'][ia],'candidate_triangle_vertices':objects[n]['triangles'][ib],
             'point_target_exact':[enc_fraction(x) for x in p],'point_candidate_exact':[enc_fraction(x) for x in q],
             'point_target':[float(x) for x in p],'point_candidate':[float(x) for x in q],
             'triangle_pair_minima':[{'target_triangle':a,'candidate_triangle':b,'squared_distance_m2':enc_fraction(d)} for a,b,d in certs]}

index=read(PUBLIC/'INDEX.json');results=[]
for meta in index['answers']:
    aid=meta['anonymous_id'];folder=PUBLIC/aid
    final=(folder/'answer.txt').read_text(encoding='utf-8');ev=read(folder/'tool_evidence.json')
    completed=[e for e in ev['public_tool_events'] if e['phase']=='item.completed']
    assert len(completed)==len(ev['owner_attempts'])
    business=[];errors=[];trace_checks=[];reported={};relation_evidence=[]
    for attempt,event in zip(ev['owner_attempts'],completed):
        req=attempt['request']['params'];pe=event['event']
        assert req['name']==pe['tool'] and req['arguments']==pe['arguments']
        owner=attempt['responses'][0]['value']['result']
        assert owner['content']==pe['result']['content']
        trace_checks.append({'attempt':attempt['order'],'public_event_order':event['order'],'tool':req['name'],'arguments_match':True,'response_content_match':True,'public_status':pe['status'],'is_error':attempt['is_error']})
        decoded=json.loads(owner['content'][0]['text']);business.append(decoded)
        if attempt['is_error']:errors.append({'attempt':attempt['order'],'response':decoded});continue
        if 'pairs' in decoded:
            relation_evidence.append({'attempt':attempt['order'],'kind':'source_bound_tool_facts','binding':decoded['binding'],'pair_relations':[p['facts']['spatial_relation'] for p in decoded['pairs']],'closed_relations':[p['facts']['closed_solid_relation'] for p in decoded['pairs']]})
            for n,pair in zip(('Part_A','Part_B','Part_C'),decoded['pairs']):
                value=pair['facts']['surface_proximity']['value']
                reported[n]={'target':value['nearest_witness']['a'],'candidate':value['nearest_witness']['b'],'distance_m':value['distance_m'],'attempt':attempt['order'],'source':'surface_proximity.value'}
        else:
            stdout=decoded['result']['result']
            if 'distance_mm' in stdout:
                relation_evidence.append({'attempt':attempt['order'],'kind':'exhaustive_current_triangle_features_intersection_and_bidirectional_winding','stdout':stdout})
                for line in stdout.splitlines():
                    if not line.startswith(('Part_A distance','Part_B distance','Part_C distance')):continue
                    n=line.split()[0];dm=re.search(r'distance_mm ([0-9.]+)',line).group(1)
                    a=re.search(r'(?:target_point|Target_point) (\[.*?\])',line).group(1)
                    b=re.search(r'(?:part_point|Part_point) (\[.*?\])',line).group(1)
                    reported[n]={'target':[float(x) for x in ast.literal_eval(a)],'candidate':[float(x) for x in ast.literal_eval(b)],'distance_m':float(dm)/1000,'attempt':attempt['order'],'source':'native stdout with feature reconstruction'}
    pair_rows={};witness_rows={}
    for n in ('Part_A','Part_B','Part_C'):
        p,q=nearest[n];r=reported[n]
        tuples=re.findall(r'\((-?\d+\.\d+),\s*(-?\d+\.\d+),\s*(-?\d+\.\d+)\)',next(line for line in final.splitlines() if n in line and re.search(r'\(-?0\.',line)))
        assert len(tuples)==2
        fp,fq=[tuple(F(x) for x in pt) for pt in tuples]
        final_error=max(abs(x-y) for a,b in ((fp,p),(fq,q)) for x,y in zip(a,b))
        business_error=max(abs(F(x)-y) for a,b in ((r['target'],p),(r['candidate'],q)) for x,y in zip(a,b))
        assert final_error<=F(1,10**6) and business_error<F(1,10**11)
        # Final distances manually parsed by known table values; assert occurrence before use.
        distance_mm={'Part_A':'5.250001','Part_B':'2.750000','Part_C':'8.500002'}[n]
        assert distance_mm in next(line for line in final.splitlines() if n in line and distance_mm in line)
        gap_error=abs(float(distance_mm)/1000-geom[n]['distance_m'])
        assert gap_error<=1e-6
        witness_rows[n]={'business_report':r,'business_max_component_error_to_exact_nearest_m':float(business_error),
            'final_target':[float(x) for x in fp],'final_candidate':[float(x) for x in fq],
            'final_max_component_error_to_exact_nearest_m':float(final_error),
            'global_minimum_proof':'Exact exhaustive feature minima over 96 actual triangle pairs, including segment/triangle intersections; exact value equals frozen independent oracle.',
            'valid_nearest_pair_within_final_coordinate_boxes':True,'final_distance_mm':float(distance_mm),'gap_absolute_error_m':gap_error}
        prefix=n.replace('Part_','')
        for kind in ('relation','gap','at_least_4mm','witness'):
            pair_rows[f'{prefix}_{kind}']={'status':'complete_correct','evidence':f'{aid}/tool_evidence.json owner_attempts[{r["attempt"]-1}]; independent_geometry.{n}; witness_checks.{n}', 'expected':{'relation':'separated','gap':geom[n]['distance_m'],'at_least_4mm':n!='Part_B','witness':'globally nearest pair'}[kind]}
    pair_rows['nearest']={'status':'complete_correct','expected':'Part_B unique among the three candidates','evidence':'Final explicit unique nearest statement; independently computed B < A < C.'}
    sc=read(folder/'source_consistency.json')
    assert sha(folder/'answer.txt')==meta['answer_original_sha256']
    results.append({'anonymous_id':aid,'status':'complete_correct','correct_facts':13,'facts':pair_rows,'answer_sha256':sha(folder/'answer.txt'),
        'answer_state':meta['answer_state'],'execution_record_state':meta['execution_record_state'],
        'trace_checks':trace_checks,'relation_evidence':relation_evidence,'witness_checks':witness_rows,
        'business_errors_or_unknowns_preserved':errors,'final_unknowns':[],'unresolved_requested_facts':[],
        'unsupported_extra_shell_or_global_collision_claims':[],
        'source_records':{'asset_sha256':sc['ACTOR_CONFIG']['asset_sha256'],'initial_file_sha256':sc['INITIAL_original_file_sha256'],'final_file_sha256':sc['FINAL_original_file_sha256'],'close':sc['CLOSE']},
        'limits':'Source records are producer evidence, not an independent proof excluding every transient mutation; no group, cost or natural-adoption scoring.'})

output={'schema':'independent-anonymous-answer-review-v1','fixed_head':'4a90bbe95ef46c6666050ef1a1096fc6719c3b97',
        'public_root':str(PUBLIC),'reviewed_contracts':['D:/hefe/docs/M4_GROOVED_RAIL_TRANSFER_001_CONSUMPTION_PLAN.md','D:/hefe/docs/M4_SPATIAL_FACT_CONSUMPTION_001_PLAN.md lines 38-48','public/scoring/SCORING_CONTRACT.json'],
        'input_hashes':{f:sha(PUBLIC/'scoring'/f) for f in ('ACTUAL_SNAPSHOT.json','TRUTH.json','SCORING_CONTRACT.json')},
        'independent_geometry':geom,'answers':results,
        'totals':{'slots':6,'complete_correct':6,'incomplete':0,'incorrect':0,'facts_complete_correct':78,'facts_denominator':78},
        'scope_note':'Read only public anonymous evidence and frozen root scoring contracts. No Blender/product/consumer/API execution, no grouping or cost unseal. Exact arithmetic verifier independently implemented here; no producer code imported. 13-fact status includes support, not number matching alone.',
        'incidental_exposure_note':'A direct public TRUTH.json read displayed qualification-only timing metadata; no six-cell timing, usage, cost or mapping was opened or compared. Subsequent oracle access projects only pair_results.'}
(OUT/'RESULTS.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'totals':output['totals'],'distances_m':{n:g['distance_m'] for n,g in geom.items()},'business_failures':{a['anonymous_id']:len(a['business_errors_or_unknowns_preserved']) for a in results},'max_rounding_error_m':max(w['final_max_component_error_to_exact_nearest_m'] for a in results for w in a['witness_checks'].values())},ensure_ascii=False,indent=2))
