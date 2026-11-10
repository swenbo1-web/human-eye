import hashlib

def acquire():
 out={}
 for obj in bpy.context.scene.objects:
  if obj.type!='MESH': continue
  eo=obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
  mesh=eo.data
  mesh.calc_loop_triangles()
  local=np.array([v.co[:] for v in mesh.vertices],dtype=np.float64)
  mat=np.array(eo.matrix_world,dtype=np.float64)
  world=local@mat[:3,:3].T+mat[:3,3]
  faces=np.array([tuple(t.vertices) for t in mesh.loop_triangles],dtype=np.int64).reshape(-1,3)
  out[obj.name]=(world,faces)
 return out
geom=acquire()
def fingerprint(g):
 return {name:hashlib.sha256(v.tobytes()+f.tobytes()).hexdigest() for name,(v,f) in g.items()}
geom_sig=fingerprint(geom)
print('meshes',len(geom),'triangles',sum(len(f) for v,f in geom.values()))
for name in ['Target','Peer_000','Competing_001','Near_003']:
 v,f=geom[name]; print(name,'bounds',v.min(0).tolist(),v.max(0).tolist(),'triangles',len(f))

# Pairwise point/triangle distances, including projected face interiors.
def point_tri(points,tris):
 p=points[:,None,:]; a=tris[None,:,0,:]; u=tris[None,:,1,:]-a; v=tris[None,:,2,:]-a
 w=p-a
 uu=np.sum(u*u,2); uv=np.sum(u*v,2); vv=np.sum(v*v,2)
 wu=np.sum(w*u,2); wv=np.sum(w*v,2); den=uu*vv-uv*uv
 s=(wu*vv-wv*uv)/den; t=(wv*uu-wu*uv)/den
 q=a+s[:,:,None]*u+t[:,:,None]*v
 d=np.sum((p-q)**2,2); d[(s<0)|(t<0)|(s+t>1)]=np.inf
 idx=np.unravel_index(np.argmin(d),d.shape)
 return float(d[idx]),points[idx[0]].copy(),q[idx].copy()

def edges(tris):
 return tris[:,[0,1,2],:].reshape(-1,3),tris[:,[1,2,0],:].reshape(-1,3)

def edge_edge(e1,e2):
 p,p_end=e1; q,q_end=e2
 p=p[:,None,:]; q=q[None,:,:]; u=p_end[:,None,:]-p; v=q_end[None,:,:]-q; w=p-q
 a=np.sum(u*u,2); b=np.sum(u*v,2); c=np.sum(v*v,2); d=np.sum(u*w,2); e=np.sum(v*w,2)
 den=a*c-b*b
 s=np.divide(b*e-c*d,den,out=np.zeros_like(den),where=den>1e-28)
 t=np.divide(a*e-b*d,den,out=np.zeros_like(den),where=den>1e-28)
 candidates=[(s,t,(s>=0)&(s<=1)&(t>=0)&(t<=1)&(den>1e-28)),(np.zeros_like(den),np.clip(e/c,0,1),True),(np.ones_like(den),np.clip((e+b)/c,0,1),True),(np.clip(-d/a,0,1),np.zeros_like(den),True),(np.clip((b-d)/a,0,1),np.ones_like(den),True)]
 best=(float('inf'),None,None)
 for s,t,valid in candidates:
  pp=p+s[:,:,None]*u; qq=q+t[:,:,None]*v
  dist=np.where(valid,np.sum((pp-qq)**2,2),np.inf)
  ix=np.unravel_index(np.argmin(dist),dist.shape)
  if dist[ix]<best[0]: best=(float(dist[ix]),pp[ix].copy(),qq[ix].copy())
 return best

def edge_hits(es,tris):
 p,pend=es; p=p[:,None,:]; direction=pend[:,None,:]-p
 a=tris[None,:,0,:]; u=tris[None,:,1,:]-a; v=tris[None,:,2,:]-a
 h=np.cross(direction,v); det=np.sum(u*h,2)
 inv=np.divide(1.,det,out=np.zeros_like(det),where=np.abs(det)>1e-25)
 s=p-a; bary1=inv*np.sum(s*h,2); cross=np.cross(s,u)
 bary2=inv*np.sum(direction*cross,2); along=inv*np.sum(v*cross,2)
 valid=(np.abs(det)>1e-25)&(bary1>=0)&(bary2>=0)&(bary1+bary2<=1)&(along>=0)&(along<=1)
 loc=np.argwhere(valid)
 if len(loc):
  row,col=loc[0]; return (p+along[:,:,None]*direction)[row,col].copy()
 return None

def surface_dist(g1,g2):
 v1,f1=g1; v2,f2=g2; t1=v1[f1]; t2=v2[f2]; e1=edges(t1); e2=edges(t2)
 for es,ts in [(e1,t2),(e2,t1)]:
  hit=edge_hits(es,ts)
  if hit is not None: return 0.,hit,hit,'intersection'
 candidates=[(*point_tri(v1,t2),'vertex-face'),(*((lambda r:(r[0],r[2],r[1]))(point_tri(v2,t1))),'face-vertex'),(*edge_edge(e1,e2),'edge-edge')]
 best=min(candidates,key=lambda r:r[0]); return math.sqrt(max(0,best[0])),best[1],best[2],best[3]
start=time.time()
results={name:surface_dist(geom['Target'],g) for name,g in geom.items() if name!='Target'}
for name,result in sorted(results.items(),key=lambda item:item[1][0]):
 print(name,format(result[0],'.12f'),result[3])
print('elapsed',time.time()-start)
