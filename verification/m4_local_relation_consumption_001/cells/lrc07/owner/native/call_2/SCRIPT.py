import bpy, numpy as np
for obj in bpy.context.scene.objects:
 if obj.type=='MESH':
  pts=np.array([tuple(obj.matrix_world @ v.co) for v in obj.data.vertices]); low=pts.min(0); high=pts.max(0)
  print(obj.name, obj.data.name, 'min',low.round(7).tolist(),'max',high.round(7).tolist(),'center',((low+high)/2).round(7).tolist())
