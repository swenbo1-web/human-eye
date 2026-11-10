import bpy
objs=[o for o in bpy.context.scene.objects if o.type=='MESH']
print('mesh_count',len(objs))
print([(o.name,len(o.data.vertices),len(o.data.polygons)) for o in objs])
print('units',bpy.context.scene.unit_settings.system,bpy.context.scene.unit_settings.scale_length)
