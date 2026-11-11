import bpy, numpy as np
objects={obj.name:obj for obj in bpy.context.scene.objects if obj.type=='MESH'}
for name,obj in sorted(objects.items()):
 points=np.array([tuple(obj.matrix_world @ vertex.co) for vertex in obj.data.vertices])
 print(name, 'mesh',obj.data.name,'bounds',np.round(points.min(0),7).tolist(),np.round(points.max(0),7).tolist(),'center',np.round((points.min(0)+points.max(0))/2,7).tolist())
print('units',bpy.context.scene.unit_settings.scale_length)
