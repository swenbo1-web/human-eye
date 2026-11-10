import bpy, numpy as np, math, time
from mathutils import Vector
from mathutils.bvhtree import BVHTree
print('scene', bpy.context.scene.name, 'units', bpy.context.scene.unit_settings.system, bpy.context.scene.unit_settings.scale_length)
for ob in bpy.context.scene.objects:
 if ob.type=='MESH':
  print(ob.name, 'verts',len(ob.data.vertices),'polys',len(ob.data.polygons),'loc',tuple(ob.location),'rot',tuple(ob.rotation_euler),'scale',tuple(ob.scale),'mods',[(m.name,m.type) for m in ob.modifiers])
