import bpy, numpy as np, time
from mathutils import Vector
from mathutils.bvhtree import BVHTree
objs=[o for o in bpy.context.scene.objects if o.type=='MESH']
print('mesh_count',len(objs))
print([(o.name,len(o.data.vertices),len(o.data.polygons)) for o in objs])
print('target',bpy.data.objects.get('Target'))