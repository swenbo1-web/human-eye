import bpy, numpy as np, math, time
from mathutils import Vector
from mathutils.bvhtree import BVHTree
start_time=time.time()
objs=[o for o in bpy.context.scene.objects if o.type=='MESH']
print('mesh_count',len(objs))
print('target',bpy.data.objects.get('Target'))
for o in objs:
 corners=np.array([tuple(o.matrix_world@Vector(c)) for c in o.bound_box])
 print(o.name,'verts',len(o.data.vertices),'polys',len(o.data.polygons),'mods',[(m.type,m.show_viewport) for m in o.modifiers], 'bounds',corners.min(axis=0).tolist(),corners.max(axis=0).tolist())