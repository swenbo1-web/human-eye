deps=bpy.context.evaluated_depsgraph_get()
def getgeom(obj):
 ev=obj.evaluated_get(deps); mesh=ev.to_mesh()
 try:
  mesh.calc_loop_triangles()
  local=np.array([tuple(v.co) for v in mesh.vertices],dtype=np.float64)
  mat=np.array(ev.matrix_world,dtype=np.float64)
  verts=local@mat[:3,:3].T+mat[:3,3]
  tri=np.array([tuple(t.vertices) for t in mesh.loop_triangles],dtype=int)
  edges=np.array(sorted({tuple(sorted((int(t[i]),int(t[(i+1)%3])))) for t in tri for i in range(3)}),dtype=int)
  return verts,tri,edges
 finally: ev.to_mesh_clear()
geoms={obj.name:getgeom(obj) for obj in meshes}
def pointfaces(points, triangles):
 origin=triangles[:,0]; side1=triangles[:,1]-origin; side2=triangles[:,2]-origin
 normal=np.cross(side1,side2); norm2=np.einsum('ij,ij->i',normal,normal)
 delta=points[:,None,:]-origin[None,:,:]
 heights=np.einsum('ptj,tj->pt',delta,normal)/np.where(norm2>0,norm2,1)[None,:]
 proj=points[:,None,:]-heights[:,:,None]*normal[None,:,:]
 rel=proj-origin[None,:,:]
 aa=np.einsum('ij,ij->i',side1,side1); ab=np.einsum('ij,ij->i',side1,side2); bb=np.einsum('ij,ij->i',side2,side2)
 ra=np.einsum('ptj,tj->pt',rel,side1); rb=np.einsum('ptj,tj->pt',rel,side2)
 den=aa*bb-ab*ab; safe=np.where(den>0,den,1)
 u=(ra*bb-rb*ab)/safe; v=(rb*aa-ra*ab)/safe
 valid=(den[None,:]>0)&(u>=0)&(v>=0)&(u+v<=1)
 dist2=np.where(valid,heights*heights*norm2[None,:],np.inf)
 index=np.unravel_index(np.argmin(dist2),dist2.shape)
 return float(dist2[index]),points[index[0]],proj[index]
def edgesdistance(first,second):
 start=first[:,0,None,:]; end=second[None,:,0,:]
 direction1=first[:,1,None,:]-start; direction2=second[None,:,1,:]-end
 delta=start-end
 aa=np.sum(direction1*direction1,axis=2); bb=np.sum(direction1*direction2,axis=2); cc=np.sum(direction2*direction2,axis=2)
 dd=np.sum(direction1*delta,axis=2); ee=np.sum(direction2*delta,axis=2)
 denominator=aa*cc-bb*bb
 ss=(bb*ee-cc*dd)/np.where(denominator>0,denominator,1)
 tt=(aa*ee-bb*dd)/np.where(denominator>0,denominator,1)
 valid=(denominator>0)&(ss>=0)&(ss<=1)&(tt>=0)&(tt<=1)
 choices=[(ss,tt,valid),(np.zeros_like(bb),np.clip(ee/np.where(cc>0,cc,1),0,1),True),(np.ones_like(bb),np.clip((ee+bb)/np.where(cc>0,cc,1),0,1),True),(np.clip(-dd/np.where(aa>0,aa,1),0,1),np.zeros_like(bb),True),(np.clip((bb-dd)/np.where(aa>0,aa,1),0,1),np.ones_like(bb),True)]
 best=(float('inf'),None,None)
 for ss,tt,valid in choices:
  firstpt=start+ss[:,:,None]*direction1; secondpt=end+tt[:,:,None]*direction2
  sq=np.where(valid,np.sum((firstpt-secondpt)**2,axis=2),np.inf)
  index=np.unravel_index(np.argmin(sq),sq.shape)
  if sq[index]<best[0]: best=(float(sq[index]),firstpt[index],secondpt[index])
 return best
def crosses(edges,triangles):
 start=edges[:,0,None,:]; direct=edges[:,1,None,:]-start
 corner=triangles[None,:,0,:]; side1=triangles[None,:,1,:]-corner; side2=triangles[None,:,2,:]-corner
 cross=np.cross(direct,side2); det=np.sum(side1*cross,axis=2)
 inv=1/np.where(det!=0,det,1)
 delta=start-corner; u=np.sum(delta*cross,axis=2)*inv
 q=np.cross(delta,side1); v=np.sum(direct*q,axis=2)*inv; along=np.sum(side2*q,axis=2)*inv
 hit=(det!=0)&(u>=0)&(v>=0)&(u+v<=1)&(along>=0)&(along<=1)
 if np.any(hit):
  index=tuple(np.argwhere(hit)[0]); return (start+along[:,:,None]*direct)[index]
 return None
targetverts,targetfaces,targetedges=geoms['Target']; targettris=targetverts[targetfaces]; targetsegs=targetverts[targetedges]
results=[]
for name,(verts,faces,edges) in geoms.items():
 if name=='Target': continue
 triangles=verts[faces]; segments=verts[edges]
 hit=crosses(targetsegs,triangles)
 if hit is None: hit=crosses(segments,targettris)
 if hit is not None: best=(0.,hit,hit)
 else:
  forward=pointfaces(targetverts,triangles); backward=pointfaces(verts,targettris); backward=(backward[0],backward[2],backward[1])
  best=min([forward,backward,edgesdistance(targetsegs,segments)],key=lambda item:item[0])
 results.append((math.sqrt(best[0]),name,best[1].tolist(),best[2].tolist()))
results.sort()
print('Complete candidates:',len(results))
for result in results: print(result)
print('target triangles:',len(targetfaces),'other triangle counts:',sorted(set(len(g[1]) for name,g in geoms.items() if name!='Target')))