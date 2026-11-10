meshdata={}
for name in names:
 obj=bpy.data.objects[name]; mesh=obj.data; mesh.calc_loop_triangles()
 local=np.array([tuple(v.co) for v in mesh.vertices],dtype=float); mat=np.array(obj.matrix_world,dtype=float)
 world=local@mat[:3,:3].T+mat[:3,3]
 tris=np.array([tuple(t.vertices) for t in mesh.loop_triangles],dtype=int)
 meshdata[name]=(world,tris)
 print(name,'local verts',local.tolist())
 print('triangles',tris.tolist())
 print('world aabb',world.min(axis=0).tolist(),world.max(axis=0).tolist())
 # incidence closedness
 from collections import Counter
 counts=Counter(tuple(sorted((int(t[i]),int(t[(i+1)%3])))) for t in tris for i in range(3))
 print('edge incidences',dict(Counter(counts.values())))
