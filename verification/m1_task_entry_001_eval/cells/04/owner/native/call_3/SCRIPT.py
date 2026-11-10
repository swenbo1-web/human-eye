import bpy, numpy as np, math, time
objs=[o for o in bpy.context.scene.objects if o.type=='MESH']
print('units',bpy.context.scene.unit_settings.system,bpy.context.scene.unit_settings.scale_length)
print('mesh_count',len(objs))
print([(o.name,len(o.data.vertices),len(o.data.polygons),len(o.modifiers)) for o in objs])