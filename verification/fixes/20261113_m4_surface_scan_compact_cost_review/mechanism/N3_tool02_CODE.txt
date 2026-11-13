geom=[]
for obj in objs:
 evaluated=obj.evaluated_get(depsgraph)
 mesh=evaluated.to_mesh()
 mesh.calc_loop_triangles()
 vertices=np.array([tuple(evaluated.matrix_world @ vertex.co) for vertex in mesh.vertices],dtype=np.float64)
 indices=np.array([tuple(tri.vertices) for tri in mesh.loop_triangles],dtype=np.int64).reshape(-1,3)
 triangles=vertices[indices]
 geom.append(dict(name=obj.name,vertices=vertices,triangles=triangles,lo=triangles.min(axis=(0,1)) if len(triangles) else None,hi=triangles.max(axis=(0,1)) if len(triangles) else None))
 evaluated.to_mesh_clear()
 print(obj.name,'vertices',len(vertices),'triangles',len(triangles),'bounds',None if not len(triangles) else (geom[-1]['lo'].tolist(),geom[-1]['hi'].tolist()))
threshold=0.002 / scene.unit_settings.scale_length
candidates=[]
for first in range(len(geom)):
 for second in range(first+1,len(geom)):
  a,b=geom[first],geom[second]
  if a['lo'] is None or b['lo'] is None: continue
  gap=np.maximum(np.maximum(a['lo']-b['hi'],b['lo']-a['hi']),0)
  bound=np.linalg.norm(gap)
  if bound<=threshold+1e-12:candidates.append((first,second,bound))
print('candidate_count',len(candidates),'total_pairs',len(geom)*(len(geom)-1)//2)
print([(geom[a]['name'],geom[b]['name'],d*1000) for a,b,d in candidates])