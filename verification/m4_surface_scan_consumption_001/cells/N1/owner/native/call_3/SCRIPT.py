deps=bpy.context.evaluated_depsgraph_get()
meshes=[]
for obj in scene.objects:
    if obj.type!='MESH': continue
    evaluated=obj.evaluated_get(deps)
    mesh=evaluated.to_mesh()
    try:
        mesh.calc_loop_triangles()
        world=np.array([list(evaluated.matrix_world @ vert.co) for vert in mesh.vertices],dtype=np.float64)*float(scene.unit_settings.scale_length)*1000.0
        indices=np.array([list(tri.vertices) for tri in mesh.loop_triangles],dtype=np.int64)
        triangles=world[indices] if len(indices) else np.empty((0,3,3))
        meshes.append(dict(name=obj.name,tri=triangles,lo=triangles.min(axis=(0,1)) if len(triangles) else None,hi=triangles.max(axis=(0,1)) if len(triangles) else None))
    finally:
        evaluated.to_mesh_clear()
print('evaluated_triangles',[(entry['name'],len(entry['tri'])) for entry in meshes])
candidates=[];excluded=[]
for first in range(len(meshes)):
    for second in range(first+1,len(meshes)):
        a,b=meshes[first],meshes[second]
        if a['lo'] is None or b['lo'] is None: continue
        lower=float(np.linalg.norm(np.maximum(np.maximum(a['lo']-b['hi'],b['lo']-a['hi']),0)))
        (candidates if lower<=2.000000001 else excluded).append((first,second,lower))
print('object_pairs',len(meshes)*(len(meshes)-1)//2,'candidates',len(candidates),'excluded',len(excluded))
print('candidate_names',[(meshes[a]['name'],meshes[b]['name'],round(d,9)) for a,b,d in candidates])
print('instances_detail',[(i.object.name,i.is_instance) for i in deps.object_instances])