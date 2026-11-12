import bpy, numpy as np, math, time
from mathutils import Vector
from mathutils.bvhtree import BVHTree
scene=bpy.context.scene
depsgraph=bpy.context.evaluated_depsgraph_get()
objs=[o for o in scene.objects if o.type=='MESH']
print('units',scene.unit_settings.system,scene.unit_settings.scale_length)
print('mesh_count',len(objs))
for o in objs:
 print(repr(o.name), 'hide',o.hide_get(),o.hide_render,'modifiers',[(m.name,m.type,m.show_viewport) for m in o.modifiers])