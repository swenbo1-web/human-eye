import bpy
print([(obj.name,len(obj.data.vertices),len(obj.data.polygons)) for obj in bpy.context.scene.objects if obj.type=='MESH'])