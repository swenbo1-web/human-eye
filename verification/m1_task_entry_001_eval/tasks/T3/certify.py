"""Independent T3 support-plane/equality-set proof on actual evaluated mesh."""
from collections import Counter
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
from exact_geometry import read_meshes,contains_triangle,encoded,decimal_sqrt,dot,vector_sub,cross


def ribbon(mesh,plane,axis,fixed_axis,fixed_value,length,below=False):
    vertices,faces=mesh['vertices'],mesh['faces']
    assert len(vertices)==40 and len(faces)==56
    assert all(v[2]<=plane if below else v[2]>=plane for v in vertices)
    zeros=[v for v in vertices if v[2]==plane]
    assert len(zeros)==8 and all(v[fixed_axis]==fixed_value and -length<=v[axis]<=length for v in zeros)
    assert all(v[axis]!=0 for v in zeros)
    intervals=[]
    directions=set()
    edges=Counter(tuple(sorted((a,b))) for face in faces for a,b in zip(face,face[1:]+face[:1]))
    assert set(edges.values())<={1,2} and any(count==1 for count in edges.values())
    for face in faces:
        tri=[vertices[i] for i in face]
        normal=cross(vector_sub(tri[1],tri[0]),vector_sub(tri[2],tri[0]))
        first=next(v for v in normal if v!=0)
        directions.add(tuple(v/first for v in normal))
        contact=[v for v in tri if v[2]==plane]
        assert len(contact)<3
        if len(contact)==2: intervals.append(tuple(sorted(v[axis] for v in contact)))
    assert len(directions)>=3
    cursor=-length
    for low,high in sorted(intervals):
        assert low<=cursor and high>=low
        cursor=max(cursor,high)
    assert cursor==length
    return {'vertices':40,'triangles':56,'open_manifold_edges':dict(Counter(edges.values())),
        'distinct_plane_normal_directions':len(directions),'support_plane_z':plane,
        'support_line_variable_axis':axis,'support_line_fixed_axis':fixed_axis,
        'support_line_fixed_value':fixed_value,'support_line_interval':[-length,length],
        'actual_support_edges':intervals,'complete_zero_plane_set_certified':True}


p=argparse.ArgumentParser()
p.add_argument('--spec',required=True);p.add_argument('--snapshot',required=True);p.add_argument('--output',required=True)
args=p.parse_args()
spec=json.loads(Path(args.spec).read_bytes())
data,meshes=read_meshes(args.snapshot)
names=spec['object_names'];delta=F(spec['gap_m']);length=F(spec['construction_scale_m'])
assert set(meshes)==set(names.values()) and spec['task']=='T3'
target=meshes[names['target']]
assert all(-length<=v[0]<=length and v[1]<=0 for v in target['vertices'])
target_cert=ribbon(target,F(0),0,1,F(0),length,below=True)
rows=[]
for role in ('cross','right','left','front','upper'):
    mesh=meshes[names[role]]
    plane=3*delta/2 if role=='upper' else delta
    if role in ('cross','upper'):
        cert=ribbon(mesh,plane,1,0,F(0),length)
        lower=plane*plane
        a,b=(F(0),F(0),F(0)),(F(0),F(0),plane)
        reason='z separation; equality contact lines intersect at exactly x=y=0'
    elif role=='right':
        c=length+delta/2
        cert=ribbon(mesh,plane,1,0,c,length)
        assert all(v[0]>=c for v in mesh['vertices'])
        lower=delta*delta+(delta/2)**2
        a,b=(length,F(0),F(0)),(c,F(0),delta)
        reason='independent x and z halfspace gaps; actual edge witnesses attain their squared sum'
    elif role=='left':
        c=-length-3*delta/4
        cert=ribbon(mesh,plane,1,0,c,length)
        assert all(v[0]<=c for v in mesh['vertices'])
        lower=delta*delta+(3*delta/4)**2
        a,b=(-length,F(0),F(0)),(c,F(0),delta)
        reason='independent negative-x and z halfspace gaps; actual edge witnesses attain their squared sum'
    else:
        c=delta/2
        cert=ribbon(mesh,plane,0,1,c,length)
        assert all(v[1]>=c for v in mesh['vertices'])
        lower=delta*delta+c*c
        a,b=(F(0),F(0),F(0)),(F(0),c,delta)
        reason='independent y and z halfspace gaps; actual edge witnesses attain their squared sum'
    assert dot(vector_sub(a,b),vector_sub(a,b))==lower
    face_a,face_b=contains_triangle(target,a),contains_triangle(mesh,b)
    minimum_vertex2=min(dot(vector_sub(x,y),vector_sub(x,y)) for x in target['vertices'] for y in mesh['vertices'])
    assert minimum_vertex2>delta*delta
    rows.append({'object':names[role],'role_private':role,'distance_squared_m2':lower,
        'distance_m_decimal90':decimal_sqrt(lower),'proof':reason,'support_certificate':cert,
        'actual_surface_witness':{'target':a,'candidate':b,'actual_triangle_indices':[face_a,face_b]},
        'minimum_all_vertex_pairs_squared_m2':minimum_vertex2,
        'all_vertex_pairs_strictly_farther_than_global_winner':True})
ranked=sorted(rows,key=lambda row:row['distance_squared_m2'])
assert ranked[0]['role_private']=='cross' and ranked[0]['distance_squared_m2']==delta*delta
assert all(row['distance_squared_m2']>delta*delta for row in ranked[1:])
winner=meshes[names['cross']]
assert (F(0),F(0),F(0)) not in target['vertices']
assert (F(0),F(0),delta) not in winner['vertices']
out={'task':'T3','method':'exact rational supporting halfspaces + complete equality-line sets + actual triangle membership; no production solver',
    'source_asset_sha256':data['source_asset_sha256'],'evaluated_mesh_sha256':hashlib.sha256(Path(args.snapshot).read_bytes()).hexdigest(),
    'all_candidates_covered':True,'candidate_count':5,'target_certificate':target_cert,
    'candidates':rows,'target':names['target'],'nearest_objects':[names['cross']],
    'distance_squared_m2':delta*delta,'distance_m':str(delta),'distance_mm':'7.8125',
    'unique_winner_margin_squared_m2':ranked[1]['distance_squared_m2']-delta*delta,
    'unique_closest_point_pair':[[F(0),F(0),F(0)],[F(0),F(0),delta]],
    'closest_points_are_edge_interiors_not_vertices':True,
    'minimum_all_winning_vertex_pairs_squared_m2':ranked[0]['minimum_all_vertex_pairs_squared_m2'],
    'potential_triangle_pairs':len(target['faces'])*sum(len(meshes[names[role]]['faces']) for role in names if role!='target'),
    'scope':'global unsigned triangle-surface distance on open folded surfaces; not a solid or penetration claim',
    'suggested_answer_tolerance_m':'1/100000'}
with Path(args.output).open('x',encoding='utf8') as stream: json.dump(encoded(out),stream,indent=2,sort_keys=True);stream.write('\n')
print(json.dumps({'certified':True,'task':'T3','candidates':5,'geometry_only_no_product':True}))
