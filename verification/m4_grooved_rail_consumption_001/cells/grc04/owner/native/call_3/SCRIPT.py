import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
depsgraph=bpy.context.evaluated_depsgraph_get()
geometry={}
for name in ('Target','Part_A','Part_B','Part_C'):
    evaluated=bpy.data.objects[name].evaluated_get(depsgraph)
    mesh=evaluated.to_mesh()
    mesh.calc_loop_triangles()
    vertices=np.array([tuple(evaluated.matrix_world @ vertex.co) for vertex in mesh.vertices], dtype=np.float64)
    triangles=np.array([tuple(triangle.vertices) for triangle in mesh.loop_triangles],dtype=np.int64)
    geometry[name]=(vertices,triangles)
    print(name, 'vertices',len(vertices),'triangles',len(triangles),'bounds',vertices.min(axis=0).tolist(),vertices.max(axis=0).tolist())
    evaluated.to_mesh_clear()
print('unit_settings',bpy.context.scene.unit_settings.system,bpy.context.scene.unit_settings.scale_length)
