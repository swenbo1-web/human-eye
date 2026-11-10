import bpy, numpy as np, math, time
meshes = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
print('mesh_count',len(meshes))
print([(obj.name,len(obj.data.vertices),len(obj.data.polygons)) for obj in meshes])
print('units',bpy.context.scene.unit_settings.system,bpy.context.scene.unit_settings.scale_length)
