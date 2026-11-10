import bpy, math, numpy as np, time
from mathutils import Vector
from mathutils.bvhtree import BVHTree
print('scene',bpy.context.scene.name,'units',bpy.context.scene.unit_settings.system,bpy.context.scene.unit_settings.scale_length)
for ob in bpy.context.scene.objects:
 print(ob.name, ob.type, 'verts',len(ob.data.vertices) if ob.type=='MESH' else None,'polys',len(ob.data.polygons) if ob.type=='MESH' else None,'matrix', [list(r) for r in ob.matrix_world], 'mods',[(m.name,m.type) for m in ob.modifiers])