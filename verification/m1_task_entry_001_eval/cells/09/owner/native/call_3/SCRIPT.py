import numpy as np
from math import sqrt
scene=bpy.context.scene
depsgraph=bpy.context.evaluated_depsgraph_get()
triangles={}
for obj in objs:
    evaluated=obj.evaluated_get(depsgraph)
    mesh=evaluated.to_mesh()
    mesh.calc_loop_triangles()
    local=np.array([tuple(vertex.co) for vertex in mesh.vertices],dtype=np.float64)
    matrix=np.array(obj.evaluated_get(depsgraph).matrix_world,dtype=np.float64)
    world=local@matrix[:3,:3].T+matrix[:3,3]
    triangles[obj.name]=world[np.array([tuple(triangle.vertices) for triangle in mesh.loop_triangles])]
    evaluated.to_mesh_clear()
print('evaluated_triangle_counts', {name:len(tris) for name,tris in triangles.items()})
def vertex_face_candidates(points,faces):
    starts=faces[:,0]; first=faces[:,1]-starts; second=faces[:,2]-starts
    normals=np.cross(first,second); normal_squared=np.einsum('ij,ij->i',normals,normals)
    offsets=points[:,None,:]-starts[None,:,:]
    signed=np.einsum('pfi,fi->pf',offsets,normals)/normal_squared
    projection=points[:,None,:]-signed[:,:,None]*normals[None,:,:]
    relative=projection-starts[None,:,:]
    dot00=np.einsum('fi,fi->f',first,first); dot01=np.einsum('fi,fi->f',first,second); dot11=np.einsum('fi,fi->f',second,second)
    dot20=np.einsum('pfi,fi->pf',relative,first); dot21=np.einsum('pfi,fi->pf',relative,second)
    denominator=dot00*dot11-dot01*dot01
    bary_first=(dot11*dot20-dot01*dot21)/denominator
    bary_second=(dot00*dot21-dot01*dot20)/denominator
    valid=(bary_first>=-1e-13)&(bary_second>=-1e-13)&(bary_first+bary_second<=1+1e-13)&(normal_squared[None,:]>0)
    squared=np.sum((points[:,None,:]-projection)**2,axis=2)
    squared[~valid]=np.inf
    index=np.unravel_index(np.argmin(squared),squared.shape)
    return float(squared[index]), points[index[0]],projection[index]
def edge_candidates(faces):
    return np.concatenate([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]],axis=0)
def surface_distance(left,right):
    candidates=[]
    candidates.append(vertex_face_candidates(left.reshape(-1,3),right))
    reverse=vertex_face_candidates(right.reshape(-1,3),left)
    candidates.append((reverse[0],reverse[2],reverse[1]))
    left_edges=edge_candidates(left); right_edges=edge_candidates(right)
    for edge in left_edges:
        origin=edge[0]; direction=edge[1]-edge[0]
        other_origins=right_edges[:,0]; other_directions=right_edges[:,1]-other_origins
        offset=origin-other_origins
        aa=float(direction@direction); bb=other_directions@direction; cc=np.einsum('ij,ij->i',other_directions,other_directions)
        dd=offset@direction; ee=np.einsum('ij,ij->i',other_directions,offset)
        denom=aa*cc-bb*bb
        first=np.divide(bb*ee-cc*dd,denom,out=np.zeros_like(denom),where=abs(denom)>1e-28)
        second=np.divide(aa*ee-bb*dd,denom,out=np.zeros_like(denom),where=abs(denom)>1e-28)
        valid=(first>=0)&(first<=1)&(second>=0)&(second<=1)&(abs(denom)>1e-28)
        first_points=origin+first[:,None]*direction
        second_points=other_origins+second[:,None]*other_directions
        squared=np.sum((first_points-second_points)**2,axis=1); squared[~valid]=np.inf
        idx=np.argmin(squared)
        candidates.append((float(squared[idx]),first_points[idx],second_points[idx]))
        for endpoint in edge:
            parameters=np.clip(np.einsum('ij,ij->i',endpoint-other_origins,other_directions)/cc,0,1)
            projections=other_origins+parameters[:,None]*other_directions
            distances=np.sum((endpoint-projections)**2,axis=1); idx=np.argmin(distances)
            candidates.append((float(distances[idx]),endpoint,projections[idx]))
        parameters=np.clip((other_origins-origin)@direction/aa,0,1)
        projections=origin+parameters[:,None]*direction
        distances=np.sum((other_origins-projections)**2,axis=1); idx=np.argmin(distances)
        candidates.append((float(distances[idx]),projections[idx],other_origins[idx]))
    best=min(candidates,key=lambda candidate:candidate[0])
    return sqrt(best[0]),best[1],best[2]
results={}
for name,tris in triangles.items():
    if name!='Mesh_DDBB95':
        result=surface_distance(triangles['Mesh_DDBB95'],tris)
        results[name]=result
        print(name,'distance_mm',format(result[0]*1000,'.12f'),'witness_target_m',result[1].tolist(),'witness_other_m',result[2].tolist())
