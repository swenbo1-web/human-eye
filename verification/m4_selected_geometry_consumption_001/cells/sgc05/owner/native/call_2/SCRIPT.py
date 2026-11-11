import bpy, numpy as np
for obj in bpy.context.scene.objects:
 if obj.type=='MESH':
  coords=np.array([tuple(obj.matrix_world @ v.co) for v in obj.data.vertices]); lo=coords.min(0); hi=coords.max(0)
  print(obj.name, obj.data.name, 'bounds',lo.tolist(),hi.tolist(),'center',((lo+hi)/2).tolist())
print('camera', [(o.name,tuple(o.location),o.data.type) for o in bpy.context.scene.objects if o.type=='CAMERA'])