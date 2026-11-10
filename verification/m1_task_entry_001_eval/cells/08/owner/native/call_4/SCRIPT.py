def nearest_surfaces(first, second):
    tri_a=first['triangles']; tri_b=second['triangles']
    best={'distance2':float('inf')}
    def consider(dist2, points_a, points_b, label):
        index=np.unravel_index(np.argmin(dist2),dist2.shape)
        value=float(dist2[index])
        if value<best['distance2']:
            best.update(distance2=value,point_a=np.array(points_a[index]).tolist(),point_b=np.array(points_b[index]).tolist(),feature=label,index=index)
    edges_a=np.stack([tri_a[:,[0,1]],tri_a[:,[1,2]],tri_a[:,[2,0]]],axis=1).reshape(-1,2,3)
    edges_b=np.stack([tri_b[:,[0,1]],tri_b[:,[1,2]],tri_b[:,[2,0]]],axis=1).reshape(-1,2,3)
    p=edges_a[:,0,None,:]; u=(edges_a[:,1]-edges_a[:,0])[:,None,:]
    q=edges_b[None,:,0,:]; v=(edges_b[:,1]-edges_b[:,0])[None,:,:]
    shape=(len(edges_a),len(edges_b),3)
    uu=np.sum(u*u,axis=-1); vv=np.sum(v*v,axis=-1)
    for endpoint in (0,1):
        pa=p+endpoint*u
        parameter=np.clip(np.sum((pa-q)*v,axis=-1)/vv,0,1)
        pb=q+parameter[...,None]*v
        pa=np.broadcast_to(pa,shape)
        consider(np.sum((pa-pb)**2,axis=-1),pa,pb,'edgeA endpoint / edgeB')
        pb=q+endpoint*v
        parameter=np.clip(np.sum((pb-p)*u,axis=-1)/uu,0,1)
        pa=p+parameter[...,None]*u
        pb=np.broadcast_to(pb,shape)
        consider(np.sum((pa-pb)**2,axis=-1),pa,pb,'edgeA / edgeB endpoint')
    w=p-q
    uv=np.sum(u*v,axis=-1); uw=np.sum(u*w,axis=-1); vw=np.sum(v*w,axis=-1)
    denom=uu*vv-uv*uv
    safe=np.where(denom>0,denom,1)
    sa=(uv*vw-vv*uw)/safe; sb=(uu*vw-uv*uw)/safe
    valid=(denom>1e-28)&(sa>=0)&(sa<=1)&(sb>=0)&(sb<=1)
    pa=p+sa[...,None]*u; pb=q+sb[...,None]*v
    consider(np.where(valid,np.sum((pa-pb)**2,axis=-1),np.inf),pa,pb,'edge / edge interiors')
    def vertex_face(vertices, triangles, reverse):
        origin=triangles[:,0]; basis_u=triangles[:,1]-origin; basis_v=triangles[:,2]-origin
        normals=np.cross(basis_u,basis_v); norm2=np.sum(normals*normals,axis=-1)
        diff=vertices[:,None,:]-origin[None,:,:]
        height=np.sum(diff*normals[None,:,:],axis=-1)/norm2[None,:]
        projected=vertices[:,None,:]-height[...,None]*normals[None,:,:]
        relative=projected-origin[None,:,:]
        du=np.sum(relative*basis_u[None,:,:],axis=-1); dv=np.sum(relative*basis_v[None,:,:],axis=-1)
        aa=np.sum(basis_u*basis_u,axis=-1); bb=np.sum(basis_u*basis_v,axis=-1); cc=np.sum(basis_v*basis_v,axis=-1)
        det=aa*cc-bb*bb
        alpha=(du*cc-dv*bb)/det; beta=(dv*aa-du*bb)/det
        valid=(alpha>=-1e-14)&(beta>=-1e-14)&(alpha+beta<=1+1e-14)
        dist2=np.where(valid,height*height*norm2[None,:],np.inf)
        original=np.broadcast_to(vertices[:,None,:],projected.shape)
        consider(dist2,projected if reverse else original,original if reverse else projected,'face / vertex' if reverse else 'vertex / face')
    vertex_face(first['verts'],tri_b,False)
    vertex_face(second['verts'],tri_a,True)
    best['distance_mm']=math.sqrt(best['distance2'])*1000*scene.unit_settings.scale_length
    return best
results={}
for name,mesh in mesh_cache.items():
    if name=='Mesh_DDBB95':continue
    result=nearest_surfaces(mesh_cache['Mesh_DDBB95'],mesh)
    results[name]=result
    lower=np.maximum(np.maximum(mesh['verts'].min(0)-mesh_cache['Mesh_DDBB95']['verts'].max(0),mesh_cache['Mesh_DDBB95']['verts'].min(0)-mesh['verts'].max(0)),0)
    print(name, result,'aabb_lower_mm',np.linalg.norm(lower)*1000)
