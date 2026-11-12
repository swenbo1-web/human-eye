"""Independent all-object-pair rational oracle with certified triangle bounds."""
from collections import Counter
from datetime import datetime,timezone
from fractions import Fraction as F
import hashlib
import importlib.util
from itertools import combinations
import json
from pathlib import Path
import time
import traceback

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
LIB=ROOT/'verification/m4_grooved_rail_transfer_001/oracle/exact_geometry.py'
spec=importlib.util.spec_from_file_location('_independent_old_geometry',LIB)
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
THRESHOLD=F(.002)

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def encode(value):
    if isinstance(value,F):return {'numerator':str(value.numerator),'denominator':str(value.denominator)}
    if isinstance(value,dict):return {str(k):encode(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [encode(v) for v in value]
    return value

def save(path,value):
    with path.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(encode(value),stream,sort_keys=True,indent=2,allow_nan=False);stream.write('\n')

def bounds(vertices):
    return tuple(min(v[k] for v in vertices) for k in range(3)),tuple(max(v[k] for v in vertices) for k in range(3))

def gaps(a,b):
    return [max(F(0),a[0][k]-b[1][k],b[0][k]-a[1][k]) for k in range(3)]

def lower_square(a,b):
    return sum((v*v for v in gaps(a,b)),F(0))

def prepare(obj):
    vertices=[tuple(F(x) for x in v) for v in obj['vertices_world']]
    faces=[tuple(f) for f in obj['triangles']]
    triangles=[tuple(vertices[i] for i in f) for f in faces]
    assert all(g.dot(g.cross(g.sub(t[1],t[0]),g.sub(t[2],t[0])),
                     g.cross(g.sub(t[1],t[0]),g.sub(t[2],t[0])))>0 for t in triangles)
    matrix=[[F(x) for x in r] for r in obj['matrix_world']]
    corners=[tuple(sum(matrix[k][j]*F(p[j]) for j in range(3))+matrix[k][3] for k in range(3))
             for p in obj['evaluated_bound_box_local']]
    api_bounds=bounds(corners)
    assert all(api_bounds[0][k]<=v[k]<=api_bounds[1][k] for v in vertices for k in range(3))
    return {'name':obj['name'],'vertices':vertices,'faces':faces,'triangles':triangles,
            'bounds':bounds(vertices),'api_bounds':api_bounds,
            'triangle_bounds':[bounds(t) for t in triangles]}

def solve(left,right):
    started=time.perf_counter_ns()
    first_left,first_right=left['triangles'][0],right['triangles'][0]
    initial=[]
    for i,a in enumerate(first_left):
        for j,b in enumerate(first_right):
            initial.append((g.squared(a,b),i,j,a,b))
    best,ia,ib,pa,pb=min(initial)
    witness={'kind':'initial_vertex_vertex','point_a':pa,'point_b':pb,
             'triangle_a':0,'triangle_b':0,'barycentric_a':g.bary_vertex(ia),'barycentric_b':g.bary_vertex(ib)}
    jobs=[(lower_square(a,b),i,j) for i,a in enumerate(left['triangle_bounds'])
          for j,b in enumerate(right['triangle_bounds'])]
    jobs.sort()
    solved=0;pruned=0;min_pruned=None;ledger=hashlib.sha256()
    for bound,i,j in jobs:
        if bound>=best:
            pruned+=1
            min_pruned=bound if min_pruned is None else min(min_pruned,bound)
            ledger.update(f'{i},{j},p,{bound.numerator}/{bound.denominator}\n'.encode())
            continue
        a,b=left['triangles'][i],right['triangles'][j]
        intersections=g.triangle_intersection(a,b)
        measured=g.triangle_distance(a,b,intersections)
        solved+=1
        candidate=measured['squared_distance_m2']
        ledger.update(f'{i},{j},s,{candidate.numerator}/{candidate.denominator}\n'.encode())
        if candidate<best:
            best=candidate;w=measured['minimum_candidates'][0]
            witness={'kind':w['kind'],'point_a':w['point_target'],'point_b':w['point_candidate'],
                     'triangle_a':i,'triangle_b':j,'barycentric_a':w['barycentric_target'],
                     'barycentric_b':w['barycentric_candidate'],'parameters':w.get('parameters')}
    assert solved+pruned==len(jobs)
    assert min_pruned is None or min_pruned>=best
    assert g.squared(witness['point_a'],witness['point_b'])==best
    assert g.blend(left['triangles'][witness['triangle_a']],witness['barycentric_a'])==witness['point_a']
    assert g.blend(right['triangles'][witness['triangle_b']],witness['barycentric_b'])==witness['point_b']
    gap=gaps(left['api_bounds'],right['api_bounds'])
    return {'object_a':left['name'],'object_b':right['name'],'exact_squared_distance_m2':best,
            'distance_interval':g.root_interval(best),'matches_threshold':best<=THRESHOLD**2,
            'witness':witness,'triangle_pairs_total':len(jobs),'triangle_pairs_solved':solved,
            'triangle_pairs_bound_pruned':pruned,'minimum_pruned_lower_squared_m2':min_pruned,
            'pruned_bounds_cover_final_minimum':True,'triangle_dispositions_sha256':ledger.hexdigest(),
            'api_AABB_Linf_retained':max(gap)<=THRESHOLD,
            'tight_AABB_L2_retained':lower_square(left['bounds'],right['bounds'])<=THRESHOLD**2,
            'api_AABB_overlap':max(gap)==0,'elapsed_ns':time.perf_counter_ns()-started}

def state_truth(state):
    path=HERE/(state.upper()+'_SNAPSHOT.json');snapshot=json.loads(path.read_bytes())
    prepared=[prepare(o) for o in snapshot['objects']]
    assert len(prepared)==24
    assert snapshot['counts']=={'objects':24,'vertices':530,'triangles':978}
    results=[]
    for left,right in combinations(prepared,2):
        row=solve(left,right);results.append(row)
        if len(results)%24==0:
            print(json.dumps({'state':state,'pairs_completed':len(results)}),flush=True)
    assert len(results)==276
    by_pair={(r['object_a'],r['object_b']):r for r in results}
    p={o['name']:o for o in prepared}
    outer,inner=p['Obj_001'],p['Obj_024']
    containment=all(outer['bounds'][0][k]<v[k]<outer['bounds'][1][k] for v in inner['vertices'] for k in range(3))
    assert containment
    box_checks=[g.audit_body(name,p[name]['vertices'],p[name]['faces']) for name in ('Obj_001','Obj_024')]
    assert all(b['passed'] for b in box_checks)
    contained=by_pair['Obj_001','Obj_024']
    assert not contained['matches_threshold'] and contained['exact_squared_distance_m2']>THRESHOLD**2
    assert (F('.003')-F('0.000001'))**2<=contained['exact_squared_distance_m2']<=(F('.003')+F('0.000001'))**2
    kept=[r for r in results if r['api_AABB_Linf_retained']]
    true=[r for r in results if r['matches_threshold']]
    difficult_negative=[r for r in results if r['api_AABB_overlap'] and not r['matches_threshold']]
    zones=[]
    for members in (('Obj_002','Obj_008','Obj_013','Obj_021'),('Obj_003','Obj_009','Obj_015','Obj_022')):
        local=[r for r in true if r['object_a'] in members and r['object_b'] in members]
        zones.append({'members':members,'matches':[(r['object_a'],r['object_b']) for r in local]})
    checks={'all_276_pairs_solved':len(results)==276,'candidate_density_at_least_69':len(kept)>=69,
            'nonempty_true_matches':bool(true),'strictly_bound_excluded_pairs':len(kept)<276,
            'overlapping_AABB_nonmatches':bool(difficult_negative),
            'strict_containment_surface_nonmatch':containment and not contained['matches_threshold'],
            'both_assembly_zones_have_matches':all(z['matches'] for z in zones),
            'all_API_bounds_enclose_actual_vertices':True,
            'all_static_valid_triangles':True,'actual_open_surface':p['Obj_012']['faces']==[(0,1,2),(0,2,3)]}
    return {'state':state,'snapshot_sha256':sha(path),'counts':snapshot['counts'],'pairs':results,
            'qualification_checks':checks,'matches':[(r['object_a'],r['object_b']) for r in true],
            'candidate_count':len(kept),'match_count':len(true),
            'AABB_overlap_nonmatch_pairs':[(r['object_a'],r['object_b']) for r in difficult_negative],
            'controls':{'strict_containment':contained,'box_closed_checks':box_checks,'zones':zones,
                        'slider_rail_pair':by_pair['Obj_002','Obj_008']},
            'totals':{'triangle_pairs':sum(r['triangle_pairs_total'] for r in results),
                      'exact_solved':sum(r['triangle_pairs_solved'] for r in results),
                      'bound_pruned':sum(r['triangle_pairs_bound_pruned'] for r in results)},
            'passed':all(checks.values())}

def main():
    started=time.perf_counter_ns();error=None;truth=None
    sources={str(p):sha(p) for p in (Path(__file__),LIB,HERE/'GEOMETRY_FREEZE.json',HERE/'BASE_SNAPSHOT.json',HERE/'EDIT_SNAPSHOT.json')}
    try:
        base=state_truth('base');save(HERE/'BASE_TRUTH.json',base)
        edit=state_truth('edit');save(HERE/'EDIT_TRUTH.json',edit)
        before=json.loads((HERE/'BASE_SNAPSHOT.json').read_bytes());after=json.loads((HERE/'EDIT_SNAPSHOT.json').read_bytes())
        changed=[]
        for a,b in zip(before['objects'],after['objects'],strict=True):
            assert a['name']==b['name'] and a['vertices_local']==b['vertices_local'] and a['triangles']==b['triangles']
            if a['matrix_world']!=b['matrix_world']:changed.append(a['name'])
        assert changed==['Obj_008']
        rail_base=base['controls']['slider_rail_pair'];rail_edit=edit['controls']['slider_rail_pair']
        assert not rail_base['matches_threshold'] and rail_edit['matches_threshold']
        truth={'schema':'surface-scan-independent-qualification-v1','qualification_status':'passed' if base['passed'] and edit['passed'] else 'failed',
               'threshold_actual_binary64_m':THRESHOLD,'sources':sources,'states':{
                   'base':{'truth_sha256':sha(HERE/'BASE_TRUTH.json'),'matches':base['match_count'],'candidates':base['candidate_count']},
                   'edit':{'truth_sha256':sha(HERE/'EDIT_TRUTH.json'),'matches':edit['match_count'],'candidates':edit['candidate_count']}},
               'counts':{'objects':24,'vertices':530,'triangles':978,'object_pairs_per_state':276},
               'changed_objects':changed,'morphology_adjustments_used':0,
               'oracle_pruning_proof':'Each triangle box uses coordinate extrema of its actual rational vertices. All triangle-pair L2 box bounds are computed, sorted, and skipped only when at least an already attained upper squared distance. Zero is a global distance lower bound. Every object pair is processed.',
               'model_consumers':0,'product_runs':0,'images':0}
        assert sources=={str(p):sha(p) for p in (Path(__file__),LIB,HERE/'GEOMETRY_FREEZE.json',HERE/'BASE_SNAPSHOT.json',HERE/'EDIT_SNAPSHOT.json')}
        save(HERE/'QUALIFICATION.json',truth)
    except BaseException as exc:
        error={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
        with (HERE/'ORACLE_FAILURES.jsonl').open('a',encoding='utf8') as f:f.write(json.dumps(error)+'\n')
        raise
    finally:
        with (HERE/'ORACLE_RUNS.jsonl').open('a',encoding='utf8') as f:
            f.write(json.dumps({'started_ns':started,'ended_ns':time.perf_counter_ns(),
                'elapsed_ns':time.perf_counter_ns()-started,'error':error,'status':None if truth is None else truth['qualification_status']})+'\n')
    print(json.dumps({'qualification_status':truth['qualification_status'],'states':truth['states'],'elapsed_ns':time.perf_counter_ns()-started}))

if __name__=='__main__':main()
