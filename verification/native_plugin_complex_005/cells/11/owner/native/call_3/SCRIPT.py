import bpy, json
result=[]
for name in ['Object_01','Object_02','Object_03','Object_04']:
    obj=bpy.data.objects.get(name)
    result.append({'name':name,'type':obj.type,'rotation_mode':obj.rotation_mode,'world_matrix':[[float(value) for value in row] for row in obj.matrix_world],'vertices':len(obj.data.vertices),'polygons':len(obj.data.polygons),'modifiers':[mod.type for mod in obj.modifiers]})
print(json.dumps(result))