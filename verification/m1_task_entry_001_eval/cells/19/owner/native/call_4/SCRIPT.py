import bpy, json
scene = bpy.context.scene
print(json.dumps({'units':{'system':scene.unit_settings.system,'scale_length':scene.unit_settings.scale_length},'meshes':[{'name':obj.name,'vertices':len(obj.data.vertices),'polygons':len(obj.data.polygons),'matrix_world':[list(row) for row in obj.matrix_world]} for obj in scene.objects if obj.type=='MESH']},ensure_ascii=False))