"""Certify T2 from saved evaluated geometry using exact boundary coverage."""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
from exact_geometry import (read_meshes,closed_boundary,box_patches,box_pair,
    contains_triangle,decimal_sqrt,encoded,dot,vector_sub)

p=argparse.ArgumentParser()
p.add_argument('--spec',required=True);p.add_argument('--snapshot',required=True);p.add_argument('--output',required=True)
args=p.parse_args()
spec=json.loads(Path(args.spec).read_bytes())
data,meshes=read_meshes(args.snapshot)
names=spec['object_names'];scale=F(spec['construction_scale_m'])
assert set(meshes)==set(names.values()) and spec['task']=='T2'
cells=[(tuple(F(v)*scale for v in low),tuple(F(v)*scale for v in high)) for low,high in spec['target_cells_base']]
patches=[]
for low,high in cells:
    for z in (low[2],high[2]): patches.append((2,z,low[:2],high[:2]))
poly=[tuple(F(v)*scale for v in point) for point in spec['polygon_base']]
for a,b in zip(poly,poly[1:]+poly[:1]):
    axis=0 if a[0]==b[0] else 1
    other=1-axis
    patches.append((axis,a[axis],(min(a[other],b[other]),-scale),(max(a[other],b[other]),scale)))
volume=sum((high[0]-low[0])*(high[1]-low[1])*(high[2]-low[2]) for low,high in cells)
target=meshes[names['target']]
certificate=closed_boundary(target,patches,volume)
assert certificate['vertices']==58 and certificate['triangles']==112
rows=[]
for role,(base_low,base_high) in spec['candidate_boxes_base'].items():
    low,high=tuple(F(v)*scale for v in base_low),tuple(F(v)*scale for v in base_high)
    mesh=meshes[names[role]]
    cert=closed_boundary(mesh,box_patches(low,high),(high[0]-low[0])*(high[1]-low[1])*(high[2]-low[2]))
    assert cert['vertices']==8 and cert['triangles']==12
    choices=[box_pair(cell,(low,high)) for cell in cells]
    distance2,point_a,point_b=min(choices,key=lambda row:row[0])
    assert distance2>0
    tri_a,tri_b=contains_triangle(target,point_a),contains_triangle(mesh,point_b)
    assert dot(vector_sub(point_a,point_b),vector_sub(point_a,point_b))==distance2
    rows.append({'object':names[role],'role_private':role,'distance_squared_m2':distance2,
        'distance_m_decimal90':decimal_sqrt(distance2),'volume_cells_checked':len(choices),
        'all_cell_lower_bounds_squared':[row[0] for row in choices],
        'surface_witness':{'target':point_a,'candidate':point_b,'actual_triangle_indices':[tri_a,tri_b]},
        'boundary_certificate':cert})
ranked=sorted(rows,key=lambda row:row['distance_squared_m2'])
assert ranked[0]['role_private']=='east' and ranked[0]['distance_squared_m2']==F(1,256)**2
assert all(row['distance_squared_m2']>ranked[0]['distance_squared_m2'] for row in ranked[1:])
center_rank=sorted(rows,key=lambda row:dot(vector_sub(meshes[row['object']]['origin'],target['origin']),vector_sub(meshes[row['object']]['origin'],target['origin'])))
assert center_rank[0]['role_private']=='void' and center_rank[0]['object']!=ranked[0]['object']
out={'task':'T2','method':'exact rational complete surface coverage + distance to three disjoint-interior rectangular volume cells; actual evaluated triangle witnesses',
    'source_asset_sha256':data['source_asset_sha256'],'evaluated_mesh_sha256':hashlib.sha256(Path(args.snapshot).read_bytes()).hexdigest(),
    'all_candidates_covered':True,'candidate_count':len(rows),'target_certificate':certificate,
    'candidates':rows,'target':names['target'],'nearest_objects':[ranked[0]['object']],
    'distance_squared_m2':ranked[0]['distance_squared_m2'],'distance_m':'1/256','distance_mm':'3.90625',
    'unique_winner_margin_squared_m2':ranked[1]['distance_squared_m2']-ranked[0]['distance_squared_m2'],
    'naive_origin_center_nearest':center_rank[0]['object'],
    'potential_triangle_pairs':sum(len(target['faces'])*len(meshes[row['object']]['faces']) for row in rows),
    'scope':'global unsigned triangle-surface distance; not penetration depth',
    'suggested_answer_tolerance_m':'1/100000'}
with Path(args.output).open('x',encoding='utf8') as stream: json.dump(encoded(out),stream,indent=2,sort_keys=True);stream.write('\n')
print(json.dumps({'certified':True,'task':'T2','candidates':len(rows),'geometry_only_no_product':True}))
