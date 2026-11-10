import numpy as np, time, hashlib
started=time.perf_counter()
depsgraph=bpy.context.evaluated_depsgraph_get()
def get_triangles(obj):
 evaluated=obj.evaluated_get(depsgraph)
 mesh=evaluated.to_mesh()
 try:
  mesh.calc_loop_triangles()
  vertices=np.array([v.co[:] for v in mesh.vertices],dtype=np.float64)
  matrix=np.array(evaluated.matrix_world,dtype=np.float64)
  vertices=vertices@matrix[:3,:3].T+matrix[:3,3]
  indices=np.array([tuple(t.vertices) for t in mesh.loop_triangles],dtype=np.int64)
  return vertices[indices]
 finally: evaluated.to_mesh_clear()
triangles={obj.name:get_triangles(obj) for obj in meshes}
print('units',bpy.context.scene.unit_settings.system,'scale_length',bpy.context.scene.unit_settings.scale_length)
print('evaluated triangles',[(name,len(tris)) for name,tris in triangles.items()])
def dot(first,second): return np.sum(first*second,axis=-1)
def triangle_distance(first,second):
 first=np.broadcast_to(first[:,None,:,:],(len(first),len(second),3,3)).reshape(-1,3,3)
 second=np.broadcast_to(second[None,:,:,:],(len(first)//len(second),len(second),3,3)).reshape(-1,3,3) if False else np.tile(second,(len(first)//len(second),1,1))
 best=float('inf'); witness=None
 def record(squared,point_a,point_b):
  nonlocal best,witness
  index=int(np.argmin(squared)); value=float(squared[index])
  if value<best: best=value; witness=(point_a[index].copy(),point_b[index].copy())
 # Vertex to face interior, both directions.
 for points,faces,reverse in [(first,second,False),(second,first,True)]:
  edge_u=faces[:,1]-faces[:,0]; edge_v=faces[:,2]-faces[:,0]
  normal=np.cross(edge_u,edge_v); norm_squared=dot(normal,normal)
  for vertex_index in range(3):
   point=points[:,vertex_index]; offset=point-faces[:,0]
   signed=dot(offset,normal)/np.where(norm_squared>0,norm_squared,1)
   projection=point-signed[:,None]*normal
   offset_projected=projection-faces[:,0]
   uu=dot(edge_u,edge_u); uv=dot(edge_u,edge_v); vv=dot(edge_v,edge_v)
   pu=dot(offset_projected,edge_u); pv=dot(offset_projected,edge_v)
   denominator=uu*vv-uv*uv
   beta=(vv*pu-uv*pv)/np.where(denominator!=0,denominator,1)
   gamma=(uu*pv-uv*pu)/np.where(denominator!=0,denominator,1)
   valid=(denominator>0)&(beta>=-1e-13)&(gamma>=-1e-13)&(beta+gamma<=1+1e-13)
   squared=np.where(valid,dot(point-projection,point-projection),np.inf)
   record(squared,projection if reverse else point,point if reverse else projection)
 # Edge pairs: endpoint projections and interior stationary pair.
 for first_edge in range(3):
  start_a=first[:,first_edge]; vector_a=first[:,(first_edge+1)%3]-start_a
  aa=dot(vector_a,vector_a)
  for second_edge in range(3):
   start_b=second[:,second_edge]; vector_b=second[:,(second_edge+1)%3]-start_b
   bb=dot(vector_b,vector_b); ab=dot(vector_a,vector_b); offset=start_a-start_b
   aw=dot(vector_a,offset); bw=dot(vector_b,offset)
   denominator=aa*bb-ab*ab
   param_a=(ab*bw-bb*aw)/np.where(denominator>0,denominator,1)
   param_b=(aa*bw-ab*aw)/np.where(denominator>0,denominator,1)
   valid=(denominator>1e-25)&(param_a>=0)&(param_a<=1)&(param_b>=0)&(param_b<=1)
   point_a=start_a+param_a[:,None]*vector_a; point_b=start_b+param_b[:,None]*vector_b
   record(np.where(valid,dot(point_a-point_b,point_a-point_b),np.inf),point_a,point_b)
   for endpoint in (0.,1.):
    point_a=start_a+endpoint*vector_a
    projection=np.clip(dot(point_a-start_b,vector_b)/np.where(bb>0,bb,1),0,1)
    point_b=start_b+projection[:,None]*vector_b
    record(dot(point_a-point_b,point_a-point_b),point_a,point_b)
    point_b=start_b+endpoint*vector_b
    projection=np.clip(dot(point_b-start_a,vector_a)/np.where(aa>0,aa,1),0,1)
    point_a=start_a+projection[:,None]*vector_a
    record(dot(point_a-point_b,point_a-point_b),point_a,point_b)
 # Edges piercing a face imply zero surface distance.
 for edges,faces in [(first,second),(second,first)]:
  edge_u=faces[:,1]-faces[:,0]; edge_v=faces[:,2]-faces[:,0]
  for edge_index in range(3):
   origin=edges[:,edge_index]; direction=edges[:,(edge_index+1)%3]-origin
   cross=np.cross(direction,edge_v); determinant=dot(edge_u,cross)
   inverse=1/np.where(determinant!=0,determinant,1)
   delta=origin-faces[:,0]; beta=dot(delta,cross)*inverse
   cross2=np.cross(delta,edge_u); gamma=dot(direction,cross2)*inverse
   parameter=dot(edge_v,cross2)*inverse
   valid=(np.abs(determinant)>1e-25)&(beta>=0)&(gamma>=0)&(beta+gamma<=1)&(parameter>=0)&(parameter<=1)
   if np.any(valid):
    point=origin[np.flatnonzero(valid)[0]]+parameter[np.flatnonzero(valid)[0]]*direction[np.flatnonzero(valid)[0]]
    return 0.,(point,point)
 return np.sqrt(best),witness
results=[]
for name,tris in triangles.items():
 if name!='Target':
  distance,witness=triangle_distance(triangles['Target'],tris)
  results.append((distance,name,witness))
results.sort(key=lambda item:item[0])
for distance,name,witness in results: print(name,format(distance,'.12f'))
print('winner_witness',results[0][2])
print('elapsed',time.perf_counter()-started)
print('fingerprint',hashlib.sha256(b''.join(name.encode()+tris.tobytes() for name,tris in sorted(triangles.items()))).hexdigest())