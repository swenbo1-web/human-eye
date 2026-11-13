def point_segment_sq(point,start,end):
 direction=end-start
 denom=np.einsum('ij,ij->i',direction,direction)
 fraction=np.divide(np.einsum('ij,ij->i',point-start,direction),denom,out=np.zeros_like(denom),where=denom>0)
 delta=point-(start+np.clip(fraction,0,1)[:,None]*direction)
 return np.einsum('ij,ij->i',delta,delta)

def point_triangle_sq(point,tri):
 start=tri[:,0]; edge_a=tri[:,1]-start; edge_b=tri[:,2]-start
 normal=np.cross(edge_a,edge_b); normal_sq=np.einsum('ij,ij->i',normal,normal)
 offset=point-start
 height=np.einsum('ij,ij->i',offset,normal)
 projected=offset-normal*np.divide(height,normal_sq,out=np.zeros_like(height),where=normal_sq>0)[:,None]
 aa=np.einsum('ij,ij->i',edge_a,edge_a); ab=np.einsum('ij,ij->i',edge_a,edge_b); bb=np.einsum('ij,ij->i',edge_b,edge_b)
 pa=np.einsum('ij,ij->i',projected,edge_a); pb=np.einsum('ij,ij->i',projected,edge_b)
 determinant=aa*bb-ab*ab
 u=np.divide(bb*pa-ab*pb,determinant,out=np.full_like(pa,np.nan),where=determinant>0)
 v=np.divide(aa*pb-ab*pa,determinant,out=np.full_like(pb,np.nan),where=determinant>0)
 inside=(u>=0)&(v>=0)&(u+v<=1)&(normal_sq>0)
 result=np.full(len(point),np.inf)
 result[inside]=height[inside]**2/normal_sq[inside]
 for index in range(3):result=np.minimum(result,point_segment_sq(point,tri[:,index],tri[:,(index+1)%3]))
 return result

def segment_segment_sq(start_a,end_a,start_b,end_b):
 direction_a=end_a-start_a; direction_b=end_b-start_b; offset=start_a-start_b
 aa=np.einsum('ij,ij->i',direction_a,direction_a); bb=np.einsum('ij,ij->i',direction_b,direction_b); ab=np.einsum('ij,ij->i',direction_a,direction_b)
 ac=np.einsum('ij,ij->i',direction_a,offset); bc=np.einsum('ij,ij->i',direction_b,offset)
 determinant=aa*bb-ab*ab
 fraction_a=np.divide(ab*bc-bb*ac,determinant,out=np.full_like(aa,np.nan),where=determinant>1e-14*aa*bb)
 fraction_b=np.divide(aa*bc-ab*ac,determinant,out=np.full_like(aa,np.nan),where=determinant>1e-14*aa*bb)
 inside=(fraction_a>=0)&(fraction_a<=1)&(fraction_b>=0)&(fraction_b<=1)
 result=np.minimum.reduce([point_segment_sq(start_a,start_b,end_b),point_segment_sq(end_a,start_b,end_b),point_segment_sq(start_b,start_a,end_a),point_segment_sq(end_b,start_a,end_a)])
 delta=offset[inside]+fraction_a[inside,None]*direction_a[inside]-fraction_b[inside,None]*direction_b[inside]
 result[inside]=np.minimum(result[inside],np.einsum('ij,ij->i',delta,delta))
 return result

def segment_triangle_hits(start,end,tri):
 direction=end-start; edge_a=tri[:,1]-tri[:,0]; edge_b=tri[:,2]-tri[:,0]
 cross=np.cross(direction,edge_b); determinant=np.einsum('ij,ij->i',edge_a,cross)
 valid=np.abs(determinant)>1e-14*np.linalg.norm(direction,axis=1)*np.linalg.norm(edge_a,axis=1)*np.linalg.norm(edge_b,axis=1)
 inverse=np.divide(1.,determinant,out=np.zeros_like(determinant),where=valid)
 offset=start-tri[:,0]
 u=np.einsum('ij,ij->i',offset,cross)*inverse
 cross2=np.cross(offset,edge_a)
 v=np.einsum('ij,ij->i',direction,cross2)*inverse
 fraction=np.einsum('ij,ij->i',edge_b,cross2)*inverse
 return valid&(u>=0)&(v>=0)&(u+v<=1)&(fraction>=0)&(fraction<=1)

def surface_distance(first,second):
 tri_a=np.repeat(first,len(second),axis=0); tri_b=np.tile(second,(len(first),1,1))
 result=np.full(len(tri_a),np.inf)
 for index in range(3):
  if np.any(segment_triangle_hits(tri_a[:,index],tri_a[:,(index+1)%3],tri_b)) or np.any(segment_triangle_hits(tri_b[:,index],tri_b[:,(index+1)%3],tri_a)):
   return 0.0,'triangle_intersection'
  result=np.minimum(result,point_triangle_sq(tri_a[:,index],tri_b))
  result=np.minimum(result,point_triangle_sq(tri_b[:,index],tri_a))
 for index_a in range(3):
  for index_b in range(3):
   result=np.minimum(result,segment_segment_sq(tri_a[:,index_a],tri_a[:,(index_a+1)%3],tri_b[:,index_b],tri_b[:,(index_b+1)%3]))
 distance=float(np.sqrt(result.min()))
 return distance,'feature_distance'

results=[]
for first,second,bound in candidates:
 distance,method=surface_distance(geom[first]['triangles'],geom[second]['triangles'])
 results.append((first,second,distance,method))
qualifying=[row for row in results if row[2]<=threshold]
print('triangles_total',sum(len(item['triangles']) for item in geom))
print('tested',len(results),'excluded_by_bounds',276-len(results),'qualifying',len(qualifying))
for first,second,distance,method in qualifying:
 print(geom[first]['name'],geom[second]['name'],format(distance*1000*scene.unit_settings.scale_length,'.9f'),method)
print('candidate_but_over_threshold')
for first,second,distance,method in results:
 if distance>threshold:print(geom[first]['name'],geom[second]['name'],format(distance*1000,'.9f'))