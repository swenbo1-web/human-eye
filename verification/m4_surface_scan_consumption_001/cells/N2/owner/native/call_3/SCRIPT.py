scan_meshes=[]
for ob in scene.objects:
    if ob.type!='MESH': continue
    ev=ob.evaluated_get(depsgraph)
    mesh=ev.to_mesh()
    try:
        mesh.calc_loop_triangles()
        vertices=np.array([tuple(v.co) for v in mesh.vertices],dtype=np.float64).reshape((-1,3))
        matrix=np.array(ev.matrix_world,dtype=np.float64)
        vertices=vertices@matrix[:3,:3].T+matrix[:3,3]
        indices=np.array([tuple(tr.vertices) for tr in mesh.loop_triangles],dtype=np.int64).reshape((-1,3))
        triangles=vertices[indices]
        scan_meshes.append({'name':ob.name,'tri':triangles,'lo':triangles.min(axis=1) if len(triangles) else np.empty((0,3)), 'hi':triangles.max(axis=1) if len(triangles) else np.empty((0,3))})
    finally: ev.to_mesh_clear()
print([(item['name'],len(item['tri']),item['lo'].min(axis=0).tolist() if len(item['tri']) else None,item['hi'].max(axis=0).tolist() if len(item['tri']) else None) for item in scan_meshes])
print('triangles',sum(len(item['tri']) for item in scan_meshes))
