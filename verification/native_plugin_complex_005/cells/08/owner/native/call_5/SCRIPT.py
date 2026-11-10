def edge_face_hit(first,second):
    verts,tris,edges=first; verts2,tris2,edges2=second
    origin=verts[edges[:,0]].astype(np.longdouble); direction=verts[edges[:,1]].astype(np.longdouble)-origin
    tri=verts2[tris2].astype(np.longdouble); edge1=tri[:,1]-tri[:,0]; edge2=tri[:,2]-tri[:,0]
    cross=np.cross(direction[:,None,:],edge2[None,:,:]); det=np.einsum('jk,ijk->ij',edge1,cross)
    scale=np.linalg.norm(direction,axis=1)[:,None]*np.linalg.norm(edge1,axis=1)[None,:]*np.linalg.norm(edge2,axis=1)[None,:]
    nonparallel=np.abs(det)>scale*1e-14
    safe=np.where(nonparallel,det,1); relative=origin[:,None,:]-tri[None,:,0,:]
    alpha=np.einsum('ijk,ijk->ij',relative,cross)/safe
    q=np.cross(relative,edge1[None,:,:]); beta=np.einsum('ik,ijk->ij',direction,q)/safe
    param=np.einsum('jk,ijk->ij',edge2,q)/safe
    hit=nonparallel&(alpha>=0)&(beta>=0)&(alpha+beta<=1)&(param>=0)&(param<=1)
    for edge_idx,tri_idx in np.argwhere(hit):
        pa=origin[edge_idx]+param[edge_idx,tri_idx]*direction[edge_idx]
        pb=tri[tri_idx,0]+alpha[edge_idx,tri_idx]*edge1[tri_idx]+beta[edge_idx,tri_idx]*edge2[tri_idx]
        if np.linalg.norm(pa-pb)<1e-10: return np.array(pa,dtype=np.float64)
    return None
results=[]
for name,geom in geometry.items():
    if name=='Target': continue
    res=surface_distance(geometry['Target'],geom)
    results.append((name,math.sqrt(res[0]),res[1].tolist(),res[2].tolist(),res[3]))
results.sort(key=lambda item:item[1])
print('recomputed_all',len(results))
for result in results[:6]: print(result)
print('Near_017',next(row for row in results if row[0]=='Near_017'))
print('others_min_max',min(r[1] for r in results[1:]),max(r[1] for r in results[1:]))