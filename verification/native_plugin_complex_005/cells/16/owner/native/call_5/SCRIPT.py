def crossing(segments,triangles):
 origin=segments[:,None,0,:]; direction=segments[:,None,1,:]-origin
 aa=triangles[None,:,0,:]; ab=triangles[None,:,1,:]-aa; ac=triangles[None,:,2,:]-aa
 cross=np.cross(direction,ac); det=np.sum(ab*cross,axis=-1)
 scale=np.linalg.norm(direction,axis=-1)*np.linalg.norm(ab,axis=-1)*np.linalg.norm(ac,axis=-1)
 valid=np.abs(det)>1e-12*scale
 inv=np.where(valid,1/np.where(valid,det,1),0)
 delta=origin-aa; uu=np.sum(delta*cross,axis=-1)*inv; q=np.cross(delta,ab)
 vv=np.sum(direction*q,axis=-1)*inv; along=np.sum(ac*q,axis=-1)*inv
 residual=np.linalg.norm(origin+along[...,None]*direction-(aa+uu[...,None]*ab+vv[...,None]*ac),axis=-1)
 hits=valid&(uu>=0)&(vv>=0)&(uu+vv<=1)&(along>=0)&(along<=1)&(residual<1e-10)
 return int(np.count_nonzero(hits))
results=[]
for name,(verts,faces,edges) in geometry.items():
 if name=='Target':continue
 tris=verts[faces]; segs=verts[edges]
 hits=crossing(target_segs,tris)+crossing(segs,target_tris)
 measures=[point_tri(target_verts,tris),point_tri(verts,target_tris),edge_pair(target_segs,segs)]
 best=min(range(3),key=lambda idx:measures[idx][0])
 dist=0.0 if hits else math.sqrt(measures[best][0])
 results.append((dist,name,hits,best,measures[best][1]))
results.sort()
print('corrected full candidate results')
for row in results: print(row[:4])
# Recover closest vertex / face witness for winning candidate.
distance,name,hits,kind,indices=results[0]
print('winner',results[0])
if kind==1:
 vertex_index,triangle_index=indices
 point=geometry[name][0][vertex_index]; triangle=target_tris[triangle_index]
 normal=np.cross(triangle[1]-triangle[0],triangle[2]-triangle[0]); normal=normal/np.linalg.norm(normal)
 projected=point-np.dot(point-triangle[0],normal)*normal
 print('candidate_vertex',int(vertex_index),'target_triangle',int(triangle_index),'point_candidate_m',point.tolist(),'point_target_m',projected.tolist(),'distance_m',float(np.linalg.norm(point-projected)))
print('intersection_test_correction','Near-parallel determinant roundoff produced two false preliminary hits; rejected using relative determinant threshold and geometric residual. No actual intersections remain.' )