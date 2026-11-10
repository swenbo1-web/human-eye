import bpy, math
for name in ['Object_01','Object_02','Object_03','Object_04']:
    obj=bpy.data.objects[name]
    print({'name':name,'world_rotation_degrees': [math.degrees(angle) for angle in obj.matrix_world.to_euler('XYZ')], 'mesh_vertices':len(obj.data.vertices),'mesh_polygons':len(obj.data.polygons)})