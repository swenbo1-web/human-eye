# Read mesh coordinates and apply the stored world matrices in double precision.
for name in names:
 obj=bpy.data.objects[name].evaluated_get(depsgraph)
 mesh=obj.to_mesh(); mesh.calc_loop_triangles()
 local=np.array([tuple(vertex.co) for vertex in mesh.vertices],dtype=np.float64)
 matrix=np.array(obj.matrix_world,dtype=np.float64)
 geo[name]=(local @ matrix[:3,:3].T + matrix[:3,3],np.array([tuple(tri.vertices) for tri in mesh.loop_triangles],dtype=np.int64))
 obj.to_mesh_clear()
def point_triangle(points, triangles):
 first=triangles[:,0]; side1=triangles[:,1]-first; side2=triangles[:,2]-first
 normal=np.cross(side1,side2); norm2=np.einsum('ij,ij->i',normal,normal)
 signed=np.einsum('ij,ij->i',points-first,normal)/norm2
 projection=points-signed[:,None]*normal
 relative=projection-first
 dot11=np.einsum('ij,ij->i',side1,side1); dot12=np.einsum('ij,ij->i',side1,side2); dot22=np.einsum('ij,ij->i',side2,side2)
 rel1=np.einsum('ij,ij->i',relative,side1); rel2=np.einsum('ij,ij->i',relative,side2)
 denominator=dot11*dot22-dot12*dot12
 bary1=(dot22*rel1-dot12*rel2)/denominator; bary2=(dot11*rel2-dot12*rel1)/denominator
 valid=(bary1>=0)&(bary2>=0)&(bary1+bary2<=1)
 closest=projection.copy(); distance=np.where(valid,np.sum((points-projection)**2,axis=1),np.inf)
 for edge_index in range(3):
  start=triangles[:,edge_index]; direction=triangles[:,(edge_index+1)%3]-start
  parameter=np.clip(np.einsum('ij,ij->i',points-start,direction)/np.einsum('ij,ij->i',direction,direction),0,1)
  candidate=start+parameter[:,None]*direction
  trial=np.sum((points-candidate)**2,axis=1); better=trial<distance
  closest[better]=candidate[better]; distance[better]=trial[better]
 return distance,closest

def surface_distance(name):
 vertices_a,indices_a=geo['Target']; vertices_b,indices_b=geo[name]
 tris_a=vertices_a[indices_a]; tris_b=vertices_b[indices_b]
 best=(float('inf'),None,None); intersections=0
 for offset in range(0,len(tris_a),16):
  batch=tris_a[offset:offset+16]
  first=np.repeat(batch,len(tris_b),axis=0); second=np.tile(tris_b,(len(batch),1,1))
  def record(dist,point_a,point_b):
   nonlocal best
   index=int(np.argmin(dist))
   if dist[index]<best[0]: best=(float(dist[index]),point_a[index].copy(),point_b[index].copy())
  for corner in range(3):
   dist,closest=point_triangle(first[:,corner],second); record(dist,first[:,corner],closest)
   dist,closest=point_triangle(second[:,corner],first); record(dist,closest,second[:,corner])
  for edge_a in range(3):
   start_a=first[:,edge_a]; direction_a=first[:,(edge_a+1)%3]-start_a
   for edge_b in range(3):
    start_b=second[:,edge_b]; direction_b=second[:,(edge_b+1)%3]-start_b
    relative=start_a-start_b
    aa=np.einsum('ij,ij->i',direction_a,direction_a); bb=np.einsum('ij,ij->i',direction_a,direction_b); cc=np.einsum('ij,ij->i',direction_b,direction_b)
    dd=np.einsum('ij,ij->i',direction_a,relative); ee=np.einsum('ij,ij->i',direction_b,relative)
    denominator=aa*cc-bb*bb; stable=denominator>1e-14*aa*cc
    param_a=np.divide(bb*ee-cc*dd,denominator,out=np.zeros_like(aa),where=stable)
    param_b=np.divide(aa*ee-bb*dd,denominator,out=np.zeros_like(aa),where=stable)
    valid=stable&(param_a>=0)&(param_a<=1)&(param_b>=0)&(param_b<=1)
    point_a=start_a+param_a[:,None]*direction_a; point_b=start_b+param_b[:,None]*direction_b
    dist=np.where(valid,np.sum((point_a-point_b)**2,axis=1),np.inf); record(dist,point_a,point_b)
  for source,target in [(first,second),(second,first)]:
   side1=target[:,1]-target[:,0]; side2=target[:,2]-target[:,0]
   for edge_index in range(3):
    origin=source[:,edge_index]; direction=source[:,(edge_index+1)%3]-origin
    cross=np.cross(direction,side2); determinant=np.einsum('ij,ij->i',side1,cross)
    stable=np.abs(determinant)>1e-14*np.linalg.norm(direction,axis=1)*np.linalg.norm(side1,axis=1)*np.linalg.norm(side2,axis=1)
    inverse=np.divide(1.,determinant,out=np.zeros_like(determinant),where=stable)
    relative=origin-target[:,0]; bary1=np.einsum('ij,ij->i',relative,cross)*inverse
    cross2=np.cross(relative,side1); bary2=np.einsum('ij,ij->i',direction,cross2)*inverse
    parameter=np.einsum('ij,ij->i',side2,cross2)*inverse
    hits=stable&(bary1>=0)&(bary2>=0)&(bary1+bary2<=1)&(parameter>=0)&(parameter<=1)
    intersections+=int(hits.sum())
 return best,intersections
results={}
for name in names[1:]:
 result,hits=surface_distance(name); results[name]=result
 print(name,'distance_m',format(np.sqrt(result[0]),'.12f'),'Target_xyz',result[1].tolist(),'other_xyz',result[2].tolist(),'intersection_hits',hits)
