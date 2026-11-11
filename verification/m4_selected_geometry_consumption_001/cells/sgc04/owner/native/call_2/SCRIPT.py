import bpy, numpy as np, json
from mathutils import Vector
meshes={o.name:o for o in bpy.context.scene.objects if o.type=='MESH'}
verts={name:np.array([tuple(o.matrix_world@v.co) for v in o.data.vertices]) for name,o in meshes.items()}
for name,o in sorted(meshes.items()):
 a=verts[name]; print(name,o.data.name,'min',np.round(a.min(0),7).tolist(),'max',np.round(a.max(0),7).tolist(),'center',np.round((a.min(0)+a.max(0))/2,7).tolist())