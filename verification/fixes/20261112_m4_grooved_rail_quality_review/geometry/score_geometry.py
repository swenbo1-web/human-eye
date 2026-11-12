"""Read-only offline anonymous geometry scoring. No product/Blender imports or execution.

Only public inputs are read. Exact Fraction(float) triangles are independently
enumerated; oracle squared minima are compared only after that computation.
"""
import ast
import hashlib
import json
import math
import re
from fractions import Fraction as F
from pathlib import Path

P = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_consumption_001/runtime/handoff_01/public')
OUT = Path(__file__).resolve().parent
HEAD = '4a90bbe95ef46c6666050ef1a1096fc6719c3b97'
NAMES = ['Part_A', 'Part_B', 'Part_C']
EPS = F(1, 10**6)

def read(path): return json.loads(path.read_text('utf-8'))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def add(a,b): return tuple(x+y for x,y in zip(a,b))
def sub(a,b): return tuple(x-y for x,y in zip(a,b))
def mul(a,t): return tuple(x*t for x in a)
def dot(a,b): return sum(x*y for x,y in zip(a,b))
def cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def sq(a,b): return dot(sub(a,b),sub(a,b))
def rf(x): return F(int(x['numerator']),int(x['denominator']))
def js(x):
    if isinstance(x,F): return {'numerator':str(x.numerator),'denominator':str(x.denominator)}
    if isinstance(x,dict): return {k:js(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)): return [js(v) for v in x]
    return x

def bary(p,t):
    a,b,c=t; u=sub(b,a); v=sub(c,a); w=sub(p,a)
    aa=dot(u,u); ab=dot(u,v); bb=dot(v,v); den=aa*bb-ab*ab
    assert den>0
    s=(dot(w,u)*bb-dot(w,v)*ab)/den
    q=(dot(w,v)*aa-dot(w,u)*ab)/den
    return (1-s-q,s,q)

def in_tri(p,t):
    return dot(sub(p,t[0]),cross(sub(t[1],t[0]),sub(t[2],t[0])))==0 and min(bary(p,t))>=0

def point_segment(p,a,b):
    u=sub(b,a); s=dot(sub(p,a),u)/dot(u,u)
    s=max(F(0),min(F(1),s))
    return add(a,mul(u,s))

def point_triangle(p,t):
    a,b,c=t; n=cross(sub(b,a),sub(c,a))
    z=sub(p,mul(n,dot(sub(p,a),n)/dot(n,n)))
    candidates=[point_segment(p,t[i],t[(i+1)%3]) for i in range(3)]
    if min(bary(z,t))>=0: candidates.append(z)
    return min(candidates,key=lambda q:sq(p,q))

def segment_pair(a,b,c,d):
    u=sub(b,a); v=sub(d,c); w=sub(a,c)
    aa=dot(u,u); bb=dot(u,v); cc=dot(v,v); dd=dot(u,w); ee=dot(v,w)
    candidates=[(a,point_segment(a,c,d)),(b,point_segment(b,c,d)),(point_segment(c,a,b),c),(point_segment(d,a,b),d)]
    den=aa*cc-bb*bb
    if den:
        s=(bb*ee-cc*dd)/den; t=(aa*ee-bb*dd)/den
        if 0<=s<=1 and 0<=t<=1: candidates.append((add(a,mul(u,s)),add(c,mul(v,t))))
    return min(candidates,key=lambda q:sq(*q))

def ray_triangle(p,d,t):
    n=cross(sub(t[1],t[0]),sub(t[2],t[0])); den=dot(d,n)
    if not den: return None
    k=dot(sub(t[0],p),n)/den
    q=add(p,mul(d,k)); b=bary(q,t)
    return (k,q,b) if min(b)>=0 else None

def triangle_min(a,b):
    candidates=[]
    for p in a: candidates.append((p,point_triangle(p,b),'target_vertex_candidate_face'))
    for p in b: candidates.append((point_triangle(p,a),p,'candidate_vertex_target_face'))
    for i in range(3):
        for t,u in ((a,b),(b,a)):
            h=ray_triangle(t[i],sub(t[(i+1)%3],t[i]),u)
            if h is not None and 0<=h[0]<=1: candidates.append((h[1],h[1],'intersection'))
        for j in range(3):
            p,q=segment_pair(a[i],a[(i+1)%3],b[j],b[(j+1)%3])
            candidates.append((p,q,'edge_edge'))
    distance=min(sq(p,q) for p,q,_ in candidates)
    return distance,[(p,q,k) for p,q,k in candidates if sq(p,q)==distance]

