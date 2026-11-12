import bpy
for obj in bpy.context.scene.objects:
    if obj.name in ['Target','Part_A','Part_B','Part_C']:
        print(obj.name, obj.type, 'matrix', [list(row) for row in obj.matrix_world], 'modifiers', [(mod.name,mod.type) for mod in obj.modifiers])
print('units',bpy.context.scene.unit_settings.system,bpy.context.scene.unit_settings.scale_length)
print('names', [obj.name for obj in bpy.context.scene.objects])