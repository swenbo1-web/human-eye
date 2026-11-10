import bpy, numpy as np
objs={o.name:o for o in bpy.context.scene.objects if o.type=='MESH'}
world={name:np.array([tuple(o.matrix_world @ v.co) for v in o.data.vertices]) for name,o in objs.items()}
for name,o in sorted(objs.items()):
 a=world[name]; print(name, o.data.name, 'n',len(a),'min',a.min(0).round(7).tolist(),'max',a.max(0).round(7).tolist(),'center',((a.min(0)+a.max(0))/2).round(7).tolist())
print('camera',bpy.context.scene.camera.name if bpy.context.scene.camera else None,'units',bpy.context.scene.unit_settings.scale_length)