import bpy, numpy as np
objs={o.name:o for o in bpy.context.scene.objects if o.type=='MESH'}
print('mesh_count',len(objs))
for name,o in sorted(objs.items()):
 v=np.array([tuple(o.matrix_world@p.co) for p in o.data.vertices]);
 print(name,o.data.name,len(v),'min',np.round(v.min(0),7).tolist(),'max',np.round(v.max(0),7).tolist(),'center',np.round((v.min(0)+v.max(0))/2,7).tolist())