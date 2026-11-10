import bpy, numpy as np, math, time
from mathutils import Vector
from mathutils.bvhtree import BVHTree
start=time.time()
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
print('mesh_count',len(meshes))
print([(o.name,len(o.data.vertices),len(o.data.polygons),[(m.type,m.show_viewport) for m in o.modifiers]) for o in meshes])
print('target',bpy.context.scene.objects.get('Target'))