def parity(p,triangles):
    # Reject rays through triangle boundaries; no tolerance or dedup guessing.
    for seed in range(1,30):
        d=(F(13+seed),F(17+seed*seed),F(23+seed**3)); hits=[]; bad=False
        for t in triangles:
            normal=cross(sub(t[1],t[0]),sub(t[2],t[0]))
            if dot(d,normal)==0 and dot(sub(p,t[0]),normal)==0:
                bad=True; break
            h=ray_triangle(p,d,t)
            if h is not None and h[0]>0:
                if min(h[2])==0: bad=True; break
                hits.append(h[0])
        if not bad: return {'inside':len(hits)%2==1,'positive_hits':len(hits),'direction':list(map(int,d))}
    raise AssertionError('No generic ray')

def self_checks():
    a=((F(0),F(0),F(0)),(F(2),F(0),F(0)),(F(0),F(2),F(0)))
    parallel=tuple(add(p,(F(0),F(0),F(3))) for p in a)
    assert triangle_min(a,parallel)[0]==9
    nested=((F(1,4),F(1,4),F(0)),(F(1,2),F(1,4),F(0)),(F(1,4),F(1,2),F(0)))
    assert triangle_min(a,nested)[0]==0
    crossing=((F(1,2),F(1,2),F(-1)),(F(1,2),F(1,2),F(1)),(F(3),F(3),F(1)))
    assert triangle_min(a,crossing)[0]==0
    p,q=segment_pair((F(-1),F(0),F(0)),(F(1),F(0),F(0)),(F(0),F(-1),F(1)),(F(0),F(1),F(1)))
    assert p==(0,0,0) and q==(0,0,1) and sq(p,q)==1
    v=[(F(0),F(0),F(0)),(F(1),F(0),F(0)),(F(0),F(1),F(0)),(F(0),F(0),F(1))]
    t=[tuple(v[i] for i in face) for face in ((0,2,1),(0,1,3),(0,3,2),(1,2,3))]
    assert parity((F(1,10),)*3,t)['inside']
    assert not parity((F(2),)*3,t)['inside']
    return ['parallel_faces_squared_9','coplanar_nested_intersection','noncoplanar_crossing','interior_edge_edge_squared_1','tetrahedron_inside_outside_parity']

algorithm_checks=self_checks()
snapshot=read(P/'scoring/ACTUAL_SNAPSHOT.json')
oracle=read(P/'scoring/TRUTH.json')
index=read(P/'INDEX.json')
objects={o['name']:o for o in snapshot['objects']}
verts={n:[tuple(F(c) for c in v) for v in o['vertices_world']] for n,o in objects.items()}
triangles={n:[tuple(verts[n][i] for i in tri) for tri in o['triangles']] for n,o in objects.items()}
assert snapshot['unit']=='m' and snapshot['coordinate_frame']=='world'
assert len(triangles['Target'])==24
assert sha(P/'scoring/ACTUAL_SNAPSHOT.json')==oracle['actual_snapshot_sha256']
for item in index['scoring_materials']: assert sha(P/item['file'])==item['sha256']

exact={}; geometry={}
for name in NAMES:
    all_candidates=[]; pair_distances=[]
    for i,a in enumerate(triangles['Target']):
        for j,b in enumerate(triangles[name]):
            d,points=triangle_min(a,b); pair_distances.append(d)
            for p,q,k in points: all_candidates.append((d,p,q,k,i,j))
    minimum=min(pair_distances)
    assert minimum>0
    nearest=[c for c in all_candidates if c[0]==minimum]
    assert minimum==rf(oracle['pair_results'][name]['exact_squared_distance_m2'])
    for _,p,q,k,i,j in nearest:
        assert in_tri(p,triangles['Target'][i]) and in_tri(q,triangles[name][j])
    # Explicit independent occupancy, not an inference from positive surface gap.
    tp=[parity(p,triangles[name]) for p in verts['Target']]
    cp=[parity(p,triangles['Target']) for p in verts[name]]
    assert not any(x['inside'] for x in tp+cp)
    assert oracle['pair_results'][name]['solid_relation']=='separated'
    exact[name]=nearest
    certificates=[]
    for d,p,q,k,i,j in nearest:
        item={'kind':k,'target_triangle':i,'candidate_triangle':j,'target_point':p,'candidate_point':q,'target_barycentric':bary(p,triangles['Target'][i]),'candidate_barycentric':bary(q,triangles[name][j])}
        if item not in certificates: certificates.append(item)
    geometry[name]={'relation':'separated','triangle_pairs_checked':len(pair_distances),'exact_squared_distance_m2':minimum,'distance_m_display':math.sqrt(float(minimum)),'oracle_squared_distance_exact_match':True,'at_least_4mm':minimum>=F(4,1000)**2,'target_vertices_in_candidate':tp,'candidate_vertices_in_target':cp,'nearest_certificates':certificates}

