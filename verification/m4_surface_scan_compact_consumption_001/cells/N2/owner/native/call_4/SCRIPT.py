def dot_rows(left,right):
 return np.sum(left*right,axis=-1)
def point_segment_sq(point,start,end):
 direction=end-start
 param=np.clip(dot_rows(point-start,direction)/dot_rows(direction,direction),0,1)
 delta=point-(start+param[...,None]*direction)
 return dot_rows(delta,delta)
def point_triangle_sq(point,tri):
 start=tri[...,0,:]; edge_one=tri[...,1,:]-start; edge_two=tri[...,2,:]-start
 normal=np.cross(edge_one,edge_two); norm_sq=dot_rows(normal,normal)
 offset=point-start
 height=dot_rows(offset,normal)/norm_sq
 projected=offset-height[...,None]*normal
 aa=dot_rows(edge_one,edge_one); ab=dot_rows(edge_one,edge_two); bb=dot_rows(edge_two,edge_two)
 pa=dot_rows(projected,edge_one); pb=dot_rows(projected,edge_two)
 denom=aa*bb-ab*ab
 bary_one=(pa*bb-pb*ab)/denom; bary_two=(pb*aa-pa*ab)/denom
 inside=(bary_one>=0)&(bary_two>=0)&(bary_one+bary_two<=1)
 best=np.minimum.reduce([point_segment_sq(point,tri[...,idx,:],tri[...,(idx+1)%3,:]) for idx in range(3)])
 return np.where(inside,np.minimum(best,height*height*norm_sq),best)
def segment_segment_sq(start_one,end_one,start_two,end_two):
 edge_one=end_one-start_one; edge_two=end_two-start_two; offset=start_one-start_two
 aa=dot_rows(edge_one,edge_one); ab=dot_rows(edge_one,edge_two); bb=dot_rows(edge_two,edge_two)
 dd=dot_rows(edge_one,offset); ee=dot_rows(edge_two,offset)
 denom=aa*bb-ab*ab
 valid=denom>1e-14*aa*bb
 safe=np.where(valid,denom,1.0)
 param_one=(ab*ee-bb*dd)/safe; param_two=(aa*ee-ab*dd)/safe
 interior=valid&(param_one>=0)&(param_one<=1)&(param_two>=0)&(param_two<=1)
 delta=offset+param_one[...,None]*edge_one-param_two[...,None]*edge_two
 best=np.minimum.reduce([point_segment_sq(start_one,start_two,end_two),point_segment_sq(end_one,start_two,end_two),point_segment_sq(start_two,start_one,end_one),point_segment_sq(end_two,start_one,end_one)])
 return np.where(interior,np.minimum(best,dot_rows(delta,delta)),best)
def segment_hits_triangle(start,end,tri):
 edge_one=tri[...,1,:]-tri[...,0,:]; edge_two=tri[...,2,:]-tri[...,0,:]
 normal=np.cross(edge_one,edge_two)
 direction=end-start
 denom=dot_rows(direction,normal)
 valid=np.abs(denom)>1e-14*np.sqrt(dot_rows(direction,direction)*dot_rows(normal,normal))
 param=dot_rows(tri[...,0,:]-start,normal)/np.where(valid,denom,1.0)
 point=start+param[...,None]*direction
 offset=point-tri[...,0,:]
 aa=dot_rows(edge_one,edge_one); ab=dot_rows(edge_one,edge_two); bb=dot_rows(edge_two,edge_two)
 pa=dot_rows(offset,edge_one); pb=dot_rows(offset,edge_two)
 det=aa*bb-ab*ab
 bary_one=(pa*bb-pb*ab)/det; bary_two=(pb*aa-pa*ab)/det
 return valid&(param>=0)&(param<=1)&(bary_one>=-1e-12)&(bary_two>=-1e-12)&(bary_one+bary_two<=1+1e-12)
def mesh_distance(tris_one,tris_two):
 one=tris_one[:,None,:,:]; two=tris_two[None,:,:,:]
 best=np.full((len(tris_one),len(tris_two)),np.inf)
 hits=np.zeros(best.shape,dtype=bool)
 for idx in range(3):
  best=np.minimum(best,point_triangle_sq(one[...,idx,:],two))
  best=np.minimum(best,point_triangle_sq(two[...,idx,:],one))
  hits|=segment_hits_triangle(one[...,idx,:],one[...,(idx+1)%3,:],two)
  hits|=segment_hits_triangle(two[...,idx,:],two[...,(idx+1)%3,:],one)
  for other in range(3):
   best=np.minimum(best,segment_segment_sq(one[...,idx,:],one[...,(idx+1)%3,:],two[...,other,:],two[...,(other+1)%3,:]))
 if np.any(hits): return 0.0
 return math.sqrt(max(0,float(best.min())))
results=[]
for first,second,lower in candidate_pairs:
 distance=mesh_distance(scan_meshes[first]['tri'],scan_meshes[second]['tri'])*mm_per_unit
 results.append((scan_meshes[first]['name'],scan_meshes[second]['name'],distance))
qualifying=[record for record in results if record[2]<=2.0+1e-9]
print('QUALIFYING',len(qualifying))
for record in qualifying: print('%s %s %.9f mm'%record)
print('NEAREST_EXCLUDED_CANDIDATES',sorted([r for r in results if r[2]>2.0+1e-9],key=lambda r:r[2])[:8])
