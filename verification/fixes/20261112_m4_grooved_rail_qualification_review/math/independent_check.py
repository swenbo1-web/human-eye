"""Root mathematical audit: no imports from the submitted oracle or product."""
from fractions import Fraction as Q
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
import hashlib, json, time

SRC = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_transfer_001')
OUT = Path(__file__).resolve().parent
start = time.perf_counter()
def load(p): return json.loads((SRC/p).read_text(encoding='utf-8-sig'))
def decode(v):
    if isinstance(v,dict):
        if set(v)=={'numerator','denominator'}: return Q(int(v['numerator']),int(v['denominator']))
        return {k:decode(x) for k,x in v.items()}
    if isinstance(v,list): return [decode(x) for x in v]
    return v
def sub(a,b): return tuple(x-y for x,y in zip(a,b))
def add(a,b): return tuple(x+y for x,y in zip(a,b))
def mul(a,t): return tuple(x*t for x in a)
def dot(a,b): return sum(x*y for x,y in zip(a,b))
def cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def norm(t): return cross(sub(t[1],t[0]),sub(t[2],t[0]))
def d2(a,b): return dot(sub(a,b),sub(a,b))
def edges(t): return [(t[i],t[(i+1)%3]) for i in range(3)]
def inside(p,t):
    n=norm(t)
    return all(dot(cross(sub(b,a),sub(p,a)),n)>=0 for a,b in edges(t))
def onseg(p,a,b): return cross(sub(p,a),sub(b,a))==(0,0,0) and dot(sub(p,a),sub(p,b))<=0
def segment_contacts(a,b,t):
    n=norm(t); h=dot(n,sub(a,t[0])); k=dot(n,sub(b,t[0]))
    if h*k>0: return set()
    if h!=k:
        p=add(a,mul(sub(b,a),h/(h-k)))
        return {p} if inside(p,t) else set()
    if h!=0: return set()
    # Independent coplanar construction: endpoint inclusion plus 2D edge intersections.
    found={p for p in (a,b) if inside(p,t)}
    drop=max(range(3),key=lambda j:abs(n[j])); dims=[j for j in range(3) if j!=drop]
    def determinant(u,v): return u[dims[0]]*v[dims[1]]-u[dims[1]]*v[dims[0]]
    u=sub(b,a)
    for c,d in edges(t):
        v=sub(d,c); w=sub(c,a); den=determinant(u,v)
        if den:
            s=determinant(w,v)/den; r=determinant(w,u)/den
            if 0<=s<=1 and 0<=r<=1: found.add(add(a,mul(u,s)))
        else:
            for p in (a,b,c,d):
                if onseg(p,a,b) and onseg(p,c,d): found.add(p)
    return found
def contacts(a,b):
    out=set()
    for x,y in edges(a): out.update(segment_contacts(x,y,b))
    for x,y in edges(b): out.update(segment_contacts(x,y,a))
    return out
def closest_segment(p,a,b):
    e=sub(b,a); t=max(Q(0),min(Q(1),dot(sub(p,a),e)/dot(e,e)))
    return add(a,mul(e,t))
def distance(a,b,c):
    if c: return Q(0)
    vals=[]
    for left,right in ((a,b),(b,a)):
        n=norm(right)
        for p in left:
            f=sub(p,mul(n,dot(sub(p,right[0]),n)/dot(n,n)))
            if inside(f,right): vals.append(d2(p,f))
            vals.extend(d2(p,closest_segment(p,x,y)) for x,y in edges(right))
    for p,q in edges(a):
        for r,s in edges(b):
            u=sub(q,p); v=sub(s,r); w=sub(r,p); n=cross(u,v); den=dot(n,n)
            if den:
                x=dot(cross(w,v),n)/den; y=dot(cross(w,u),n)/den
                if 0<=x<=1 and 0<=y<=1: vals.append(d2(add(p,mul(u,x)),add(r,mul(v,y))))
    return min(vals)
def classify(p,ts):
    assert not any(dot(norm(t),sub(p,t[0]))==0 and inside(p,t) for t in ts)
    for k in range(2,200):
        direction=(Q(k),Q(k*k+1),Q(1)); hits=[]; reject=False
        for t in ts:
            n=norm(t); den=dot(n,direction); num=dot(n,sub(t[0],p))
            if not den:
                if not num: reject=True; break
                continue
            tau=num/den
            if tau<=0: continue
            hit=add(p,mul(direction,tau))
            signs=[dot(cross(sub(b,a),sub(hit,a)),n) for a,b in edges(t)]
            if min(signs)<0: continue
            if min(signs)==0: reject=True; break
            hits.append(tau)
        if not reject:
            assert len(set(hits))==len(hits)
            return {'status':'inside' if len(hits)%2 else 'outside','direction':direction,'hits':sorted(hits)}
    raise AssertionError('ray directions exhausted')
