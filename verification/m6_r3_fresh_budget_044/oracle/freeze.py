"""044 independent Fraction reference for the one fixed historical assembly pair.

This module never imports an A/B/C runtime.  Stored binary64 world coordinates and
ordered author faces are the input; no scene, mesh, or tessellation is generated.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from fractions import Fraction as Q
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import time
import traceback
from types import SimpleNamespace

HERE=Path(__file__).resolve().parent
VER=HERE.parents[1]
SOURCE=VER/'closed_solid_read_001'
RAW=Path('D:/HumanEye/runs/M6-044-R3-FRESH-BUDGET/oracle')
PINS={'scene.blend':'a1a593fc1591365bbbff0c62c535af90ab8b1cdd2dc5ce560d3922252c4e1fcb',
      'author_mesh_snapshots.json':'5a089d22faad7c90b9a28c6ea408ea8b73e8b939e47a3cb66a193ba85f23fc14',
      'TRUTH.json':'d01b0006ef1d4416c8b40663e8aabb7ba64730c7c833b516c3ee1631651a38ff'}
PAIR=('Object_01','Object_02')
RAYS=((1,2,3),(3,1,2),(2,3,1),(1,-2,3),(-3,1,2),(2,3,-1),(5,7,11),(11,-7,5))

def pin(path):
    p=Path(path).resolve(strict=True);data=p.read_bytes()
    return {'path':str(p),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}

def read(path):return json.loads(Path(path).read_bytes())

def save(path,value):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf8',newline='\n') as out:json.dump(value,out,indent=2,allow_nan=False);out.write('\n')
    return pin(p)

def digest(rows,kind):
    code={'f64':'d','i32':'i'}[kind]
    values=[x for row in rows for x in row]
    return hashlib.sha256(struct.pack('<'+code*len(values),*values)).hexdigest()

def load_meshes(path=RAW/'INPUTS.json'):
    inputs=read(path);assert pin(inputs['geometry']['path'])==inputs['geometry']
    data=read(inputs['geometry']['path'])
    meshes=[SimpleNamespace(name=name,object_id=name,vertices=[tuple(x) for x in data['objects'][name]['vertices_world_m']],
                faces=[tuple(x) for x in data['objects'][name]['triangles']]) for name in inputs['pair']]
    return meshes[0],meshes[1],inputs

def prepare():
    RAW.mkdir(parents=True,exist_ok=False)
    refs={name:pin(SOURCE/'inputs'/name) for name in PINS}
    assert all(refs[name]['sha256']==PINS[name] for name in PINS)
    old=read(SOURCE/'qa_01/RESULTS.json')
    call,=[x for x in old['public_calls'] if x['state']=='initial' and x['candidate']=='Object_02']
    assert call['arguments']=={'session_id':'closed-solid-read','include_image':False,'query':{'mode':'task',
        'objects':[{'name':'Object_01'},{'name':'Object_02'}],
        'requested_facts':['closed_solid_relation','surface_proximity']}}
    historical=save(RAW/'ORIGINAL_CALL.json',{'source_receipt':pin(SOURCE/'qa_01/RESULTS.json'),'row':call})
    state=read(refs['author_mesh_snapshots.json']['path'])['initial'];assert state['unit_scale_m']==1.
    objects={x['name']:x for x in state['objects']};normalized={};root=[]
    for name in PAIR:
        row=objects[name];vertices=row['world_vertices'];faces=row['faces'];matrix=row['matrix_world']
        projected=[[(((v[0]*matrix[k][0]+v[1]*matrix[k][1])+v[2]*matrix[k][2])+matrix[k][3])*state['unit_scale_m']
                    for k in range(3)] for v in row['vertices_local']]
        assert digest(projected,'f64')==digest(vertices,'f64'),'historical world arithmetic differs'
        assert all(len(face)==3 for face in faces)
        normalized[name]={'name':name,'vertices_world_m':vertices,'triangles':faces,
            'vertices_local':row['vertices_local'],'matrix_world':matrix,
            'source_vertex_rows':list(range(len(vertices))),'source_triangle_rows':list(range(len(faces))),
            'native_polygon_ids':None,'native_polygon_mapping_status':'author snapshot has ordered triangle faces but no polygon-to-loop table',
            'hashes':{'world_f64_le':digest(vertices,'f64'),'local_f64_le':digest(row['vertices_local'],'f64'),
                'faces_i32_le':digest(faces,'i32'),'matrix_f64_le':digest(matrix,'f64')},
            'world_expression':'(((x*m_col0+y*m_col1)+z*m_col2)+translation)*scale; exact binary64 order matches stored world_vertices'}
        root.append(([min(Q(p[k]) for p in vertices) for k in range(3)],
                     [max(Q(p[k]) for p in vertices) for k in range(3)]))
    assert [len(normalized[x]['triangles']) for x in PAIR]==[96,12]
    directions=[all(root[a][0][k]<root[b][0][k] and root[b][1][k]<root[a][1][k] for k in range(3))
                for a,b in ((0,1),(1,0))]
    geometry=save(RAW/'GEOMETRY.json',{'schema':'m6-044-fixed-archived-native-geometry-v1','objects':normalized})
    provenance=read(SOURCE/'PRESERVATION.json')
    source_provenance=save(RAW/'PROVENANCE.json',{'preservation_receipt':pin(SOURCE/'PRESERVATION.json'),
        'original_assets':provenance['original_assets'],'historical_evidence_index':pin(SOURCE/'EVIDENCE_INDEX.json'),
        'author_state':'initial','unchanged_original_assets':provenance['original_assets_written'] is False,
        'no_Blender_open_performed_by_this_oracle':True})
    oracle=VER/'m6_bvh_witness_projection_029/oracle.py'
    inputs=save(RAW/'INPUTS.json',{'schema':'m6-044-fixed-archived-pair-inputs-v1','pair':list(PAIR),'originals':refs,
        'geometry':geometry,'historical_call':historical,'provenance':source_provenance,
        'original_request':call['arguments'],'coordinate_frame':'world','unit':'m','unit_scale_m':1.,
        'root_boxes_exact':[[[str(x) for x in side] for side in box] for box in root],
        'root_strict_containment':any(directions),'root_containing_object':PAIR[directions.index(True)] if any(directions) else None,
        'root_containment_is_not_a_surface_or_solid_separation_certificate':True,
        'index_domain':'zero_based_original_author_triangle_rows; face vertex IDs refer to unchanged original source vertex rows',
        'runtime_scope':'archived original binary64 input; ordinary native copy still requires host rebind'})
    plan=save(RAW/'PLAN.json',{'schema':'m6-044-independent-oracle-prereg-v1','inputs':inputs,'source':pin(__file__),
        'independent_feature_oracle':pin(oracle),'pair_order':list(PAIR),'exact_triangle_pair_obligations':1152,
        'pruning':False,'canonical_rule':'lexicographically earliest original ordered triangle pair among all exact global minima',
        'point_rule':'one independently attained exact source-member point pair for earliest canonical face pair',
        'relation_support':'original independent nonzero-error interval and actual old closed-shell result; independent exact distance/topology/outside-ray corroboration',
        'fixed_ray_directions':RAYS,'tested_A_B_C_imports':0,'Blender':0,'MCP':0})
    print(json.dumps({'inputs':inputs,'plan':plan}),flush=True)
    return plan

def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])

def topology(mesh):
    edges=Counter();oriented=Counter();neighbors=defaultdict(set);byedge=defaultdict(list)
    points=[tuple(map(Q,p)) for p in mesh.vertices];volume=Q(0)
    for i,face in enumerate(mesh.faces):
        a,b,c=[points[v] for v in face];assert dot(cross(sub(b,a),sub(c,a)),cross(sub(b,a),sub(c,a)))>0
        volume+=dot(a,cross(b,c))/6
        for u,v in zip(face,face[1:]+face[:1]):edges[tuple(sorted((u,v)))]+=1;oriented[(u,v)]+=1;byedge[tuple(sorted((u,v)))].append(i)
    assert all(n==2 for n in edges.values()) and all(oriented[(u,v)]==oriented[(v,u)]==1 for u,v in edges)
    for faces in byedge.values():a,b=faces;neighbors[a].add(b);neighbors[b].add(a)
    reached={0};pending=[0]
    while pending:
        for j in neighbors[pending.pop()]-reached:reached.add(j);pending.append(j)
    assert len(reached)==len(mesh.faces) and volume!=0
    return {'closed_oriented_edge_pairs':len(edges),'connected_faces':len(reached),
        'nonzero_signed_volume_world_m3':str(volume),'self_embedding_validity':'reuses original independently certified immutable assembly source; no new self-intersection validator claimed'}

def outside_ray(point,mesh):
    p=tuple(map(Q,point));triangles=[[tuple(map(Q,mesh.vertices[v])) for v in f] for f in mesh.faces]
    rejected=[]
    for direction in RAYS:
        hits=[];bad=False
        for i,(a,b,c) in enumerate(triangles):
            e1,e2=sub(b,a),sub(c,a);n=cross(e1,e2);denom=dot(n,direction)
            numerator=dot(n,sub(a,p))
            if denom==0:
                if numerator==0:bad=True;break
                continue
            t=numerator/denom
            if t<=0:continue
            q=tuple(x+t*d for x,d in zip(p,direction));v=sub(q,a)
            d11,d12,d22=dot(e1,e1),dot(e1,e2),dot(e2,e2);D=d11*d22-d12*d12
            s=(dot(v,e1)*d22-dot(v,e2)*d12)/D;u=(dot(v,e2)*d11-dot(v,e1)*d12)/D
            if s<0 or u<0 or s+u>1:continue
            if s==0 or u==0 or s+u==1:bad=True;break
            hits.append({'face':i,'ray_parameter':str(t),'point':[str(x) for x in q]})
        if bad:rejected.append(list(direction));continue
        assert len(hits)%2==0,'point is inside the other archived shell'
        return {'direction':list(direction),'strict_face_hits':hits,'parity':'outside','rejected_degenerate_rays':rejected}
    raise AssertionError('all fixed exact ray directions degenerate')

def solve(plan_path=RAW/'PLAN.json'):
    began=time.perf_counter_ns();cpu=time.process_time_ns();plan=read(plan_path)
    assert pin(__file__)==plan['source'] and pin(plan['independent_feature_oracle']['path'])==plan['independent_feature_oracle']
    spec=importlib.util.spec_from_file_location('_044_independent_fraction',plan['independent_feature_oracle']['path'])
    oracle=importlib.util.module_from_spec(spec);sys.modules[spec.name]=oracle;spec.loader.exec_module(oracle)
    left,right,inputs=load_meshes(plan['inputs']['path']);old=read(inputs['originals']['TRUTH.json']['path'])
    result={'status':'fail','plan':pin(plan_path),'tested_A_B_C_imports':0,'Blender':0,'MCP':0}
    try:
        exact=oracle.exhaustive(left,right,use_bounds=False)
        assert exact['full_pair_count']==exact['exact_feature_pairs']==1152 and exact['independent_AABB_proved_pairs']==0
        assert exact['distance_squared']>0 and exact['input_pair']==min(exact['minimizing_input_pairs'])
        oracle.validate_exact_witness(exact,exact['input_pair'],exact['one_independent_witness'],left,right)
        rounded=oracle.nearest_float_sqrt(exact['distance_squared'])
        relation=old['states']['initial']['probes']['Object_02'];lo,hi=map(Q,relation['distance_interval_m'])
        assert lo>0 and lo*lo<=exact['distance_squared']<=hi*hi and relation['relation']=='separated'
        old_call=read(inputs['historical_call']['path'])['row'];public=old_call['public_value']['facts']
        assert public['closed_solid_relation']['value']=='separated'
        assert rounded.hex()==public['surface_proximity']['value']['distance_m'].hex()
        canonical=exact['input_pair'];points=exact['one_independent_witness'];meshes=(left,right)
        truth={'schema':'m6-044-independent-exact-truth-v1','status':'pass','inputs':plan['inputs'],
            'exact_distance_squared_world_m2':str(exact['distance_squared']),'distance_m':rounded,
            'distance_float_hex':rounded.hex(),'canonical_source_triangle_pair':list(canonical),
            'all_minimizing_source_triangle_pairs':[list(x) for x in exact['minimizing_input_pairs']],
            'exact_points_world_m':[[str(x) for x in p] for p in points],
            'canonical_face_source_vertices':[list(mesh.faces[index]) for mesh,index in zip(meshes,canonical)],
            'canonical_face_world_triangles':[[list(mesh.vertices[v]) for v in mesh.faces[index]] for mesh,index in zip(meshes,canonical)],
            'exact_witness_source_membership':True,'enumeration':oracle.json_exact(exact),
            'relation':'separated','historical_interval_certificate':relation,
            'historical_actual_call':inputs['historical_call'],
            'topology':[topology(mesh) for mesh in meshes],
            'exact_outside_ray_corroboration':[outside_ray(left.vertices[0],right),outside_ray(right.vertices[0],left)],
            'relation_scope':'old independent source certificate plus positive exhaustive surface distance, closed oriented connected topology and both exact outside-parity witnesses; positive AABB containment alone is not used'}
        truth_ref=save(RAW/'TRUTH.json',truth);result.update(status='pass',truth=truth_ref)
    except BaseException as exc:result['error']={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
    result.update(cost_wall_ns=time.perf_counter_ns()-began,cost_cpu_ns=time.process_time_ns()-cpu,
        cost_scope='independent freeze restore, complete exact feature enumeration and certificate checks; process startup excluded')
    ref=save(RAW/'RESULTS.json',result);print(json.dumps(ref),flush=True);return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('freeze','solve','all'));args=p.parse_args()
    if args.mode in ('freeze','all'):prepare()
    if args.mode in ('solve','all'):sys.exit(0 if solve()['status']=='pass' else 1)
