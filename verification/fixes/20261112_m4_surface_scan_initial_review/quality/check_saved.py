"""Independent rational verification. No author or product code is imported."""
from collections import Counter
from fractions import Fraction as F
from itertools import combinations
from pathlib import Path
import hashlib
import json
import math
import subprocess
import time

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BASE = ROOT/'verification/m4_surface_scan_001'
OUT = Path(__file__).resolve().parent
COMMIT = '726e88efba548e85eba1eb148b91486470c5d2c1'
QUALCOMMIT = '96fce78b98cb749885792112e039a406744d282b'
SOURCE = 'b3654f6f943c3fb6feff0011397c0a8c20872e41f35973e6baf53e3a5e277314'
TH = F(.002)
TOL = F(1,10**10)
FILES = {}
CHECKS = []

def raw(path):
    path = Path(path)
    b = path.read_bytes()
    FILES[path.relative_to(ROOT).as_posix()] = {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
    return b

def read(path): return json.loads(raw(path))
def exact(x): return F(int(x['numerator']),int(x['denominator']))
def check(name, test):
    CHECKS.append({'name':name,'passed':bool(test)})
    if not test: raise AssertionError(name)
def dump(name,value):
    def encode(x):
        if isinstance(x,F):return {'numerator':str(x.numerator),'denominator':str(x.denominator)}
        raise TypeError(type(x).__name__)
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=encode)+'\n',encoding='utf8',newline='\n')

def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def lerp(a,b,t):return tuple(x+(y-x)*t for x,y in zip(a,b))
def sq(a,b):return dot(sub(a,b),sub(a,b))
def box(points):return tuple((min(p[k] for p in points),max(p[k] for p in points)) for k in range(3))
def gaps(a,b):return tuple(max(0,x[0]-y[1],y[0]-x[1]) for x,y in zip(a,b))
def box_sq(a,b):return sum(v*v for v in gaps(a,b))
EDGES=((0,1),(1,2),(2,0))

def projected_weights(p,t):
    e,f,r=sub(t[1],t[0]),sub(t[2],t[0]),sub(p,t[0])
    ee,ff,ef=dot(e,e),dot(f,f),dot(e,f)
    determinant=ee*ff-ef*ef
    if not determinant:raise ValueError('degenerate')
    er,fr=dot(e,r),dot(f,r)
    u,v=(ff*er-ef*fr)/determinant,(ee*fr-ef*er)/determinant
    return (1-u-v,u,v)

def point_segment_sq(p,a,b):
    e=sub(b,a)
    parameter=max(F(0),min(F(1),dot(sub(p,a),e)/dot(e,e)))
    return sq(p,lerp(a,b,parameter))

def point_triangle_sq(p,t):
    weights=projected_weights(p,t)
    if min(weights)>=0:
        q=tuple(sum(weights[j]*t[j][k] for j in range(3)) for k in range(3))
        return sq(p,q)
    return min(point_segment_sq(p,t[i],t[j]) for i,j in EDGES)

def segment_pair_sq(a,b,c,d):
    # Convex quadratic on a parameter square: stationary interior or its edges.
    u,v,w=sub(b,a),sub(d,c),sub(a,c)
    aa,bb,cc,dd,ee=dot(u,u),dot(u,v),dot(v,v),dot(u,w),dot(v,w)
    determinant=aa*cc-bb*bb
    values=[point_segment_sq(a,c,d),point_segment_sq(b,c,d),
            point_segment_sq(c,a,b),point_segment_sq(d,a,b)]
    if determinant:
        s,t=(bb*ee-cc*dd)/determinant,(aa*ee-bb*dd)/determinant
        if 0<=s<=1 and 0<=t<=1:values.append(sq(lerp(a,b,s),lerp(c,d,t)))
    return min(values)

def crosses_face(a,b,t):
    n=cross(sub(t[1],t[0]),sub(t[2],t[0]))
    ha,hb=dot(n,sub(a,t[0])),dot(n,sub(b,t[0]))
    # Coplanar contacts are covered by the point/edge minima below.
    if ha==hb or ha*hb>0:return False
    u=ha/(ha-hb)
    return 0<=u<=1 and min(projected_weights(lerp(a,b,u),t))>=0

def triangle_sq(a,b):
    for i,j in EDGES:
        if crosses_face(a[i],a[j],b) or crosses_face(b[i],b[j],a):return F(0)
    best=min(*(point_triangle_sq(p,b) for p in a),*(point_triangle_sq(p,a) for p in b))
    if best==0:return best
    for i,j in EDGES:
        for k,l in EDGES:
            best=min(best,segment_pair_sq(a[i],a[j],b[k],b[l]))
            if best==0:return best
    return best

