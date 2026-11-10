import bpy, numpy as np
from mathutils import Vector
meshes={o.name:o for o in bpy.context.scene.objects if o.type=='MESH'}
world={n:np.array([tuple(o.matrix_world@v.co) for v in o.data.vertices],dtype=float) for n,o in meshes.items()}
for n,o in sorted(meshes.items()):
 a=world[n]; print(n,o.data.name,'bounds',np.round(a.min(0),7).tolist(),np.round(a.max(0),7).tolist(),'center',np.round((a.min(0)+a.max(0))/2,7).tolist())
print('camera',bpy.context.scene.camera.name,tuple(bpy.context.scene.camera.location),bpy.context.scene.camera.data.type)
