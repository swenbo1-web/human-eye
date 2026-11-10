import bpy, time
from mathutils import Vector
from mathutils.bvhtree import BVHTree
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
print('mesh_count',len(meshes))
for o in meshes:
 print(o.name, 'verts',len(o.data.vertices),'polys',len(o.data.polygons),'mods',len(o.modifiers))