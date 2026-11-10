import bpy, numpy as np, math
from mathutils import Vector
from mathutils.bvhtree import BVHTree
objs={n:bpy.data.objects.get(n) for n in ['Object_01','Object_02','Object_03','Object_04']}
for n,o in objs.items():
 print(n, 'type',o.type if o else None)
 if o:
  print('matrix', [list(r) for r in o.matrix_world], 'verts',len(o.data.vertices),'faces',len(o.data.polygons),'modifiers',[(m.name,m.type) for m in o.modifiers])
  print('bounds', [list(o.matrix_world@Vector(v)) for v in o.bound_box])
