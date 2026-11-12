"""Saved-data feasibility only: a supplied direction must pass all-vertex support.

No oracle normal, product import, runtime predicate or closed-domain validation.
Direction is the fixed candidate's first saved public nearest-witness difference.
This cannot certify an embedded closed shell or replace the old acceptance.
"""
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import subprocess

ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
HERE=Path(__file__).resolve().parent
COMMIT='743a484f16f1dadff8dedcf1abad8d0a14398d17'
sources=[]
def read(path):
    raw=subprocess.check_output(['git','-C',str(ROOT),'show',COMMIT+':'+path])
    sources.append({'path':path,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)})
    return json.loads(raw)
def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def encode(q):return [q.numerator,q.denominator]

snapshot=read('verification/spatial_task_qualification_001/entry/run_01/ACTUAL_SNAPSHOT.json')
objects={row['name']:row for row in snapshot['objects']}
rows=[]
for name in ('Peer_000','Competing_001','Near_003','cube12_control'):
    sample=read('verification/m3_pair_scalability_001/testing/paired_01/'+name+'_1_candidate.json')
    left_name,right_name=('Control_A','Control_B') if name=='cube12_control' else ('Target',name)
    left,right=[tuple(map(F,p)) for p in objects[left_name]['vertices_world']], [tuple(map(F,p)) for p in objects[right_name]['vertices_world']]
    result=sample['surface']
    direction=sub(tuple(map(F,result['point_b_world'])),tuple(map(F,result['point_a_world'])))
    origin=left[0]
    a=[dot(direction,sub(p,origin)) for p in left]
    b=[dot(direction,sub(p,origin)) for p in right]
    gap=min(b)-max(a);squared_norm=dot(direction,direction)
    lower_sq=gap*gap/squared_norm if gap>0 and squared_norm else None
    rows.append({'case':name,'direction_from':'first saved candidate public witness difference, not oracle',
                 'direction':[encode(x) for x in direction],
                 'left_vertices':len(left),'right_vertices':len(right),'dot_products':len(left)+len(right),
                 'strict_support_separation':gap>0,'projection_gap':encode(gap),
                 'direction_squared_norm':encode(squared_norm),
                 'support_distance_lower_bound_sq_m2':encode(lower_sq) if lower_sq is not None else None,
                 'support_distance_lower_bound_m_approx':math.sqrt(float(lower_sq)) if lower_sq is not None else None,
                 'existing_surface_distance_m':result['distance_m'],
                 'lower_bound_proves_at_least_4mm':lower_sq>=F(1,250)**2 if lower_sq is not None else False,
                 'closed_domain_verified':False})
out={'fixed_commit':COMMIT,'scope':'feasibility of sufficient convex-hull separation fact; not product, embedded-shell proof or timing',
     'hypothesis':'all-vertex positive support gap implies disjoint convex hulls regardless of either input self-intersection',
     'proposal_policy':'one direction per case, fixed before testing; no direction/axis search or geometry changes',
     'rows':rows,'sources':sources,'new_product_calls':0,'new_Blender_calls':0,'new_model_calls':0}
(HERE/'SUPPORT_FEASIBILITY.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps([{k:r[k] for k in ('case','dot_products','strict_support_separation','support_distance_lower_bound_m_approx','lower_bound_proves_at_least_4mm')} for r in rows]))
