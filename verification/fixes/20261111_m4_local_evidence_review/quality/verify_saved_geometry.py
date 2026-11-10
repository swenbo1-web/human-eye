"""Independent saved-data check: standard library only; no producer imports."""
from fractions import Fraction as Q
from pathlib import Path
import hashlib
import json
import math

BASE = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_local_relation_evidence_001')
OUT = Path(__file__).resolve().parent
hashes, checks, failures, proofs = {}, [], [], []

def load(path):
    raw = path.read_bytes()
    hashes[str(path)] = hashlib.sha256(raw).hexdigest()
    return json.loads(raw)

def check(condition, label):
    checks.append(label)
    if not condition:
        failures.append(label)

def qp(p): return tuple(Q.from_float(float(x)) for x in p)
def sub(a,b): return tuple(x-y for x,y in zip(a,b))
def dot(a,b): return sum(x*y for x,y in zip(a,b))
def cross(a,b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def addscale(p,d,t): return tuple(x+y*t for x,y in zip(p,d))
def normal(t): return cross(sub(t[1],t[0]),sub(t[2],t[0]))
def det2(a,b): return a[0]*b[1]-a[1]*b[0]

def bary2(point, tri):
    """Projected signed 2D area ratios, not the QA Gram-system oracle."""
    n = normal(tri)
    drop = max(range(3), key=lambda i: abs(n[i]))
    axes = [i for i in range(3) if i != drop]
    flatten = lambda v: tuple(v[i] for i in axes)
    u,v,w = [flatten(sub(p,tri[0])) for p in (tri[1],tri[2],point)]
    den = det2(u,v)
    assert den
    b,c = det2(w,v)/den, det2(u,w)/den
    return (1-b-c,b,c)

def solve(tris):
    # Two plane equations yield a line. Bound its free parameter using six
    # projected signed-area ratios; their common strict interval is the witness.
    normals = [normal(t) for t in tris]
    direction = cross(*normals)
    assert any(direction)
    k = max(range(3),key=lambda i:abs(direction[i]))
    u,v = [i for i in range(3) if i != k]
    n,m = normals
    a,b = dot(n,tris[0][0]),dot(m,tris[1][0])
    den = n[u]*m[v]-n[v]*m[u]
    origin = [Q(0)]*3
    origin[u],origin[v] = (a*m[v]-n[v]*b)/den,(n[u]*b-a*m[u])/den
    slope = tuple(x/direction[k] for x in direction)
    lows, highs = [], []
    for tri in tris:
        start = bary2(origin,tri)
        after = bary2(addscale(origin,slope,Q(1)),tri)
        rates = sub(after,start)
        for value, rate in zip(start,rates):
            if rate > 0: lows.append(-value/rate)
            elif rate < 0: highs.append(-value/rate)
            else: assert value > 0
    lo,hi = max(lows),min(highs)
    assert lo < hi
    midpoint = addscale(origin,slope,(lo+hi)/2)
    weights = [bary2(midpoint,t) for t in tris]
    assert all(min(w)>0 and sum(w)==1 for w in weights)
    assert all(dot(n,sub(midpoint,t[0]))==0 for n,t in zip(normals,tris))
    return midpoint,weights,[addscale(origin,slope,z) for z in (lo,hi)]

def fact(result):
    if 'local_evidence' in result:return result
    if 'pairs' in result:return result['pairs'][0]['facts']['closed_solid_relation']
    if 'candidates' in result:return result['candidates'][0]['closed_solid_relation']
    return result['facts']['closed_solid_relation']

def proof(label, evidence, meshes):
    triangles=[]
    for side, mesh in enumerate(meshes):
        ordinal=evidence['triangle_indices'][side]
        check(type(ordinal) is int and 0<=ordinal<len(mesh['faces']),label+'.ordinal'+str(side))
        actual=[mesh['vertices'][j] for j in mesh['faces'][ordinal]]
        check(evidence['triangle_vertices_world_m'][side]==actual,label+'.source_vertices'+str(side))
        triangles.append(tuple(qp(p) for p in actual))
    midpoint,weights,ends=solve(triangles)
    tolerance=Q.from_float(1e-9)
    minimum_float_error=sum((Q.from_float(float(x))-x)**2 for x in midpoint)
    status=evidence['point_status']
    if status=='approximate':
        error=sum((x-y)**2 for x,y in zip(qp(evidence['point_world_m']),midpoint))
        check(error<=tolerance*tolerance,label+'.published_error')
        check('point_reason' not in evidence,label+'.no_refusal_reason')
    else:
        error=None
        check(status=='unknown' and evidence['point_world_m'] is None,label+'.unknown_null')
        check(evidence['point_reason']=='world_point_precision_exceeded',label+'.unknown_reason')
        check(minimum_float_error>tolerance*tolerance,label+'.nearest_binary64_cannot_meet_tolerance')
    check(evidence['type']=='transverse_triangle_crossing',label+'.type')
    check(evidence['publication_tolerance_m']==1e-9,label+'.tolerance')
    check(evidence['point_scope']=='boundary_crossing_localization_not_volume_interior_or_penetration_depth',label+'.boundary_scope')
    check(evidence['triangle_scope']=='current_capture_zero_based_triangles_target_then_candidate_not_polygon_ids',label+'.triangle_scope')
    record={'label':label,'triangle_indices':evidence['triangle_indices'],'midpoint':[str(x) for x in midpoint],
      'segment':[[str(x) for x in p] for p in ends],'strict_barycentric':[[str(x) for x in w] for w in weights],
      'point_status':status,'published_squared_error_m2':str(error) if error is not None else None,
      'nearest_binary64_squared_error_m2':str(minimum_float_error),'nearest_binary64_error_m':math.sqrt(float(minimum_float_error))}
    proofs.append(record)
    return record

all_evidence={}
for role in ('baseline_01','candidate_01','baseline_02','candidate_02'):
    evidence=load(BASE/role/'EVIDENCE.json')
    key=next(k for k in evidence if k.endswith(':LocalRelationEvidenceTests'))
    all_evidence[role]=evidence[key]
    result=load(BASE/role/'RESULTS.json')
    check(result['tests']==36 and not result['errors'] and not result['skipped'],role+'.36_methods_no_error_or_skip')
    if role.endswith('_01'):
        check(len(result['failures'])==1 and 'AssertionError: 1 != 0' in result['failures'][0]['traceback'],role+'.preserved_wrong_cache_expectation')
    else:check(not result['failures'] and result['successful'],role+'.author36_pass')

new=all_evidence['candidate_02'];old=all_evidence['baseline_02']
check(len(new)==len(old)==15,'fifteen_exported_cases_each')
for name,case in new.items():
    for field in ('input','calls','loop_counts','loop_work_amounts','diagnostics'):
        check(case[field]==old[name][field],name+'.old_new_'+field+'_equal')
    obj=fact(case['result']) if name.startswith(('service','public')) else case['result']
    if 'local_evidence' in obj:proof('offline.'+name,obj['local_evidence'],case['input'])

check(new['frozen_swapped']['input']==list(reversed(new['frozen']['input'])),'swap.actual_inputs_reversed')
for a,b in zip(new['frozen']['input'],new['frozen_rigid']['input']):
    expected=[[-v[1]+8,v[2]-16,-v[0]+32] for v in a['vertices']]
    check(b['vertices']==expected and b['faces']==a['faces'],'rigid.'+a['name']+'.actual_transform')

tet=new['contact_then_transverse']
for side,mesh in enumerate(tet['input']):
    tri=tuple(qp(mesh['vertices'][i]) for i in mesh['faces'][0])
    p=(Q(3,2),Q(3,2),Q(0))
    check(dot(normal(tri),sub(p,tri[0]))==0 and min(bary2(p,tri))>0,'first_contact.coplanar_strict_point'+str(side))
check(tet['first_contact_triangle_indices']==[0,0],'first_contact.recorded_00')
check(tet['result']['local_evidence']['triangle_indices']==[3,1],'final_transverse_is_31')
tetproof=next(p for p in proofs if p['label']=='offline.contact_then_transverse')
check(tetproof['midpoint']==['11/5','1','4/5'],'tetra.exact_known_midpoint')
large=new['large_point_unavailable']
for small,big in zip(tet['input'],large['input']):
    check(big['vertices']==[[x+2**40 for x in v] for v in small['vertices']],'large.exact_translation.'+small['name'])

for name in ('separated','touching','contained','open_unknown','service_geometry_changed'):
    case=new[name];result=fact(case['result']) if name.startswith('service') else case['result']
    check('local_evidence' not in result,name+'.no_fabricated_transverse_evidence')
for role in ('baseline_02','candidate_02'):
    cases=all_evidence[role]
    check([cases[n]['calls']['kernel'] for n in ('service_cold','service_warm','service_same_geometry_new_generation','service_geometry_changed')]==[1,0,1,1],role+'.cache_kernel_sequence')
    for name in ('service_warm','service_same_geometry_new_generation'):
        check(cases[name]['result']['facts']==cases['service_cold']['result']['facts'],role+'.'+name+'.facts_unchanged_and_detached')

frozen=load(BASE.parent/'m4_observation_baseline_001/scoring/source/qual001/admin/world_geometry.json')
check(hashes[str(BASE.parent/'m4_observation_baseline_001/scoring/source/qual001/admin/world_geometry.json')]=='daa66107b5b6787dd0083ba5794cb9507218ab8717ee57eb593b749616fd65ab','world_source_pin')
objects={v['name']:v for v in frozen['objects']}
meshes=[{'vertices':objects[n]['world_vertices'],'faces':objects[n]['triangles']} for n in ('N16','N13')]
public_payloads=[]
for profile in ('C','S'):
    folder=BASE/'entry/run_01'/('candidate_'+profile)
    initial=load(folder/'owner/INITIAL.json')
    current={v['name']:v for v in initial['objects']}
    for name in ('N16','N13'):
        check(current[name]['vertices_local']==objects[name]['local_vertices'] and current[name]['matrix_world']==objects[name]['matrix_world'] and current[name]['faces']==objects[name]['polygons'],profile+'.'+name+'.actual_source_snapshot_matches')
    for i in range(1,7):
        response=load(folder/'owner'/('tool_'+str(i).zfill(2))/'RESPONSE.json')
        value=json.loads(response['result']['content'][0]['text'])
        f=fact(value);e=f['local_evidence'];public_payloads.append(e)
        proof('public.'+profile+'.'+str(i),e,meshes)
        check(f['value']=='penetrating' and f['certificate']=='transverse_boundary_interiors',profile+'.'+str(i)+'.original_classification')
check(all(e==public_payloads[0] for e in public_payloads),'all12_public_payloads_equal')
check(len(proofs)==22,'10_offline_and12_public_proofs')

result={'status':'PASS' if not failures else 'FAIL','method':'Independent standard-library Fraction plane-line solution and projected 2D determinant barycentric inequalities. No product/QA oracle imports or execution. Mathematical line parameterization is also used by an author review; this is independent implementation, not a wholly different geometric theorem.',
 'checks':len(checks),'failed_checks':failures,'proofs':proofs,'input_sha256':hashes,
 'scope':'Saved public geometry, finite exported cases, cache trace comparison and original failure preservation. No rerun of author matrix; reported 36/36 remains author execution evidence.',
 'executed_product_calls':0,'Blender_sessions':0,'model_calls':0,'modified_author_files':False}
target=OUT/'INDEPENDENT_GEOMETRY.json'
with target.open('x',encoding='utf-8',newline='\n') as handle:json.dump(result,handle,ensure_ascii=False,indent=2);handle.write('\n')
print(json.dumps({'status':result['status'],'checks':len(checks),'failures':failures,'proofs':len(proofs),'output':str(target),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}))
