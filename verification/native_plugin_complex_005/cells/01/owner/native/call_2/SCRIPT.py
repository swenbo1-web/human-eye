import bpy, numpy as np, math, time
from mathutils import Vector
from mathutils.bvhtree import BVHTree
print('scene',bpy.context.scene.name,'units',bpy.context.scene.unit_settings.system,bpy.context.scene.unit_settings.scale_length)
for obj in bpy.context.scene.objects:
 print(obj.name,obj.type,'verts',len(obj.data.vertices) if obj.type=='MESH' else None,'polys',len(obj.data.polygons) if obj.type=='MESH' else None,'matrix', [list(row) for row in obj.matrix_world], 'modifiers',[(mod.name,mod.type) for mod in obj.modifiers])