import bpy
for name in ['Target','Peer_000','Competing_001','Near_003']:
 obj=bpy.data.objects.get(name)
 print(name, 'MISSING' if obj is None else {'type':obj.type,'matrix_world':[list(row) for row in obj.matrix_world], 'vertices':len(obj.data.vertices) if obj.type=='MESH' else None,'polygons':len(obj.data.polygons) if obj.type=='MESH' else None,'modifiers':[(mod.name,mod.type,mod.show_viewport) for mod in obj.modifiers]})
print('units',bpy.context.scene.unit_settings.system,bpy.context.scene.unit_settings.scale_length)
