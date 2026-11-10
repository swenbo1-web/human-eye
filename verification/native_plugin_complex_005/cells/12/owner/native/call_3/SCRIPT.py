obs={name:bpy.data.objects[name] for name in ['Object_01','Object_02','Object_03','Object_04']}
geo={}
for name,ob in obs.items():
 me=ob.data; me.calc_loop_triangles()
 local=np.array([v.co[:] for v in me.vertices],dtype=float)
 mat=np.array(ob.matrix_world,dtype=float)
 world=local@mat[:3,:3].T+mat[:3,3]
 tris=np.array([t.vertices[:] for t in me.loop_triangles],dtype=int)
 geo[name]=(world,tris,local,mat)
 edges={}
 for face in tris:
  for idx in range(3):
   edge=tuple(sorted((int(face[idx]),int(face[(idx+1)%3]))));edges[edge]=edges.get(edge,0)+1
 print(name,'local vertices',local.tolist(),'triangles',tris.tolist() if name=='Object_01' else '', 'edge incidence', sorted(set(edges.values())), 'AABB',world.min(0).tolist(),world.max(0).tolist())
