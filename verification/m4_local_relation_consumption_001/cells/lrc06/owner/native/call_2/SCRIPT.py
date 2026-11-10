import bpy, numpy as np
from mathutils import Vector
objs={o.name:o for o in bpy.context.scene.objects if o.type=='MESH'}
print('counts',len(bpy.context.scene.objects),len(objs))
for name,o in sorted(objs.items()):
 v=np.array([tuple(o.matrix_world @ p.co) for p in o.data.vertices]); print(name,o.data.name,len(v),'bounds',np.round(v.min(0),7).tolist(),np.round(v.max(0),7).tolist(),'center',np.round((v.min(0)+v.max(0))/2,7).tolist())
print('camera',bpy.context.scene.camera.name,tuple(bpy.context.scene.camera.location),bpy.context.scene.camera.data.type)