import numpy as np
from collections import Counter
names=['Target','Peer_000','Competing_001','Near_003']
geoms={}
deps=bpy.context.evaluated_depsgraph_get()
for name in names:
 obj=bpy.data.objects[name].evaluated_get(deps)
 mesh=obj.to_mesh()
 mesh.calc_loop_triangles()
 matrix=np.array(obj.matrix_world,dtype=np.float64)
 verts=np.array([v.co[:] for v in mesh.vertices],dtype=np.float64)@matrix[:3,:3].T+matrix[:3,3]
 faces=np.array([t.vertices[:] for t in mesh.loop_triangles],dtype=int)
 edges=np.array(list({tuple(sorted((int(face[k]),int(face[(k+1)%3])))) for face in faces for k in range(3)}))
 counts=Counter(tuple(sorted((int(face[k]),int(face[(k+1)%3])))) for face in faces for k in range(3))
 geoms[name]=(verts,faces,edges)
 print(name,'world_bounds',verts.min(axis=0).tolist(),verts.max(axis=0).tolist(),'closed_manifold_edges',all(v==2 for v in counts.values()))
 obj.to_mesh_clear()

def closest_vertex_face(points,triangles):
 best=(float('inf'),None,None)
 for start in range(0,len(points),64):
  pts=points[start:start+64,None,:]
  origin=triangles[None,:,0,:]; edge1=triangles[None,:,1,:]-origin; edge2=triangles[None,:,2,:]-origin
  normal=np.cross(edge1,edge2); norm2=np.sum(normal*normal,axis=-1)
  height=np.sum((pts-origin)*normal,axis=-1)/norm2
  projection=pts-height[...,None]*normal
  offset=projection-origin
  dot11=np.sum(edge1*edge1,axis=-1); dot12=np.sum(edge1*edge2,axis=-1); dot22=np.sum(edge2*edge2,axis=-1)
  dotp1=np.sum(offset*edge1,axis=-1); dotp2=np.sum(offset*edge2,axis=-1)
  denom=dot11*dot22-dot12*dot12
  bary1=(dot22*dotp1-dot12*dotp2)/denom; bary2=(dot11*dotp2-dot12*dotp1)/denom
  dist2=np.where((bary1>=0)&(bary2>=0)&(bary1+bary2<=1),height*height*norm2,np.inf)
  idx=np.unravel_index(np.argmin(dist2),dist2.shape)
  if dist2[idx]<best[0]: best=(float(dist2[idx]),pts[idx[0],0].copy(),projection[idx].copy())
 return best

def closest_edges(va,ea,vb,eb):
 best=(float('inf'),None,None)
 other_start=vb[eb[:,0]][None,:,:]; other_delta=(vb[eb[:,1]]-vb[eb[:,0]])[None,:,:]
 cc=np.sum(other_delta*other_delta,axis=-1)
 for start in range(0,len(ea),64):
  block=ea[start:start+64]
  first=va[block[:,0]][:,None,:]; direction=(va[block[:,1]]-va[block[:,0]])[:,None,:]
  difference=first-other_start
  aa=np.sum(direction*direction,axis=-1); bb=np.sum(direction*other_delta,axis=-1); dd=np.sum(direction*difference,axis=-1); ee=np.sum(other_delta*difference,axis=-1)
  denom=aa*cc-bb*bb
  ss=np.divide(bb*ee-cc*dd,denom,out=np.zeros_like(denom),where=denom>1e-28)
  ss=np.clip(ss,0,1); tt=(bb*ss+ee)/cc
  ss=np.where(tt<0,np.clip(-dd/aa,0,1),ss)
  ss=np.where(tt>1,np.clip((bb-dd)/aa,0,1),ss)
  tt=np.clip(tt,0,1)
  pa=first+ss[...,None]*direction; pb=other_start+tt[...,None]*other_delta
  dist2=np.sum((pa-pb)**2,axis=-1); idx=np.unravel_index(np.argmin(dist2),dist2.shape)
  if dist2[idx]<best[0]: best=(float(dist2[idx]),pa[idx].copy(),pb[idx].copy())
 return best

def intersections(verts,edges,triangles):
 hits=[]
 origin=triangles[None,:,0,:]; edge1=triangles[None,:,1,:]-origin; edge2=triangles[None,:,2,:]-origin
 for start in range(0,len(edges),64):
  block=edges[start:start+64]; base=verts[block[:,0]][:,None,:]; direction=(verts[block[:,1]]-verts[block[:,0]])[:,None,:]
  cross=np.cross(direction,edge2); det=np.sum(edge1*cross,axis=-1)
  inv=np.divide(1.,det,out=np.zeros_like(det),where=np.abs(det)>1e-24)
  delta=base-origin; uu=np.sum(delta*cross,axis=-1)*inv
  qq=np.cross(delta,edge1); vv=np.sum(direction*qq,axis=-1)*inv; tt=np.sum(edge2*qq,axis=-1)*inv
  mask=(np.abs(det)>1e-24)&(uu>=0)&(vv>=0)&(uu+vv<=1)&(tt>=0)&(tt<=1)
  if np.any(mask):
   idx=tuple(np.argwhere(mask)[0]); return (base+tt[...,None]*direction)[idx].tolist()
 return None

def winding(point,triangles):
 delta=triangles-point
 lengths=np.linalg.norm(delta,axis=-1)
 num=np.einsum('ij,ij->i',delta[:,0],np.cross(delta[:,1],delta[:,2]))
 den=np.prod(lengths,axis=1)+np.einsum('ij,ij->i',delta[:,0],delta[:,1])*lengths[:,2]+np.einsum('ij,ij->i',delta[:,1],delta[:,2])*lengths[:,0]+np.einsum('ij,ij->i',delta[:,2],delta[:,0])*lengths[:,1]
 return float(np.sum(2*np.arctan2(num,den))/(4*np.pi))

va,fa,ea=geoms['Target']; results={}
for name in names[1:]:
 vb,fb,eb=geoms[name]
 cand1=closest_vertex_face(va,vb[fb]); reverse=closest_vertex_face(vb,va[fa]); cand2=(reverse[0],reverse[2],reverse[1]); cand3=closest_edges(va,ea,vb,eb)
 best=min([cand1,cand2,cand3],key=lambda item:item[0])
 hit=intersections(va,ea,vb[fb]) or intersections(vb,eb,va[fa])
 wa=winding(va[0],vb[fb]); wb=winding(vb[0],va[fa])
 results[name]={'distance_m':float(np.sqrt(best[0])),'target_point_m':best[1].tolist(),'candidate_point_m':best[2].tolist(),'intersection_point':hit,'winding_target_in_other':wa,'winding_other_in_target':wb,'feature_type':['vertex-face','face-vertex','edge-edge'][[cand1,cand2,cand3].index(best)] if False else int(np.argmin([cand1[0],cand2[0],cand3[0]]))}
 print(name,results[name])
