import bpy
print([(obj.name, len(obj.data.polygons)) for obj in bpy.context.scene.objects if obj.type == 'MESH'])