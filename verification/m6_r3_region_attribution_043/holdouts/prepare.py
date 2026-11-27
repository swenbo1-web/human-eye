"""Freeze actual low/high world geometry and untimed shared-call control inputs."""
from fractions import Fraction as Q
from pathlib import Path
import itertools
import struct
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from common import BASE,CANDIDATE,FROZEN,HIGH,RAW,SOURCE,VER,dump,installation,need,pin,read


def bytes64(vertices):return b''.join(struct.pack('<3d',*v) for v in vertices)


def cube_faces_proof(vertices,faces):
    points=[tuple(map(Q,v)) for v in vertices]
    need(set(points)==set(itertools.product((Q(-1),Q(1)),repeat=3)),'reference_cube_corners')
    sides={}
    for face in faces:
        ps={points[i] for i in face};need(len(ps)==3,'cube_face_nondegenerate')
        k=[(axis,next(iter(ps))[axis]) for axis in range(3) if len({p[axis] for p in ps})==1]
        need(len(k)==1,'cube_face_plane');sides.setdefault(k[0],[]).append(ps)
    need(len(sides)==6,'closed_six_square_faces')
    for (axis,sign),pair in sides.items():
        need(len(pair)==2,'two_native_triangles_per_square')
        diagonal=list(pair[0]&pair[1]);need(len(diagonal)==2 and len(pair[0]|pair[1])==4,'complete_square_union')
        need(all(diagonal[0][k]!=diagonal[1][k] for k in range(3) if k!=axis),'common_square_diagonal')


def region(label,objects,frozen):
    target=objects[frozen['target']]['evaluated'];reference=objects[frozen['reference']]['evaluated']
    wanted=frozen['regions'][label];box=wanted['box_m'];world=target['vertices_world_m'];faces=target['triangles']
    inside=[all(Q(lo)<=Q(x)<=Q(hi) for x,lo,hi in zip(v,box['min'],box['max'])) for v in world]
    rows=[i for i,f in enumerate(faces) if all(inside[v] for v in f)];vertices=sorted({v for i in rows for v in faces[i]})
    need(rows==wanted['triangle_ids'] and len(vertices)==wanted['associated_vertex_count'],'complete_native_selection')
    mapping={v:i for i,v in enumerate(vertices)}
    left={'name':frozen['target'],'vertices_world':[world[v] for v in vertices],
          'faces':[[mapping[v] for v in faces[i]] for i in rows],
          'native_triangle_rows':rows,'native_vertex_rows':vertices}
    right={'name':frozen['reference'],'vertices_world':reference['vertices_world_m'],'faces':reference['triangles'],
           'native_triangle_rows':list(range(len(reference['triangles']))),'native_vertex_rows':list(range(len(reference['vertices_world_m'])))}
    cube_faces_proof(right['vertices_world'],right['faces'])
    exact=[tuple(map(Q,v)) for v in left['vertices_world']]
    need(all(all(-1<x<1 for x in p) for p in exact),'strict_root_axis_containment')
    bounds={(axis,sign):min(1-sign*p[axis] for p in exact) for axis in range(3) for sign in (-1,1)}
    d=min(bounds.values());need(d==Q(wanted['distance_exact_m'])==bounds[(2,1)],'independent_Cube_surface_distance')
    pa=tuple(map(Q,wanted['source_point_exact_m']));pb=tuple(map(Q,wanted['reference_point_exact_m']))
    need(pa in exact and pb==(pa[0],pa[1],Q(1)) and pb[2]-pa[2]==d,'frozen_unique_attainment')
    top=max(p[2] for p in exact);points={p for p in exact if p[2]==top}
    need(points=={pa},'unique_closest_source_point')
    attaining=[row for row in rows if any(Q(world[v][2])==top for v in faces[row])]
    native=[min(attaining),min(wanted['cube_witness_triangle_ids'])]
    need(native==[min(wanted['source_witness_triangle_ids']),0],'canonical_native_pair')
    face0=[tuple(map(Q,right['vertices_world'][v])) for v in right['faces'][0]]
    def turn(a,b,p):return (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])
    turns=[turn(face0[i],face0[(i+1)%3],pb) for i in range(3)]
    need(all(p[2]==1 for p in face0) and (all(t>=0 for t in turns) or all(t<=0 for t in turns)),
         'independent_reference_face0_attainment')
    proof={'method':'exact closed-Cube six-face coverage and attained global plane lower bound',
           'distance_exact_m':str(d),'distance_squared_exact_m2':str(d*d),'unique_closest_source_point':True,
           'canonical_native_pair':native,'point_a_exact':list(map(str,pa)),'point_b_exact':list(map(str,pb)),
           'point_a_m':wanted['source_point_world_m'],'point_b_m':wanted['reference_point_world_m'],
           'direction_a_to_b':[0.,0.,1.],'strict_root_containment_independent':True}
    if label=='high':
        actual=read(HIGH);need(pin(HIGH)['sha256']=='6f6274e27ce2a3a1137a1dc817aca2413362d31027416bff3aff45fb831090b9','042_actual_packet')
        need(actual['region']['source_triangle_indices']==rows and actual['region']['source_vertex_indices']==vertices,'042_actual_source_map')
        need(actual['region']['faces']==left['faces'] and bytes64(actual['region']['vertices'])==bytes64(left['vertices_world']),'042_actual_geometry_bits')
        need(actual['reference']['faces']==right['faces'] and bytes64(actual['reference']['vertices'])==bytes64(right['vertices_world']),'042_actual_reference_bits')
    return {'case_id':'Yanyite_'+label,'scope':'same-source real holdout' if label=='low' else 'actual042 high shared-call check',
            'source_kind':'independently reconstructed existing raw evaluated world geometry; not a new native capture',
            'left':left,'right':right,'box_m':box,'source':pin(SOURCE),'frozen':pin(FROZEN),
            'actual_capture':pin(HIGH) if label=='high' else None,'independent_truth':proof}


