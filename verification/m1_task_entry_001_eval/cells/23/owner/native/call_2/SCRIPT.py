import bpy, math, time
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
names=['Part_49','Part_17','Part_26','Part_38']
print('units',bpy.context.scene.unit_settings.system,bpy.context.scene.unit_settings.scale_length)
for name in names:
 obj=bpy.data.objects.get(name)
 print(name, None if obj is None else (obj.type,len(obj.data.vertices),len(obj.data.polygons),[list(v) for v in obj.matrix_world],list(obj.dimensions)))