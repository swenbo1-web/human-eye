def dot(a,b): return np.sum(a*b,axis=-1)
def point_faces(points,tris):
    pp=points[:,None,:]; aa=tris[None,:,0,:]; uu=tris[None,:,1,:]-aa; vv=tris[None,:,2,:]-aa
    normal=np.cross(uu,vv); nn=dot(normal,normal)
    signed=dot(pp-aa,normal)/nn
    proj=pp-signed[...,None]*normal
    rel=proj-aa; du=dot(rel,uu); dv=dot(rel,vv); u2=dot(uu,uu); v2=dot(vv,vv); uv=dot(uu,vv)
    denom=u2*v2-uv*uv
    beta=(du*v2-dv*uv)/denom; gamma=(dv*u2-du*uv)/denom
    valid=(beta>=0)&(gamma>=0)&(beta+gamma<=1)
    ds=np.where(valid,dot(pp-proj,pp-proj),np.inf)
    idx=np.unravel_index(np.argmin(ds),ds.shape)
    best=(float(ds[idx]),points[idx[0]].copy(),proj[idx].copy(),'vertex-face')
    for edge in range(3):
        start=tris[None,:,edge,:]; vec=tris[None,:,(edge+1)%3,:]-start
        tt=np.clip(dot(pp-start,vec)/dot(vec,vec),0,1)
        qq=start+tt[...,None]*vec
        ds=dot(pp-qq,pp-qq); idx=np.unravel_index(np.argmin(ds),ds.shape)
        if ds[idx]<best[0]:best=(float(ds[idx]),points[idx[0]].copy(),qq[idx].copy(),'vertex-edge')
    return best

def edges_of(tris):
    return tris.reshape(-1,3),tris[:,[1,2,0],:].reshape(-1,3)

def crossing(starts,ends,tris):
    pp=starts[:,None,:]; direction=(ends-starts)[:,None,:]
    aa=tris[None,:,0,:]; uu=tris[None,:,1,:]-aa; vv=tris[None,:,2,:]-aa
    normal=np.cross(uu,vv); denom=dot(direction,normal)
    with np.errstate(divide='ignore',invalid='ignore'):
        param=dot(aa-pp,normal)/denom
        qq=pp+param[...,None]*direction
        rel=qq-aa; du=dot(rel,uu); dv=dot(rel,vv); u2=dot(uu,uu); v2=dot(vv,vv); uv=dot(uu,vv)
        det=u2*v2-uv*uv
        beta=(du*v2-dv*uv)/det; gamma=(dv*u2-du*uv)/det
        valid=(denom!=0)&(param>=0)&(param<=1)&(beta>=0)&(gamma>=0)&(beta+gamma<=1)
    hit=np.argwhere(valid)
    return qq[tuple(hit[0])].copy() if len(hit) else None

def mesh_distance(first,second):
    ast,aend=edges_of(first['tri']); bst,bend=edges_of(second['tri'])
    for starts,ends,tris in [(ast,aend,second['tri']),(bst,bend,first['tri'])]:
        hit=crossing(starts,ends,tris)
        if hit is not None:return (0.0,hit,hit,'intersection')
    best=point_faces(first['v'],second['tri'])
    reverse=point_faces(second['v'],first['tri'])
    if reverse[0]<best[0]:best=(reverse[0],reverse[2],reverse[1],reverse[3])
    pp=ast[:,None,:]; qq=bst[None,:,:]; uu=(aend-ast)[:,None,:]; vv=(bend-bst)[None,:,:]; ww=pp-qq
    aa=dot(uu,uu); bb=dot(uu,vv); cc=dot(vv,vv); dd=dot(uu,ww); ee=dot(vv,ww)
    det=aa*cc-bb*bb
    with np.errstate(divide='ignore',invalid='ignore'):
        ss=(bb*ee-cc*dd)/det; tt=(aa*ee-bb*dd)/det
    valid=(det>1e-28)&(ss>=0)&(ss<=1)&(tt>=0)&(tt<=1)
    pa=pp+ss[...,None]*uu; pb=qq+tt[...,None]*vv
    ds=np.where(valid,dot(pa-pb,pa-pb),np.inf)
    idx=np.unravel_index(np.argmin(ds),ds.shape)
    if ds[idx]<best[0]:best=(float(ds[idx]),pa[idx].copy(),pb[idx].copy(),'edge-edge')
    return best
start=time.time()
results={name:mesh_distance(tg,g) for name,g in geo.items() if name!='Target'}
print('seconds',time.time()-start,'candidate count',len(results))
print('ranked',[(name,math.sqrt(result[0]),result[3]) for name,result in sorted(results.items(),key=lambda item:item[1][0])])
name=min(results,key=lambda name:results[name][0]); result=results[name]
print('winner',name,'distance',math.sqrt(result[0]),'target point',result[1].tolist(),'other point',result[2].tolist(),'feature',result[3])
print('minimum triangle normal squared',min(float(np.min(dot(np.cross(g['tri'][:,1]-g['tri'][:,0],g['tri'][:,2]-g['tri'][:,0]),np.cross(g['tri'][:,1]-g['tri'][:,0],g['tri'][:,2]-g['tri'][:,0])))) for g in geo.values()))