import bpy, numpy as np
from mathutils import Vector
meshes={o.name:o for o in bpy.context.scene.objects if o.type=='MESH'}
worldverts={name:np.array([tuple(obj.matrix_world @ v.co) for v in obj.data.vertices]) for name,obj in meshes.items()}
for name,verts in sorted(worldverts.items()):
 print(name, 'mesh',meshes[name].data.name,'min',np.round(verts.min(0),7).tolist(),'max',np.round(verts.max(0),7).tolist(),'center',np.round((verts.min(0)+verts.max(0))/2,7).tolist())
print('unit',bpy.context.scene.unit_settings.scale_length)
