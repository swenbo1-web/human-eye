import bpy, numpy as np, math
from mathutils import Vector
from mathutils.bvhtree import BVHTree
names=['Object_01','Object_02','Object_03','Object_04']
for name in names:
 obj=bpy.data.objects.get(name)
 if obj is None: print(name,'MISSING'); continue
 print(name, 'type',obj.type,'matrix', [list(row) for row in obj.matrix_world], 'modifiers',[(m.name,m.type) for m in obj.modifiers])
 if obj.type=='MESH': print('mesh',len(obj.data.vertices),len(obj.data.polygons),'bbox world',[tuple(obj.matrix_world @ Vector(c)) for c in obj.bound_box])
print('units',bpy.context.scene.unit_settings.system,bpy.context.scene.unit_settings.scale_length)
