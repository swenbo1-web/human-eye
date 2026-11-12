import bpy, numpy as np, math, time
from mathutils import Vector
from mathutils.bvhtree import BVHTree
scene=bpy.context.scene
depsgraph=bpy.context.evaluated_depsgraph_get()
print('units',scene.unit_settings.system,scene.unit_settings.scale_length)
objs=[o for o in scene.objects if o.type=='MESH']
print('mesh_count',len(objs))
scan=[]
for obj in objs:
    evaluated=obj.evaluated_get(depsgraph)
    mesh=evaluated.to_mesh()
    mesh.calc_loop_triangles()
    vertices=np.array([tuple(evaluated.matrix_world @ vertex.co) for vertex in mesh.vertices],dtype=np.float64).reshape(-1,3)
    indices=np.array([tuple(triangle.vertices) for triangle in mesh.loop_triangles],dtype=np.int64).reshape(-1,3)
    triangles=vertices[indices]
    scan.append({'name':obj.name,'vertices':vertices,'indices':indices,'triangles':triangles})
    print(obj.name, 'verts',len(vertices),'tris',len(triangles),'bounds', (vertices.min(axis=0).tolist(),vertices.max(axis=0).tolist()) if len(vertices) else None)
    evaluated.to_mesh_clear()
