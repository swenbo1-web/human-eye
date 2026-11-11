import bpy, numpy as np
from mathutils import Vector
meshes={o.name:o for o in bpy.context.scene.objects if o.type=='MESH'}
def coords(o): return np.array([tuple(o.matrix_world@v.co) for v in o.data.vertices],dtype=float)
for name,o in sorted(meshes.items()):
 a=coords(o); lo=a.min(0); hi=a.max(0)
 print(name, 'mesh',o.data.name,'min',lo.round(7).tolist(),'max',hi.round(7).tolist(),'center',((lo+hi)/2).round(7).tolist())
print('units',bpy.context.scene.unit_settings.system,bpy.context.scene.unit_settings.scale_length)
