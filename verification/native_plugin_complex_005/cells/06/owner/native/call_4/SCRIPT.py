def dot(a,b): return np.sum(a*b,axis=-1)
def point_face(points,triangles):
 p=points[:,None,:]; a=triangles[None,:,0,:]; u=triangles[None,:,1,:]-a; v=triangles[None,:,2,:]-a
 w=p-a; uu=dot(u,u); uv=dot(u,v); vv=dot(v,v); wu=dot(w,u); wv=dot(w,v); den=uu*vv-uv*uv
 s=np.divide(vv*wu-uv*wv,den,out=np.zeros_like(wu),where=den>1e-30)
 t=np.divide(uu*wv-uv*wu,den,out=np.zeros_like(wu),where=den>1e-30)
 q=a+s[...,None]*u+t[...,None]*v
 d2=dot(p-q,p-q); d2=np.where((den>1e-30)&(s>=0)&(t>=0)&(s+t<=1),d2,np.inf)
 ix=np.unravel_index(np.argmin(d2),d2.shape)
 return float(d2[ix]), points[ix[0]],q[ix],('vertex_face',int(ix[0]),int(ix[1]))
def edge_edge(edges1,edges2):
 a=edges1[:,None,0,:]; b=edges2[None,:,0,:]; u=edges1[:,None,1,:]-a; v=edges2[None,:,1,:]-b; w=a-b
 aa=dot(u,u); bb=dot(u,v); cc=dot(v,v); dd=dot(u,w); ee=dot(v,w); den=aa*cc-bb*bb
 shape=den.shape
 safea=np.where(aa>0,aa,1); safec=np.where(cc>0,cc,1)
 s0=np.divide(bb*ee-cc*dd,den,out=np.zeros(shape),where=den>1e-30)
 t0=np.divide(aa*ee-bb*dd,den,out=np.zeros(shape),where=den>1e-30)
 choices=[(s0,t0,(den>1e-30)&(s0>=0)&(s0<=1)&(t0>=0)&(t0<=1)),(np.zeros(shape),np.clip(ee/safec,0,1),True),(np.ones(shape),np.clip((ee+bb)/safec,0,1),True),(np.clip(-dd/safea,0,1),np.zeros(shape),True),(np.clip((bb-dd)/safea,0,1),np.ones(shape),True)]
 best=(np.inf,None,None,None)
 for s,t,valid in choices:
  p=a+s[...,None]*u; q=b+t[...,None]*v; d2=np.where(valid,dot(p-q,p-q),np.inf); ix=np.unravel_index(np.argmin(d2),shape)
  if d2[ix]<best[0]: best=(float(d2[ix]),p[ix],q[ix],('edge_edge',int(ix[0]),int(ix[1]),float(s[ix]),float(t[ix])))
 return best
def crossing(edges,triangles):
 p=edges[:,None,0,:]; direction=edges[:,None,1,:]-p; a=triangles[None,:,0,:]; u=triangles[None,:,1,:]-a; v=triangles[None,:,2,:]-a
 h=np.cross(direction,v); determinant=dot(u,h); valid=np.abs(determinant)>1e-25
 inv=np.divide(1.,determinant,out=np.zeros_like(determinant),where=valid); w=p-a
 s=dot(w,h)*inv; q=np.cross(w,u); t=dot(direction,q)*inv; r=dot(v,q)*inv
 hits=valid&(s>=0)&(t>=0)&(s+t<=1)&(r>=0)&(r<=1)
 inds=np.argwhere(hits)
 if len(inds):
  i,j=inds[0]; pt=p[i,0]+r[i,j]*direction[i,0];return (0.,pt,pt,('intersection',int(i),int(j),float(r[i,j])))
 return None
def mesh_distance(g1,g2):
 v1=g1['v']; v2=g2['v']; tri1=v1[g1['t']];tri2=v2[g2['t']];ed1=v1[g1['e']];ed2=v2[g2['e']]
 hit=crossing(ed1,tri2)
 if hit is not None:return hit
 hit=crossing(ed2,tri1)
 if hit is not None:return (hit[0],hit[2],hit[1],('reverse',hit[3]))
 choices=[point_face(v1,tri2),edge_edge(ed1,ed2)]
 rev=point_face(v2,tri1); choices.append((rev[0],rev[2],rev[1],('reverse',rev[3])))
 return min(choices,key=lambda x:x[0])
results={}
for name,g in geom.items():
 if name!='Target':results[name]=mesh_distance(tg,g)
ranking=sorted(results,key=lambda n:results[n][0])
for name in ranking:print(name,'distance',format(np.sqrt(results[name][0]),'.15g'),'feature',results[name][3])
print('elapsed',time.time()-start)