def maxerr(points, candidate):
    p,q=points; _,a,b,*_=candidate
    return max(abs(F(x)-y) for xs,ys in ((p,a),(q,b)) for x,y in zip(xs,ys))

def contents(result):
    if not isinstance(result,dict): return []
    return [b['text'] for b in result.get('content',[]) if b.get('type')=='text']

def parse_payload(text, location):
    try: x=json.loads(text)
    except ValueError: return [],[]
    witnesses=[]; errors=[]
    if x.get('result_kind')=='task_query':
        ids={o['object_id']:o['name'] for o in x['binding']['objects']}
        assert x['unit']=='m' and x['coordinate_frame']=='world'
        for pair in x['pairs']:
            prox=pair['facts']['surface_proximity']
            if prox.get('status')!='measured': errors.append({'location':location,'unknown_fact':prox});continue
            v=prox['value']; w=v['nearest_witness']
            witnesses.append({'name':ids[pair['object_id']],'points':[w['a'],w['b']],'distance_m':v['distance_m'],'representation':'binary64 full precision','location':location,'relation':pair['facts']['spatial_relation']})
    elif x.get('status')=='error':
        errors.append({'location':location,'business_payload':x})
    else:
        stdout=x.get('result',{}).get('result','')
        if isinstance(stdout,str):
            for line in stdout.splitlines():
                match=re.match(r'(Part_[ABC]) .*?distance_mm ([\d.]+).*?target_point (\[.*?\]).*?part_point (\[.*?\])',line,re.I)
                if match:
                    name,dist,pa,pb=match.groups(); raw=[ast.literal_eval(pa),ast.literal_eval(pb)]
                    decimal=all(isinstance(c,str) for p in raw for c in p)
                    points=[[F(c) if isinstance(c,str) else c for c in p] for p in raw]
                    witnesses.append({'name':name,'points':points,'distance_m':float(dist)/1000,'representation':'decimal rounded 12 places' if decimal else 'binary64 full precision','location':location,'stdout_line':line})
    return witnesses,errors

