depsgraph=bpy.context.evaluated_depsgraph_get()
geometry={}
for obj in objs:
    evaluated=obj.evaluated_get(depsgraph)
    matrix=np.array(evaluated.matrix_world,dtype=np.float64)
    vertices=np.array([tuple(vertex.co) for vertex in evaluated.data.vertices],dtype=np.float64)
    vertices=vertices@matrix[:3,:3].T+matrix[:3,3]
    faces=[tuple(poly.vertices) for poly in evaluated.data.polygons]
    geometry[obj.name]=(vertices,np.array([(face[0],face[index],face[index+1]) for face in faces for index in range(1,len(face)-1)],dtype=int))
    print(obj.name,'bounds',vertices.min(axis=0).tolist(),vertices.max(axis=0).tolist(),'face_sizes',sorted(set(map(len,faces))))
print('target_world_matrix',np.array(bpy.data.objects['Mesh_D17AB2'].matrix_world).tolist())