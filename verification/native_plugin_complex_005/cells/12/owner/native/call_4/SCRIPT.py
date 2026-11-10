target_world,target_tris,target_local,target_mat=geo['Object_01']
inv_target=np.linalg.inv(target_mat)
for name in ['Object_02','Object_03','Object_04']:
 world=geo[name][0]
 in_target=world@inv_target[:3,:3].T+inv_target[:3,3]
 print(name,'vertices in target frame',in_target.tolist())
# Point-triangle distances: projection inside triangle, otherwise closest point on its three edges.
def point_triangle_batch(points, triangles):
 point=points[:,None,:]; first=triangles[None,:,0,:]; second=triangles[None,:,1,:]; third=triangles[None,:,2,:]
 side1=second-first; side2=third-first; relative=point-first
 aa=np.sum(side1*side1,-1); ab=np.sum(side1*side2,-1); bb=np.sum(side2*side2,-1)
 ra=np.sum(relative*side1,-1); rb=np.sum(relative*side2,-1); denominator=aa*bb-ab*ab
 coord1=(bb*ra-ab*rb)/denominator; coord2=(aa*rb-ab*ra)/denominator
 projected=first+coord1[...,None]*side1+coord2[...,None]*side2
 inside=(coord1>=0)&(coord2>=0)&(coord1+coord2<=1)
 distances=np.where(inside,np.sum((point-projected)**2,-1),np.inf)
 closest=projected.copy()
 for begin,end in [(first,second),(second,third),(third,first)]:
  direction=end-begin
  parameter=np.clip(np.sum((point-begin)*direction,-1)/np.sum(direction*direction,-1),0,1)
  candidate=begin+parameter[...,None]*direction
  square=np.sum((point-candidate)**2,-1); improve=square<distances
  distances=np.where(improve,square,distances); closest=np.where(improve[...,None],candidate,closest)
 index=np.unravel_index(np.argmin(distances),distances.shape)
 return float(distances[index]),points[index[0]],closest[index],index

def unique_edges(tris):
 return np.array(sorted({tuple(sorted((int(face[idx]),int(face[(idx+1)%3])))) for face in tris for idx in range(3)}))

def edge_edge_batch(vertices_a,tris_a,vertices_b,tris_b):
 edges_a=vertices_a[unique_edges(tris_a)];edges_b=vertices_b[unique_edges(tris_b)]
 start_a=edges_a[:,None,0];start_b=edges_b[None,:,0]
 dir_a=edges_a[:,None,1]-start_a;dir_b=edges_b[None,:,1]-start_b; relative=start_a-start_b
 aa=np.sum(dir_a*dir_a,-1);bb=np.sum(dir_a*dir_b,-1);cc=np.sum(dir_b*dir_b,-1)
 dd=np.sum(dir_a*relative,-1);ee=np.sum(dir_b*relative,-1);denom=aa*cc-bb*bb
 valid=denom>1e-25
 para_a=np.divide(bb*ee-cc*dd,denom,out=np.zeros_like(denom),where=valid)
 para_b=np.divide(aa*ee-bb*dd,denom,out=np.zeros_like(denom),where=valid)
 valid=valid&(para_a>=0)&(para_a<=1)&(para_b>=0)&(para_b<=1)
 pairs=[(para_a,para_b,valid)]
 for fixed in [0.,1.]:
  pairs.append((np.full_like(denom,fixed),np.clip((ee+bb*fixed)/cc,0,1),np.ones_like(valid)))
  pairs.append((np.clip((bb*fixed-dd)/aa,0,1),np.full_like(denom,fixed),np.ones_like(valid)))
 best=(np.inf,None,None)
 for para_a,para_b,valid in pairs:
  point_a=start_a+para_a[...,None]*dir_a;point_b=start_b+para_b[...,None]*dir_b
  square=np.where(valid,np.sum((point_a-point_b)**2,-1),np.inf)
  index=np.unravel_index(np.argmin(square),square.shape)
  if square[index]<best[0]:best=(float(square[index]),point_a[index],point_b[index])
 return best
for name in ['Object_02','Object_03','Object_04']:
 world,tris,_,_=geo[name]
 result_a=point_triangle_batch(world,target_world[target_tris])
 result_b=point_triangle_batch(target_world,world[tris])
 result_c=edge_edge_batch(target_world,target_tris,world,tris)
 best=min([(result_a[0],result_a[2],result_a[1]),result_b[:3],result_c],key=lambda result:result[0])
 print('DISTANCE',name,math.sqrt(best[0]),'target point',best[1].tolist(),'candidate point',best[2].tolist(),'feature distances',*[math.sqrt(result[0]) for result in [result_a,result_b,result_c]])
