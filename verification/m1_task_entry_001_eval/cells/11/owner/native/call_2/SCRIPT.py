import bpy, math, time
from mathutils import Vector
from mathutils.bvhtree import BVHTree
s=bpy.context.scene
print('units',s.unit_settings.system,s.unit_settings.scale_length)
print('target',bpy.data.objects.get('Mesh_D17AB2'))
print('meshes',[(o.name,len(o.data.vertices),len(o.data.polygons)) for o in s.objects if o.type=='MESH'])