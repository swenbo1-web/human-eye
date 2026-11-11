import bpy, numpy as np
from mathutils import Vector
objs={o.name:o for o in bpy.context.scene.objects if o.type=='MESH'}
print('meshes',len(objs),'objects',len(bpy.context.scene.objects))
for name,o in sorted(objs.items()):
 v=np.array([tuple(o.matrix_world @ p.co) for p in o.data.vertices]);
 print(name,o.data.name,'n',len(v),'min',np.round(v.min(0),7).tolist(),'max',np.round(v.max(0),7).tolist(),'center',np.round((v.min(0)+v.max(0))/2,7).tolist())