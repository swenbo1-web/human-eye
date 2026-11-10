import bpy, numpy as np
from mathutils import Vector
objs={o.name:o for o in bpy.context.scene.objects if o.type=='MESH'}
print('meshes',len(objs),'objects',len(bpy.context.scene.objects))
verts={name:np.array([tuple(o.matrix_world@v.co) for v in o.data.vertices]) for name,o in objs.items()}
for name,o in sorted(objs.items()):
 a=verts[name]; print(name,o.data.name,'n',len(a),'min',np.round(a.min(0),7).tolist(),'max',np.round(a.max(0),7).tolist(),'center',np.round((a.min(0)+a.max(0))/2,7).tolist())
print('camera',bpy.context.scene.camera.name,tuple(bpy.context.scene.camera.location),bpy.context.scene.camera.data.type)
