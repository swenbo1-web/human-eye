import bpy, numpy as np
objs={o.name:o for o in bpy.context.scene.objects if o.type=='MESH'}
world={name:np.array([tuple(o.matrix_world@v.co) for v in o.data.vertices],dtype=float) for name,o in objs.items()}
for name,v in sorted(world.items()):
 print(name,objs[name].data.name,'n',len(v),'min',np.round(v.min(0),7).tolist(),'max',np.round(v.max(0),7).tolist(),'center',np.round((v.min(0)+v.max(0))/2,7).tolist())
print('camera',[(o.name,tuple(o.location),o.data.type) for o in bpy.context.scene.objects if o.type=='CAMERA'])