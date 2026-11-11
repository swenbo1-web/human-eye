import bpy, numpy as np
objs={o.name:o for o in bpy.context.scene.objects if o.type=='MESH'}
print('meshes',len(objs))
for name,o in sorted(objs.items()):
 v=np.array([tuple(o.matrix_world@p.co) for p in o.data.vertices]);lo=v.min(0);hi=v.max(0)
 print(name,o.data.name,len(v),'bounds',lo.tolist(),hi.tolist(),'center',((lo+hi)/2).tolist())
print('camera',[(o.name,tuple(o.location),o.data.type) for o in bpy.context.scene.objects if o.type=='CAMERA'])