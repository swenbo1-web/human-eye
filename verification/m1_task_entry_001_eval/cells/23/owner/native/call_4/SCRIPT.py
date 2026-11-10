def point_tri_min(points,triangles):
 point=points[:,None,:]; a=triangles[None,:,0,:]; b=triangles[None,:,1,:]; c=triangles[None,:,2,:]
 ab=b-a; ac=c-a; ap=point-a
 normal=np.cross(ab,ac); normal_sq=np.sum(normal*normal,axis=-1)
 projected=point-(np.sum(ap*normal,axis=-1)/normal_sq)[...,None]*normal
 vp=projected-a
 d00=np.sum(ab*ab,axis=-1);d01=np.sum(ab*ac,axis=-1);d11=np.sum(ac*ac,axis=-1)
 d20=np.sum(vp*ab,axis=-1);d21=np.sum(vp*ac,axis=-1);den=d00*d11-d01*d01
 bary_b=(d11*d20-d01*d21)/den;bary_c=(d00*d21-d01*d20)/den
 inside=(bary_b>=-1e-12)&(bary_c>=-1e-12)&(bary_b+bary_c<=1+1e-12)
 dist=np.where(inside,np.sum((point-projected)**2,axis=-1),np.inf)
 best=np.unravel_index(np.argmin(dist),dist.shape)
 return float(dist[best]),points[best[0]],projected[best]
def unique_edges(faces):
 return np.unique(np.sort(np.concatenate([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]]),axis=1),axis=0)
def edge_min(va,fa,vb,fb):
 ea=va[unique_edges(fa)]; eb=vb[unique_edges(fb)]
 p=ea[:,None,0,:]; q=eb[None,:,0,:];u=ea[:,None,1,:]-p;v=eb[None,:,1,:]-q;w=p-q
 aa=np.sum(u*u,axis=-1);bb=np.sum(u*v,axis=-1);cc=np.sum(v*v,axis=-1);dd=np.sum(u*w,axis=-1);ee=np.sum(v*w,axis=-1)
 denom=aa*cc-bb*bb
 ss=np.divide(bb*ee-cc*dd,denom,out=np.zeros_like(denom),where=denom>1e-30)
 tt=np.divide(aa*ee-bb*dd,denom,out=np.zeros_like(denom),where=denom>1e-30)
 choices=[(ss,tt,(ss>=0)&(ss<=1)&(tt>=0)&(tt<=1)&(denom>1e-30)),(np.zeros_like(denom),np.clip(ee/cc,0,1),True),(np.ones_like(denom),np.clip((ee+bb)/cc,0,1),True),(np.clip(-dd/aa,0,1),np.zeros_like(denom),True),(np.clip((bb-dd)/aa,0,1),np.ones_like(denom),True)]
 best=(np.inf,None,None)
 for s,t,valid in choices:
  pa=p+s[...,None]*u;pb=q+t[...,None]*v;dist=np.where(valid,np.sum((pa-pb)**2,axis=-1),np.inf);idx=np.unravel_index(np.argmin(dist),dist.shape)
  if dist[idx]<best[0]:best=(float(dist[idx]),pa[idx],pb[idx])
 return best
def winding(points,triangles):
 vec=triangles[None,:,:,:]-points[:,None,None,:];a,b,c=vec[:,:,0],vec[:,:,1],vec[:,:,2]
 la=np.linalg.norm(a,axis=-1);lb=np.linalg.norm(b,axis=-1);lc=np.linalg.norm(c,axis=-1)
 numerator=np.sum(a*np.cross(b,c),axis=-1)
 denominator=la*lb*lc+np.sum(a*b,axis=-1)*lc+np.sum(b*c,axis=-1)*la+np.sum(c*a,axis=-1)*lb
 return np.sum(2*np.arctan2(numerator,denominator),axis=1)/(4*np.pi)
def crossing_count(va,fa,vb,fb):
 edges=va[unique_edges(fa)];tri=vb[fb];p=edges[:,None,0];direction=edges[:,None,1]-p;a=tri[None,:,0];e1=tri[None,:,1]-a;e2=tri[None,:,2]-a
 h=np.cross(direction,e2);det=np.sum(e1*h,axis=-1);ok=np.abs(det)>1e-20
 inv=np.divide(1.,det,out=np.zeros_like(det),where=ok);s=p-a;u=inv*np.sum(s*h,axis=-1);q=np.cross(s,e1);v=inv*np.sum(direction*q,axis=-1);t=inv*np.sum(e2*q,axis=-1)
 hits=ok&(u>=-1e-10)&(v>=-1e-10)&(u+v<=1+1e-10)&(t>=-1e-10)&(t<=1+1e-10)
 strict=hits&(u>1e-8)&(v>1e-8)&(u+v<1-1e-8)&(t>1e-8)&(t<1-1e-8)
 return int(hits.sum()),int(strict.sum())
va,fa=geo['Part_49']
for name in names[1:]:
 vb,fb=geo[name]
 results=[point_tri_min(va,vb[fb]),point_tri_min(vb,va[fa]),edge_min(va,fa,vb,fb)]
 best=min(results,key=lambda item:item[0])
 print(name,'surface_distance_mm',np.sqrt(best[0])*1000,'closest_points_mm',best[1]*1000,best[2]*1000,'crossings',crossing_count(va,fa,vb,fb),crossing_count(vb,fb,va,fa))
 wind_b=winding(vb,va[fa]);wind_a=winding(va,vb[fb]);print('candidate_vertices_winding',np.round(wind_b,9),'target_inside_vertices',int((np.abs(wind_a)>.9).sum()))