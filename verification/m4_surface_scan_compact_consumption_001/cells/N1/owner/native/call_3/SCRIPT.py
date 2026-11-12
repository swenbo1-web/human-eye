def dot_array(first,second):
    return np.sum(first*second,axis=-1)

def point_segment_sq(points,start,end):
    direction=end-start
    denom=dot_array(direction,direction)
    fraction=np.divide(dot_array(points-start,direction),denom,out=np.zeros(np.broadcast_shapes(points.shape[:-1],denom.shape)),where=denom>0)
    fraction=np.clip(fraction,0,1)
    return dot_array(points-start-fraction[...,None]*direction,points-start-fraction[...,None]*direction)

def projected_face_sq(points,triangle):
    origin=triangle[...,0,:]
    side_first=triangle[...,1,:]-origin
    side_second=triangle[...,2,:]-origin
    normal=np.cross(side_first,side_second)
    normal_sq=dot_array(normal,normal)
    delta=points-origin
    signed=dot_array(delta,normal)
    height=np.divide(signed,normal_sq,out=np.zeros_like(signed),where=normal_sq>0)
    projection=delta-height[...,None]*normal
    denom=dot_array(side_first,side_first)*dot_array(side_second,side_second)-dot_array(side_first,side_second)**2
    coord_first=np.divide(dot_array(side_second,side_second)*dot_array(projection,side_first)-dot_array(side_first,side_second)*dot_array(projection,side_second),denom,out=np.zeros_like(signed),where=denom>0)
    coord_second=np.divide(dot_array(side_first,side_first)*dot_array(projection,side_second)-dot_array(side_first,side_second)*dot_array(projection,side_first),denom,out=np.zeros_like(signed),where=denom>0)
    inside=(denom>0)&(coord_first>=0)&(coord_second>=0)&(coord_first+coord_second<=1)
    return np.where(inside,signed*height,np.inf)

def segment_face_hit(start,end,triangle):
    origin=triangle[...,0,:]
    side_first=triangle[...,1,:]-origin
    side_second=triangle[...,2,:]-origin
    direction=end-start
    cross_first=np.cross(direction,side_second)
    determinant=dot_array(side_first,cross_first)
    valid=determinant!=0
    inverse=np.divide(1.0,determinant,out=np.zeros_like(determinant),where=valid)
    delta=start-origin
    coord_first=dot_array(delta,cross_first)*inverse
    cross_second=np.cross(delta,side_first)
    coord_second=dot_array(direction,cross_second)*inverse
    along=dot_array(side_second,cross_second)*inverse
    return valid&(coord_first>=0)&(coord_second>=0)&(coord_first+coord_second<=1)&(along>=0)&(along<=1)

def triangle_pair_min(first,second):
    first=first[:,None,:,:]
    second=second[None,:,:,:]
    best=np.full((first.shape[0],second.shape[1]),np.inf)
    for vertex_index in range(3):
        best=np.minimum(best,projected_face_sq(first[...,vertex_index,:],second))
        best=np.minimum(best,projected_face_sq(second[...,vertex_index,:],first))
    for first_index in range(3):
        start_first=first[...,first_index,:]; end_first=first[...,(first_index+1)%3,:]
        best=np.where(segment_face_hit(start_first,end_first,second),0,best)
        start_second=second[...,first_index,:]; end_second=second[...,(first_index+1)%3,:]
        best=np.where(segment_face_hit(start_second,end_second,first),0,best)
        for second_index in range(3):
            start_second=second[...,second_index,:]; end_second=second[...,(second_index+1)%3,:]
            for points,start,end in [(start_first,start_second,end_second),(end_first,start_second,end_second),(start_second,start_first,end_first),(end_second,start_first,end_first)]:
                best=np.minimum(best,point_segment_sq(points,start,end))
            direction_first=end_first-start_first; direction_second=end_second-start_second; delta=start_first-start_second
            aa=dot_array(direction_first,direction_first); bb=dot_array(direction_first,direction_second); cc=dot_array(direction_second,direction_second)
            dd=dot_array(direction_first,delta); ee=dot_array(direction_second,delta)
            denominator=aa*cc-bb*bb
            along_first=np.divide(bb*ee-cc*dd,denominator,out=np.zeros_like(denominator),where=denominator>0)
            along_second=np.divide(aa*ee-bb*dd,denominator,out=np.zeros_like(denominator),where=denominator>0)
            valid=(denominator>0)&(along_first>=0)&(along_first<=1)&(along_second>=0)&(along_second<=1)
            residual=delta+along_first[...,None]*direction_first-along_second[...,None]*direction_second
            best=np.minimum(best,np.where(valid,dot_array(residual,residual),np.inf))
    return math.sqrt(max(0,float(best.min())))

started=time.time()
results=[]
pruned=0
threshold=0.002/scene.unit_settings.scale_length
for first_index,first_obj in enumerate(scan):
    for second_obj in scan[first_index+1:]:
        if not len(first_obj['triangles']) or not len(second_obj['triangles']):
            continue
        first_bounds=(first_obj['triangles'].min(axis=(0,1)),first_obj['triangles'].max(axis=(0,1)))
        second_bounds=(second_obj['triangles'].min(axis=(0,1)),second_obj['triangles'].max(axis=(0,1)))
        gap=np.maximum(0,np.maximum(first_bounds[0]-second_bounds[1],second_bounds[0]-first_bounds[1]))
        lower=float(np.linalg.norm(gap))
        if lower>threshold+1e-12:
            pruned+=1
            continue
        distance=triangle_pair_min(first_obj['triangles'],second_obj['triangles'])
        results.append((first_obj['name'],second_obj['name'],distance*scene.unit_settings.scale_length*1000))
qualifying=[entry for entry in results if entry[2]<=2.0]
print('elapsed',time.time()-started,'all_pairs',len(scan)*(len(scan)-1)//2,'aabb_excluded',pruned,'exact_tested',len(results),'qualifying',len(qualifying))
for entry in qualifying:
    print('%s %s %.9f mm'%entry)
print('closest_excluded_exact',sorted([entry for entry in results if entry[2]>2],key=lambda entry:entry[2])[:8])
print('total_triangles',sum(len(item['triangles']) for item in scan))