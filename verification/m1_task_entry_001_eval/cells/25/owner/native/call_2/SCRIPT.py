import bpy, math, time
from mathutils import Vector
print('units', bpy.context.scene.unit_settings.system, bpy.context.scene.unit_settings.scale_length)
print('target', bpy.data.objects.get('Mesh_D17AB2'))
objs=[o for o in bpy.context.scene.objects if o.type=='MESH']
print('mesh_count',len(objs))
print([(o.name,len(o.data.vertices),len(o.data.polygons)) for o in objs])