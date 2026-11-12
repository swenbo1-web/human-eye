import numpy as np, itertools
from mathutils import Vector
mesh_triangles={}
depsgraph=bpy.context.evaluated_depsgraph_get()
for obj in bpy.context.scene.objects:
    if obj.type!='MESH': continue
    evaluated=obj.evaluated_get(depsgraph)
    mesh=evaluated.data
    coords=np.array([tuple(evaluated.matrix_world @ vertex.co) for vertex in mesh.vertices],dtype=float)
    triangles=[]
    for polygon in mesh.polygons:
        vertices=list(polygon.vertices)
        for index in range(1,len(vertices)-1): triangles.append(coords[[vertices[0],vertices[index],vertices[index+1]]])
    mesh_triangles[obj.name]=np.array(triangles)
def point_face_dist(points,triangles):
    origin=triangles[:,0]; edge_u=triangles[:,1]-origin; edge_v=triangles[:,2]-origin
    normal=np.cross(edge_u,edge_v); norm2=np.sum(normal*normal,axis=-1)
    offset=points[:,None,:]-origin[None,:,:]
    signed=np.sum(offset*normal[None,:,:],axis=-1)
    projection=offset-signed[:,:,None]*normal[None,:,:]/norm2[None,:,None]
    uu=np.sum(edge_u*edge_u,axis=-1); uv=np.sum(edge_u*edge_v,axis=-1); vv=np.sum(edge_v*edge_v,axis=-1)
    pu=np.sum(projection*edge_u[None,:,:],axis=-1); pv=np.sum(projection*edge_v[None,:,:],axis=-1)
    denominator=uu*vv-uv*uv
    bary_u=(pu*vv-pv*uv)/denominator; bary_v=(pv*uu-pu*uv)/denominator
    inside=(bary_u>=0)&(bary_v>=0)&(bary_u+bary_v<=1)
    return np.min(np.where(inside,signed*signed/norm2[None,:],np.inf))
def edges_of(triangles):
    return triangles.reshape(-1,3),triangles[:,[1,2,0],:].reshape(-1,3)
def segment_face_hit(starts,ends,triangles):
    direction=ends-starts; edge_u=triangles[:,1]-triangles[:,0]; edge_v=triangles[:,2]-triangles[:,0]
    cross=np.cross(direction[:,None,:],edge_v[None,:,:]); determinant=np.sum(edge_u[None,:,:]*cross,axis=-1)
    valid=np.abs(determinant)>1e-25
    inverse=np.divide(1.0,determinant,out=np.zeros_like(determinant),where=valid)
    offset=starts[:,None,:]-triangles[None,:,0,:]
    bary_u=np.sum(offset*cross,axis=-1)*inverse
    cross2=np.cross(offset,edge_u[None,:,:])
    bary_v=np.sum(direction[:,None,:]*cross2,axis=-1)*inverse
    parameter=np.sum(edge_v[None,:,:]*cross2,axis=-1)*inverse
    return np.any(valid&(bary_u>=0)&(bary_v>=0)&(bary_u+bary_v<=1)&(parameter>=0)&(parameter<=1))
def endpoint_edge_distance(points,starts,ends):
    direction=ends-starts
    offset=points[:,None,:]-starts[None,:,:]
    parameter=np.clip(np.sum(offset*direction[None,:,:],axis=-1)/np.sum(direction*direction,axis=-1)[None,:],0,1)
    delta=offset-parameter[:,:,None]*direction[None,:,:]
    return np.min(np.sum(delta*delta,axis=-1))
def mesh_distance(first,second):
    starts_a,ends_a=edges_of(first); starts_b,ends_b=edges_of(second)
    if segment_face_hit(starts_a,ends_a,second) or segment_face_hit(starts_b,ends_b,first): return 0.0
    minimum=min(point_face_dist(starts_a,second),point_face_dist(starts_b,first),endpoint_edge_distance(starts_a,starts_b,ends_b),endpoint_edge_distance(starts_b,starts_a,ends_a))
    direction_a=(ends_a-starts_a)[:,None,:]; direction_b=(ends_b-starts_b)[None,:,:]; offset=starts_a[:,None,:]-starts_b[None,:,:]
    aa=np.sum(direction_a*direction_a,axis=-1); ab=np.sum(direction_a*direction_b,axis=-1); bb=np.sum(direction_b*direction_b,axis=-1)
    ad=np.sum(direction_a*offset,axis=-1); bd=np.sum(direction_b*offset,axis=-1); denominator=aa*bb-ab*ab
    valid=denominator>1e-30
    parameter_a=np.divide(ab*bd-bb*ad,denominator,out=np.zeros_like(denominator),where=valid)
    parameter_b=np.divide(aa*bd-ab*ad,denominator,out=np.zeros_like(denominator),where=valid)
    valid &= (parameter_a>=0)&(parameter_a<=1)&(parameter_b>=0)&(parameter_b<=1)
    delta=offset+parameter_a[:,:,None]*direction_a-parameter_b[:,:,None]*direction_b
    minimum=min(minimum,np.min(np.where(valid,np.sum(delta*delta,axis=-1),np.inf)))
    return float(np.sqrt(minimum))
compact_matches=[]
for name_a,name_b in itertools.combinations(sorted(mesh_triangles),2):
    first=mesh_triangles[name_a]; second=mesh_triangles[name_b]
    gap=np.maximum(np.maximum(first.min(axis=(0,1))-second.max(axis=(0,1)),second.min(axis=(0,1))-first.max(axis=(0,1))),0)
    if np.linalg.norm(gap)>0.002: continue
    distance=mesh_distance(first,second)
    if distance<=0.002: compact_matches.append((name_a,name_b,distance*1000))
print('MATCHES',len(compact_matches))
for name_a,name_b,distance in compact_matches: print(name_a,name_b,format(distance,'.9f'))