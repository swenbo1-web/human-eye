import bpy, math, numpy as np, time
from mathutils import Vector
from mathutils.bvhtree import BVHTree
print('scene',bpy.context.scene.name,'units',bpy.context.scene.unit_settings.system,bpy.context.scene.unit_settings.scale_length)
for o in bpy.context.scene.objects:
 if o.type=='MESH':
  print(o.name,'verts',len(o.data.vertices),'polys',len(o.data.polygons),'matrix', [list(r) for r in o.matrix_world], 'modifiers',[(m.name,m.type) for m in o.modifiers])
