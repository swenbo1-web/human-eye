import hashlib
start=time.perf_counter()
depsgraph=bpy.context.evaluated_depsgraph_get()
def capture_geom(obj):
    evaluated=obj.evaluated_get(depsgraph)
    mesh=evaluated.to_mesh()
    try:
        mesh.calc_loop_triangles()
        local=np.array([tuple(v.co) for v in mesh.vertices],dtype=np.float64)
        matrix=np.array(evaluated.matrix_world,dtype=np.float64)
        verts=local@matrix[:3,:3].T+matrix[:3,3]
        faces=np.array([tuple(t.vertices) for t in mesh.loop_triangles],dtype=np.int64)
        edges=np.unique(np.sort(np.concatenate([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]]),axis=1),axis=0)
        return {'v':verts,'f':faces,'e':edges,'tri':verts[faces],'seg':verts[edges]}
    finally:
        evaluated.to_mesh_clear()
geoms={obj.name:capture_geom(obj) for obj in objs}
fingerprint=hashlib.sha256(b''.join(name.encode()+g['v'].tobytes()+g['f'].tobytes() for name,g in sorted(geoms.items()))).hexdigest()
print('world_evaluated_mesh_fingerprint',fingerprint)
print('evaluated_counts',[(name,len(g['v']),len(g['f']),len(g['e'])) for name,g in geoms.items()][:4])
def point_faces(points,triangles):
    point=points[:,None,:]; a=triangles[None,:,0]; b=triangles[None,:,1]; c=triangles[None,:,2]
    ab=b-a; ac=c-a; ap=point-a
    normal=np.cross(ab,ac); norm2=np.sum(normal*normal,axis=-1)
    signed=np.sum(ap*normal,axis=-1)
    projected=point-normal*np.divide(signed,norm2,out=np.zeros_like(signed),where=norm2>0)[...,None]
    relative=projected-a
    aa=np.sum(ab*ab,axis=-1); bb=np.sum(ab*ac,axis=-1); cc=np.sum(ac*ac,axis=-1)
    ra=np.sum(relative*ab,axis=-1); rc=np.sum(relative*ac,axis=-1)
    den=aa*cc-bb*bb
    u=np.divide(cc*ra-bb*rc,den,out=np.zeros_like(ra),where=den>0)
    v=np.divide(aa*rc-bb*ra,den,out=np.zeros_like(rc),where=den>0)
    inside=(u>=0)&(v>=0)&(u+v<=1)&(den>0)
    d2=np.where(inside,np.sum((point-projected)**2,axis=-1),np.inf)
    idx=np.unravel_index(np.argmin(d2),d2.shape)
    return float(d2[idx]),points[idx[0]].copy(),projected[idx].copy(),int(idx[1])
def edge_edges(seg1,seg2):
    p=seg1[:,None,0]; q=seg2[None,:,0]; u=seg1[:,None,1]-p; v=seg2[None,:,1]-q; w=p-q
    aa=np.sum(u*u,axis=-1); bb=np.sum(u*v,axis=-1); cc=np.sum(v*v,axis=-1); dd=np.sum(u*w,axis=-1); ee=np.sum(v*w,axis=-1)
    denom=aa*cc-bb*bb
    s=np.divide(bb*ee-cc*dd,denom,out=np.zeros_like(dd),where=denom>1e-28)
    t=np.divide(aa*ee-bb*dd,denom,out=np.zeros_like(dd),where=denom>1e-28)
    valid=(denom>1e-28)&(s>=0)&(s<=1)&(t>=0)&(t<=1)
    candidates=[(s,t,valid),(np.zeros_like(dd),np.clip(ee/cc,0,1),True),(np.ones_like(dd),np.clip((ee+bb)/cc,0,1),True),(np.clip(-dd/aa,0,1),np.zeros_like(dd),True),(np.clip((bb-dd)/aa,0,1),np.ones_like(dd),True)]
    best=(np.inf,None,None,None)
    for s,t,valid in candidates:
        first=p+s[...,None]*u; second=q+t[...,None]*v
        d2=np.where(valid,np.sum((first-second)**2,axis=-1),np.inf)
        idx=np.unravel_index(np.argmin(d2),d2.shape)
        if d2[idx]<best[0]: best=(float(d2[idx]),first[idx].copy(),second[idx].copy(),tuple(map(int,idx)))
    return best
def piercing(segments,triangles):
    origin=segments[:,None,0]; direction=segments[:,None,1]-origin
    a=triangles[None,:,0]; ab=triangles[None,:,1]-a; ac=triangles[None,:,2]-a
    h=np.cross(direction,ac); det=np.sum(ab*h,axis=-1)
    inverse=np.divide(1.0,det,out=np.zeros_like(det),where=np.abs(det)>1e-18)
    offset=origin-a
    u=np.sum(offset*h,axis=-1)*inverse
    cross=np.cross(offset,ab)
    v=np.sum(direction*cross,axis=-1)*inverse
    t=np.sum(ac*cross,axis=-1)*inverse
    hits=(np.abs(det)>1e-18)&(u>=0)&(v>=0)&(u+v<=1)&(t>=0)&(t<=1)
    if np.any(hits):
        idx=tuple(np.argwhere(hits)[0]); pt=(origin+direction*t[...,None])[idx]
        return (0.0,pt,pt,tuple(map(int,idx)))
    return None
results=[]
target_geom=geoms['Target']
for name,g in geoms.items():
    if name=='Target': continue
    intersect=piercing(target_geom['seg'],g['tri']) or piercing(g['seg'],target_geom['tri'])
    if intersect is not None:
        best=intersect; kind='intersection'
    else:
        first=point_faces(target_geom['v'],g['tri'])
        other=point_faces(g['v'],target_geom['tri'])
        second=(other[0],other[2],other[1],other[3])
        third=edge_edges(target_geom['seg'],g['seg'])
        best,kind=min([(first,'target vertex / face'),(second,'face / candidate vertex'),(third,'edge / edge')],key=lambda entry:entry[0][0])
    results.append({'name':name,'distance':float(np.sqrt(best[0])),'kind':kind,'target_point':best[1].tolist(),'candidate_point':best[2].tolist(),'feature_indices':best[3]})
results.sort(key=lambda row:row['distance'])
print('examined_candidates',len(results),'elapsed_seconds',time.perf_counter()-start)
print('ranked_distances',[(r['name'],r['distance'],r['kind']) for r in results])
print('nearest_witness',results[0])