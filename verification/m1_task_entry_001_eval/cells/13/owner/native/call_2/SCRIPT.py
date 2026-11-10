import bpy, numpy as np, math, time
from mathutils import Vector
from mathutils.bvhtree import BVHTree
start_time=time.time()
scene=bpy.context.scene
print('units',scene.unit_settings.system,scene.unit_settings.scale_length)
print('meshes',[(o.name,len(o.data.vertices),len(o.data.polygons),o.hide_viewport,o.hide_render) for o in scene.objects if o.type=='MESH'])
print('target',bpy.data.objects.get('Mesh_DDBB95'))