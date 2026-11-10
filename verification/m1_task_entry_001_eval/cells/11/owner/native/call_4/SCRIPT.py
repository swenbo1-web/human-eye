def dot(a,b): return np.einsum('...i,...i->...',a,b)
def triangle_pair_distances(ta,tb):
    count_a,count_b=len(ta),len(tb)
    aa=np.repeat(ta,count_b,axis=0); bb=np.tile(tb,(count_a,1,1))
    n=len(aa); best=np.full(n,np.inf); pa=np.zeros((n,3)); pb=np.zeros((n,3)); hit=np.zeros(n,dtype=bool)
    def update(x,y,valid=None):
        dd=dot(x-y,x-y)
        mask=dd<best
        if valid is not None: mask &= valid
        best[mask]=dd[mask]; pa[mask]=x[mask]; pb[mask]=y[mask]
    for rev in (False,True):
        src,dst=(bb,aa) if rev else (aa,bb)
        base=dst[:,0]; u=dst[:,1]-base; v=dst[:,2]-base
        norm=np.cross(u,v); norm2=dot(norm,norm)
        uu=dot(u,u); uv=dot(u,v); vv=dot(v,v); det=uu*vv-uv*uv
        for k in range(3):
            point=src[:,k]
            offset=point-base
            projected=point-(dot(offset,norm)/norm2)[:,None]*norm
            rel=projected-base
            pu=dot(rel,u); pv=dot(rel,v)
            alpha=(vv*pu-uv*pv)/det; beta=(uu*pv-uv*pu)/det
            valid=(alpha>=-1e-13)&(beta>=-1e-13)&(alpha+beta<=1+1e-13)
            update(projected,point,valid) if rev else update(point,projected,valid)
            end=src[:,(k+1)%3]; direction=end-point
            denom=dot(direction,norm)
            good=np.abs(denom)>1e-15
            frac=np.divide(dot(base-point,norm),denom,out=np.zeros(n),where=good)
            crossing=point+frac[:,None]*direction
            rel=crossing-base; pu=dot(rel,u); pv=dot(rel,v)
            alpha=(vv*pu-uv*pv)/det; beta=(uu*pv-uv*pu)/det
            valid=good&(frac>=0)&(frac<=1)&(alpha>=-1e-13)&(beta>=-1e-13)&(alpha+beta<=1+1e-13)
            hit |= valid
            update(crossing,crossing,valid)
    for i in range(3):
        p=aa[:,i]; u=aa[:,(i+1)%3]-p; uu=dot(u,u)
        for j in range(3):
            q=bb[:,j]; v=bb[:,(j+1)%3]-q; vv=dot(v,v)
            w=p-q; uv=dot(u,v); uw=dot(u,w); vw=dot(v,w)
            for fraction in (0.,1.):
                x=p+fraction*u
                t=np.clip(dot(x-q,v)/vv,0,1)
                update(x,q+t[:,None]*v)
                y=q+fraction*v
                t=np.clip(dot(y-p,u)/uu,0,1)
                update(p+t[:,None]*u,y)
            det=uu*vv-uv*uv
            good=det>1e-14*uu*vv
            ss=np.divide(uv*vw-vv*uw,det,out=np.zeros(n),where=good)
            tt=np.divide(uu*vw-uv*uw,det,out=np.zeros(n),where=good)
            valid=good&(ss>=0)&(ss<=1)&(tt>=0)&(tt<=1)
            update(p+ss[:,None]*u,q+tt[:,None]*v,valid)
    idx=int(np.argmin(best))
    return {'distance':float(np.sqrt(best[idx])),'point_target':pa[idx].tolist(),'point_other':pb[idx].tolist(),'triangle_target':idx//count_b,'triangle_other':idx%count_b,'intersection_pairs':int(hit.sum())}
results={}
for name,(_,_,tri) in geom.items():
    if name=='Mesh_D17AB2': continue
    results[name]=triangle_pair_distances(geom['Mesh_D17AB2'][2],tri)
for name,r in sorted(results.items(),key=lambda x:x[1]['distance']):
    print(name,'distance_mm',format(r['distance']*s.unit_settings.scale_length*1000,'.12f'),r)
