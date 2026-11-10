depsgraph=bpy.context.evaluated_depsgraph_get()
mesh_cache={}
for obj in scene.objects:
    if obj.type!='MESH': continue
    evaluated=obj.evaluated_get(depsgraph)
    mesh=evaluated.to_mesh()
    mesh.calc_loop_triangles()
    local=np.array([tuple(v.co) for v in mesh.vertices],dtype=np.float64)
    matrix=np.array(evaluated.matrix_world,dtype=np.float64)
    verts=local @ matrix[:3,:3].T + matrix[:3,3]
    indices=np.array([tuple(tri.vertices) for tri in mesh.loop_triangles],dtype=int)
    mesh_cache[obj.name]={'verts':verts,'indices':indices,'triangles':verts[indices]}
    evaluated.to_mesh_clear()
    print(obj.name,'triangles',len(indices),'bounds_m',verts.min(axis=0).tolist(),verts.max(axis=0).tolist(),'modifiers',[(m.name,m.type) for m in obj.modifiers])
print('mm_per_unit',scene.unit_settings.scale_length*1000)
