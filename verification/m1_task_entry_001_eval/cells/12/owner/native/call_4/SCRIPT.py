import bpy
print('units', bpy.context.scene.unit_settings.system, bpy.context.scene.unit_settings.scale_length)
for obj in bpy.context.scene.objects:
    if obj.type == 'MESH':
        print(obj.name, 'vertices', len(obj.data.vertices), 'faces',len(obj.data.polygons), 'modifiers',len(obj.modifiers))
        if obj.name in ['Mesh_D17AB2','Mesh_097A63']:
            print('world_vertices', [tuple(obj.matrix_world @ vertex.co) for vertex in obj.data.vertices])