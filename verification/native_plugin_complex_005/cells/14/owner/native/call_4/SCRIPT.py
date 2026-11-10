target=cache['Object_01']
inv_target=np.linalg.inv(target['matrix'])
for name in ['Object_02','Object_03','Object_04']:
 points=cache[name]['world']@inv_target[:3,:3].T+inv_target[:3,3]
 print(name,'in target coordinates',points.tolist())
# Confirm cached geometry and transforms against the current scene before using them.
print('cache_current',all(np.array_equal(np.array(bpy.data.objects[name].matrix_world),data['matrix']) and np.array_equal(np.array([v.co[:] for v in bpy.data.objects[name].data.vertices]),data['local']) and np.array_equal(np.array([t.vertices[:] for t in bpy.data.objects[name].data.loop_triangles]),data['tris']) for name,data in cache.items()))
def point_triangle(point, triangle):
 first,second,third=triangle
 edge_a=second-first; edge_b=third-first
 normal=np.cross(edge_a,edge_b)
 projected=point-normal*np.dot(point-first,normal)/np.dot(normal,normal)
 offset=projected-first
 aa=np.dot(edge_a,edge_a); ab=np.dot(edge_a,edge_b); bb=np.dot(edge_b,edge_b)
 pa=np.dot(offset,edge_a); pb=np.dot(offset,edge_b)
 denom=aa*bb-ab*ab
 coord_a=(bb*pa-ab*pb)/denom; coord_b=(aa*pb-ab*pa)/denom
 if coord_a>=0 and coord_b>=0 and coord_a+coord_b<=1: return projected
 candidates=[]
 for start,end in [(first,second),(second,third),(third,first)]:
  delta=end-start
  candidates.append(start+np.clip(np.dot(point-start,delta)/np.dot(delta,delta),0,1)*delta)
 return min(candidates,key=lambda candidate:np.dot(candidate-point,candidate-point))
def segment_segment(start_a,end_a,start_b,end_b):
 delta_a=end_a-start_a; delta_b=end_b-start_b; offset=start_a-start_b
 aa=np.dot(delta_a,delta_a); bb=np.dot(delta_b,delta_b); ab=np.dot(delta_a,delta_b)
 da=np.dot(delta_a,offset); db=np.dot(delta_b,offset)
 denom=aa*bb-ab*ab
 param_a=np.clip((ab*db-da*bb)/denom,0,1) if denom>1e-25 else 0.
 param_b=(ab*param_a+db)/bb
 if param_b<0: param_b=0.; param_a=np.clip(-da/aa,0,1)
 elif param_b>1: param_b=1.; param_a=np.clip((ab-da)/aa,0,1)
 return start_a+param_a*delta_a,start_b+param_b*delta_b
for name in ['Object_02','Object_04']:
 data=cache[name]; best=(float('inf'),None,None,None)
 for index_a,indices_a in enumerate(target['tris']):
  triangle_a=target['world'][indices_a]
  for index_b,indices_b in enumerate(data['tris']):
   triangle_b=data['world'][indices_b]
   pairs=[]
   for point in triangle_a: pairs.append((point,point_triangle(point,triangle_b)))
   for point in triangle_b: pairs.append((point_triangle(point,triangle_a),point))
   for edge_a in range(3):
    for edge_b in range(3): pairs.append(segment_segment(triangle_a[edge_a],triangle_a[(edge_a+1)%3],triangle_b[edge_b],triangle_b[(edge_b+1)%3]))
   for point_a,point_b in pairs:
    distance_sq=np.dot(point_a-point_b,point_a-point_b)
    if distance_sq<best[0]: best=(distance_sq,point_a.copy(),point_b.copy(),(index_a,index_b))
 print(name,'min surface gap',math.sqrt(best[0]),'world witnesses',best[1].tolist(),best[2].tolist(),'triangle pair',best[3])