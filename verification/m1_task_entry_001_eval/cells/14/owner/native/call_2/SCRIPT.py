import bpy
objs=[o for o in bpy.context.scene.objects if o.type=='MESH']
print('mesh_count',len(objs))
print('target',[(o.name,len(o.data.vertices),len(o.data.polygons)) for o in objs if o.name=='Mesh_DDBB95'])
print('units',bpy.context.scene.unit_settings.system,bpy.context.scene.unit_settings.scale_length)
print('meshes',[(o.name,len(o.data.vertices),len(o.data.polygons)) for o in objs])