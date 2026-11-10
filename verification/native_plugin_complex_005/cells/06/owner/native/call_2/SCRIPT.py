import bpy, numpy as np, time
from mathutils import Vector
from mathutils.bvhtree import BVHTree
start=time.time()
objs=[o for o in bpy.context.scene.objects if o.type=='MESH']
print('mesh_count',len(objs))
for o in objs:
 print(o.name, 'verts',len(o.data.vertices),'polys',len(o.data.polygons),'mods',[(m.name,m.type) for m in o.modifiers], 'loc',tuple(o.location))
print('target_exists', any(o.name=='Target' for o in objs))