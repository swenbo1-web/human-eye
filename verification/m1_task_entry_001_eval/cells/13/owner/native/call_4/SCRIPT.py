def point_face_candidates(points, vertices, faces):
 tri=vertices[faces]
 first=tri[:,0]; edge1=tri[:,1]-first; edge2=tri[:,2]-first
 normal=np.cross(edge1,edge2); normal2=np.einsum('ij,ij->i',normal,normal)
 delta=points[:,None,:]-first[None,:,:]
 height=np.einsum('pfi,fi->pf',delta,normal)/normal2[None,:]
 projected=points[:,None,:]-height[:,:,None]*normal[None,:,:]
 local=projected-first[None,:,:]
 aa=np.einsum('ij,ij->i',edge1,edge1); ab=np.einsum('ij,ij->i',edge1,edge2); bb=np.einsum('ij,ij->i',edge2,edge2)
 la=np.einsum('pfi,fi->pf',local,edge1); lb=np.einsum('pfi,fi->pf',local,edge2)
 denom=aa*bb-ab*ab
 bary1=(la*bb-lb*ab)/denom; bary2=(lb*aa-la*ab)/denom
 valid=(bary1>=-1e-13)&(bary2>=-1e-13)&(bary1+bary2<=1+1e-13)&(normal2[None,:]>0)
 dist2=height*height*normal2[None,:]
 dist2=np.where(valid,dist2,np.inf)
 index=np.unravel_index(np.argmin(dist2),dist2.shape)
 return float(dist2[index]), points[index[0]].copy(),projected[index].copy(),('vertex-face',int(index[0]),int(index[1]))
def unique_edges(faces):
 return np.unique(np.sort(np.concatenate([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]]),axis=1),axis=0)
def edge_candidates(verts_a,faces_a,verts_b,faces_b):
 edges_a=unique_edges(faces_a); edges_b=unique_edges(faces_b)
 pa=verts_a[edges_a[:,0]][:,None,:]; pb=verts_b[edges_b[:,0]][None,:,:]
 da=(verts_a[edges_a[:,1]]-verts_a[edges_a[:,0]])[:,None,:]
 db=(verts_b[edges_b[:,1]]-verts_b[edges_b[:,0]])[None,:,:]
 diff=pa-pb
 aa=np.sum(da*da,axis=2); bb=np.sum(da*db,axis=2); cc=np.sum(db*db,axis=2)
 dd=np.sum(da*diff,axis=2); ee=np.sum(db*diff,axis=2)
 denom=aa*cc-bb*bb
 candidates=[]
 with np.errstate(divide='ignore',invalid='ignore'):
  sa=(bb*ee-cc*dd)/denom; sb=(aa*ee-bb*dd)/denom
 valid=(denom>1e-25)&(sa>=0)&(sa<=1)&(sb>=0)&(sb<=1)
 candidates.append((sa,sb,valid))
 shape=bb.shape
 for param in (0.,1.):
  sa=np.full(shape,param); sb=np.clip((ee+bb*param)/cc,0,1)
  candidates.append((sa,sb,np.ones(shape,dtype=bool)))
 for param in (0.,1.):
  sb=np.full(shape,param); sa=np.clip((bb*param-dd)/aa,0,1)
  candidates.append((sa,sb,np.ones(shape,dtype=bool)))
 best=(float('inf'),None,None,None)
 for sa,sb,valid in candidates:
  qa=pa+sa[:,:,None]*da; qb=pb+sb[:,:,None]*db
  dist2=np.where(valid,np.sum((qa-qb)**2,axis=2),np.inf)
  index=np.unravel_index(np.argmin(dist2),dist2.shape)
  if dist2[index]<best[0]: best=(float(dist2[index]),qa[index].copy(),qb[index].copy(),('edge-edge',edges_a[index[0]].tolist(),edges_b[index[1]].tolist()))
 return best
results={}
verts_a,faces_a=geometry['Mesh_DDBB95']
for name,(verts_b,faces_b) in geometry.items():
 if name=='Mesh_DDBB95':continue
 candidates=[point_face_candidates(verts_a,verts_b,faces_b)]
 reverse=point_face_candidates(verts_b,verts_a,faces_a)
 candidates.append((reverse[0],reverse[2],reverse[1],('face-vertex',)+reverse[3][1:]))
 candidates.append(edge_candidates(verts_a,faces_a,verts_b,faces_b))
 best=min(candidates,key=lambda candidate:candidate[0]);results[name]=best
 print(name,'minimum_mm',math.sqrt(best[0])*1000,'target_point_mm',(best[1]*1000).tolist(),'other_point_mm',(best[2]*1000).tolist(),'feature',best[3])
print('elapsed_seconds',time.time()-start_time)
