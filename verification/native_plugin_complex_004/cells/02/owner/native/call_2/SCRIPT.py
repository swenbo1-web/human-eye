import bpy, math, numpy as np
from mathutils import Vector
objs = [bpy.data.objects.get('Object_%02d'%index) for index in range(1,5)]
for obj in objs:
    if obj is None: print('MISSING'); continue
    print(obj.name, 'type', obj.type, 'matrix', [list(row) for row in obj.matrix_world], 'vertices',len(obj.data.vertices) if obj.type=='MESH' else None,'polygons',len(obj.data.polygons) if obj.type=='MESH' else None, 'modifiers',[(mod.name,mod.type) for mod in obj.modifiers])
print('units',bpy.context.scene.unit_settings.system,bpy.context.scene.unit_settings.scale_length)
