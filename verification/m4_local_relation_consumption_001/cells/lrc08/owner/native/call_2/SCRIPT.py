import bpy, numpy as np
from mathutils import Vector
objs={o.name:o for o in bpy.context.scene.objects if o.type=='MESH'}
verts={n:np.array([tuple(o.matrix_world@v.co) for v in o.data.vertices],dtype=float) for n,o in objs.items()}
for n,o in sorted(objs.items()):
 v=verts[n]; print(n,o.data.name,'min',np.round(v.min(0),7).tolist(),'max',np.round(v.max(0),7).tolist(),'center',np.round((v.min(0)+v.max(0))/2,7).tolist())
print('CAMERAS',[(o.name,o.data.type,tuple(o.location)) for o in bpy.context.scene.objects if o.type=='CAMERA'])