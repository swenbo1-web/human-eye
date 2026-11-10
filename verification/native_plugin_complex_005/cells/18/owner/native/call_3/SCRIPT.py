import numpy as np, math, time
start=time.time()
depsgraph=bpy.context.evaluated_depsgraph_get()
def read_triangles(obj):
    evaluated=obj.evaluated_get(depsgraph)
    mesh=evaluated.to_mesh()
    try:
        mesh.calc_loop_triangles()
        vertices=np.array([tuple(v.co) for v in mesh.vertices],dtype=np.float64)
        matrix=np.array(evaluated.matrix_world,dtype=np.float64)
        vertices=vertices@matrix[:3,:3].T+matrix[:3,3]
        indices=np.array([tuple(tri.vertices) for tri in mesh.loop_triangles],dtype=int)
        return vertices[indices]
    finally:
        evaluated.to_mesh_clear()
triangles_by_name={obj.name:read_triangles(obj) for obj in bpy.context.scene.objects if obj.type=='MESH'}
def dot(left,right): return np.sum(left*right,axis=-1)
def point_tri(points,triangles):
    # Broadcast points against triangles; include projected face and boundary segments.
    origin=triangles[...,0,:]; edge_one=triangles[...,1,:]-origin; edge_two=triangles[...,2,:]-origin
    normal=np.cross(edge_one,edge_two); norm_squared=dot(normal,normal)
    signed=dot(points-origin,normal)
    projected=points-(signed/np.maximum(norm_squared,1e-300))[...,None]*normal
    relative=projected-origin
    aa=dot(edge_one,edge_one); ab=dot(edge_one,edge_two); bb=dot(edge_two,edge_two)
    ar=dot(relative,edge_one); br=dot(relative,edge_two); determinant=aa*bb-ab*ab
    coord_one=(bb*ar-ab*br)/np.maximum(determinant,1e-300)
    coord_two=(aa*br-ab*ar)/np.maximum(determinant,1e-300)
    inside=(coord_one>=0)&(coord_two>=0)&(coord_one+coord_two<=1)&(norm_squared>1e-280)
    best=np.where(inside,signed*signed/np.maximum(norm_squared,1e-300),np.inf)
    for index in range(3):
        base=triangles[...,index,:]; edge=triangles[...,(index+1)%3,:]-base
        fraction=np.clip(dot(points-base,edge)/np.maximum(dot(edge,edge),1e-300),0,1)
        delta=points-base-fraction[...,None]*edge
        best=np.minimum(best,dot(delta,delta))
    return best

def triangle_distance(first,second):
    best=float('inf'); intersects=False
    for vertex_index in range(3):
        best=min(best,float(np.min(point_tri(first[:,None,vertex_index,:],second[None,:,:,:]))))
        best=min(best,float(np.min(point_tri(second[:,None,vertex_index,:],first[None,:,:,:]))))
    for index in range(3):
        base=first[:,None,index,:]; direction=first[:,None,(index+1)%3,:]-base
        for other_index in range(3):
            other_base=second[None,:,other_index,:]; other_direction=second[None,:,(other_index+1)%3,:]-other_base
            offset=base-other_base
            aa=dot(direction,direction); bb=dot(direction,other_direction); cc=dot(other_direction,other_direction)
            dd=dot(direction,offset); ee=dot(other_direction,offset); determinant=aa*cc-bb*bb
            valid=determinant>1e-28
            along_first=(bb*ee-cc*dd)/np.where(valid,determinant,1)
            along_second=(aa*ee-bb*dd)/np.where(valid,determinant,1)
            valid=valid&(along_first>=0)&(along_first<=1)&(along_second>=0)&(along_second<=1)
            delta=offset+along_first[...,None]*direction-along_second[...,None]*other_direction
            best=min(best,float(np.min(np.where(valid,dot(delta,delta),np.inf))))
    # Test edge/face piercing in both directions (not captured by feature distances).
    for source,destination in [(first,second),(second,first)]:
        base=destination[None,:,0,:]; side_one=destination[None,:,1,:]-base; side_two=destination[None,:,2,:]-base
        normal=np.cross(side_one,side_two)
        aa=dot(side_one,side_one); ab=dot(side_one,side_two); bb=dot(side_two,side_two); determinant=aa*bb-ab*ab
        for index in range(3):
            edge_base=source[:,None,index,:]; direction=source[:,None,(index+1)%3,:]-edge_base
            denominator=dot(direction,normal)
            valid=np.abs(denominator)>1e-28
            fraction=dot(base-edge_base,normal)/np.where(valid,denominator,1)
            relative=edge_base+fraction[...,None]*direction-base
            ar=dot(relative,side_one); br=dot(relative,side_two)
            coord_one=(bb*ar-ab*br)/np.maximum(determinant,1e-300)
            coord_two=(aa*br-ab*ar)/np.maximum(determinant,1e-300)
            hit=valid&(fraction>=0)&(fraction<=1)&(coord_one>=0)&(coord_two>=0)&(coord_one+coord_two<=1)&(determinant>1e-280)
            if np.any(hit): return 0.0
    return math.sqrt(max(best,0))
target_triangles=triangles_by_name['Target']
results=sorted((triangle_distance(target_triangles,triangles),name) for name,triangles in triangles_by_name.items() if name!='Target')
print('candidate_count',len(results),'seconds',time.time()-start)
print('all_distances_m',results)
print('triangle_counts',sorted(set(len(triangles) for triangles in triangles_by_name.values())))