def self_checks():
    t=tuple(tuple(F(v) for v in row) for row in ((0,0,0),(2,0,0),(0,2,0)))
    check('independent_geometry.parallel_distance',triangle_sq(t,tuple(tuple(v+(F(3) if k==2 else 0) for k,v in enumerate(p)) for p in t))==9)
    inner=tuple(tuple(F(v) for v in p) for p in ((.25,.25,0),(.5,.25,0),(.25,.5,0)))
    check('independent_geometry.coplanar_contained',triangle_sq(t,inner)==0)
    pierced=tuple(tuple(F(v) for v in p) for p in ((.5,.5,-1),(.5,.5,1),(3,3,1)))
    check('independent_geometry.cross_face',triangle_sq(t,pierced)==0)
    check('independent_geometry.parallel_segments',segment_pair_sq((F(0),F(0),F(0)),(F(2),F(0),F(0)),(F(1),F(1),F(0)),(F(3),F(1),F(0)))==1)
    check('independent_geometry.skew_interiors',segment_pair_sq((F(-1),F(0),F(0)),(F(1),F(0),F(0)),(F(0),F(-1),F(1)),(F(0),F(1),F(1)))==1)

def prepare(state):
    snapshot=read(BASE/'qualification'/f'{state.upper()}_SNAPSHOT.json')
    truth=read(BASE/'qualification'/f'{state.upper()}_TRUTH.json')
    check(state+'.snapshot_counts',snapshot['counts']=={'objects':24,'vertices':530,'triangles':978})
    objects={}
    for ob in snapshot['objects']:
        n=ob['name'];vertices=[tuple(F(x) for x in p) for p in ob['vertices_world']]
        matrix=[[F(v) for v in row] for row in ob['matrix_world']]
        local=[tuple(F(x) for x in p) for p in ob['vertices_local']]
        transformed=[tuple(sum(matrix[k][j]*p[j] for j in range(3))+matrix[k][3] for k in range(3)) for p in local]
        check(state+'.'+n+'.exact_world_transform',vertices==transformed)
        tris=[tuple(vertices[i] for i in face) for face in ob['triangles']]
        check(state+'.'+n+'.nondegenerate',all(dot(cross(sub(t[1],t[0]),sub(t[2],t[0])),cross(sub(t[1],t[0]),sub(t[2],t[0])))>0 for t in tris))
        corners=[tuple(sum(matrix[k][j]*F(p[j]) for j in range(3))+matrix[k][3] for k in range(3)) for p in ob['evaluated_bound_box_local']]
        api=box(corners)
        check(state+'.'+n+'.bounds_enclosure',all(api[k][0]<=v[k]<=api[k][1] for v in vertices for k in range(3)))
        objects[n]={'raw':ob,'vertices':vertices,'triangles':tris,'boxes':[box(t) for t in tris],'api':api,'box':box(vertices)}
    expected={tuple(sorted((p['object_a'],p['object_b']))):p for p in truth['pairs']}
    pairs=set(combinations(sorted(objects),2))
    check(state+'.all_pairs',len(truth['pairs'])==len(expected)==276 and set(expected)==pairs)
    for pair,row in expected.items():
        d=exact(row['exact_squared_distance_m2']);w=row['witness'];oa,ob=(objects[n] for n in pair)
        points=[]
        for key,o in [('a',oa),('b',ob)]:
            tri=o['triangles'][w['triangle_'+key]];weights=[exact(x) for x in w['barycentric_'+key]]
            pt=tuple(exact(x) for x in w['point_'+key]);points.append(pt)
            check(state+'.'+str(pair)+'.witness_'+key,sum(weights)==1 and min(weights)>=0 and pt==tuple(sum(weights[j]*tri[j][k] for j in range(3)) for k in range(3)))
        check(state+'.'+str(pair)+'.witness_distance',sq(*points)==d)
        check(state+'.'+str(pair)+'.threshold',row['matches_threshold']==(d<=TH*TH))
        check(state+'.'+str(pair)+'.AABB_predicate',row['api_AABB_Linf_retained']==(max(gaps(oa['api'],ob['api']))<=TH))
        check(state+'.'+str(pair)+'.triangle_denominator',row['triangle_pairs_total']==len(oa['triangles'])*len(ob['triangles'])==row['triangle_pairs_solved']+row['triangle_pairs_bound_pruned'])
    return snapshot,objects,expected

def independent_mesh_sq(a,b):
    best=sq(a['triangles'][0][0],b['triangles'][0][0])
    jobs=sorted((box_sq(ba,bb),i,j) for i,ba in enumerate(a['boxes']) for j,bb in enumerate(b['boxes']))
    solved=0
    for lower,i,j in jobs:
        if lower>=best:break
        best=min(best,triangle_sq(a['triangles'][i],b['triangles'][j]));solved+=1
    return best,solved,len(jobs)-solved

