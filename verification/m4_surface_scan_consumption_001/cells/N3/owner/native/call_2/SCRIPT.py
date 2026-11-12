import bpy, math, numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
scene=bpy.context.scene
depsgraph=bpy.context.evaluated_depsgraph_get()
print('units',scene.unit_settings.system,scene.unit_settings.scale_length)
objs=[o for o in scene.objects if o.type=='MESH']
print('mesh_objects',len(objs))
for o in objs:
 print(o.name, 'verts',len(o.data.vertices),'polygons',len(o.data.polygons),'modifiers',[(m.name,m.type,m.show_viewport) for m in o.modifiers])