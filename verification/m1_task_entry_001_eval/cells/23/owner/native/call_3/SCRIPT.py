depsgraph=bpy.context.evaluated_depsgraph_get()
geo={}
for name in names:
 obj=bpy.data.objects[name]; ev=obj.evaluated_get(depsgraph); mesh=ev.to_mesh(); mesh.calc_loop_triangles()
 local=np.array([v.co[:] for v in mesh.vertices],dtype=np.float64)
 mat=np.array(ev.matrix_world,dtype=np.float64)
 verts=local@mat[:3,:3].T+mat[:3,3]
 faces=np.array([t.vertices[:] for t in mesh.loop_triangles],dtype=int)
 geo[name]=(verts,faces)
 edges={}
 for f in faces:
  for i,j in ((f[0],f[1]),(f[1],f[2]),(f[2],f[0])):
   edge=tuple(sorted((int(i),int(j))));edges[edge]=edges.get(edge,0)+1
 print(name,'bounds_mm',verts.min(axis=0)*1000,verts.max(axis=0)*1000,'triangles',len(faces),'nonmanifold_edges',sum(count!=2 for count in edges.values()),'modifiers',[(m.name,m.type) for m in obj.modifiers])
 ev.to_mesh_clear()
print('target_local_vertices',np.array([v.co[:] for v in bpy.data.objects['Part_49'].data.vertices]))