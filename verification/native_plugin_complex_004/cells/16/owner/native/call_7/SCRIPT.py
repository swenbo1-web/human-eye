def crossings(starts,ends,triangles):
 origin=triangles[:,0];edge_u=triangles[:,1]-origin;edge_v=triangles[:,2]-origin
 direction=ends-starts
 cross=np.cross(direction[:,None,:],edge_v[None,:,:]);det=np.einsum('ijk,jk->ij',cross,edge_u)
 scale=np.linalg.norm(direction,axis=1)[:,None]*np.linalg.norm(edge_u,axis=1)[None,:]*np.linalg.norm(edge_v,axis=1)[None,:]
 valid=np.abs(det)>1e-12*scale;safe=np.where(valid,det,1)
 delta=starts[:,None,:]-origin[None,:,:]
 bary_u=np.sum(delta*cross,axis=2)/safe
 cross2=np.cross(delta,edge_u[None,:,:])
 bary_v=np.einsum('ijk,ik->ij',cross2,direction)/safe
 parameter=np.einsum('ijk,jk->ij',cross2,edge_v)/safe
 valid &= (bary_u>=0)&(bary_v>=0)&(bary_u+bary_v<=1)&(parameter>=0)&(parameter<=1)
 if np.any(valid):
  row,col=np.argwhere(valid)[0];point=starts[row]+parameter[row,col]*direction[row]
  return 0.,point,point,(int(row),int(col))
 return None
assert unchanged
results={name:surface_distance(target,geom) for name,geom in geometry.items() if name!='Target'}
ordered=sorted(results.items(),key=lambda item:item[1][0])
print('coverage',len(results),'meshes; unresolved 0')
for name,entry in ordered:
 print(name,format(math.sqrt(entry[0]),'.12f'))
name,entry=ordered[0]
print('winner',name,'feature',entry[4],entry[3])
print('point on Target',entry[1].tolist(),'point on winner',entry[2].tolist(),'distance',np.linalg.norm(entry[1]-entry[2]))
print('minimum triangle double area',min(np.linalg.norm(np.cross(g['t'][:,1]-g['t'][:,0],g['t'][:,2]-g['t'][:,0]),axis=1).min() for g in geometry.values()))
