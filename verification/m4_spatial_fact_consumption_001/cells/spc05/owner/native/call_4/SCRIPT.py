def mesh_check(name):
 vertices,indices=geo[name]
 counts={}
 for face in indices:
  for index in range(3):
   edge=tuple(sorted((int(face[index]),int(face[(index+1)%3])))); counts[edge]=counts.get(edge,0)+1
 return all(count==2 for count in counts.values())
def winding_numbers(points, mesh_name):
 vertices,indices=geo[mesh_name]; triangles=vertices[indices]
 output=[]
 for point in points:
  rays=triangles-point; lengths=np.linalg.norm(rays,axis=2)
  numerator=np.einsum('ij,ij->i',rays[:,0],np.cross(rays[:,1],rays[:,2]))
  denominator=lengths.prod(axis=1)+np.einsum('ij,ij->i',rays[:,0],rays[:,1])*lengths[:,2]+np.einsum('ij,ij->i',rays[:,1],rays[:,2])*lengths[:,0]+np.einsum('ij,ij->i',rays[:,2],rays[:,0])*lengths[:,1]
  output.append(np.sum(2*np.arctan2(numerator,denominator))/(4*np.pi))
 return np.array(output)
print('closed_edge_manifold',{name:mesh_check(name) for name in names})
for name in names[1:]:
 winding_a=winding_numbers(geo['Target'][0],name); winding_b=winding_numbers(geo[name][0],'Target')
 print(name,'max_abs_winding_Target_in_other',float(np.max(np.abs(winding_a))),'max_abs_winding_other_in_Target',float(np.max(np.abs(winding_b))))
