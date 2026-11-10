import bpy, numpy as np, time
from mathutils import Vector
from mathutils.bvhtree import BVHTree
start=time.time()
scene=bpy.context.scene
deps=bpy.context.evaluated_depsgraph_get()
meshes=[o for o in scene.objects if o.type=='MESH']
print('mesh_count',len(meshes))
print([(o.name,len(o.data.vertices),len(o.data.polygons)) for o in meshes])
print('target',scene.objects.get('Target'))