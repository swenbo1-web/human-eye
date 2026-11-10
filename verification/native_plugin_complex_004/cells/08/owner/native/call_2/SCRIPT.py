import bpy, numpy as np, math, time
from mathutils import Vector
from mathutils.bvhtree import BVHTree
print('scene',bpy.context.scene.name)
print([(o.name,o.type,len(o.data.vertices) if o.type=='MESH' else None,len(o.data.polygons) if o.type=='MESH' else None) for o in bpy.context.scene.objects])
print('target',bpy.context.scene.objects.get('Target'))