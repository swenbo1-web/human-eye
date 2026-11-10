def interior_projection(points, triangles):
 origin=triangles[:,0]; e1=triangles[:,1]-origin; e2=triangles[:,2]-origin
 normals=np.cross(e1,e2); n2=np.einsum('ij,ij->i',normals,normals)
 delta=points[:,None,:]-origin[None,:,:]
 signed=np.einsum('pfi,fi->pf',delta,normals)/n2[None,:]
 projected=points[:,None,:]-signed[:,:,None]*normals[None,:,:]
 diff=projected-origin[None,:,:]
 aa=np.einsum('ij,ij->i',e1,e1); bb=np.einsum('ij,ij->i',e1,e2); cc=np.einsum('ij,ij->i',e2,e2)
 dd=np.einsum('pfi,fi->pf',diff,e1); ee=np.einsum('pfi,fi->pf',diff,e2)
 denom=aa*cc-bb*bb
 u=(dd*cc-ee*bb)/denom; v=(ee*aa-dd*bb)/denom
 inside=(u>=-1e-13)&(v>=-1e-13)&(u+v<=1+1e-13)
 dist2=np.where(inside,signed*signed*n2[None,:],np.inf)
 idx=np.unravel_index(np.argmin(dist2),dist2.shape)
 return float(dist2[idx]),points[idx[0]].copy(),projected[idx].copy()
def edge_distances(segments_a,segments_b):
 start_a=segments_a[:,0,None,:]; start_b=segments_b[None,:,0,:]
 vec_a=(segments_a[:,1]-segments_a[:,0])[:,None,:]; vec_b=(segments_b[:,1]-segments_b[:,0])[None,:,:]
 offset=start_a-start_b
 aa=np.sum(vec_a*vec_a,axis=2); bb=np.sum(vec_a*vec_b,axis=2); cc=np.sum(vec_b*vec_b,axis=2)
 dd=np.sum(vec_a*offset,axis=2); ee=np.sum(vec_b*offset,axis=2)
 denom=aa*cc-bb*bb
 safe=np.where(denom>1e-28,denom,1.0)
 s=(bb*ee-cc*dd)/safe; t=(aa*ee-bb*dd)/safe
 valid=(denom>1e-28)&(s>=0)&(s<=1)&(t>=0)&(t<=1)
 options=[(s,t,valid),(np.zeros_like(dd),np.clip(ee/cc,0,1),None),(np.ones_like(dd),np.clip((ee+bb)/cc,0,1),None),(np.clip(-dd/aa,0,1),np.zeros_like(dd),None),(np.clip((bb-dd)/aa,0,1),np.ones_like(dd),None)]
 best=(float('inf'),None,None)
 for s,t,valid in options:
  pa=start_a+s[:,:,None]*vec_a; pb=start_b+t[:,:,None]*vec_b
  d2=np.sum((pa-pb)**2,axis=2)
  if valid is not None: d2=np.where(valid,d2,np.inf)
  idx=np.unravel_index(np.argmin(d2),d2.shape)
  if d2[idx]<best[0]: best=(float(d2[idx]),pa[idx].copy(),pb[idx].copy())
 return best
def crossing(segments,triangles):
 origin=triangles[:,0]; e1=triangles[:,1]-origin; e2=triangles[:,2]-origin
 normal=np.cross(e1,e2)
 start=segments[:,0]; direction=segments[:,1]-start
 numer=np.einsum('sfi,fi->sf',origin[None,:,:]-start[:,None,:],normal)
 denom=np.einsum('si,fi->sf',direction,normal)
 parameter=numer/np.where(np.abs(denom)>1e-25,denom,1)
 points=start[:,None,:]+parameter[:,:,None]*direction[:,None,:]
 diff=points-origin[None,:,:]
 aa=np.sum(e1*e1,axis=1); bb=np.sum(e1*e2,axis=1); cc=np.sum(e2*e2,axis=1)
 dd=np.einsum('sfi,fi->sf',diff,e1); ee=np.einsum('sfi,fi->sf',diff,e2)
 det=aa*cc-bb*bb
 u=(cc*dd-bb*ee)/det; v=(aa*ee-bb*dd)/det
 valid=(np.abs(denom)>1e-25)&(parameter>=0)&(parameter<=1)&(u>=-1e-13)&(v>=-1e-13)&(u+v<=1+1e-13)
 if np.any(valid):
  idx=np.argwhere(valid)[0]; return points[tuple(idx)].copy()
 return None
def surface_distance(geom_a,geom_b):
 points_a,tri_a,edge_a=geom_a; points_b,tri_b,edge_b=geom_b
 triangles_a=points_a[tri_a]; triangles_b=points_b[tri_b]; segments_a=points_a[edge_a]; segments_b=points_b[edge_b]
 for seg,tri in [(segments_a,triangles_b),(segments_b,triangles_a)]:
  hit=crossing(seg,tri)
  if hit is not None: return (0.0,hit,hit,'intersection')
 fwd=interior_projection(points_a,triangles_b); rev=interior_projection(points_b,triangles_a); edge=edge_distances(segments_a,segments_b)
 choices=[(*fwd,'vertex-face'),(rev[0],rev[2],rev[1],'face-vertex'),(*edge,'edge-edge')]
 best=min(choices,key=lambda x:x[0]); return (np.sqrt(best[0]),best[1],best[2],best[3])
start_time=time.monotonic()
results=[]
for name,geom in geoms.items():
 if name!='Target': results.append((name,*surface_distance(target,geom)))
results.sort(key=lambda x:x[1])
print('elapsed',time.monotonic()-start_time,'tested',len(results))
for row in results: print(row[0],format(row[1],'.12f'),row[4])
for row in results[:2]: print('witness',row[0],row[2].tolist(),row[3].tolist())