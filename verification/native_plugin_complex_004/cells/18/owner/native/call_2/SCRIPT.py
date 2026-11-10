import bpy
mesh_objects=[obj for obj in bpy.context.scene.objects if obj.type=='MESH']
print('mesh_count',len(mesh_objects))
print([(obj.name,len(obj.data.vertices),len(obj.data.polygons)) for obj in mesh_objects])
print('Target_matches',[(obj.name,obj.type) for obj in bpy.context.scene.objects if obj.name=='Target'])