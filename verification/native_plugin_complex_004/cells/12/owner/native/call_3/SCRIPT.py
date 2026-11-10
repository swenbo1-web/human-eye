names=['Object_01','Object_02','Object_03','Object_04']; meshes={}
for name in names:
 ob=bpy.data.objects[name]; me=ob.data; me.calc_loop_triangles()
 local=np.array([tuple(v.co) for v in me.vertices],dtype=float)
 world=np.array([tuple(ob.matrix_world@v.co) for v in me.vertices],dtype=float)
 tri=np.array([tuple(t.vertices) for t in me.loop_triangles],dtype=int)
 meshes[name]=(local,world,tri)
 print('\n',name,'matrix',np.array(ob.matrix_world).tolist())
 print('local vertices',local.tolist());print('world AABB',world.min(axis=0).tolist(),world.max(axis=0).tolist())
 if name=='Object_01': print('triangles',tri.tolist())
