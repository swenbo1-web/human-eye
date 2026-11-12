import bpy, numpy as np, math, time
from mathutils import Vector
from mathutils.bvhtree import BVHTree
scene=bpy.context.scene
print('units',scene.unit_settings.system,scene.unit_settings.scale_length)
print('mesh_objects',[(o.name,len(o.data.vertices),len(o.data.polygons),o.hide_get(),o.hide_render) for o in scene.objects if o.type=='MESH'])
print('instances',len(list(bpy.context.evaluated_depsgraph_get().object_instances)))