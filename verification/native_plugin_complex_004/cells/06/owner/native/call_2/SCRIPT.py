import bpy, math, time
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
scene=bpy.context.scene
deps=bpy.context.evaluated_depsgraph_get()
objs=[o for o in scene.objects if o.type=='MESH']
print('mesh_count',len(objs))
for o in objs:
 print(o.name,'vertices',len(o.data.vertices),'polygons',len(o.data.polygons),'modifiers',[(m.type,m.show_viewport) for m in o.modifiers],'matrix', [list(r) for r in o.matrix_world])