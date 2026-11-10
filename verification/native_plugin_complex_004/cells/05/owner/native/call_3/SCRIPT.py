import numpy as np, time, hashlib
start=time.time()
deps=bpy.context.evaluated_depsgraph_get()
def capture_mesh(obj):
    evaluated=obj.evaluated_get(deps)
    mesh=evaluated.to_mesh()
    try:
        mesh.calc_loop_triangles()
        local=np.array([v.co[:] for v in mesh.vertices],dtype=np.float64)
        matrix=np.array(evaluated.matrix_world,dtype=np.float64)
        world=local@matrix[:3,:3].T+matrix[:3,3]
        indices=np.array([t.vertices[:] for t in mesh.loop_triangles],dtype=np.int64)
        return world[indices],world
    finally:
        evaluated.to_mesh_clear()
geometry={obj.name:capture_mesh(obj) for obj in bpy.context.scene.objects if obj.type=='MESH'}
def point_triangle_distance_sq(points, triangles):
    offset=points-triangles[:,0]
    first=triangles[:,1]-triangles[:,0]
    second=triangles[:,2]-triangles[:,0]
    normal=np.cross(first,second)
    normal_sq=np.sum(normal*normal,axis=-1)
    dot=np.sum(offset*normal,axis=-1)
    projection=points-(dot/normal_sq)[:,None]*normal
    relative=projection-triangles[:,0]
    aa=np.sum(first*first,axis=-1); ab=np.sum(first*second,axis=-1); bb=np.sum(second*second,axis=-1)
    ra=np.sum(relative*first,axis=-1); rb=np.sum(relative*second,axis=-1)
    denominator=aa*bb-ab*ab
    bary_a=(bb*ra-ab*rb)/denominator; bary_b=(aa*rb-ab*ra)/denominator
    inside=(bary_a>=0)&(bary_b>=0)&(bary_a+bary_b<=1)
    return np.where(inside,dot*dot/normal_sq,np.inf)
def segment_dist_sq(begin_a,end_a,begin_b,end_b):
    direction_a=end_a-begin_a; direction_b=end_b-begin_b; offset=begin_a-begin_b
    aa=np.sum(direction_a*direction_a,axis=-1); bb=np.sum(direction_b*direction_b,axis=-1); ab=np.sum(direction_a*direction_b,axis=-1)
    ar=np.sum(direction_a*offset,axis=-1); br=np.sum(direction_b*offset,axis=-1)
    denominator=aa*bb-ab*ab
    param_a=np.divide(ab*br-bb*ar,denominator,out=np.zeros_like(denominator),where=denominator>1e-28)
    param_a=np.clip(param_a,0,1)
    param_b=(ab*param_a+br)/bb
    param_a=np.where(param_b<0,np.clip(-ar/aa,0,1),param_a)
    param_a=np.where(param_b>1,np.clip((ab-ar)/aa,0,1),param_a)
    param_b=np.clip(param_b,0,1)
    difference=offset+param_a[:,None]*direction_a-param_b[:,None]*direction_b
    return np.sum(difference*difference,axis=-1)
def crosses(begin,end,triangles):
    direction=end-begin
    first=triangles[:,1]-triangles[:,0]; second=triangles[:,2]-triangles[:,0]
    cross=np.cross(direction,second); determinant=np.sum(first*cross,axis=-1)
    valid=np.abs(determinant)>1e-20
    inverse=np.divide(1.0,determinant,out=np.zeros_like(determinant),where=valid)
    offset=begin-triangles[:,0]
    bary_a=np.sum(offset*cross,axis=-1)*inverse
    cross2=np.cross(offset,first)
    bary_b=np.sum(direction*cross2,axis=-1)*inverse
    parameter=np.sum(second*cross2,axis=-1)*inverse
    return valid&(bary_a>=0)&(bary_b>=0)&(bary_a+bary_b<=1)&(parameter>=0)&(parameter<=1)
def mesh_distance(triangles_a,triangles_b):
    paired_a=np.repeat(triangles_a,len(triangles_b),axis=0)
    paired_b=np.tile(triangles_b,(len(triangles_a),1,1))
    best=np.inf
    for vertex in range(3):
        if np.any(crosses(paired_a[:,vertex],paired_a[:,(vertex+1)%3],paired_b)) or np.any(crosses(paired_b[:,vertex],paired_b[:,(vertex+1)%3],paired_a)):
            return 0.0
        best=min(best,np.min(point_triangle_distance_sq(paired_a[:,vertex],paired_b)),np.min(point_triangle_distance_sq(paired_b[:,vertex],paired_a)))
        for edge in range(3):
            best=min(best,np.min(segment_dist_sq(paired_a[:,vertex],paired_a[:,(vertex+1)%3],paired_b[:,edge],paired_b[:,(edge+1)%3])))
    return float(np.sqrt(best))
results=[]
for name,(triangles,vertices) in geometry.items():
    if name!='Target': results.append((mesh_distance(geometry['Target'][0],triangles),name))
results.sort()
print('evaluated meshes:',len(geometry),'target triangles:',len(geometry['Target'][0]))
print('all distances (m):',results)
print('elapsed_seconds',time.time()-start)
