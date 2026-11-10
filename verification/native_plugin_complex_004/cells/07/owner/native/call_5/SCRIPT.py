print('indices',index)
print('seg',targetsegs[edge_index].tolist(),'triangle',triangles[face_index].tolist())
print('stored',u[index],v[index],along[index],det[index])
origin=targetsegs[edge_index,0]; ray=targetsegs[edge_index,1]-origin; tri=triangles[face_index]
system=np.column_stack((ray,-(tri[1]-tri[0]),-(tri[2]-tri[0])))
solution=np.linalg.solve(system,tri[0]-origin)
print('direct solve t,u,v',solution.tolist(),'det',np.linalg.det(system))
print('arrays',direction[edge_index,0].tolist(),side1[0,face_index].tolist(),side2[0,face_index].tolist(),delta[edge_index,face_index].tolist())
print('point1',point1.tolist(),'point2',point2.tolist())