def subdivide(vertices,faces):
    vertices=[list(v) for v in vertices];mid={};out=[]
    def midpoint(a,b):
        key=tuple(sorted((a,b)))
        if key not in mid:
            mid[key]=len(vertices);vertices.append([(vertices[a][k]+vertices[b][k])/2 for k in range(3)])
        return mid[key]
    for a,b,c in faces:
        ab,bc,ca=midpoint(a,b),midpoint(b,c),midpoint(c,a)
        out.extend([[a,ab,ca],[ab,b,bc],[ca,bc,c],[ab,bc,ca]])
    return vertices,out


def main():
    RAW.mkdir(parents=True,exist_ok=True)
    frozen=read(FROZEN);need(pin(FROZEN)['sha256']=='e52c9d575bc06da45bfac7e5cef4098027159ca34ad5cb6d07e4858f8f617b23','034_fixed_input')
    source=read(SOURCE);need(source['source']['asset_sha256']=='614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d','native_source_asset')
    objects={o['name']:o for o in source['objects']};cases={}
    for label in ('low','high'):
        value=region(label,objects,frozen);path=RAW/'inputs'/(value['case_id']+'.json');dump(path,value);cases[value['case_id']]=pin(path)
    fixture_path=VER/'scale_diag_001/fixtures/G60_D12.json';fixture=read(fixture_path);obj={o['name']:o for o in fixture['objects']}
    def mesh(name):
        o=obj[name];return {'name':name,'vertices_world':o['vertices_world'],'faces':o['triangles'],
            'native_triangle_rows':list(range(len(o['triangles']))),'native_vertex_rows':list(range(len(o['vertices_world'])))}
    old=BASE/'s1/warm_diagnostic/cells/G60_1_r3/first_nearest.json';answer=read(old)['value']
    g60={'case_id':'G60_Target_Peer_000','scope':'already-required main-family compound/cache regression, not an additional holdout family',
         'source_kind':'existing actualG60 archived complete world arrays','source':pin(fixture_path),'left':mesh('Target'),'right':mesh('Peer_000'),
         'formal_reference':pin(old),'expected_surface':{'distance_m':answer['distance_m'],'point_a_m':answer['best_known_evidence'][0]['point_a_world'],
             'point_b_m':answer['best_known_evidence'][0]['point_b_world'],'direction_a_to_b':answer['best_known_evidence'][0]['direction_a_to_b']},
         'independent_truth':None}
    path=RAW/'inputs/G60_Target_Peer_000.json';dump(path,g60);cases[g60['case_id']]=pin(path)
    cube=objects['Cube']['evaluated'];verts,faces=subdivide(cube['vertices_world_m'],cube['triangles'])
    def closed(scale,name):return {'name':name,'vertices_world':[[scale*x for x in v] for v in verts],'faces':faces,
        'native_triangle_rows':list(range(len(faces))),'native_vertex_rows':list(range(len(verts)))}
    nested={'case_id':'control_closed_nested_cubes','scope':'control-only analytic closed-shell fixture; no additional real asset family',
        'source_kind':'exact dyadic uniform scaling and shared-edge subdivision of archived Cube',
        'left':closed(.5,'inner_control'),'right':closed(1.,'outer_control'),
        'independent_truth':{'distance_exact_m':'1/2','distance_squared_exact_m2':'1/4','closed_relation':'penetrating',
            'reason':'strict inner closed cube containment gives positive volume intersection, positive surface distance',
            'strict_root_containment_independent':True}}
    path=RAW/'inputs/control_closed_nested_cubes.json';dump(path,nested);cases[nested['case_id']]=pin(path)
    plan={'schema':'m6-043-untimed-holdout-plan-v1','contract':'46ae1484','case_order':list(cases),'cases':cases,
        'arms':{arm:installation(arm) for arm in ('A','B','C')},'timing_samples':False,'Blender':0,'models':0,
        'other_real_family':'Only separately frozen unrotated M4 Obj_014→Obj_003; owned by independent oracle agent, never selected/run here',
        'checks':['direct exact surface/canonical witness','actual integer-root FIFO applicability',
                  'shared spatial+closed+surface route','shared closed+surface route',
                  'successful result reuse and detached result','unknown not cached','one-dyadic reference-translation invalidation'],
        'sources':{p.name:pin(p) for p in HERE.glob('*.py')}}
    dump(RAW/'PLAN.json',plan);print(pin(RAW/'PLAN.json'))


if __name__=='__main__':main()