def mix(t,b): return tuple(sum(p[j]*w for p,w in zip(t,b)) for j in range(3))
def check_witness(w,a,b,square):
    ba=w['barycentric_target']; bb=w['barycentric_candidate']
    assert sum(ba)==sum(bb)==1 and min(ba)>=0 and min(bb)>=0
    p=mix(a,ba); q=mix(b,bb)
    assert list(p)==w['point_target'] and list(q)==w['point_candidate']
    assert d2(p,q)==w['squared_distance_m2']==square
def chain(faces):
    c=Counter()
    for face in faces:
        sign=(-1)**sum(face[i]>face[j] for i in range(3) for j in range(i+1,3))
        c[tuple(sorted(face))]+=sign
    return {k:v for k,v in c.items() if v}

snap=load('asset/ACTUAL_SNAPSHOT.json'); truth=decode(load('oracle/TRUTH.json')); cert=load('review/ACTUAL_CERTIFICATES.json')
objs={o['name']:o for o in snap['objects']}
vs={n:[tuple(Q(x) for x in p) for p in o['vertices_world']] for n,o in objs.items()}
fs={n:o['triangles'] for n,o in objs.items()}
ts={n:[tuple(vs[n][i] for i in face) for face in f] for n,f in fs.items()}
assert sum(map(len,vs.values()))==26 and sum(map(len,fs.values()))==36
# Small discriminating regressions for the independent geometry implementation.
base=tuple(tuple(Q(v) for v in p) for p in [(0,0,0),(4,0,0),(0,4,0)])
nested=tuple(tuple(Q(v) for v in p) for p in [(1,1,0),(2,1,0),(1,2,0)])
assert contacts(base,nested)==set(nested)
assert not contacts(base,tuple(add(p,(0,0,1)) for p in base))
assert distance(base,tuple(add(p,(0,0,1)) for p in base),set())==1
crossing=tuple(tuple(Q(v) for v in p) for p in [(1,1,-1),(1,1,1),(2,1,0)])
assert contacts(base,crossing)
body_results={}; self_count=0
for name,faces in fs.items():
    incidence=defaultdict(list)
    for i,f in enumerate(faces):
        assert dot(norm(ts[name][i]),norm(ts[name][i]))>0
        for j in range(3): incidence[tuple(sorted((f[j],f[(j+1)%3])))].append((i,f[j],f[(j+1)%3]))
    assert all(len(v)==2 and v[0][1:]==tuple(reversed(v[1][1:])) for v in incidence.values())
    reached={0}
    while True:
        more={a[0] for uses in incidence.values() if any(u[0] in reached for u in uses) for a in uses}
        if more<=reached: break
        reached |= more
    assert len(reached)==len(faces)
    volume=sum(dot(vs[name][a],cross(vs[name][b],vs[name][c])) for a,b,c in faces)/6
    assert volume>0
    checks=[]
    for i,j in combinations(range(len(faces)),2):
        cc=contacts(ts[name][i],ts[name][j]); shared=set(faces[i])&set(faces[j])
        if len(shared)==2:
            u,v=sorted(shared); assert all(onseg(p,vs[name][u],vs[name][v]) for p in cc)
        elif len(shared)==1: assert cc<={vs[name][next(iter(shared))]}
        else: assert not cc
        original=truth['body_checks'][name]['self_pair_certificates'][len(checks)]
        assert original['triangle_ids']==[i,j] and cc=={tuple(p) for p in original['intersection_endpoints']}
        checks.append({'triangles':[i,j],'contacts':sorted(cc),'legal':True}); self_count+=1
    body_results[name]={'self_pairs':checks,'signed_volume':volume,'connected':True,'closed_oriented':True}

