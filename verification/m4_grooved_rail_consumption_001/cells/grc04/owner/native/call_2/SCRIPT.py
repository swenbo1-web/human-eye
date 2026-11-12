import bpy
for obj in bpy.context.scene.objects:
    print(obj.name, obj.type)
