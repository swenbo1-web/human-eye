import bpy, numpy as np, math, time
from mathutils import Vector
from mathutils.bvhtree import BVHTree
print([(o.name,o.type) for o in bpy.context.scene.objects])
for name in ['Object_01','Object_02','Object_03','Object_04']:
 o=bpy.data.objects.get(name)
 if o:
  print(name,'matrix', [list(r) for r in o.matrix_world], 'verts',len(o.data.vertices) if o.type=='MESH' else None,'polys',len(o.data.polygons) if o.type=='MESH' else None,'modifiers',[(m.name,m.type) for m in o.modifiers])