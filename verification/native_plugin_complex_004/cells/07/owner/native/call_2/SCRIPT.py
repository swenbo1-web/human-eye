import bpy, numpy as np, math, time
from mathutils import Vector
scene=bpy.context.scene
print('scene',scene.name,'units',scene.unit_settings.system,scene.unit_settings.scale_length)
meshes=[o for o in scene.objects if o.type=='MESH']
print('mesh_count',len(meshes))
for o in meshes:
 print(o.name, len(o.data.vertices),len(o.data.polygons), 'mods',len(o.modifiers))