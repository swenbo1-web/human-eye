import json, math
_v1,_t1 = _consumer_geoms['Object_01']
_v2,_t2 = _consumer_geoms['Object_02']
_x1=max(v[0] for v in _v1)
_x2=min(v[0] for v in _v2)
_face1=[{'triangle':i,'vertices':[list(_v1[j]) for j in t]} for i,t in enumerate(_t1) if all(abs(_v1[j][0]-_x1)<1e-12 for j in t)]
_face2=[{'triangle':i,'vertices':[list(_v2[j]) for j in t]} for i,t in enumerate(_t2) if all(abs(_v2[j][0]-_x2)<1e-12 for j in t)]
print(json.dumps({'x_gap_lower_bound_m':_x2-_x1,'surface_witness_01':[_x1,0.0,0.0],'surface_witness_02':[_x2,0.0,0.0],'distance_m':_x2-_x1,'unit_direction_01_to_02':[1.0,0.0,0.0],'opposing_surface_triangles_01':_face1,'opposing_surface_triangles_02':_face2}))
