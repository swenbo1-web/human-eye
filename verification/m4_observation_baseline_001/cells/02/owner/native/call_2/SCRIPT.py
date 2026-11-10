import bpy, numpy as np
objs={o.name:o for o in bpy.context.scene.objects if o.type=='MESH'}
print('meshes',len(objs),'total',len(bpy.context.scene.objects))
for name,o in sorted(objs.items()):
 v=np.array([tuple(o.matrix_world@p.co) for p in o.data.vertices]); lo=v.min(0); hi=v.max(0)
 print(name,'data',o.data.name,'min',lo.tolist(),'max',hi.tolist(),'center',((lo+hi)/2).tolist())
print('camera',bpy.context.scene.camera.name,tuple(bpy.context.scene.camera.location),bpy.context.scene.camera.data.type)