pair_results={}; pair_count=0; witness_count=0; contain_count=0
for name in ('Part_A','Part_B','Part_C'):
    original=truth['pair_results'][name]; rows=[]
    for i,a in enumerate(ts['Target']):
        for j,b in enumerate(ts[name]):
            cc=contacts(a,b); sq=distance(a,b,cc); assert not cc
            old=original['triangle_pair_certificates'][len(rows)]
            assert [old['target_triangle_id'],old['candidate_triangle_id']]==[i,j]
            assert sq==old['squared_distance_m2'] and not old['intersection_endpoints']
            for w in old['minimum_candidates']: check_witness(w,a,b,sq); witness_count+=1
            rows.append({'triangles':[i,j],'square':sq,'intersection':False}); pair_count+=1
    minimum=min(r['square'] for r in rows); assert minimum==original['exact_squared_distance_m2']
    interval=original['sqrt_interval']; lo=Q(interval['lower_decimal_m']); hi=Q(interval['upper_decimal_m'])
    assert lo==interval['lower_exact_m'] and hi==interval['upper_exact_m']
    assert 0<=lo<=hi and lo*lo<=minimum<=hi*hi and hi-lo<=Q(1,10**70)
    queries=[]
    for source,destination,field in [('Target',name,'target_vertices_in_candidate_ray_parity'),(name,'Target','candidate_vertices_in_target_ray_parity')]:
        for vi,p in enumerate(vs[source]):
            c=classify(p,ts[destination]); assert c['status']=='outside'==original[field][vi]['status']
            queries.append({'source':source,'destination':destination,'vertex':vi,**c}); contain_count+=1
    w=original['selected_feature_witness']; a=ts['Target'][w['target_triangle_id']]; b=ts[name][w['candidate_triangle_id']]
    check_witness(w,a,b,minimum)
    ba=w['barycentric_target']; bb=w['barycentric_candidate']; ta=w['target_vertex_ids']; tb=w['candidate_vertex_ids']
    assert ta==fs['Target'][w['target_triangle_id']] and tb==fs[name][w['candidate_triangle_id']]
    if name=='Part_A': assert set(ta)<={3,4,10,11} and min(ba)>0 and [tb[k] for k in range(3) if bb[k]]==[0]
    elif name=='Part_B':
        assert {ta[k] for k in range(3) if ba[k]}=={0,7} and {tb[k] for k in range(3) if bb[k]}=={0,1}
        assert all(0<v<1 for v in ba+bb if v)
        u=sub(vs['Target'][7],vs['Target'][0]); v=sub(vs[name][1],vs[name][0]); gap=sub(w['point_candidate'],w['point_target'])
        assert dot(cross(u,v),cross(u,v))>0 and dot(gap,u)==dot(gap,v)==0
    else: assert min(ta)>=7 and min(ba)>0 and [tb[k] for k in range(3) if bb[k]]==[0]
    pair_results[name]={'triangle_pairs':rows,'minimum_square':minimum,'sqrt_interval_m':[lo,hi],
        'distance_mm':float((lo+hi)*500),'containment_queries':queries,'selected_witness':w,
        'at_least_4mm':minimum>=Q(1,250)**2,'feature_passed':True}

# All actual Target support triplets, not merely the ideal extrusion hull.
hull_supports=0
for a,b,c in combinations(vs['Target'],3):
    n=cross(sub(b,a),sub(c,a))
    if n==(0,0,0): continue
    signs=[dot(n,sub(p,a)) for p in vs['Target']]
    if min(signs)<0<max(signs): continue
    assert min(signs)!=max(signs)
    n=mul(n,-1) if min(signs)>=0 else n
    assert all(dot(n,sub(p,a))<0 for p in vs['Part_A']); hull_supports+=1
assert hull_supports>0
prism_rows=cert['A_prism_bounds']; accumulated=[]; support_checks=[]
for row in prism_rows:
    cap=row['cap']; points=[vs['Target'][i] for i in cap+[i+7 for i in cap]]
    used={i for f in row['oriented_faces'] for i in f}
    assert used==set(cap+[i+7 for i in cap]) and len(row['oriented_faces'])==8
    directed=Counter((f[j],f[(j+1)%3]) for f in row['oriented_faces'] for j in range(3))
    assert all(directed[(b,a)]==count for (a,b),count in directed.items())
    n=tuple(Q(x) for x in row['direction'])
    gap=min(dot(p,n) for p in vs['Part_A'])-max(dot(p,n) for p in points)
    assert gap>0 and gap==Q(row['projected_gap'])
    assert gap*gap/dot(n,n)==Q(row['distance_square_lower_bound_m2'])
    accumulated+=row['oriented_faces']; support_checks.append({'cap':cap,'gap':gap})
assert chain(accumulated)==chain(fs['Target'])
assert pair_count==288 and self_count==294 and contain_count==54
assert [pair_results[n]['at_least_4mm'] for n in pair_results]==[True,False,True]
assert min(pair_results,key=lambda n:pair_results[n]['minimum_square'])=='Part_B'
sources=['asset/ACTUAL_SNAPSHOT.json','oracle/TRUTH.json','oracle/exact_geometry.py','oracle/exact_oracle.py','review/actual_certificates.py','review/ACTUAL_CERTIFICATES.json']
result={'passed':True,'execution':'new independent implementation; stdlib only; no submitted modules imported',
    'counts':{'interbody_pairs':pair_count,'self_pairs':self_count,'containment':contain_count,'saved_minimum_witnesses':witness_count,'synthetic_checks':4,'hull_support_triplets':hull_supports},
    'body_results':body_results,'pair_results':pair_results,'A_material_void_support_checks':support_checks,
    'A_actual_oriented_chain_identity':True,'sources':{p:hashlib.sha256((SRC/p).read_bytes()).hexdigest() for p in sources},
    'checker_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'elapsed_seconds':time.perf_counter()-start}
(OUT/'RESULTS.json').write_text(json.dumps(result,default=str,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'passed':True,'counts':result['counts'],'distances_mm':{n:r['distance_mm'] for n,r in pair_results.items()},'elapsed_seconds':result['elapsed_seconds']}))
