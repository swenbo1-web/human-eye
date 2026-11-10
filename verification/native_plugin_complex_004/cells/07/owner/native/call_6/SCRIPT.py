def crosses(edges,triangles):
 start=edges[:,0,None,:]; direct=edges[:,1,None,:]-start
 corner=triangles[None,:,0,:]; side1=triangles[None,:,1,:]-corner; side2=triangles[None,:,2,:]-corner
 cross=np.cross(direct,side2); det=np.sum(side1*cross,axis=2)
 scale=np.linalg.norm(direct,axis=2)*np.linalg.norm(side1,axis=2)*np.linalg.norm(side2,axis=2)
 stable=np.abs(det)>1e-12*scale
 inv=1/np.where(stable,det,1)
 delta=start-corner; u=np.sum(delta*cross,axis=2)*inv
 q=np.cross(delta,side1); v=np.sum(direct*q,axis=2)*inv; along=np.sum(side2*q,axis=2)*inv
 hit=stable&(u>=0)&(v>=0)&(u+v<=1)&(along>=0)&(along<=1)
 if np.any(hit):
  index=tuple(np.argwhere(hit)[0]); return (start+along[:,:,None]*direct)[index]
 return None
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
print('candidates',len(results))
for result in results[:5]: print(result)
print('remaining min',min(r[0] for r in results[5:]))