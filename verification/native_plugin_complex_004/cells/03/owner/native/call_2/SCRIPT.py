import bpy, numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
names=['Object_01','Object_02','Object_03','Object_04']
for name in names:
 o=bpy.data.objects.get(name)
 if o is None: print(name,'MISSING'); continue
 print(name,'type',o.type,'matrix_world',list(map(list,o.matrix_world)),'vertices',len(o.data.vertices) if o.type=='MESH' else None,'polygons',len(o.data.polygons) if o.type=='MESH' else None,'modifiers',[(m.name,m.type) for m in o.modifiers])
print('units',bpy.context.scene.unit_settings.system,bpy.context.scene.unit_settings.scale_length)
