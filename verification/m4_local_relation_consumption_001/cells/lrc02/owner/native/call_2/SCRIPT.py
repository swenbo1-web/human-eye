import bpy, numpy as np
from mathutils import Vector
objs={o.name:o for o in bpy.context.scene.objects if o.type=='MESH'}
print('meshes',len(objs))
for name,o in sorted(objs.items()):
 v=np.array([tuple(o.matrix_world@p.co) for p in o.data.vertices]); print(name, o.data.name, 'min',v.min(0).round(7).tolist(),'max',v.max(0).round(7).tolist(),'center',((v.min(0)+v.max(0))/2).round(7).tolist())
print('camera',[(o.name,tuple(o.location),o.data.type) for o in bpy.context.scene.objects if o.type=='CAMERA'])