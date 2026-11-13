scan_meshes=[]
for obj in objs:
 ev=obj.evaluated_get(depsgraph)
 mesh=ev.to_mesh()
 try:
  mesh.calc_loop_triangles()
  coords=np.array([tuple(ev.matrix_world @ vertex.co) for vertex in mesh.vertices],dtype=np.float64).reshape((-1,3))
  inds=np.array([tuple(tri.vertices) for tri in mesh.loop_triangles],dtype=int).reshape((-1,3))
  triangles=coords[inds]
  scan_meshes.append(dict(name=obj.name,tri=triangles,lo=triangles.min(axis=(0,1)) if len(triangles) else None,hi=triangles.max(axis=(0,1)) if len(triangles) else None))
 finally:
  ev.to_mesh_clear()
mm_per_unit=scene.unit_settings.scale_length*1000.0
limit=2.0/mm_per_unit
candidate_pairs=[]
for first in range(len(scan_meshes)):
 for second in range(first+1,len(scan_meshes)):
  one,two=scan_meshes[first],scan_meshes[second]
  if one['lo'] is None or two['lo'] is None: continue
  gap=np.maximum(0,np.maximum(one['lo']-two['hi'],two['lo']-one['hi']))
  lower=float(np.linalg.norm(gap))
  if lower<=limit+1e-12: candidate_pairs.append((first,second,lower))
print('TOTAL_PAIRS',len(objs)*(len(objs)-1)//2,'AABB_CANDIDATES',len(candidate_pairs),'TRIANGLES',sum(len(m['tri']) for m in scan_meshes))
print('CANDIDATES',[(scan_meshes[a]['name'],scan_meshes[b]['name'],round(d*mm_per_unit,6)) for a,b,d in candidate_pairs])
print('DEGENERATE_TRIANGLES',[(m['name'],int(np.sum(np.linalg.norm(np.cross(m['tri'][:,1]-m['tri'][:,0],m['tri'][:,2]-m['tri'][:,0]),axis=1)==0))) for m in scan_meshes if np.any(np.linalg.norm(np.cross(m['tri'][:,1]-m['tri'][:,0],m['tri'][:,2]-m['tri'][:,0]),axis=1)==0)])
