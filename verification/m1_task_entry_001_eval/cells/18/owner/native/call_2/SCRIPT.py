import bpy, numpy as np, time
from mathutils.bvhtree import BVHTree
names=['Part_49','Part_17','Part_26','Part_38']
print('units',bpy.context.scene.unit_settings.system,bpy.context.scene.unit_settings.scale_length)
for name in names:
 o=bpy.data.objects.get(name)
 print(name, None if o is None else (o.type,len(o.data.vertices),len(o.data.polygons),list(o.matrix_world.translation),list(o.dimensions)))
