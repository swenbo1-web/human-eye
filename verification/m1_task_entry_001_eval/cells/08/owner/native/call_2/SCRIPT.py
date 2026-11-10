import bpy, math, time
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
start_time=time.time()
scene=bpy.context.scene
target=bpy.data.objects.get('Mesh_DDBB95')
print('units',scene.unit_settings.system,scene.unit_settings.scale_length)
print('target',target.name if target else None)
print('meshes',[(o.name,len(o.data.vertices),len(o.data.polygons)) for o in scene.objects if o.type=='MESH'])