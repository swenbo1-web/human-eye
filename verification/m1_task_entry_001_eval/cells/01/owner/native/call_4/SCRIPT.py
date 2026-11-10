def vertex_face_min(points,tris):
 origin=tris[:,0]; side1=tris[:,1]-origin; side2=tris[:,2]-origin
 normals=np.cross(side1,side2); normal2=np.sum(normals*normals,axis=1)
 displacement=points[:,None,:]-origin[None,:,:]
 height=np.einsum('pfi,fi->pf',displacement,normals)/normal2[None,:]
 projected=points[:,None,:]-height[:,:,None]*normals[None,:,:]
 offset=projected-origin[None,:,:]
 aa=np.sum(side1*side1,axis=1); bb=np.sum(side1*side2,axis=1); cc=np.sum(side2*side2,axis=1)
 dd=np.einsum('pfi,fi->pf',offset,side1); ee=np.einsum('pfi,fi->pf',offset,side2)
 denom=aa*cc-bb*bb
 uu=(cc*dd-bb*ee)/denom; vv=(aa*ee-bb*dd)/denom
 valid=(uu>=-1e-12)&(vv>=-1e-12)&(uu+vv<=1+1e-12)
 dist2=np.where(valid,height*height*normal2,np.inf)
 point_index,face_index=np.unravel_index(np.argmin(dist2),dist2.shape)
 return float(dist2[point_index,face_index]),points[point_index],projected[point_index,face_index]
def edge_edge_min(first,second):
 first_start=first[:,0,None,:]; second_start=second[None,:,0,:]
 first_dir=(first[:,1]-first[:,0])[:,None,:]; second_dir=(second[:,1]-second[:,0])[None,:,:]
 offset=first_start-second_start
 aa=np.sum(first_dir*first_dir,axis=-1); bb=np.sum(first_dir*second_dir,axis=-1); cc=np.sum(second_dir*second_dir,axis=-1)
 dd=np.sum(first_dir*offset,axis=-1); ee=np.sum(second_dir*offset,axis=-1)
 denom=aa*cc-bb*bb
 safe=np.where(denom>1e-30,denom,1.)
 ss=(bb*ee-cc*dd)/safe; tt=(aa*ee-bb*dd)/safe
 options=[(ss,tt,(denom>1e-30)&(ss>=0)&(ss<=1)&(tt>=0)&(tt<=1)),(np.zeros_like(dd),np.clip(ee/cc,0,1),True),(np.ones_like(dd),np.clip((ee+bb)/cc,0,1),True),(np.clip(-dd/aa,0,1),np.zeros_like(ee),True),(np.clip((bb-dd)/aa,0,1),np.ones_like(ee),True)]
 best=(float('inf'),None,None)
 for ss,tt,valid in options:
  point1=first_start+ss[:,:,None]*first_dir; point2=second_start+tt[:,:,None]*second_dir
  dist2=np.where(valid,np.sum((point1-point2)**2,axis=-1),np.inf)
  idx=np.unravel_index(np.argmin(dist2),dist2.shape)
  if dist2[idx]<best[0]: best=(float(dist2[idx]),point1[idx],point2[idx])
 return best
for name in names[1:]:
 target=geom['Part_49']; candidate=geom[name]
 results=[vertex_face_min(candidate['v'],target['tri']),vertex_face_min(target['v'],candidate['tri']),edge_edge_min(candidate['v'][candidate['e']],target['v'][target['e']])]
 best=min(results,key=lambda item:item[0])
 print(name,'feature_distances_mm',[math.sqrt(item[0])*1000 for item in results],'best_points_mm',best[1]*1000,best[2]*1000)
 # Manifold check and surface-crossing broad phase, with solid-angle evidence above identifying penetration.
 for label,geometry in [('target',target),('candidate',candidate)]:
  all_edges=np.sort(np.concatenate([geometry['f'][:,[0,1]],geometry['f'][:,[1,2]],geometry['f'][:,[2,0]]]),axis=1)
  counts=np.unique(all_edges,axis=0,return_counts=True)[1]
  print(label,'edge_incidence',np.unique(counts,return_counts=True))
 tree_target=BVHTree.FromPolygons(target['v'].tolist(),target['f'].tolist(),all_triangles=True,epsilon=0.0)
 tree_candidate=BVHTree.FromPolygons(candidate['v'].tolist(),candidate['f'].tolist(),all_triangles=True,epsilon=0.0)
 print('surface_overlap_pairs',len(tree_target.overlap(tree_candidate)))