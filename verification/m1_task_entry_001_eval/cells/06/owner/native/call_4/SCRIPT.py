def point_triangle_min(points,triangles):
    p=points[:,None,:]; a=triangles[None,:,0,:]; b=triangles[None,:,1,:]; c=triangles[None,:,2,:]
    ab=b-a; ac=c-a; normal=np.cross(ab,ac); nn=np.sum(normal*normal,axis=-1)
    offset=np.sum((p-a)*normal,axis=-1)/nn
    q=p-offset[...,None]*normal
    aq=q-a; d00=np.sum(ab*ab,axis=-1); d01=np.sum(ab*ac,axis=-1); d11=np.sum(ac*ac,axis=-1)
    d20=np.sum(aq*ab,axis=-1); d21=np.sum(aq*ac,axis=-1); denom=d00*d11-d01*d01
    u=(d11*d20-d01*d21)/denom; v=(d00*d21-d01*d20)/denom
    inside=(u>=-1e-13)&(v>=-1e-13)&(u+v<=1+1e-13)
    dd=np.sum((p-q)**2,axis=-1); dd[~inside]=np.inf
    idx=np.unravel_index(np.argmin(dd),dd.shape)
    best=(float(dd[idx]),points[idx[0]].copy(),q[idx].copy(),'vertex-face')
    for start,end in [(a,b),(b,c),(c,a)]:
        edge=end-start; t=np.sum((p-start)*edge,axis=-1)/np.sum(edge*edge,axis=-1)
        r=start+np.clip(t,0,1)[...,None]*edge
        dd=np.sum((p-r)**2,axis=-1); idx=np.unravel_index(np.argmin(dd),dd.shape)
        if dd[idx]<best[0]: best=(float(dd[idx]),points[idx[0]].copy(),r[idx].copy(),'vertex-edge')
    return best

def edge_edge_min(edges_a,edges_b):
    p=edges_a[:,None,0,:]; q=edges_b[None,:,0,:]
    u=edges_a[:,None,1,:]-p; v=edges_b[None,:,1,:]-q; w=p-q
    aa=np.sum(u*u,axis=-1); bb=np.sum(u*v,axis=-1); cc=np.sum(v*v,axis=-1)
    dd=np.sum(u*w,axis=-1); ee=np.sum(v*w,axis=-1); denom=aa*cc-bb*bb
    valid=denom>1e-25
    s=np.divide(bb*ee-cc*dd,denom,out=np.zeros_like(denom),where=valid)
    t=np.divide(aa*ee-bb*dd,denom,out=np.zeros_like(denom),where=valid)
    valid &= (s>=0)&(s<=1)&(t>=0)&(t<=1)
    pa=p+s[...,None]*u; pb=q+t[...,None]*v
    dist=np.sum((pa-pb)**2,axis=-1); dist[~valid]=np.inf
    idx=np.unravel_index(np.argmin(dist),dist.shape)
    return float(dist[idx]),pa[idx].copy(),pb[idx].copy(),'edge-edge'

def segment_triangle_hit(edges,triangles):
    p=edges[:,None,0,:]; direction=edges[:,None,1,:]-p
    a=triangles[None,:,0,:]; ab=triangles[None,:,1,:]-a; ac=triangles[None,:,2,:]-a
    h=np.cross(direction,ac); det=np.sum(ab*h,axis=-1); valid=np.abs(det)>1e-18
    inv=np.divide(1.,det,out=np.zeros_like(det),where=valid)
    s=p-a; u=inv*np.sum(s*h,axis=-1); q=np.cross(s,ab)
    v=inv*np.sum(direction*q,axis=-1); t=inv*np.sum(ac*q,axis=-1)
    hit=valid&(u>=-1e-12)&(v>=-1e-12)&(u+v<=1+1e-12)&(t>=-1e-12)&(t<=1+1e-12)
    if hit.any():
        idx=tuple(np.argwhere(hit)[0]); point=(p+t[...,None]*direction)[idx]
        return (0.,point.copy(),point.copy(),'intersection')
    return None

target=geo['Mesh_D17AB2']; results={}
for name,other in geo.items():
    if name=='Mesh_D17AB2': continue
    va=target['v']; vb=other['v']; ta=va[target['t']]; tb=vb[other['t']]; ea=va[target['e']]; eb=vb[other['e']]
    candidates=[point_triangle_min(va,tb),edge_edge_min(ea,eb)]
    rev=point_triangle_min(vb,ta); candidates.append((rev[0],rev[2],rev[1],rev[3]+' reversed'))
    for hit in [segment_triangle_hit(ea,tb),segment_triangle_hit(eb,ta)]:
        if hit is not None: candidates.append(hit)
    best=min(candidates,key=lambda value:value[0]); results[name]=best
for name,best in sorted(results.items(),key=lambda item:item[1][0]):
    print(name,'distance_mm',format(math.sqrt(best[0])*scene.unit_settings.scale_length*1000,'.12f'),'target_point_m',best[1].tolist(),'other_point_m',best[2].tolist(),'feature',best[3])
