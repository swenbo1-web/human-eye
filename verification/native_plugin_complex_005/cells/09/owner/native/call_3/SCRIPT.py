import hashlib

def read_geom(obj):
    ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh=ev.to_mesh()
    try:
        mesh.calc_loop_triangles()
        verts=np.array([tuple(v.co) for v in mesh.vertices],dtype=np.float64)
        mat=np.array(ev.matrix_world,dtype=np.float64)
        verts=verts@mat[:3,:3].T+mat[:3,3]
        faces=np.array([tuple(t.vertices) for t in mesh.loop_triangles],dtype=np.int64).reshape(-1,3)
        return verts,faces
    finally: ev.to_mesh_clear()

def signature(geoms):
    digest=hashlib.sha256()
    for name,(verts,faces) in sorted(geoms.items()):
        digest.update(name.encode());digest.update(verts.tobytes());digest.update(faces.tobytes())
    return digest.hexdigest()

geoms={o.name:read_geom(o) for o in bpy.context.scene.objects if o.type=='MESH'}
geom_sig=signature(geoms)
print('scene_signature',geom_sig)
print('evaluated_counts',[(n,len(v),len(f)) for n,(v,f) in geoms.items()])
print('units',scene.unit_settings.system,scene.unit_settings.scale_length)
print('target_world_bounds',geoms['Target'][0].min(axis=0).tolist(),geoms['Target'][0].max(axis=0).tolist())

def edges_from(v,f):
    indices=np.unique(np.sort(np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]),axis=1),axis=0)
    return v[indices[:,0]],v[indices[:,1]]

def dot(a,b): return np.sum(a*b,axis=-1)

def point_face(vertices,triangles):
    p=vertices[:,None,:]; a=triangles[None,:,0,:]; u=triangles[None,:,1,:]-a; w=triangles[None,:,2,:]-a
    n=np.cross(u,w); nn=dot(n,n); rel=p-a
    signed=dot(rel,n)
    projection=p-n*np.divide(signed,nn,out=np.zeros_like(signed),where=nn>0)[...,None]
    r=projection-a
    uu=dot(u,u); uw=dot(u,w); ww=dot(w,w); ru=dot(r,u); rw=dot(r,w)
    den=uu*ww-uw*uw
    s=np.divide(ww*ru-uw*rw,den,out=np.full_like(ru,np.nan),where=den>0)
    t=np.divide(uu*rw-uw*ru,den,out=np.full_like(ru,np.nan),where=den>0)
    ok=(s>=0)&(t>=0)&(s+t<=1)&(nn>0)
    distances=np.where(ok,dot(p-projection,p-projection),np.inf)
    index=np.unravel_index(np.argmin(distances),distances.shape)
    return float(distances[index]),vertices[index[0]],projection[index]

def edge_edge(a,b,c,d):
    a=a[:,None,:]; b=b[:,None,:]; c=c[None,:,:]; d=d[None,:,:]
    u=b-a; v=d-c; w=a-c
    aa=dot(u,u); bb=dot(u,v); cc=dot(v,v); dd=dot(u,w); ee=dot(v,w)
    candidates=[]
    for p,base,direction,length,flip in [(a,c,v,cc,False),(b,c,v,cc,False),(c,a,u,aa,True),(d,a,u,aa,True)]:
        fraction=np.clip(np.divide(dot(p-base,direction),length,out=np.zeros_like(dot(p-base,direction)),where=length>0),0,1)
        q=base+fraction[...,None]*direction
        diff=p-q; distances=dot(diff,diff)
        ix=np.unravel_index(np.argmin(distances),distances.shape)
        pp=np.broadcast_to(p,q.shape)[ix]; qq=q[ix]
        candidates.append((float(distances[ix]),qq if flip else pp,pp if flip else qq))
    den=aa*cc-bb*bb
    s=np.divide(bb*ee-cc*dd,den,out=np.full_like(den,np.nan),where=den>0)
    t=np.divide(aa*ee-bb*dd,den,out=np.full_like(den,np.nan),where=den>0)
    pp=a+s[...,None]*u; qq=c+t[...,None]*v
    ds=np.where((s>=0)&(s<=1)&(t>=0)&(t<=1),dot(pp-qq,pp-qq),np.inf)
    ix=np.unravel_index(np.argmin(ds),ds.shape)
    candidates.append((float(ds[ix]),pp[ix],qq[ix]))
    return min(candidates,key=lambda x:x[0])

def crossing(a,b,triangles):
    a=a[:,None,:]; direction=(b[:,None,:]-a)
    v0=triangles[None,:,0,:]; e1=triangles[None,:,1,:]-v0; e2=triangles[None,:,2,:]-v0
    h=np.cross(direction,e2); det=dot(e1,h)
    inv=np.divide(1.,det,out=np.zeros_like(det),where=det!=0)
    offset=a-v0; s=dot(offset,h)*inv; q=np.cross(offset,e1); t=dot(direction,q)*inv; ray=dot(e2,q)*inv
    ok=(det!=0)&(s>=0)&(t>=0)&(s+t<=1)&(ray>=0)&(ray<=1)
    ids=np.argwhere(ok)
    if len(ids):
        ii,jj=ids[0]; p=a[ii,0]+ray[ii,jj]*direction[ii,0]
        return (0.,p,p)
    return None

def surface_distance(g1,g2):
    v1,f1=g1; v2,f2=g2
    a,b=edges_from(v1,f1); c,d=edges_from(v2,f2)
    tri1=v1[f1]; tri2=v2[f2]
    for cross in [crossing(a,b,tri2),crossing(c,d,tri1)]:
        if cross is not None:return cross
    first=point_face(v1,tri2); reverse=point_face(v2,tri1)
    return min([first,(reverse[0],reverse[2],reverse[1]),edge_edge(a,b,c,d)],key=lambda x:x[0])

start=time.time()
results=[]
for name,geometry in geoms.items():
    if name=='Target':continue
    ds,p,q=surface_distance(geoms['Target'],geometry)
    results.append((float(np.sqrt(max(0,ds))),name,p.tolist(),q.tolist()))
results.sort()
print('elapsed_seconds',time.time()-start)
print('all_surface_distances',[(name,dist) for dist,name,p,q in results])
print('closest_witnesses',results[:3])