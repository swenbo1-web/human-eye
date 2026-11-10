dg=bpy.context.evaluated_depsgraph_get()
geo={}
for obj in scene.objects:
    if obj.type!='MESH': continue
    ev=obj.evaluated_get(dg); mesh=ev.to_mesh(); mesh.calc_loop_triangles()
    local=np.array([v.co[:] for v in mesh.vertices],dtype=np.float64)
    mat=np.array(ev.matrix_world,dtype=np.float64)
    verts=local @ mat[:3,:3].T + mat[:3,3]
    tris=np.array([t.vertices[:] for t in mesh.loop_triangles],dtype=np.int64)
    edges=np.unique(np.sort(np.concatenate([tris[:,[0,1]],tris[:,[1,2]],tris[:,[2,0]]]),axis=1),axis=0)
    geo[obj.name]={'v':verts,'t':tris,'e':edges}
    print(obj.name,'evaluated',len(verts),len(tris),'bounds',verts.min(axis=0).tolist(),verts.max(axis=0).tolist(),'modifiers',[(m.name,m.type) for m in obj.modifiers])
    ev.to_mesh_clear()
