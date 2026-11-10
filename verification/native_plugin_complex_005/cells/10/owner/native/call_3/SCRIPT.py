names=['Object_01','Object_02','Object_03','Object_04']
meshes={}
for name in names:
 obj=bpy.data.objects[name]; mesh=obj.data; mesh.calc_loop_triangles()
 vertices=np.array([list(v.co) for v in mesh.vertices],dtype=float)
 matrix=np.array(obj.matrix_world,dtype=float)
 world=vertices@matrix[:3,:3].T+matrix[:3,3]
 triangles=np.array([list(t.vertices) for t in mesh.loop_triangles],dtype=int)
 meshes[name]={'local':vertices,'world':world,'triangles':triangles,'matrix':matrix}
 print(name,'local vertices',vertices.tolist(),'triangles',triangles.tolist())
 print('world AABB',world.min(axis=0).tolist(),world.max(axis=0).tolist())
 print('edges face-count', {count:sum(1 for value in [sum(1 for tri in triangles if a in tri and b in tri) for a,b in {tuple(sorted((int(tri[j]),int(tri[(j+1)%3])))) for tri in triangles for j in range(3)}] if value==count) for count in [1,2,3]})