import bpy, numpy as np, math, time
from mathutils import Vector
from mathutils.bvhtree import BVHTree
print('scene', bpy.context.scene.name)
objs=[o for o in bpy.context.scene.objects if o.type=='MESH']
print('mesh_count',len(objs))
for o in objs:
 print(o.name, 'verts',len(o.data.vertices),'polys',len(o.data.polygons),'modifiers',[(m.name,m.type) for m in o.modifiers], 'matrix', [list(r) for r in o.matrix_world])