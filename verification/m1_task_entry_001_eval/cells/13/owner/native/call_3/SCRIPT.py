depsgraph=bpy.context.evaluated_depsgraph_get()
geometry={}
for obj in scene.objects:
 if obj.type!='MESH': continue
 evaluated=obj.evaluated_get(depsgraph)
 mesh=evaluated.to_mesh()
 mesh.calc_loop_triangles()
 vertices=np.array([tuple(v.co) for v in mesh.vertices],dtype=np.float64)
 matrix=np.array(evaluated.matrix_world,dtype=np.float64)
 vertices=vertices@matrix[:3,:3].T+matrix[:3,3]
 triangles=np.array([tuple(t.vertices) for t in mesh.loop_triangles],dtype=np.int64)
 geometry[obj.name]=(vertices,triangles)
 print(obj.name,'vertices',len(vertices),'triangles',len(triangles),'bounds',vertices.min(axis=0).tolist(),vertices.max(axis=0).tolist(),'modifiers',[(m.name,m.type) for m in obj.modifiers])
 evaluated.to_mesh_clear()
