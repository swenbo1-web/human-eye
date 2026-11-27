"""One and only one 045 geometry: inherited 044 rule at isqrt(16384)+1.

No tested kernel import or solver execution.  The global optimum is independently
proved from exact linear functionals of the serialized world coordinates.
"""
from __future__ import annotations
import argparse
from fractions import Fraction as Q
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import struct
import sys
import time

HERE=Path(__file__).resolve().parent
VER=HERE.parents[1]
RAW=Path('D:/HumanEye/runs/M6-045-R3-REPLACEMENT-ENTRY/oracle')
GENERATOR=VER/'m6_r3_fresh_budget_044/freeze_pressure.py'
GENERATOR_SHA='e92a6a5c3b0d79c147d6c49067b0fc7897b9ee75264c2b8217094823fb5dc112'
POSITIVE=Path('D:/HumanEye/runs/M6-044-R3-FRESH-BUDGET/pressure/FINAL_FREEZE.json')
FACES_CAP=4096
NARROW_CAP=16384
WORK_CAP=1179648

def pin(path):
    p=Path(path).resolve(strict=True);b=p.read_bytes()
    return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}

def read(path):return json.loads(Path(path).read_bytes())

def save(path,value):
    p=Path(path)
    with p.open('x',encoding='utf8',newline='\n') as out:
        json.dump(value,out,indent=2,allow_nan=False,ensure_ascii=False);out.write('\n')
    return pin(p)

def hash_array(rows,code):
    values=[x for row in rows for x in row]
    return hashlib.sha256(struct.pack('<'+code*len(values),*values)).hexdigest()

def sqrt_rounded(q):
    """Certify binary64 rounding using exact midpoint squares, including ties-even."""
    assert q>0
    result=math.sqrt(float(q))
    while True:
        lo=math.nextafter(result,-math.inf);hi=math.nextafter(result,math.inf)
        low_mid=(Q(lo)+Q(result))/2;high_mid=(Q(result)+Q(hi))/2
        odd=struct.unpack('<Q',struct.pack('<d',result))[0]&1
        if q<low_mid**2 or q==low_mid**2 and odd:result=lo
        elif q>high_mid**2 or q==high_mid**2 and odd:result=hi
        else:return result

