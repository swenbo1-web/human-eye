import numpy as np
from mathutils import Vector
scene=bpy.context.scene
depsgraph=bpy.context.evaluated_depsgraph_get()
geometry={}
for obj in mesh_objects:
    evaluated=obj.evaluated_get(depsgraph)
    mesh=evaluated.to_mesh()
    mesh.calc_loop_triangles()
    matrix=np.array(evaluated.matrix_world,dtype=np.float64)
    vertices=np.array([tuple(vertex.co) for vertex in mesh.vertices],dtype=np.float64)
    vertices=vertices@matrix[:3,:3].T+matrix[:3,3]
    indices=np.array([tuple(triangle.vertices) for triangle in mesh.loop_triangles],dtype=np.int64)
    geometry[obj.name]=(vertices,indices,vertices[indices])
    evaluated.to_mesh_clear()
print('evaluated_triangles',[(name,len(data[2])) for name,data in geometry.items()])
target_vertices=geometry['Target'][0]
target_min=target_vertices.min(axis=0); target_max=target_vertices.max(axis=0)
aabb_bounds=[]
for name,(vertices,indices,triangles) in geometry.items():
    if name=='Target': continue
    gap=np.maximum(np.maximum(vertices.min(axis=0)-target_max,target_min-vertices.max(axis=0)),0)
    aabb_bounds.append((float(np.linalg.norm(gap)),name))
print('target_bounds',target_min.tolist(),target_max.tolist())
print('candidate_aabb_lower_bounds',sorted(aabb_bounds))