import bpy, numpy as np, math, time
from mathutils import Vector
from mathutils.bvhtree import BVHTree
print('scene',bpy.context.scene.name,'units',bpy.context.scene.unit_settings.system,bpy.context.scene.unit_settings.scale_length)
for obj in bpy.context.scene.objects:
 print(obj.name,obj.type,'loc',tuple(obj.location),'rot',tuple(obj.rotation_euler),'scale',tuple(obj.scale),'verts',len(obj.data.vertices) if obj.type=='MESH' else None,'polys',len(obj.data.polygons) if obj.type=='MESH' else None,'mods',[(m.name,m.type) for m in obj.modifiers])
