import numpy as np, time
start=time.time()
deps=bpy.context.evaluated_depsgraph_get()
def world_tri(obj):
    ev=obj.evaluated_get(deps); mesh=ev.to_mesh()
    try:
        mesh.calc_loop_triangles()
        coords=np.array([tuple(v.co) for v in mesh.vertices],dtype=np.float64)
        mat=np.array(ev.matrix_world,dtype=np.float64)
        coords=coords@mat[:3,:3].T+mat[:3,3]
        inds=np.array([tuple(t.vertices) for t in mesh.loop_triangles],dtype=np.int64)
        return coords[inds]
    finally: ev.to_mesh_clear()
triangles={obj.name:world_tri(obj) for obj in meshes}
def dot(a,b): return np.sum(a*b,axis=-1)
def point_segments(points,first,last):
    direction=last-first
    denominator=dot(direction,direction)
    parameter=np.clip(dot(points-first,direction)/np.where(denominator>0,denominator,1),0,1)
    closest=first+parameter[...,None]*direction
    return dot(points-closest,points-closest),closest
def point_tri(points,tri):
    first,second,third=tri[...,0,:],tri[...,1,:],tri[...,2,:]
    edge1=second-first;edge2=third-first;offset=points-first
    normal=np.cross(edge1,edge2); normal2=dot(normal,normal)
    projection=points-(dot(offset,normal)/np.where(normal2>0,normal2,1))[...,None]*normal
    aa=dot(edge1,edge1);ab=dot(edge1,edge2);bb=dot(edge2,edge2)
    pa=dot(projection-first,edge1);pb=dot(projection-first,edge2)
    denom=aa*bb-ab*ab
    uu=(bb*pa-ab*pb)/np.where(denom!=0,denom,1)
    vv=(aa*pb-ab*pa)/np.where(denom!=0,denom,1)
    inside=(uu>=0)&(vv>=0)&(uu+vv<=1)&(normal2>0)
    best=np.where(inside,dot(points-projection,points-projection),np.inf)
    witness=projection.copy()
    for corner in range(3):
        squared,closest=point_segments(points,tri[...,corner,:],tri[...,(corner+1)%3,:])
        update=squared<best;best=np.minimum(best,squared);witness=np.where(update[...,None],closest,witness)
    return best,witness
def surface_distance(target,candidate):
    best=np.inf; pair=None; feature=None
    def retain(squared,first,second,label):
        nonlocal best,pair,feature
        index=np.unravel_index(np.argmin(squared),squared.shape)
        value=float(squared[index])
        if value<best:
            best=value;pair=(np.broadcast_to(first,squared.shape+(3,))[index].copy(),np.broadcast_to(second,squared.shape+(3,))[index].copy());feature=label
    for corner in range(3):
        point=target[:,None,corner,:]; tri=candidate[None,:,:,:]
        squared,closest=point_tri(point,tri);retain(squared,point,closest,'target vertex / candidate triangle')
        point=candidate[None,:,corner,:];tri=target[:,None,:,:]
        squared,closest=point_tri(point,tri);retain(squared,closest,point,'candidate vertex / target triangle')
    for corner1 in range(3):
        first=target[:,None,corner1,:];direction1=target[:,None,(corner1+1)%3,:]-first
        for corner2 in range(3):
            second=candidate[None,:,corner2,:];direction2=candidate[None,:,(corner2+1)%3,:]-second
            offset=first-second
            aa=dot(direction1,direction1);bb=dot(direction1,direction2);cc=dot(direction2,direction2)
            dd=dot(direction1,offset);ee=dot(direction2,offset);denom=aa*cc-bb*bb
            uu=(bb*ee-cc*dd)/np.where(denom>0,denom,1);vv=(aa*ee-bb*dd)/np.where(denom>0,denom,1)
            valid=(denom>0)&(uu>=0)&(uu<=1)&(vv>=0)&(vv<=1)
            closest1=first+uu[...,None]*direction1;closest2=second+vv[...,None]*direction2
            squared=np.where(valid,dot(closest1-closest2,closest1-closest2),np.inf)
            retain(squared,closest1,closest2,'edge / edge')
    # Segment/triangle crossings are required in addition to boundary distances.
    for swap in [False,True]:
        source,other=(candidate,target) if swap else (target,candidate)
        tri=other[None,:,:,:];edge1=tri[...,1,:]-tri[...,0,:];edge2=tri[...,2,:]-tri[...,0,:]
        for corner in range(3):
            origin=source[:,None,corner,:];direction=source[:,None,(corner+1)%3,:]-origin
            cross=np.cross(direction,edge2);det=dot(edge1,cross);nonparallel=det!=0
            inv=1/np.where(nonparallel,det,1);offset=origin-tri[...,0,:]
            uu=dot(offset,cross)*inv;cross2=np.cross(offset,edge1);vv=dot(direction,cross2)*inv;tt=dot(edge2,cross2)*inv
            valid=nonparallel&(uu>=0)&(vv>=0)&(uu+vv<=1)&(tt>=0)&(tt<=1)
            if np.any(valid):
                idx=np.argwhere(valid)[0];point=(origin+tt[...,None]*direction)[tuple(idx)]
                return 0.0,(point,point),'surface intersection'
    return float(np.sqrt(best)),pair,feature
results=[]
for name,tri in triangles.items():
    if name!='Target':
        distance,witness,feature=surface_distance(triangles['Target'],tri)
        results.append((distance,name,witness,feature))
results.sort(key=lambda item:item[0])
print('evaluated_meshes',len(triangles),'candidate_count',len(results),'triangle_counts',sorted(set(len(t) for t in triangles.values())))
print('all_distances_m',[(name,round(distance,12)) for distance,name,_,_ in results])
print('closest_details',[(name,distance,[point.tolist() for point in witness],feature) for distance,name,witness,feature in results[:3]])
print('elapsed_s',time.time()-start)
