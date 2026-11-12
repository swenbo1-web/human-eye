import numpy as np
geo={}
depsgraph=bpy.context.evaluated_depsgraph_get()
for name in names:
 evaluated=bpy.data.objects[name].evaluated_get(depsgraph)
 mesh=evaluated.to_mesh()
 mesh.calc_loop_triangles()
 local=np.array([list(vertex.co) for vertex in mesh.vertices],dtype=np.float64)
 matrix=np.array([list(row) for row in evaluated.matrix_world],dtype=np.float64)
 vertices=local@matrix[:3,:3].T+matrix[:3,3]
 triangles=np.array([list(tri.vertices) for tri in mesh.loop_triangles],dtype=int)
 geo[name]=(vertices,triangles)
 print(name,'vertices',len(vertices),'triangles',len(triangles),'local_bounds',local.min(axis=0),local.max(axis=0),'closed',all(sum(1 for poly in mesh.polygons if edge.vertices[0] in poly.vertices and edge.vertices[1] in poly.vertices)==2 for edge in mesh.edges) if len(mesh.edges)<200 else 'not checked')
 evaluated.to_mesh_clear()
print('target vertices',geo['Target'][0].tolist())