current_names={obj.name for obj in bpy.context.scene.objects if obj.type=='MESH'}
unchanged=current_names==set(geoms)
if unchanged:
 for name, cached in geoms.items():
  fresh=getgeom(bpy.context.scene.objects[name])
  if not all(np.array_equal(a,b) for a,b in zip(fresh,cached)): unchanged=False; break
print('current evaluated geometry matches calculation:',unchanged)
verts,faces,edges=geoms['Near_017']; triangles=verts[faces]
start=targetsegs[:,0,None,:]; direction=targetsegs[:,1,None,:]-start
corner=triangles[None,:,0,:]; side1=triangles[None,:,1,:]-corner; side2=triangles[None,:,2,:]-corner
cross=np.cross(direction,side2); det=np.sum(side1*cross,axis=2); inv=1/np.where(det!=0,det,1)
delta=start-corner; u=np.sum(delta*cross,axis=2)*inv; q=np.cross(delta,side1); v=np.sum(direction*q,axis=2)*inv; along=np.sum(side2*q,axis=2)*inv
hits=np.argwhere((det!=0)&(u>0)&(v>0)&(u+v<1)&(along>0)&(along<1))
print('strict interior segment-triangle crossings:',len(hits))
index=tuple(hits[0]); edge_index,face_index=index
point1=targetsegs[edge_index,0]+along[index]*(targetsegs[edge_index,1]-targetsegs[edge_index,0])
point2=triangles[face_index,0]+u[index]*(triangles[face_index,1]-triangles[face_index,0])+v[index]*(triangles[face_index,2]-triangles[face_index,0])
print('Target edge vertex indices',targetedges[edge_index].tolist(),'Near_017 triangle indices',faces[face_index].tolist())
print('segment parameter',float(along[index]),'triangle barycentric',[float(1-u[index]-v[index]),float(u[index]),float(v[index])])
print('intersection world m',point1.tolist(),'residual m',float(np.linalg.norm(point1-point2)))