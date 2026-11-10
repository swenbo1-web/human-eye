objs={name:bpy.data.objects[name] for name in ['Object_01','Object_02','Object_03','Object_04']}
geo={}
for name,obj in objs.items():
 mesh=obj.data; mesh.calc_loop_triangles()
 local=np.array([v.co[:] for v in mesh.vertices],dtype=float)
 world=np.array([tuple(obj.matrix_world@v.co) for v in mesh.vertices],dtype=float)
 faces=np.array([tuple(t.vertices) for t in mesh.loop_triangles],dtype=int)
 geo[name]={'v':world,'f':faces,'local':local,'matrix':np.array(obj.matrix_world)}
 print(name,'local vertices',local.tolist(),'triangles',faces.tolist())
 print('world AABB',world.min(axis=0).tolist(),world.max(axis=0).tolist())
 edges={}
 for face in faces:
  for a,b in zip(face,np.roll(face,-1)):
   key=tuple(sorted((int(a),int(b)))); edges[key]=edges.get(key,0)+1
 print('edge incidence',dict((x,list(edges.values()).count(x)) for x in set(edges.values())))
 geo[name]['bvh']=BVHTree.FromPolygons([Vector(v) for v in world],faces.tolist(),all_triangles=True,epsilon=0.0)
for name in list(objs)[1:]:
 pairs=geo['Object_01']['bvh'].overlap(geo[name]['bvh'])
 print('triangle overlap',name,len(pairs),pairs[:24])
