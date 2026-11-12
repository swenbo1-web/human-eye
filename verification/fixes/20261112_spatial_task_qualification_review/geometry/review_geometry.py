"""Independent, stdlib-only replay of saved geometry certificates.

No product, Blender, author verifier, or oracle module is imported or executed.
All source data are read from one Git commit and checked against working bytes.
"""
from pathlib import Path
from fractions import Fraction as F
from collections import defaultdict
from decimal import Decimal, localcontext
import hashlib
import json
import math
import subprocess
import sys
import time

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
HERE = Path(__file__).resolve().parent
COMMIT = '93121974595badc90944d5353d23ae7897feda54'
BASE = 'verification/spatial_task_qualification_001/'
OLD = 'verification/scale_diag_001/'
CHECKS, INPUTS, CACHE = [], {}, {}

def check(name, ok, detail=None):
    CHECKS.append({'check': name, 'passed': bool(ok), **({'detail': detail} if detail is not None else {})})
    if not ok:
        raise AssertionError(name)

def sha(blob): return hashlib.sha256(blob).hexdigest()
def canonical(v): return json.dumps(v, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()
def frozen(path):
    if path not in CACHE:
        b = subprocess.check_output(['git', 'show', COMMIT + ':' + path], cwd=ROOT)
        local = (ROOT / path).read_bytes()
        check('git_working_bytes:' + path, local == b)
        INPUTS[path] = {'sha256': sha(b), 'bytes': len(b), 'git_blob': sha(b'blob ' + str(len(b)).encode() + b'\0' + b)}
        CACHE[path] = b
    return CACHE[path]
def data(path): return json.loads(frozen(path))
def eq(name, a, b): check(name, canonical(a) == canonical(b))
def vec(v): return tuple(F(x) for x in v)
def rat(v): return F(v[0], v[1])
def dot(a, b): return sum((x*y for x,y in zip(a,b)), F(0))
def sub(a, b): return tuple(x-y for x,y in zip(a,b))
def cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def encoded(x): return [x.numerator, x.denominator]
def sqrt_float_enclosure(value):
    with localcontext() as context:
        context.prec = 100
        estimate = float((Decimal(value.numerator)/Decimal(value.denominator)).sqrt())
    lo = hi = estimate
    while F(lo)*F(lo) > value: lo = math.nextafter(lo, -math.inf)
    while F(hi)*F(hi) < value: hi = math.nextafter(hi, math.inf)
    return lo, hi

def topology(row):
    name = row['name']; vertices = list(map(vec, row['vertices_world'])); edges = defaultdict(list)
    for fi, tri in enumerate(row['triangles']):
        check(name + ':triangle:' + str(fi), len(tri) == len(set(tri)) == 3 and
              all(type(i) is int and 0 <= i < len(vertices) for i in tri))
        a,b,c = [vertices[i] for i in tri]
        check(name + ':nondegenerate:' + str(fi), dot(cross(sub(b,a),sub(c,a)),cross(sub(b,a),sub(c,a))) > 0)
        for a,b in zip(tri, tri[1:] + tri[:1]): edges[tuple(sorted((a,b)))].append((fi,a,b))
    check(name + ':closed_oriented_edges', all(len(v)==2 and v[0][1:]==v[1][1:][::-1] for v in edges.values()))
    adjacency = defaultdict(set)
    for a,b in edges.values(): adjacency[a[0]].add(b[0]); adjacency[b[0]].add(a[0])
    seen, todo = {0}, [0]
    while todo:
        for item in adjacency[todo.pop()]:
            if item not in seen: seen.add(item); todo.append(item)
    check(name + ':connected', len(seen)==len(row['triangles']))
    check(name + ':Euler2', len(vertices)-len(edges)+len(row['triangles'])==2)
    return {'vertices':len(vertices),'triangles':len(row['triangles']),'edges':len(edges),
            'closed_oriented_connected_Euler2':True,'all_world_triangles_nondegenerate':True,
            'self_intersection_independently_recomputed':False}

def weighted_point(row, triangle, weights, label):
    check(label + ':triangle_index', type(triangle) is int and 0 <= triangle < len(row['triangles']))
    w = [rat(x) for x in weights]
    check(label + ':barycentric_valid', len(w)==3 and min(w)>=0 and sum(w)==1)
    tri = [vec(row['vertices_world'][i]) for i in row['triangles'][triangle]]
    return tuple(sum(w[i]*tri[i][j] for i in range(3)) for j in range(3))

def locate_point(row, point):
    p=vec(point)
    for ti,indices in enumerate(row['triangles']):
        a,b,c=[vec(row['vertices_world'][i]) for i in indices]
        e,f,q=sub(b,a),sub(c,a),sub(p,a)
        if dot(q,cross(e,f)) != 0: continue
        ee,ef,ff=dot(e,e),dot(e,f),dot(f,f)
        det=ee*ff-ef*ef
        if det <= 0: continue
        u=(dot(q,e)*ff-dot(q,f)*ef)/det
        v=(dot(q,f)*ee-dot(q,e)*ef)/det
        if min(1-u-v,u,v)>=0:
            return {'triangle':ti,'barycentric':[encoded(x) for x in (1-u-v,u,v)]}
    raise AssertionError('point_not_in_actual_triangle:' + row['name'])

def main():
    started=time.perf_counter_ns()
    # Check fixed provenance before consuming any values; author review summaries are not inputs.
    paths=[BASE+x for x in (
      'assets/ORIGINAL_EVALUATED.json','assets/BUILD_SNAPSHOT.json','assets/DERIVED_MANIFEST.json',
      'assets/G508_control.blend','assets/build_asset.py','entry/qa_snapshot.py',
      'entry/run_01/ACTUAL_SNAPSHOT.json','entry/run_01/QA_SNAPSHOT_RECEIPT.json',
      'entry/run_01/ACTUAL_SOURCE_BINDING.json','entry/run_01/control_task_RESULT.json',
      'entry/run_01/product/007/RX.bin','entry/run_01/native/WIRE/001/RESPONSE.bin',
      'entry/run_01/native/WIRE/003/RESPONSE.bin','entry/run_01/native/WIRE/004/RESPONSE.bin',
      'oracle/formal_replay_01/ORACLE.json','oracle/formal_replay_01/RESULTS.json','oracle/verify_actual.py')]
    paths += [OLD+x for x in ('fixtures/G508.json','fixtures/G508.blend','ORACLE.json','oracle.py')]
    for p in paths: frozen(p)
    snap=data(BASE+'entry/run_01/ACTUAL_SNAPSHOT.json')
    original=data(BASE+'assets/ORIGINAL_EVALUATED.json')
    build=data(BASE+'assets/BUILD_SNAPSHOT.json')
    old=data(OLD+'fixtures/G508.json')
    manifest=data(BASE+'assets/DERIVED_MANIFEST.json')
    oracle=data(BASE+'oracle/formal_replay_01/ORACLE.json')
    replay=data(BASE+'oracle/formal_replay_01/RESULTS.json')
    check('formal_raw_snapshot_sha', replay['snapshot_file_sha256']==sha(frozen(BASE+'entry/run_01/ACTUAL_SNAPSHOT.json')))
    check('formal_oracle_canonical_snapshot_sha', oracle['binding']['snapshot_sha256']==sha(canonical(snap)))
    check('fixed_old_oracle_source_sha', oracle['independent_oracle_source_sha256']==sha(frozen(OLD+'oracle.py')))
    check('manifest_derived_blend', manifest['asset_sha256']==sha(frozen(BASE+'assets/G508_control.blend')))
    check('manifest_source_blend', manifest['source_asset_sha256']==sha(frozen(OLD+'fixtures/G508.blend')))
    check('manifest_source_json', manifest['source_json_sha256']==sha(frozen(OLD+'fixtures/G508.json')))
    for key,path in [('build_snapshot_sha256','BUILD_SNAPSHOT.json'),('original_evaluated_sha256','ORIGINAL_EVALUATED.json')]:
        check('manifest_'+key, manifest[key]==sha(frozen(BASE+'assets/'+path)))
    context={'unit':'m','coordinate_frame':'world','scale_length':1.0,'frame':1,'subframe':0.0}
    for label,obj in [('original',original),('build',build),('actual',snap)]:
        eq(label+':context',{k:obj[k] for k in context},context)
    rows={r['name']:r for r in snap['objects']}
    eq('all14_names',sorted(rows),sorted(r['name'] for r in build['objects']))
    check('counts_14_848_1640',(len(rows),sum(len(r['vertices_local']) for r in rows.values()),sum(len(r['triangles']) for r in rows.values()))==(14,848,1640))
    for r in build['objects']: eq('actual_equals_build:'+r['name'],rows[r['name']],r)
    for r in original['objects']: eq('original12_evaluated_unchanged:'+r['name'],rows[r['name']],r)
    for r in old['objects']:
        for key in ('logical_id','vertices_local','vertices_world','matrix_world','triangles'):
            eq('old_G508:'+r['name']+':'+key,rows[r['name']][key],r[key])
    for name,r in rows.items():
        matrix=r['matrix_world']
        for vi,(p,w) in enumerate(zip(r['vertices_local'],r['vertices_world'])):
            result=[(sum(matrix[i][j]*p[j] for j in range(3))+matrix[i][3])*snap['scale_length'] for i in range(3)]
            eq('forward_world:'+name+':'+str(vi),result,w)
        native_id='blender:'+sha(json.dumps([r['library_path'],r['name_full']],sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode())
        check('native_object_id:'+name,native_id==r['object_id'])
    receipt=data(BASE+'entry/run_01/QA_SNAPSHOT_RECEIPT.json')
    wire=data(BASE+'entry/run_01/native/WIRE/001/RESPONSE.bin')
    eq('actual_snapshot_equals_QA_receipt',snap,json.loads(receipt['response']['result']['result']))
    eq('QA_receipt_equals_raw_WIRE',receipt['response'],wire)
    topology_results={name:topology(row) for name,row in rows.items()}
    capture_bindings=[]
    for num,expected_names in [('003',{'Target','Peer_000','Competing_001','Near_003'}),('004',{'Control_A','Control_B'})]:
        raw=data(BASE+'entry/run_01/native/WIRE/'+num+'/RESPONSE.bin')
        packet=json.loads(raw['result']['result'].split('HUMAN_EYE_BLENDER_MCP:',1)[1])['result']
        capture=packet['capture']; resources={(r['id'],r['revision']):r for r in packet['resources']}
        eq('capture_names:'+num,sorted(m['name'] for m in capture['meshes']),sorted(expected_names))
        check('capture_units:'+num,capture['unit']=='m' and capture['coordinate_frame']=='world')
        for m in capture['meshes']:
            ref=m['_scene_resource']; resource=resources[(ref['id'],ref['revision'])]; actual=rows[m['name']]
            for key,a,b in [('object_id',m['object_id'],actual['object_id']),('vertices',resource['vertices_local'],actual['vertices_local']),('triangles',resource['faces'],actual['triangles']),('matrix',ref['matrix'],actual['matrix_world']),('scale',ref['scale'],snap['scale_length'])]:
                eq('product_capture:'+num+':'+m['name']+':'+key,a,b)
        capture_bindings.append({'wire':num,'names':sorted(expected_names),'exact_source_arrays':True})
    pair_results=[]; certificates={}
    check('exact_three_pair_names',{p['candidate_name'] for p in oracle['pairs']}=={'Peer_000','Competing_001','Near_003'})
    for cert in oracle['pairs']:
        name=cert['candidate_name']; a=rows['Target']; b=rows[name]
        n=tuple(rat(x) for x in cert['support_normal']); norm2=dot(n,n)
        projections_a=[dot(vec(v),n) for v in a['vertices_world']]
        projections_b=[dot(vec(v),n) for v in b['vertices_world']]
        gap=min(projections_b)-max(projections_a)
        check(name+':positive_support_gap',gap>0 and norm2>0)
        check(name+':recorded_support_gap',gap==rat(cert['support_gap']))
        check(name+':recorded_normal_squared',norm2==rat(cert['normal_squared']))
        check(name+':support_vertex_a',projections_a[cert['support_vertex_a']]==max(projections_a))
        check(name+':support_vertex_b',projections_b[cert['support_vertex_b']]==min(projections_b))
        w=cert['witness']; pa=weighted_point(a,w['triangle_a'],w['barycentric_a'],name+':left')
        pb=weighted_point(b,w['triangle_b'],w['barycentric_b'],name+':right')
        upper2=dot(sub(pb,pa),sub(pb,pa)); lower2=gap*gap/norm2
        check(name+':support_lower_le_witness_upper',lower2<=upper2)
        check(name+':recorded_squared_distance',upper2==rat(w['squared_distance']))
        eq(name+':displayed_witness_a',[float(x) for x in pa],w['point_a_world_m'])
        eq(name+':displayed_witness_b',[float(x) for x in pb],w['point_b_world_m'])
        check(name+':recorded_outward_lower',F(cert['distance_lower_m'])**2<=lower2)
        check(name+':recorded_outward_upper',F(cert['distance_upper_m'])**2>=upper2)
        lo=sqrt_float_enclosure(lower2)[0]; hi=sqrt_float_enclosure(upper2)[1]
        check(name+':independent_width_below_tolerance',F(hi)-F(lo)<F(1,1000000))
        threshold=F(1,250)**2
        decision='satisfied' if lower2>=threshold else 'not_satisfied' if upper2<threshold else 'unknown'
        check(name+':minimum_4mm',decision==cert['minimum_4mm'])
        check(name+':closed_claim_recorded',cert['solid_relation']=='separated' and cert['relation_qualified'] is True)
        certificates[name]=(lower2,upper2)
        pair_results.append({'candidate':name,'independent_lower_m':lo,'independent_upper_m':hi,
          'lower_squared_exact':encoded(lower2),'upper_squared_exact':encoded(upper2),'minimum_4mm':decision,
          'actual_triangle_indices':[w['triangle_a'],w['triangle_b']],
          'all_vertex_support_recomputed':True,'rational_barycentric_witness_recomputed':True,
          'closed_embedding_proof':'fixed prior oracle source reviewed and exact input reused; not independently recomputed'})
    check('unique_nearest_Peer',all(certificates['Peer_000'][1]<bounds[0] for name,bounds in certificates.items() if name!='Peer_000'))
    eq('reported_nearest',oracle['three_candidate_nearest']['name'],'Peer_000')
    response=data(BASE+'entry/run_01/product/007/RX.bin')
    public=data(BASE+'entry/run_01/control_task_RESULT.json')
    eq('public_control_equals_raw_RX',response,public['response'])
    body=json.loads(response['result']['content'][0]['text'])
    eq('public_control_body',body,public['body'])
    check('public_control_observed_separated',body['status']=='observed' and body['pairs'][0]['facts']['closed_solid_relation']['value']=='separated')
    proximity=body['pairs'][0]['facts']['surface_proximity']; witness=proximity['value']['nearest_witness']
    check('control_distance_exact_one',proximity['value']['distance_m']==1 and body['pairs'][0]['separation_gap']['value']==1)
    control_rows=[rows['Control_A'],rows['Control_B']]
    control_points=[witness['a'],witness['b']]
    control_membership=[locate_point(row,p) for row,p in zip(control_rows,control_points)]
    check('control_public_points_squared_distance_one',dot(sub(vec(control_points[1]),vec(control_points[0])),sub(vec(control_points[1]),vec(control_points[0])))==1)
    check('control_exact_support_one',min(F(v[0]) for v in control_rows[1]['vertices_world'])-max(F(v[0]) for v in control_rows[0]['vertices_world'])==1)
    eq('control_public_direction',witness['direction_a_to_b'],[1.0,0.0,0.0])
    for row,w in zip(control_rows,oracle['control']['witnesses']):
        p=weighted_point(row,w['triangle'],w['barycentric'],'control_oracle:'+row['name'])
        eq('control_oracle_point:'+row['name'],[float(v) for v in p],[float(v) for v in w['point_world_m']])
    control_result={'distance_m':1,'public_points':control_points,'independent_actual_triangle_membership':control_membership,
                    'exact_support_lower_and_actual_point_upper_equal':True,'public_witness_may_differ_from_oracle_witness':True}
    result={'fixed_commit':COMMIT,'independent_reviewer':'planning-chat child directory_source_closure; not author root',
      'passed':True,'checks':len(CHECKS),'failed':0,'elapsed_ns':time.perf_counter_ns()-started,
      'objects':14,'vertices':848,'triangles':1640,'source_bindings':capture_bindings,'topology':topology_results,
      'pairs':pair_results,'unique_nearest':'Peer_000','control':control_result,
      'independent_new_Blender_calls':0,'independent_new_product_calls':0,'independent_new_model_calls':0,
      'not_independently_reexecuted':['prior actual-world injective PL extension/self-intersection proof','Blender evaluation','model consumers','runtime/installation closure']}
    return result

if __name__=='__main__':
    try: result=main()
    except BaseException as exc:
        import traceback
        result={'passed':False,'error':type(exc).__name__+': '+str(exc),'traceback':traceback.format_exc(),'checks':len(CHECKS),'failed':sum(not c['passed'] for c in CHECKS)}
    for name,obj in [('RESULTS.json',result),('CHECKS.json',CHECKS),('INPUTS.json',INPUTS)]:
        (HERE/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('passed','checks','failed') if k in result},ensure_ascii=False))
    if not result['passed']: print(result['traceback']);sys.exit(1)
