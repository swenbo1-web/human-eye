def edge_hits(es,tris):
 starts,ends=es; p=starts[:,None,:]; direction=ends[:,None,:]-p
 a=tris[None,:,0,:]; u=tris[None,:,1,:]-a; v=tris[None,:,2,:]-a
 h=np.cross(direction,v); det=np.sum(u*h,2)
 scale=np.linalg.norm(direction,axis=2)*np.linalg.norm(u,axis=2)*np.linalg.norm(v,axis=2)
 stable=np.abs(det)>1e-12*scale
 inv=np.divide(1.,det,out=np.zeros_like(det),where=stable)
 delta=p-a; bary1=inv*np.sum(delta*h,2); cross=np.cross(delta,u)
 bary2=inv*np.sum(direction*cross,2); along=inv*np.sum(v*cross,2)
 valid=stable&(bary1>=0)&(bary2>=0)&(bary1+bary2<=1)&(along>=0)&(along<=1)
 for row,col in np.argwhere(valid):
  ep=p[row,0]+along[row,col]*direction[row,0]
  fp=tris[col,0]+bary1[row,col]*(tris[col,1]-tris[col,0])+bary2[row,col]*(tris[col,2]-tris[col,0])
  if np.linalg.norm(ep-fp)<1e-10: return ep
 return None
print('current_geometry_matches',fingerprint(acquire())==geom_sig)
results={name:surface_dist(geom['Target'],g) for name,g in geom.items() if name!='Target'}
for name,result in sorted(results.items(),key=lambda item:item[1][0])[:6]:
 print(name,format(result[0],'.12f'),result[3],'points',result[1].tolist(),result[2].tolist())
print('all_candidates',len(results),'intersections',sum(r[0]==0 for r in results.values()),'max_distance',max(r[0] for r in results.values()))
