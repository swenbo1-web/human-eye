import bpy, numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
print('units',bpy.context.scene.unit_settings.system,bpy.context.scene.unit_settings.scale_length)
for name in ['Target','Part_A','Part_B','Part_C']:
 obj=bpy.data.objects.get(name)
 print(name, 'MISSING' if obj is None else (obj.type,tuple(obj.location),len(obj.data.vertices) if obj.type=='MESH' else None,[(mod.name,mod.type,mod.show_viewport) for mod in obj.modifiers]))
