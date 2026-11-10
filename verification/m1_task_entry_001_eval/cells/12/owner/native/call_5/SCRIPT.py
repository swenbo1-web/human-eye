from mathutils import Vector
first = bpy.data.objects['Mesh_D17AB2']
second = bpy.data.objects['Mesh_097A63']
probe = Vector((2.00390625, 0.125, 0.0))
for obj in [first, second]:
    hit, location, normal, face_index = obj.closest_point_on_mesh(obj.matrix_world.inverted() @ probe)
    print(obj.name, 'hit', hit, 'point_m', tuple(obj.matrix_world @ location), 'face_index',face_index)
print('exact_gap_mm', (2.00390625 - 2.0) * 1000.0)