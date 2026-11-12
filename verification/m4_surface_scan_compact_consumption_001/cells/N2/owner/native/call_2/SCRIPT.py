import bpy, numpy as np, math, time
from mathutils import Vector
from mathutils.bvhtree import BVHTree
scene=bpy.context.scene
depsgraph=bpy.context.evaluated_depsgraph_get()
objs=[o for o in scene.objects if o.type=='MESH']
print('UNIT',scene.unit_settings.system,scene.unit_settings.scale_length)
print('MESH_COUNT',len(objs))
for o in objs:
 print(repr(o.name),'verts',len(o.data.vertices),'polys',len(o.data.polygons),'mods',[(m.type,m.show_viewport) for m in o.modifiers],'hidden',o.hide_get(),o.hide_viewport)
