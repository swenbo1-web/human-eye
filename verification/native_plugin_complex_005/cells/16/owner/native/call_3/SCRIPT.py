deps=bpy.context.evaluated_depsgraph_get()
geometry={}
for obj in objs:
 ev=obj.evaluated_get(deps); mesh=ev.to_mesh(); mesh.calc_loop_triangles()
 local=np.array([v.co[:] for v in mesh.vertices],dtype=np.float64)
 matrix=np.array(ev.matrix_world,dtype=np.float64)
 verts=local@matrix[:3,:3].T+matrix[:3,3]
 faces=np.array([t.vertices[:] for t in mesh.loop_triangles],dtype=np.int64)
 edges=np.unique(np.sort(np.concatenate([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]]),axis=1),axis=0)
 geometry[obj.name]=(verts,faces,edges)
 ev.to_mesh_clear()
def point_tri(points, triangles):
 a=triangles[None,:,0,:]; ab=triangles[None,:,1,:]-a; ac=triangles[None,:,2,:]-a
 delta=points[:,None,:]-a
 normals=np.cross(ab,ac); norm2=np.sum(normals*normals,axis=-1)
 plane=np.sum(delta*normals,axis=-1)/norm2
 projection=delta-plane[...,None]*normals
 aa=np.sum(ab*ab,axis=-1); bb=np.sum(ab*ac,axis=-1); cc=np.sum(ac*ac,axis=-1)
 dd=np.sum(projection*ab,axis=-1); ee=np.sum(projection*ac,axis=-1)
 denom=aa*cc-bb*bb
 uu=(cc*dd-bb*ee)/denom; vv=(aa*ee-bb*dd)/denom
 inside=(uu>=0)&(vv>=0)&(uu+vv<=1)
 sq=np.where(inside,plane*plane*norm2,np.inf)
 index=np.unravel_index(np.argmin(sq),sq.shape)
 return float(sq[index]),index

def edge_pair(sega,segb):
 origin=sega[:,None,0,:]; other=segb[None,:,0,:]
 first=sega[:,None,1,:]-origin; second=segb[None,:,1,:]-other; delta=origin-other
 aa=np.sum(first*first,axis=-1); bb=np.sum(first*second,axis=-1); cc=np.sum(second*second,axis=-1)
 dd=np.sum(first*delta,axis=-1); ee=np.sum(second*delta,axis=-1)
 denom=aa*cc-bb*bb
 safe=np.where(denom>1e-28,denom,1)
 ss=(bb*ee-cc*dd)/safe; tt=(aa*ee-bb*dd)/safe
 valid=(denom>1e-28)&(ss>=0)&(ss<=1)&(tt>=0)&(tt<=1)
 sq=np.where(valid,np.sum((delta+ss[...,None]*first-tt[...,None]*second)**2,axis=-1),np.inf)
 for ss,tt in [(np.zeros_like(ee),np.clip(ee/cc,0,1)),(np.ones_like(ee),np.clip((ee+bb)/cc,0,1)),(np.clip(-dd/aa,0,1),np.zeros_like(dd)),(np.clip((bb-dd)/aa,0,1),np.ones_like(dd))]:
  sq=np.minimum(sq,np.sum((delta+ss[...,None]*first-tt[...,None]*second)**2,axis=-1))
 index=np.unravel_index(np.argmin(sq),sq.shape)
 return float(sq[index]),index

def crossing(segments,triangles):
 origin=segments[:,None,0,:]; direction=segments[:,None,1,:]-origin
 aa=triangles[None,:,0,:]; ab=triangles[None,:,1,:]-aa; ac=triangles[None,:,2,:]-aa
 cross=np.cross(direction,ac); det=np.sum(ab*cross,axis=-1)
 valid=np.abs(det)>1e-18; inv=np.where(valid,1/np.where(valid,det,1),0)
 delta=origin-aa; uu=np.sum(delta*cross,axis=-1)*inv
 q=np.cross(delta,ab); vv=np.sum(direction*q,axis=-1)*inv; along=np.sum(ac*q,axis=-1)*inv
 hits=valid&(uu>=0)&(vv>=0)&(uu+vv<=1)&(along>=0)&(along<=1)
 return int(np.count_nonzero(hits))

target_verts,target_faces,target_edges=geometry['Target']; target_tris=target_verts[target_faces]; target_segs=target_verts[target_edges]
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
print('evaluated_geometry',len(geometry),'triangle_counts',sorted(set(len(item[1]) for item in geometry.values())))
for result in results:print(result)
print('elapsed',time.time()-start_time)