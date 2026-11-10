def point_tri_min(points, verts, tris):
 triangles=verts[tris]; start=triangles[:,0]; edge1=triangles[:,1]-start; edge2=triangles[:,2]-start
 normal=np.cross(edge1,edge2); normal_sq=np.sum(normal*normal,axis=1)
 offset=points[:,None,:]-start[None,:,:]
 height=np.einsum('pti,ti->pt',offset,normal)/normal_sq
 projected=points[:,None,:]-height[:,:,None]*normal[None,:,:]
 rel=projected-start
 d00=np.sum(edge1*edge1,axis=1);d01=np.sum(edge1*edge2,axis=1);d11=np.sum(edge2*edge2,axis=1)
 d20=np.einsum('pti,ti->pt',rel,edge1);d21=np.einsum('pti,ti->pt',rel,edge2)
 denom=d00*d11-d01*d01
 bary1=(d11*d20-d01*d21)/denom;bary2=(d00*d21-d01*d20)/denom
 good=(bary1>=-1e-12)&(bary2>=-1e-12)&(bary1+bary2<=1+1e-12)
 distances=np.where(good,height*height*normal_sq,np.inf)
 idx=np.unravel_index(np.argmin(distances),distances.shape)
 return float(distances[idx]),points[idx[0]],projected[idx]
def edges_of(tris):
 return np.unique(np.sort(np.concatenate([tris[:,[0,1]],tris[:,[1,2]],tris[:,[2,0]]]),axis=1),axis=0)
def edge_min(verts1,tris1,verts2,tris2):
 edges1=verts1[edges_of(tris1)]; edges2=verts2[edges_of(tris2)]
 start1=edges1[:,0,None,:];start2=edges2[None,:,0,:]
 direction1=(edges1[:,1]-edges1[:,0])[:,None,:];direction2=(edges2[:,1]-edges2[:,0])[None,:,:]
 offset=start1-start2
 aa=np.sum(direction1*direction1,axis=-1);bb=np.sum(direction1*direction2,axis=-1);cc=np.sum(direction2*direction2,axis=-1)
 dd=np.sum(direction1*offset,axis=-1);ee=np.sum(direction2*offset,axis=-1)
 denominator=aa*cc-bb*bb
 safe=np.where(denominator>1e-30,denominator,1)
 ss=(bb*ee-cc*dd)/safe;tt=(aa*ee-bb*dd)/safe
 interior=(denominator>1e-30)&(ss>=0)&(ss<=1)&(tt>=0)&(tt<=1)
 choices=[(ss,tt,interior),(np.zeros_like(dd),np.clip(ee/cc,0,1),True),(np.ones_like(dd),np.clip((ee+bb)/cc,0,1),True),(np.clip(-dd/aa,0,1),np.zeros_like(dd),True),(np.clip((bb-dd)/aa,0,1),np.ones_like(dd),True)]
 best=(np.inf,None,None)
 for ss,tt,valid in choices:
  first=start1+ss[:,:,None]*direction1;second=start2+tt[:,:,None]*direction2
  dist=np.where(valid,np.sum((first-second)**2,axis=-1),np.inf)
  idx=np.unravel_index(np.argmin(dist),dist.shape)
  if dist[idx]<best[0]:best=(float(dist[idx]),first[idx],second[idx])
 return best
for name in ['Part_26','Part_38']:
 verts,tris=meshes[name]
 candidates=[point_tri_min(verts,basev,baset),point_tri_min(basev,verts,tris),edge_min(verts,tris,basev,baset)]
 best=min(candidates,key=lambda item:item[0])
 print(name,'minimum_mm',np.sqrt(best[0])*1000,'witness_world_m',best[1].tolist(),best[2].tolist(),'method_distances_mm',[np.sqrt(item[0])*1000 for item in candidates])
# Strictly interior witness for both overlapping solids, away from their boundaries.
verts,tris=meshes['Part_17']; witness=verts.mean(axis=0)
print('Part_17 interior witness m',witness.tolist(),'windings',winding([witness],verts,tris).tolist(),winding([witness],basev,baset).tolist())
print('Part_17 witness boundary distances mm',basebvh.find_nearest(witness)[3]*1000,BVHTree.FromPolygons(verts.tolist(),tris.tolist(),all_triangles=True).find_nearest(witness)[3]*1000)
