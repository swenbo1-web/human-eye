import bpy, numpy as np
objs={o.name:o for o in bpy.context.scene.objects if o.type=='MESH'}
verts={n:np.array([tuple(o.matrix_world@v.co) for v in o.data.vertices],dtype=float) for n,o in objs.items()}
for n,o in sorted(objs.items()):
 a=verts[n]; print(n,o.data.name,'verts',len(a),'min',np.round(a.min(0),7).tolist(),'max',np.round(a.max(0),7).tolist(),'center',np.round((a.min(0)+a.max(0))/2,7).tolist())
print('camera',[(o.name,tuple(o.location),o.data.type) for o in bpy.context.scene.objects if o.type=='CAMERA'])