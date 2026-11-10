import bpy, numpy as np
for o in bpy.context.scene.objects:
 if o.type=='MESH':
  pts=np.array([tuple(o.matrix_world@v.co) for v in o.data.vertices]); lo=pts.min(0); hi=pts.max(0)
  print(o.name,o.data.name,'min',np.round(lo,7).tolist(),'max',np.round(hi,7).tolist(),'center',np.round((lo+hi)/2,7).tolist())
