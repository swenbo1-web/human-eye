def crossing(a,b,triangles):
    a=a[:,None,:]; direction=(b[:,None,:]-a)
    v0=triangles[None,:,0,:]; e1=triangles[None,:,1,:]-v0; e2=triangles[None,:,2,:]-v0
    h=np.cross(direction,e2); det=dot(e1,h)
    scale=np.sqrt(dot(direction,direction)*dot(e1,e1)*dot(e2,e2))
    stable=np.abs(det)>1e-12*scale
    inv=np.divide(1.,det,out=np.zeros_like(det),where=stable)
    offset=a-v0; s=dot(offset,h)*inv; q=np.cross(offset,e1); t=dot(direction,q)*inv; ray=dot(e2,q)*inv
    point=a+ray[...,None]*direction
    other=v0+s[...,None]*e1+t[...,None]*e2
    ok=stable&(s>=0)&(t>=0)&(s+t<=1)&(ray>=0)&(ray<=1)&(dot(point-other,point-other)<1e-20)
    ids=np.argwhere(ok)
    if len(ids):
        ii,jj=ids[0]; p=point[ii,jj]
        return (0.,p,p)
    return None

fresh={o.name:read_geom(o) for o in bpy.context.scene.objects if o.type=='MESH'}
print('geometry_unchanged',signature(fresh)==geom_sig)
results=[]
for name,geometry in fresh.items():
    if name=='Target':continue
    ds,p,q=surface_distance(fresh['Target'],geometry)
    results.append((float(np.sqrt(max(0,ds))),name,p.tolist(),q.tolist()))
results.sort()
print('all_final_distances',[(name,dist) for dist,name,p,q in results])
print('closest_witnesses',results[:2])
print('complete_candidates',len(results),'unresolved',0)