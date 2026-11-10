import bpy, numpy as np
from mathutils import Vector
objs={o.name:o for o in bpy.context.scene.objects if o.type=='MESH'}
for name,o in sorted(objs.items()):
 v=np.array([tuple(o.matrix_world@p.co) for p in o.data.vertices]); lo=v.min(0); hi=v.max(0)
 print(name, o.data.name, 'bounds',lo.tolist(),hi.tolist(),'center',((lo+hi)/2).tolist())