def prove(doc):
    """Use only deserialized world coordinates, never inherited prove() or solver output."""
    n=math.isqrt(NARROW_CAP)+1
    assert n==129 and doc['subdivision_n']==n
    sides=[];arrays={};boxes=[]
    for label in ('left','right'):
        mesh=doc[label];points=[tuple(Q(x) for x in p) for p in mesh['vertices_world']]
        faces=mesh['faces'];assert len(faces)==n and len(points)==3*n and len(set(points))==3*n
        assert faces==[[3*i,3*i+1,3*i+2] for i in range(n)]
        tris=[]
        for face in faces:
            p,q,r=[points[v] for v in face];a,b=[tuple(x-y for x,y in zip(v,p)) for v in (q,r)]
            assert any(a[i]*b[j]-a[j]*b[i] for i,j in ((0,1),(0,2),(1,2)))
            tris.append((p,q,r))
        sides.append(tris)
        boxes.append(([min(p[k] for p in points) for k in range(3)],
                      [max(p[k] for p in points) for k in range(3)]))
        f32=[[struct.unpack('<f',struct.pack('<f',x))[0] for x in p] for p in mesh['vertices_world']]
        assert f32==mesh['vertices_world'],'ordinary native mesh storage would change geometry'
        arrays[label]={'name':mesh['name'],'vertices':3*n,'triangles':n,
            'world_f64_le_sha256':hash_array(mesh['vertices_world'],'d'),
            'world_f32_le_sha256':hash_array(mesh['vertices_world'],'f'),
            'faces_i32_le_sha256':hash_array(faces,'i'),'native_f32_roundtrip_exact':True,
            'source_vertex_rows':list(range(3*n)),'source_triangle_rows':list(range(n)),
            'native_polygon_mapping':'one triangular native polygon per frozen row, to be checked on actual host'}
    left,right=sides
    assert len({frozenset(t) for t in left+right})==2*n
    normal=lambda p:p[0]+p[1]-2*p[2]
    tangent=lambda p:(p[0]-p[1])/2
    assert all(normal(p)==0 for tri in left+right[:-1] for p in tri)
    offsets={normal(p) for p in right[-1]};assert len(offsets)==1
    offset=offsets.pop();assert offset>0
    squared=offset*offset/Q(6)
    assert squared==Q(3,32768)
    high=max(tangent(p) for tri in left for p in tri)
    low_main=min(tangent(p) for tri in right[:-1] for p in tri)
    low_last=min(tangent(p) for p in right[-1])
    assert low_main>high and low_last==high
    main_lower=2*(low_main-high)**2;assert main_lower>squared
    lmatch=[(i,j,p) for i,tri in enumerate(left) for j,p in enumerate(tri) if tangent(p)==high]
    rmatch=[(n-1,j,p) for j,p in enumerate(right[-1]) if tangent(p)==low_last]
    assert len(lmatch)==len(rmatch)==1
    i,li,a=lmatch[0];j,ri,b=rmatch[0]
    delta=tuple(y-x for x,y in zip(a,b))
    assert delta==(Q(1,256),Q(1,256),Q(-1,128))
    assert sum(x*x for x in delta)==squared and [i,j]==[128,128]
    assert all(boxes[1][0][k]<boxes[0][0][k] and boxes[0][1][k]<boxes[1][1][k] for k in range(3))
    for k in range(3):
        lbox=[(min(p[k] for p in tri),max(p[k] for p in tri)) for tri in left]
        rbox=[(min(p[k] for p in tri),max(p[k] for p in tri)) for tri in right]
        assert max(x[0] for x in lbox)<=min(x[1] for x in rbox)
        assert max(x[0] for x in rbox)<=min(x[1] for x in lbox)
    rounded=sqrt_rounded(squared)
    return {'schema':'m6-045-independent-analytic-truth-v1','status':'pass',
        'distance_squared_exact':str(squared),'exact_distance_squared_world_m2':str(squared),
        'distance_m':rounded,'distance_float_hex':rounded.hex(),
        'canonical_native_face_pair':[i,j],'canonical_source_triangle_pair':[i,j],
        'all_minimizing_source_triangle_pairs':[[i,j]],'unique_witness_world_exact':[[str(x) for x in p] for p in (a,b)],
        'exact_points_world_m':[[str(x) for x in p] for p in (a,b)],
        'point_a_world':[float(x) for x in a],'point_b_world':[float(x) for x in b],
        'direction_a_to_b':[sqrt_rounded(Q(1,6)),sqrt_rounded(Q(1,6)),-sqrt_rounded(Q(2,3))],
        'unique_source_vertex_pair':[3*i+li,3*j+ri],
        'canonical_face_source_vertices':[doc['left']['faces'][i],doc['right']['faces'][j]],
        'other_band_distance_squared_lower':str(main_lower),'actual_distinct_faces':[n,n],
        'native_root_strict_containment':True,'all_cross_aabbs_overlap':True,
        'possible_triangle_pairs':n*n,'actual_narrow_phase_pairs':'not run; cannot be inferred from possible pairs',
        'proof_coverage':{'main_band_pairs':n*(n-1),'last_triangle_pairs':n,'total':n*n},
        'linear_functionals':{'normal':[1,1,-2],'normal_length_squared':6,'normal_offset':str(offset),
            'tangent':'(x-y)/2','left_t_max':str(high),'right_main_t_min':str(low_main),'right_last_t_min':str(low_last)},
        'proof':'For main right bands, the tangent functional gives squared distance >= 2*(tBmin-tAmax)^2. '
            'For the last right triangle, parallel-plane Cauchy gives offset^2/6. Equality requires pure normal displacement, '
            'therefore equal tangent coordinates. The two closed tangent ranges intersect only at one unique vertex each. '
            'Their exact displacement attains the plane bound. Thus the global nearest points and original face pair are unique.',
        'array_bindings':arrays,'independent_of_candidate_version':True,'tested_A_B_C_imports':0}

