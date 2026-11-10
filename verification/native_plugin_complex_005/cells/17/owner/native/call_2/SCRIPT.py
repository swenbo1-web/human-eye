import bpy, numpy as np, time
from mathutils import Vector
from mathutils.bvhtree import BVHTree
scene=bpy.context.scene
meshes=[o for o in scene.objects if o.type=='MESH']
print('mesh_count',len(meshes))
print([(o.name,len(o.data.vertices),len(o.data.polygons)) for o in meshes])
print('unit',scene.unit_settings.system,scene.unit_settings.scale_length)
