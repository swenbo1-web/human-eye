fresh=acquire()
print('current_geometry_matches',fingerprint(fresh)==geom_sig)
name='Near_017'
print('winner',name,'distance',results[name][0],'witness',results[name][1].tolist())
# Independently expose the intersecting edge and triangle and solve their intersection.
ta=geom['Target'][0][geom['Target'][1]]; tb=geom[name][0][geom[name][1]]
found=False
for label,source,dest in [('Target edge / Near_017 face',ta,tb),('Near_017 edge / Target face',tb,ta)]:
 if found: break
 for ti,tri in enumerate(source):
  if found: break
  for ei in range(3):
   if found: break
   start=tri[ei]; end=tri[(ei+1)%3]; direction=end-start
   for tj,face in enumerate(dest):
    matrix=np.column_stack((direction,-(face[1]-face[0]),-(face[2]-face[0])))
    if abs(np.linalg.det(matrix))<1e-25: continue
    coeff=np.linalg.solve(matrix,face[0]-start)
    along,u,v=coeff
    if 0<=along<=1 and u>=0 and v>=0 and u+v<=1:
     edgepoint=start+along*direction
     facepoint=face[0]+u*(face[1]-face[0])+v*(face[2]-face[0])
     print('intersection',label,'triangle_indices',ti,tj,'edge_index',ei)
     print('edge_parameter',float(along),'face_barycentric',[float(1-u-v),float(u),float(v)])
     print('point_world_m',edgepoint.tolist(),'residual_m',float(np.linalg.norm(edgepoint-facepoint)))
     print('edge_endpoints',start.tolist(),end.tolist(),'face_vertices',face.tolist())
     found=True; break
print('candidate_count',len(results),'positive_others',sum(r[0]>0 for r in results.values()),'unresolved',0)
