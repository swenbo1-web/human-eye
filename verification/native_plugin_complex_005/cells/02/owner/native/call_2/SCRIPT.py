import bpy, numpy as np, math, time
from mathutils import Vector
from mathutils.bvhtree import BVHTree
objs={n:bpy.data.objects.get(n) for n in ['Object_01','Object_02','Object_03','Object_04']}
for n,o in objs.items():
 print(n, 'missing' if o is None else {'type':o.type,'loc':list(o.location),'rot':list(o.rotation_euler),'scale':list(o.scale),'matrix':[list(r) for r in o.matrix_world],'vertices':len(o.data.vertices) if o.type=='MESH' else None,'polygons':len(o.data.polygons) if o.type=='MESH' else None,'modifiers':[(m.name,m.type) for m in o.modifiers]})
print('units',bpy.context.scene.unit_settings.system,bpy.context.scene.unit_settings.scale_length)