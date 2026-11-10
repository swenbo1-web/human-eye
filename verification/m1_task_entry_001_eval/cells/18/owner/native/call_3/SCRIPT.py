dg=bpy.context.evaluated_depsgraph_get()
meshes={}
for name in names:
 obj=bpy.data.objects[name].evaluated_get(dg); mesh=obj.to_mesh(); mesh.calc_loop_triangles()
 verts=np.array([tuple(obj.matrix_world @ vert.co) for vert in mesh.vertices],dtype=np.float64)
 tris=np.array([tuple(tri.vertices) for tri in mesh.loop_triangles],dtype=int)
 meshes[name]=(verts,tris)
 obj.to_mesh_clear()
 print(name,'bounds',verts.min(axis=0),verts.max(axis=0),'tris',len(tris),'unique verts',len(np.unique(verts,axis=0)))
 print('coordinates',*[np.unique(verts[:,axis]).tolist() for axis in range(3)])
