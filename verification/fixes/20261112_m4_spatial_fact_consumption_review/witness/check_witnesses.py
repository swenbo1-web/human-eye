"""Independent saved-data geometry review. Standard library only; no product imports.

Read scope is the public handoff. Fraction(float) represents each captured
binary64 world vertex exactly. An independently chosen separating normal
(cross product of the captured transform's z and x columns) gives a rigorous
global lower bound over ALL vertices, hence all complete triangles. An attained
vertex/triangle pair found without using any consumer answer gives an upper bound.
Every answer witness is separately recovered on actual triangles, with exact
nonnegative barycentrics. The attained distance is compared to the global lower
bound. This is a numerical optimality certificate, not a claim of symbolic
equality between binary64 output and an irrational mathematical optimum.
"""
from fractions import Fraction as F
from pathlib import Path
from math import sqrt, isqrt
import ast
import hashlib
import json
import re

PUBLIC = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_spatial_fact_consumption_001/runtime/handoff_01/public')
OUT = Path(__file__).resolve().parent
NAMES = ['Peer_000', 'Competing_001', 'Near_003']
EPS = F(1, 10**6)
# This is a stricter INTERNAL certificate requirement, not an expanded grade tolerance.
CERT_EPS = F(1, 10**15)

def sub(a,b): return tuple(x-y for x,y in zip(a,b))
def add(a,b): return tuple(x+y for x,y in zip(a,b))
def scale(a,t): return tuple(x*t for x in a)
def dot(a,b): return sum(x*y for x,y in zip(a,b))
def cross(a,b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def vfrac(a): return tuple(F(x) for x in a)
def vf(a): return [float(x) for x in a]
def fr(a): return [a.numerator,a.denominator]
def sqrt_interval(q):
    """Outward decimal bounds on sqrt(q), proved using integer arithmetic."""
    scale10 = 10**30
    k = isqrt((q.numerator*scale10*scale10)//q.denominator)
    lo, hi = F(k,scale10), F(k+1,scale10)
    assert lo*lo <= q <= hi*hi
    return lo, hi

def triangle_nearest(p, a, b, c):
    """Exhaust the face projection and its three boundary segments."""
    ab, ac, ap = sub(b,a), sub(c,a), sub(p,a)
    aa,bb,cc = dot(ab,ab),dot(ab,ac),dot(ac,ac)
    det=aa*cc-bb*bb
    candidates=[]
    if det>0:
        u=(dot(ap,ab)*cc-dot(ap,ac)*bb)/det
        v=(dot(ap,ac)*aa-dot(ap,ab)*bb)/det
        if u>=0 and v>=0 and u+v<=1:
            candidates.append((add(a,add(scale(ab,u),scale(ac,v))),(1-u-v,u,v)))
    for i,j in ((0,1),(1,2),(2,0)):
        vertices=(a,b,c)
        edge=sub(vertices[j],vertices[i]); den=dot(edge,edge)
        t=max(0,min(1,dot(sub(p,vertices[i]),edge)/den)) if den else 0
        weights=[0,0,0]; weights[i]=1-t; weights[j]=t
        candidates.append((add(vertices[i],scale(edge,t)),tuple(weights)))
    q,w=min(candidates,key=lambda r: dot(sub(p,r[0]),sub(p,r[0])))
    return dot(sub(p,q),sub(p,q)),q,w

snapshot=json.loads((PUBLIC/'scoring/ACTUAL_SNAPSHOT.json').read_text(encoding='utf-8'))
objects={o['name']:o for o in snapshot['objects']}
V={name:[vfrac(v) for v in objects[name]['vertices_world']] for name in ['Target']+NAMES}
T={name:[tuple(t) for t in objects[name]['triangles']] for name in ['Target']+NAMES}
assert snapshot['unit']=='m' and snapshot['coordinate_frame']=='world' and snapshot['scale_length']==1
for name in V:
    assert set(i for tri in T[name] for i in tri)==set(range(len(V[name])))
    assert all(len(t)==3 for t in T[name])

def nearest_on_surface(p,name):
    # Float search proposes one feature; membership and distance are then exact.
    # No global correctness depends on the proposal being the closest feature:
    # exact global lower support + attained upper distance are checked separately.
    fp=vf(p); verts=[vf(v) for v in V[name]]
    proposal=min(range(len(T[name])),key=lambda k:triangle_nearest(fp,*(verts[i] for i in T[name][k]))[0])
    ds,q,w=triangle_nearest(p,*(V[name][i] for i in T[name][proposal]))
    assert all(x>=0 for x in w) and sum(w)==1
    assert tuple(sum(w[j]*V[name][T[name][proposal][j]][i] for j in range(3)) for i in range(3))==q
    return {'triangle':proposal,'weights':w,'point':q,'residual_squared':ds}

matrix=objects['Target']['matrix_world']
normal=cross(tuple(F(matrix[i][2]) for i in range(3)),tuple(F(matrix[i][0]) for i in range(3)))
assert dot(normal,normal)>0
supports={name:[dot(normal,v) for v in V[name]] for name in V}
global_bounds={}
for name in NAMES:
    gap=min(supports[name])-max(supports['Target'])
    assert gap>0
    lower_sq=gap*gap/dot(normal,normal)
    # Independent attained upper: choose all Target vertices on its top support
    # within 1e-12 in unnormalized support units, project to candidate triangles.
    eligible=[i for i,s in enumerate(supports['Target']) if max(supports['Target'])-s<F(1,10**12)]
    fv=[vf(v) for v in V[name]]
    best=None
    for vi in eligible:
        fp=vf(V['Target'][vi])
        for ti,tri in enumerate(T[name]):
            ds,_,_=triangle_nearest(fp,*(fv[i] for i in tri))
            if best is None or ds<best[0]: best=(ds,vi,ti)
    _,vi,ti=best
    ds,q,w=triangle_nearest(V['Target'][vi],*(V[name][i] for i in T[name][ti]))
    lo=sqrt_interval(lower_sq)[0]; hi=sqrt_interval(ds)[1]
    assert hi>=lo and hi-lo<CERT_EPS
    global_bounds[name]={'lo':lo,'hi':hi,'normal':normal,'gap':gap,'lower_sq':lower_sq,'upper_sq':ds,
        'target_vertex':vi,'candidate_triangle':ti,'candidate_barycentric':w,
        'a':V['Target'][vi],'b':q,'support_target_vertex':supports['Target'].index(max(supports['Target'])),
        'support_candidate_vertex':supports[name].index(min(supports[name]))}

truth=json.loads((PUBLIC/'scoring/TRUTH.json').read_text(encoding='utf-8'))
truth_by_name={r['candidate_name']:r for r in truth['pairs']}
for name,b in global_bounds.items():
    t=truth_by_name[name]
    # Bounds need not be identical because this independent direction was selected
    # from the transform, rather than imported from the reference certificate.
    assert abs(float((b['lo']+b['hi'])/2)-t['distance_midpoint_m'])<float(CERT_EPS)
assert global_bounds['Peer_000']['hi']<min(global_bounds[n]['lo'] for n in NAMES[1:])

def decode_response(o):
    vals=[]
    for r in o['responses']:
        for block in r['value'].get('result',{}).get('content',[]):
            if block.get('type')=='text':
                try: vals.append(json.loads(block['text']))
                except (TypeError,ValueError): vals.append(block['text'])
    return vals

def extract_tool(e):
    got={}
    for attempt in e['owner_attempts']:
        for val in decode_response(attempt):
            if isinstance(val,dict) and val.get('result_kind')=='task_query':
                idnames={o['object_id']:o['name'] for o in val['binding']['objects']}
                for pair in val['pairs']:
                    name=idnames[pair['object_id']]
                    proximity=pair.get('facts',{}).get('surface_proximity',{})
                    if proximity.get('status')=='measured':
                        v=proximity['value']; w=v['nearest_witness']
                        got[name]={'a':w['a'],'b':w['b'],'distance_m':v['distance_m'],
                            'order':attempt['order'],'precision':'binary64','source':'surface_proximity.value.nearest_witness'}
            elif isinstance(val,dict) and isinstance(val.get('result'),dict):
                out=val['result'].get('result','')
                if not isinstance(out,str): continue
                # Owner stdout preserves literal backslash-n for some bridge outputs.
                for line in out.replace('\\n','\n').splitlines():
                    for name in NAMES:
                        if not line.startswith(name+' '): continue
                        rest=line[len(name)+1:]
                        if rest.startswith('{'):
                            row=ast.literal_eval(rest)
                            if 'target_point_m' in row:
                                got[name]={'a':row['target_point_m'],'b':row['candidate_point_m'],
                                    'distance_m':row['distance_m'],'order':attempt['order'],
                                    'precision':'binary64','source':'native stdout target_point_m/candidate_point_m'}
                        else:
                            m=re.search(r'distance_(m|mm)\s+([\d.eE+-]+).*?(?:Target_xyz|Target_world_m)\s+(\[[^\]]+\]).*?(?:other_xyz|other_world_m)\s+(\[[^\]]+\])',rest)
                            if m:
                                a,b=ast.literal_eval(m[3]),ast.literal_eval(m[4])
                                rounded=isinstance(a[0],str)
                                got[name]={'a':[float(x) for x in a],'b':[float(x) for x in b],
                                    'distance_m':float(m[2])/(1000 if m[1]=='mm' else 1),'order':attempt['order'],
                                    'precision':'12_decimal_stdout' if rounded else 'binary64','source':'native stdout explicit world endpoints'}
    return got

def parse_final(text):
    got={}
    for name in NAMES:
        lines=[line for line in text.splitlines() if line.startswith('|') and name in line]
        pointline=next(line for line in lines if re.search(r'\([\d\s.,+−-]+\)',line))
        coords=re.findall(r'\(([\d\s.,+−-]+)\)',pointline)
        points=[[float(v.strip().replace('−','-')) for v in s.split(',')] for s in coords]
        assert len(points)==2 and all(len(p)==3 for p in points)
        numeric=[]
        for line in lines:
            numeric.extend(float(c.strip()) for c in line.split('|') if re.fullmatch(r'\s*\d+\.\d+\s*',c))
        assert len(numeric)==1
        got[name]={'a':points[0],'b':points[1],'distance_m':numeric[0]/1000}
    return got

def serial_surface(s):
    return {'triangle':s['triangle'],'barycentric_exact':[fr(F(w)) for w in s['weights']],
            'surface_point_exact':[fr(x) for x in s['point']], 'surface_point_m':vf(s['point']),
            'point_to_surface_recovery_upper_m':float(sqrt_interval(s['residual_squared'])[1])}

results=[]
answer_folders=sorted(PUBLIC.glob('answer_*'))
assert len(answer_folders)==6
for folder in answer_folders:
    e=json.loads((folder/'tool_evidence.json').read_text(encoding='utf-8'))
    tool=extract_tool(e); final=parse_final((folder/'answer.txt').read_text(encoding='utf-8'))
    assert set(tool)==set(NAMES)
    rows=[]
    for name in NAMES:
        ev=tool[name]; f=final[name]; bounds=global_bounds[name]
        sa=nearest_on_surface(vfrac(ev['a']),'Target'); sb=nearest_on_surface(vfrac(ev['b']),name)
        if ev['precision']=='12_decimal_stdout':
            # The saved stdout is rounded. Construct a jointly compatible pair
            # rather than treating the two independent surface projections as
            # sufficient. Alternating projections only propose this pair; the
            # exact all-vertex global lower bound below certifies its optimality.
            for _ in range(3):
                sb=nearest_on_surface(sa['point'],name)
                sa=nearest_on_surface(sb['point'],'Target')
            for side,s in [('a',sa),('b',sb)]:
                displacement=sub(vfrac(ev[side]),s['point'])
                s['residual_squared']=dot(displacement,displacement)
        diff=sub(sa['point'],sb['point']); ds=dot(diff,diff)
        upper=sqrt_interval(ds)[1]
        # Exact triangle membership plus independently certified GLOBAL lower bound
        # is the sufficient certificate; point distance/surface proximity alone is not.
        optimality_gap=upper-bounds['lo']
        assert optimality_gap>=0
        recovery=max(sqrt_interval(sa['residual_squared'])[1],sqrt_interval(sb['residual_squared'])[1])
        recovery_limit=F(1,10**11) if ev['precision']=='12_decimal_stdout' else F(1,10**12)
        round_errors=[abs(F(f[end][i])-F(ev[end][i])) for end in ['a','b'] for i in range(3)]
        recovered_round_errors=[abs(F(f[end][i])-s['point'][i]) for end,s in [('a',sa),('b',sb)] for i in range(3)]
        distance_error=max(abs(F(f['distance_m'])-bounds['lo']),abs(F(f['distance_m'])-bounds['hi']))
        tool_distance_error=max(abs(F(ev['distance_m'])-bounds['lo']),abs(F(ev['distance_m'])-bounds['hi']))
        checks={'actual_triangle_membership_exact_after_numeric_recovery':True,
            'tool_point_recovery_within_strict_internal_limit':recovery<=recovery_limit,
            'global_optimality_certified_within_1e_minus_15_m':optimality_gap<=CERT_EPS,
            'final_coordinate_component_gate_1e_minus_6_m':max(round_errors)<=EPS and max(recovered_round_errors)<=EPS,
            'distance_gate_1e_minus_6_m':distance_error<=EPS,
            'tool_distance_gate_1e_minus_6_m':tool_distance_error<=EPS}
        row={'candidate':name,'checks':checks,'passed':all(checks.values()),'tool_evidence':ev,'final_text':f,
            'target_surface_certificate':serial_surface(sa),'candidate_surface_certificate':serial_surface(sb),
            'attained_squared_distance_exact':fr(ds),'attained_distance_m':sqrt(float(ds)),
            'certified_global_optimality_gap_upper_m':float(optimality_gap),
            'full_precision_recovery_upper_m':float(recovery),
            'final_vs_tool_max_component_error_m':float(max(round_errors)),
            'final_vs_recovered_max_component_error_m':float(max(recovered_round_errors)),
            'claimed_gap_max_error_vs_global_interval_m':float(distance_error),
            'true_at_least_4mm':bounds['lo']>=F(4,1000), 'separated':bounds['lo']>0}
        rows.append(row)
    result={'anonymous_id':folder.name,'geometric_witness_quality':'pass' if all(r['passed'] for r in rows) else 'fail',
        'scope':'saved public geometry, three distances, actual-surface witnesses, final text rounding only',
        'pairs':rows}
    results.append(result)
    (OUT/(folder.name+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

certificates={}
for name,b in global_bounds.items():
    certificates[name]={'normal_exact':[fr(x) for x in b['normal']], 'support_gap_exact':fr(b['gap']),
        'support_target_vertex':b['support_target_vertex'],'support_candidate_vertex':b['support_candidate_vertex'],
        'lower_squared_exact':fr(b['lower_sq']), 'upper_squared_exact':fr(b['upper_sq']),
        'distance_lower_m':float(b['lo']),'distance_upper_m':float(b['hi']),
        'certified_interval_width_m':float(b['hi']-b['lo']),
        'independent_upper_witness':{'target_vertex':b['target_vertex'],'candidate_triangle':b['candidate_triangle'],
            'candidate_barycentric_exact':[fr(F(x)) for x in b['candidate_barycentric']],
            'target_point_m':vf(b['a']),'candidate_point_m':vf(b['b'])},
        'truth_interval_m':[truth_by_name[name]['distance_lower_m'],truth_by_name[name]['distance_upper_m']]}
report={'evidence_commit_assigned':'5cdf62f311f94890ca569d06c1a858f1578225e4',
    'evidence_commit_verification':'Commit identity supplied by parent; this child ran no Git commands.',
    'public_root':str(PUBLIC),'input_sha256':{
        str(p.relative_to(PUBLIC)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [PUBLIC/'scoring/ACTUAL_SNAPSHOT.json',PUBLIC/'scoring/TRUTH.json',PUBLIC/'scoring/SCORING_CONTRACT.json']+
        [p for a in sorted(PUBLIC.glob('answer_*')) for p in [a/'answer.txt',a/'tool_evidence.json']]},
    'method':'Independent exact rational all-vertex support lower bound + attained triangle upper bound; recovered actual-surface witnesses checked against that global bound; decimal text checked componentwise.',
    'numerical_scope':'Symbolic equality of floating output to exact minimizers is not asserted. Global optimality is certified to at most 1e-15 m (actual gaps reported), stricter than the frozen 1e-6 m gate. No wider distance tolerance or fixed reference witness is used.',
    'external_calls':{'Blender':0,'consumer_models':0,'API':0},
    'imports':'Python standard library only; no product solver, reference verifier, numpy or Blender imports.',
    'global_geometry_certificates':certificates,'nearest_only_among_requested':'Peer_000',
    'all_six_geometric_witnesses_pass':all(r['geometric_witness_quality']=='pass' for r in results),
    'anonymous_results':results}
(OUT/'WITNESS_RESULTS.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'all_six_pass':report['all_six_geometric_witnesses_pass'],
    'global_distance_intervals':{k:[v['distance_lower_m'],v['distance_upper_m']] for k,v in certificates.items()},
    'max_recovery_m':max(p['full_precision_recovery_upper_m'] for r in results for p in r['pairs']),
    'max_global_optimality_gap_m':max(p['certified_global_optimality_gap_upper_m'] for r in results for p in r['pairs']),
    'max_final_coordinate_error_m':max(p['final_vs_recovered_max_component_error_m'] for r in results for p in r['pairs'])},indent=2))