def recompute(state,objects,expected):
    rows=[];started=time.perf_counter()
    for index,pair in enumerate(sorted(expected)):
        d,solved,pruned=independent_mesh_sq(*(objects[n] for n in pair))
        check(state+'.'+str(pair)+'.independent_exact_minimum',d==exact(expected[pair]['exact_squared_distance_m2']))
        rows.append({'pair':pair,'exact_squared':d,'triangle_pairs_solved':solved,'triangle_pairs_bound_excluded':pruned})
        if (index+1)%48==0:print(json.dumps({'stage':'independent_oracle','state':state,'pairs':index+1}),flush=True)
    return {'pairs':rows,'elapsed_seconds':time.perf_counter()-started}

def main():
    started=time.perf_counter();self_checks()
    prepared={state:prepare(state) for state in ('base','edit')}
    before,after=prepared['base'][1],prepared['edit'][1]
    check('edit.only_Obj_008_world_changed',[n for n in before if before[n]['vertices']!=after[n]['vertices']]==['Obj_008'])
    check('edit.topology_local_unchanged',all(before[n]['raw']['vertices_local']==after[n]['raw']['vertices_local'] and before[n]['raw']['triangles']==after[n]['raw']['triangles'] for n in before))
    oracle={state:recompute(state,prepared[state][1],prepared[state][2]) for state in ('base','edit')}
    dump('ORACLE_RECOMPUTE.json',oracle)
    ids={'blender:'+hashlib.sha256(json.dumps(['',n],ensure_ascii=False,separators=(',',':')).encode()).hexdigest():n for n in before}
    witness_cache={};observations=[];max_error=0.
    def verify(label,state,body,diag):
        nonlocal max_error
        objects,truth=prepared[state][1:];matches={p for p,r in truth.items() if r['matches_threshold']}
        check(label+'.public_contract',body['result_kind']=='surface_scan' and body['status']=='complete' and body['threshold_m']==.002 and body['unit']=='m' and body['coordinate_frame']=='world' and body['execution_authority'] is False)
        check(label+'.solid_semantics',body['measurement_semantics']['solid_relation']=='not_evaluated')
        check(label+'.source',body['binding']['runtime_source_sha256']==SOURCE)
        check(label+'.scope',not body['scope_issues'] and not body['unsupported_objects'] and not body['unresolved'])
        part={};counts=Counter()
        for row in diag['dispositions']:
            pair=tuple(sorted(ids[i] for i in row['object_ids']))
            check(label+'.unique_partition.'+str(pair),pair not in part and pair in truth)
            part[pair]=row;counts[row['status']]+=1;d=exact(truth[pair]['exact_squared_distance_m2'])
            check(label+'.partition_truth.'+str(pair),row['status'] in ('bound_excluded','measured_match','measured_nonmatch') and (row['status']=='measured_match')==(pair in matches))
            if row['status']=='bound_excluded':
                check(label+'.valid_exclusion.'+str(pair),F(row['lower_bound_m'])>TH and F(row['lower_bound_m'])**2<=d)
            else:
                err=abs(row['distance_m']-math.sqrt(float(d)));max_error=max(max_error,err)
                check(label+'.partition_distance.'+str(pair),math.isfinite(row['distance_m']) and err<=float(TOL))
        check(label+'.full_partition',set(part)==set(truth))
        seen=set();witnesses=0
        for row in body['matches']:
            pair=tuple(sorted(o['name'] for o in row['objects']));check(label+'.unique_public.'+str(pair),pair not in seen and pair in matches);seen.add(pair)
            check(label+'.public_ids.'+str(pair),all(ids[o['id']]==o['name'] for o in row['objects']))
            d=exact(truth[pair]['exact_squared_distance_m2']);err=abs(row['distance_m']-math.sqrt(float(d)));max_error=max(max_error,err)
            check(label+'.public_distance.'+str(pair),math.isfinite(row['distance_m']) and row['distance_m']>=0 and err<=float(TOL) and row['witness_status']=='measured')
            check(label+'.witness_separation.'+str(pair),abs(math.dist(row['point_a_world'],row['point_b_world'])-row['distance_m'])<=float(TOL))
            for k,key in enumerate(('point_a_world','point_b_world')):
                n=row['objects'][k]['name'];p=tuple(F(x) for x in row[key]);ck=(state,n,p)
                if ck not in witness_cache:
                    witness_cache[ck]=min(point_triangle_sq(p,t) for t in objects[n]['triangles'])
                check(label+'.surface_witness.'+str(pair)+'.'+key,witness_cache[ck]<=TOL*TOL);witnesses+=1
        check(label+'.full_public_match_set',seen==matches)
        coverage=body['coverage'];check(label+'.coverage',coverage['objects']==24 and coverage['total_pairs']==276 and coverage['catalog_scope_confirmed'] and all(coverage[k]==counts[k] for k in ['bound_excluded','measured_match','measured_nonmatch','unknown','deferred']))
        check(label+'.delivery',body['delivery']['complete'] and body['delivery']['matches_total']==body['delivery']['delivered_matches']==len(matches))
        observations.append({'label':label,'state':state,'pairs':len(part),'matches':len(matches),'surface_witness_occurrences':witnesses,'counts':dict(counts)})
    for sequence in range(1,6):
        path=BASE/'engineering/run_01'/f'sequence_{sequence:02d}';data=read(path/'RESULTS.json')
        check(f'seq{sequence}.planned_rows',[x['state'] for x in data['business']]==['cold','repeat','edit'])
        check(f'seq{sequence}.execution',not data['errors'] and data['automatic_retries']==0 and data['runtime_exit']['confirmed'] and data['runtime_exit']['exit_code']==0 and data['native_close']['process_reaped'])
        for row in data['business']:
            label=f'seq{sequence}.{row["state"]}';state='edit' if row['state']=='edit' else 'base'
            request=read(path/(row['state']+'_REQUEST.json'));receipt=read(path/(row['state']+'_RESPONSE_RECEIPT.json'))
            check(label+'.raw_request',request==row['request'] and request['params']['arguments']['query']=={'mode':'surface_scan','threshold_m':.002})
            check(label+'.response_body_binding',receipt['body']==row['body'] and json.loads(row['response']['result']['content'][0]['text'])==row['body'])
            check(label+'.diagnostic_binding',any(a.get('task_work')==row['diagnostics'] for a in row['audit']))
            check(label+'.no_execution_error',not row['errors'])
            verify(label,state,row['body'],row['diagnostics'])
    proc=read(BASE/'engineering/process_01/RESULTS.json')
    check('Process.execution',not proc['errors'] and proc['actual_commands']==['capabilities','capture_surface_scan','shutdown'])
    rx=[json.loads(line) for line in raw(BASE/'engineering/process_01/MCP_RX.bin').splitlines() if line.strip()]
    check('Process.raw_response',any('result'in r and r['result'].get('content') and json.loads(r['result']['content'][0].get('text','{}'))==proc['body'] for r in rx))
    verify('Process.base','base',proc['body'],proc['diagnostics'])
    check('planned_16_observations',len(observations)==16)
    # Source review files are hashed as actually read, not counted as geometry runs.
    for rel in ['qualification/oracle.py','qualification/check_controls.py','qualification/REPORT.md','audit_engineering.py','engineering/verify_state.py','FINAL_TARGETED_TESTS.txt','kernel_design/ENGINEERING_REVIEW.md','host_design/FINAL_REVIEW.md']:
        raw(BASE/rel)
    raw(ROOT/'verification/m4_grooved_rail_transfer_001/oracle/exact_geometry.py')
    gitchecks=[]
    for rel,meta in FILES.items():
        blob=subprocess.check_output(['git','show',COMMIT+':'+rel],cwd=ROOT)
        check('git_delivery:'+rel,hashlib.sha256(blob).hexdigest()==meta['sha256'])
        if '/qualification/' in rel:
            frozen=subprocess.check_output(['git','show',QUALCOMMIT+':'+rel],cwd=ROOT)
            check('git_qualification:'+rel,hashlib.sha256(frozen).hexdigest()==meta['sha256'])
            gitchecks.append(rel)
    result={'passed':True,'source':SOURCE,'delivery':COMMIT,'independent_states':2,'independent_scenario':1,'independent_exact_pairs':552,'observations':observations,'main_dispositions':sum(o['pairs'] for o in observations[:-1]),'process_dispositions':observations[-1]['pairs'],'main_public_distances':sum(o['matches'] for o in observations[:-1]),'process_public_distances':observations[-1]['matches'],'surface_witness_occurrences':sum(o['surface_witness_occurrences'] for o in observations),'unique_surface_witnesses':len(witness_cache),'max_public_or_measured_distance_error_m':max_error,'assertions':len(CHECKS),'all_assertions_passed':all(c['passed'] for c in CHECKS),'actual_files_read':len(FILES),'qualification_files_old_git_matched':len(gitchecks),'new_product_blender_consumer_api_runs':0,'elapsed_seconds':time.perf_counter()-started}
    dump('RESULTS.json',result);dump('CHECKS.json',CHECKS);dump('INPUTS.json',FILES)
    print(json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__':
    try:main()
    except BaseException:
        dump('CHECKS_FAILURE.json',CHECKS);dump('INPUTS_FAILURE.json',FILES)
        raise
