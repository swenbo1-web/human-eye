import bpy, numpy as np, time
from mathutils import Vector
from mathutils.bvhtree import BVHTree
start_time=time.time()
mesh_objects=[obj for obj in bpy.context.scene.objects if obj.type=='MESH']
print('mesh_count',len(mesh_objects))
print([(obj.name,len(obj.data.vertices),len(obj.data.polygons),len(obj.modifiers)) for obj in mesh_objects])
print('target_exists',any(obj.name=='Target' for obj in mesh_objects))