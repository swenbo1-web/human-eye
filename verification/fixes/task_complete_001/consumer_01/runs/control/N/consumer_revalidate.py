import bpy, json, hashlib
_previous = dict(_consumer_geoms)
bpy.context.view_layer.update()
_dg_now = bpy.context.evaluated_depsgraph_get()
_dg_now.update()
_validation = []
for _name in ['Object_01','Object_02']:
    _obj = bpy.data.objects[_name]
    _ev = _obj.evaluated_get(_dg_now)
    _mesh = _ev.to_mesh()
    _mesh.calc_loop_triangles()
    _verts = [tuple(_ev.matrix_world @ v.co) for v in _mesh.vertices]
    _tris = [tuple(t.vertices) for t in _mesh.loop_triangles]
    _consumer_geoms[_name] = (_verts,_tris)
    _raw = [tuple(_obj.matrix_world @ v.co) for v in _obj.data.vertices]
    _validation.append({'name':_name,'current_equals_precheck_cache':(_verts,_tris)==_previous[_name],'original_equals_evaluated_vertices':_raw==_verts,'geometry_sha256':hashlib.sha256(repr((_verts,_tris)).encode()).hexdigest(),'triangle_indices':_tris,'local_object_location':list(_obj.location)})
    _ev.to_mesh_clear()
_v1,_t1 = _consumer_geoms['Object_01']
_v2,_t2 = _consumer_geoms['Object_02']
_x1=max(v[0] for v in _v1)
_x2=min(v[0] for v in _v2)
_faces1=[i for i,t in enumerate(_t1) if all(abs(_v1[j][0]-_x1)<1e-12 for j in t)]
_faces2=[i for i,t in enumerate(_t2) if all(abs(_v2[j][0]-_x2)<1e-12 for j in t)]
print(json.dumps({'revalidation':_validation,'x_gap_m':_x2-_x1,'surface_witness_01':[_x1,0.,0.],'surface_witness_02':[_x2,0.,0.],'opposing_triangles_01':_faces1,'opposing_triangles_02':_faces2}))
