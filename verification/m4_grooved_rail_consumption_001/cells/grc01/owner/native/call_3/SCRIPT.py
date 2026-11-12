dg=bpy.context.evaluated_depsgraph_get()
geom={}
for name in ['Target','Part_A','Part_B','Part_C']:
 obj=bpy.data.objects[name].evaluated_get(dg)
 mesh=obj.to_mesh();mesh.calc_loop_triangles()
 matrix=np.array(obj.matrix_world,dtype=np.float64)
 verts=np.array([tuple(v.co) for v in mesh.vertices],dtype=np.float64)
 verts=verts@matrix[:3,:3].T+matrix[:3,3]
 tris=np.array([tuple(t.vertices) for t in mesh.loop_triangles],dtype=int)
 geom[name]=(verts,tris)
 print(name,'world vertices',verts.tolist(),'triangles',tris.tolist())
 print('edges',[(tuple(edge.vertices),edge.is_loose) for edge in mesh.edges])
 obj.to_mesh_clear()