def main():
    began=time.perf_counter_ns();cpu=time.process_time_ns();RAW.mkdir(parents=True,exist_ok=False)
    assert pin(GENERATOR)['sha256']==GENERATOR_SHA
    positive=read(POSITIVE)
    assert positive['n']==125
    assert pin(positive['geometry']['path'])==positive['geometry'] and pin(positive['exact_truth']['path'])==positive['exact_truth']
    plan=save(RAW/'PLAN.json',{'schema':'m6-045-only-one-input-prereg-v1','source':pin(__file__),
        'contract':'3e9e06ea381d3ad3669f7ac14e5ba25e4ba245f0','inherited_generator':pin(GENERATOR),
        'n_expression':'math.isqrt(16384)+1','n':math.isqrt(16384)+1,'only_generator_argument_changed':'n',
        'retained_044_positive':pin(POSITIVE),'retained_positive_geometry':positive['geometry'],
        'retained_positive_truth':positive['exact_truth'],'limits':{'faces':FACES_CAP,'narrow_phase_pairs':NARROW_CAP,'work_units':WORK_CAP},
        'request_budget_s':30.0,'new_calibrations':0,'tested_A_B_C_imports':0,'Blender':0,'MCP':0,
        'rules':['call inherited geometry(129) once','no inherited prove() call','independently prove serialized world bytes',
            'one input only; no selection after solver results; 16641 possible pairs does not imply 16641 narrow calls']})
    with (RAW/'INHERITED_GENERATOR.py').open('xb') as out:out.write(GENERATOR.read_bytes())
    spec=importlib.util.spec_from_file_location('_045_inherited_geometry_generator',GENERATOR)
    generator=importlib.util.module_from_spec(spec);spec.loader.exec_module(generator)
    doc=generator.geometry(math.isqrt(NARROW_CAP)+1)
    geometry=save(RAW/'FINAL_GEOMETRY.json',doc)
    assert not any(x=='human_eye_plugin' or x.startswith('human_eye_plugin.') for x in sys.modules)
    # The inherited generator imports only the already-fixed stdlib helper common.py.
    truth=prove(read(geometry['path']))
    truth_ref=save(RAW/'FINAL_INDEPENDENT_TRUTH.json',truth)
    frozen=save(RAW/'FINAL_FREEZE.json',{'schema':'m6-045-unique-input-freeze-v1','status':'frozen_before_A_B_C',
        'plan':plan,'n':129,'geometry':geometry,'exact_truth':truth_ref,'generator':pin(GENERATOR),
        'limits':{'faces':FACES_CAP,'narrow_phase_pairs':NARROW_CAP,'work_units':WORK_CAP},
        'planned_arms':['A','B','C'],'source_kind':doc['source_kind'],'request_budget_s':30.0,
        'admissible_public_surface':True,'new_calibrations':0,'generated_input_count':1,'tested_A_B_C_imports':0,
        'input_shape':{'left':{'vertices':387,'triangles':129},'right':{'vertices':387,'triangles':129}},
        'Blender':0,'MCP':0})
    result=save(RAW/'RESULTS.json',{'schema':'m6-045-oracle-result-v1','status':'pass','freeze':frozen,
        'geometry':geometry,'truth':truth_ref,'source':pin(__file__),
        'cost_wall_ns':time.perf_counter_ns()-began,'cost_cpu_ns':time.process_time_ns()-cpu,
        'cost_scope':'complete Python freeze/proof function inclusive I/O; interpreter startup excluded',
        'generated_input_count':1,'tested_A_B_C_imports':0,'Blender':0,'MCP':0})
    print(json.dumps({'status':'pass','result':result,'freeze':frozen,'geometry':geometry,'truth':truth_ref}))

if __name__=='__main__':main()
