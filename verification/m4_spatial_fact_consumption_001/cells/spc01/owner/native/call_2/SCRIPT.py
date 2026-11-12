import bpy
names=['Target','Peer_000','Competing_001','Near_003']
for name in names:
 obj=bpy.data.objects.get(name)
 print(name, 'MISSING' if obj is None else {'type':obj.type,'matrix_world':[list(row) for row in obj.matrix_world],'dimensions':list(obj.dimensions),'modifiers':[(mod.name,mod.type) for mod in obj.modifiers]})
print('units',bpy.context.scene.unit_settings.system,bpy.context.scene.unit_settings.scale_length)
