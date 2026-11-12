import bpy, numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
names=['Target','Peer_000','Competing_001','Near_003']
for name in names:
 obj=bpy.data.objects.get(name)
 print(name, 'MISSING' if obj is None else {'type':obj.type,'matrix_world':[list(row) for row in obj.matrix_world],'modifiers':[(mod.name,mod.type) for mod in obj.modifiers]})
print('units',bpy.context.scene.unit_settings.system,bpy.context.scene.unit_settings.scale_length)
depsgraph=bpy.context.evaluated_depsgraph_get()
geo={}
for name in names:
 obj=bpy.data.objects.get(name)
 if obj is None: continue
 evaluated=obj.evaluated_get(depsgraph)
 mesh=evaluated.to_mesh()
 mesh.calc_loop_triangles()
 vertices=np.array([tuple(evaluated.matrix_world @ vert.co) for vert in mesh.vertices],dtype=np.float64)
 triangles=np.array([tuple(tri.vertices) for tri in mesh.loop_triangles],dtype=np.int64)
 geo[name]=(vertices,triangles)
 print(name,'vertices',len(vertices),'triangles',len(triangles),'bounds',vertices.min(axis=0).tolist(),vertices.max(axis=0).tolist())
 evaluated.to_mesh_clear()
