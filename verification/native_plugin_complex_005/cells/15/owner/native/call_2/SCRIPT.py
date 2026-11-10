import bpy, math, numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
objs={n:bpy.data.objects.get(n) for n in ['Object_01','Object_02','Object_03','Object_04']}
for n,o in objs.items():
 print(n, None if o is None else {'type':o.type,'matrix': [list(r) for r in o.matrix_world], 'vertices': len(o.data.vertices) if o.type=='MESH' else None,'polygons':len(o.data.polygons) if o.type=='MESH' else None,'modifiers':[(m.name,m.type) for m in o.modifiers]})