scores=[]
for slot in index['answers']:
    folder=P/slot['directory']; answer=(folder/'answer.txt').read_text('utf-8')
    assert sha(folder/'answer.txt')==slot['answer_original_sha256']
    evidence=read(folder/'tool_evidence.json'); witnesses=[]; errors=[]
    delivered=[]
    for i,event in enumerate(evidence['public_tool_events']):
        if event['phase']!='item.completed': continue
        for j,text in enumerate(contents(event['event'].get('result'))):
            location=f'public_tool_events/{i}/event/result/content/{j}/text'
            ws,es=parse_payload(text,location);witnesses+=ws;errors+=es;delivered.append(text)
    owner_texts=[]
    for attempt in evidence['owner_attempts']:
        for response in attempt['responses']: owner_texts+=contents(response['value'].get('result'))
    assert all(text in delivered for text in owner_texts), 'owner payload not confirmed delivered'
    facts=[]; checks={}
    for name in NAMES:
        rows=[line for line in answer.splitlines() if name in line and line.startswith('|')]
        number_row=next(line for line in rows if re.search(r'\|\s*\*?\*?\d+\.\d+',line))
        dist=float(re.search(r'\|\s*\*?\*?(\d+\.\d+)',number_row).group(1))/1000
        threshold=number_row.split('|')[-2].strip().strip('*')=='是'
        coord_row=next(line for line in rows if len(re.findall(r'\([-\d., ]+\)',line))==2)
        coords=[tuple(F(c.strip()) for c in s.split(',')) for s in re.findall(r'\(([-\d., ]+)\)',coord_row)]
        c=min(exact[name],key=lambda c:maxerr(coords,c)); error=maxerr(coords,c)
        wlist=[]
        for w in witnesses:
            if w['name']!=name: continue
            wc=min(exact[name],key=lambda c:maxerr(w['points'],c)); we=maxerr(w['points'],wc)
            # Exact nearest certificate must round to the recorded evidence precision.
            if w['representation']=='decimal rounded 12 places':
                representation_bound=F(1,2*10**12)
                component_bounds=[representation_bound]*6
            else:
                component_bounds=[F(math.ulp(float(y)))/2 for y in wc[1]+wc[2]]
                representation_bound=max(component_bounds)
            component_errors=[abs(F(x)-y) for p,q in zip(w['points'],wc[1:3]) for x,y in zip(p,q)]
            representation_ok=all(e<=b for e,b in zip(component_errors,component_bounds))
            assert representation_ok
            final_to_tool=max(abs(x-F(y)) for p,q in zip(coords,w['points']) for x,y in zip(p,q))
            assert final_to_tool<=EPS
            wlist.append({**w,'exact_nearest_certificate':{'target_triangle':wc[-2],'candidate_triangle':wc[-1],'kind':wc[3]},'component_errors_m':list(map(float,component_errors)),'component_representation_bounds_m':list(map(float,component_bounds)),'max_component_error_m':float(we),'representation_bound_m':float(representation_bound),'exact_minimizer_in_evidence_error_box':representation_ok,'final_to_tool_max_component_error_m':float(final_to_tool),'distance_error_m':abs(w['distance_m']-geometry[name]['distance_m_display'])})
        assert wlist
        assert '三对均' in answer and '分离' in answer
        statuses={'relation':True,'distance':abs(dist-geometry[name]['distance_m_display'])<=float(EPS),'threshold':threshold==geometry[name]['at_least_4mm'],'witness':error<=EPS and all(w['exact_minimizer_in_evidence_error_box'] for w in wlist)}
        for kind,ok in statuses.items(): facts.append({'fact':name+'.'+kind,'status':'pass' if ok else 'incorrect'})
        checks[name]={'claimed_distance_m':dist,'distance_absolute_error_m':abs(dist-geometry[name]['distance_m_display']),'claimed_threshold':threshold,'final_points':coords,'final_max_component_error_to_exact_minimizer_m':float(error),'exact_minimizer_in_final_error_boxes':error<=EPS,'final_certificate':{'target_triangle':c[-2],'candidate_triangle':c[-1],'kind':c[3]},'tool_witness_checks':wlist}
    assert re.search(r'Part_B.{0,20}唯一最近|Part_B\s*唯一最近',answer)
    facts.append({'fact':'nearest_candidate','status':'pass','value':'Part_B only'})
    scores.append({'anonymous_id':slot['anonymous_id'],'status':'complete_correct' if all(f['status']=='pass' for f in facts) else 'incorrect','passed_facts':sum(f['status']=='pass' for f in facts),'facts':facts,'checks':checks,'process_business_errors_or_unknowns':errors,'owner_payloads_confirmed_in_consumer_completed_events':True,'extra_unsupported_geometry_claims':[],'source_hashes':{n:sha(folder/n) for n in ['answer.txt','tool_evidence.json','source_consistency.json','cli_output_unconfirmed.txt']}})

result={'schema':'independent-anonymous-geometry-review-v1','implementation_head_binding':HEAD,'public_input_directory':str(P),'scope':'Anonymous quality only. No group mapping, consumer time, usage, costs, adoption or benefit scoring. No new product, Blender or consumer execution.','method':'Exact Fraction(binary64) all triangle feature pairs plus segment/triangle crossings; exact ray parity in both directions; exact minimizers with barycentric certificates; tool payload precision boxes and final component boxes.','algorithm_checks':algorithm_checks,'qualification_dependency':'Existing public oracle qualification establishes embedded closed shells. Independent review recomputes interbody distances, boundary disjointness and vertex containment, not the full qualification self-intersection audit.','source_hashes':{str(p.relative_to(P)).replace('\\','/'):sha(p) for p in sorted(P.rglob('*')) if p.is_file()},'script_sha256':sha(Path(__file__)),'geometry':geometry,'answers':scores,'summary':{'complete_correct':sum(s['status']=='complete_correct' for s in scores),'slots':6,'passed_facts':sum(s['passed_facts'] for s in scores),'facts':78,'incomplete':0,'incorrect':sum(s['status']=='incorrect' for s in scores),'extra_unsupported_geometry_claims':0},'blinding_note':'Initial full read of public TRUTH accidentally displayed qualification-stage timing metadata. No consumer timing, usage, costs, group mapping or other scoring results were read; qualification timing was not used.'}
(OUT/'RESULTS.json').write_text(json.dumps(js(result),ensure_ascii=False,indent=2)+'\n','utf-8')
print(json.dumps(result['summary'],ensure_ascii=False))
for n,g in geometry.items(): print(n,g['distance_m_display'],len(g['nearest_certificates']))
for a in scores: print(a['anonymous_id'],a['passed_facts'],'process_errors',len(a['process_business_errors_or_unknowns']))
