import bpy, json
result=[]
for name in ['Object_01','Object_02','Object_03','Object_04']:
    obj=bpy.data.objects.get(name)
    result.append({'name':name,'matrix_world':[list(row) for row in obj.matrix_world],'rotation_mode':obj.rotation_mode,'rotation_euler_rad':list(obj.rotation_euler),'mesh_vertices':len(obj.data.vertices) if obj.type=='MESH' else None,'mesh_polygons':len(obj.data.polygons) if obj.type=='MESH' else None})
print(json.dumps(result))