for name in ['Target','Near_017']:
 obj=bpy.context.scene.objects.get(name); ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get()); mesh=ev.to_mesh(); mesh.calc_loop_triangles()
 mat=np.array(ev.matrix_world,dtype=np.float64); cur=np.array([v.co[:] for v in mesh.vertices])@mat[:3,:3].T+mat[:3,3]
 face_now=np.array([tri.vertices[:] for tri in mesh.loop_triangles])
 print(name,'cache_matches_current',np.array_equal(cur,geometry[name][0]) and np.array_equal(face_now,geometry[name][1]))
 ev.to_mesh_clear()
verts,faces,edges=geometry['Near_017']; triangles=verts[faces]
for label,segments,tris,edge_ids in [('Target edge / Near_017 triangle',target_segs,triangles,target_edges),('Near_017 edge / Target triangle',verts[edges],target_tris,edges)]:
 origin=segments[:,None,0,:]; direction=segments[:,None,1,:]-origin
 aa=tris[None,:,0,:]; ab=tris[None,:,1,:]-aa; ac=tris[None,:,2,:]-aa
 cross=np.cross(direction,ac); det=np.sum(ab*cross,axis=-1); valid=np.abs(det)>1e-18; inv=np.where(valid,1/np.where(valid,det,1),0)
 delta=origin-aa; uu=np.sum(delta*cross,axis=-1)*inv; q=np.cross(delta,ab); vv=np.sum(direction*q,axis=-1)*inv; along=np.sum(ac*q,axis=-1)*inv
 hit=valid&(uu>=0)&(vv>=0)&(uu+vv<=1)&(along>=0)&(along<=1)
 for edge_idx,tri_idx in np.argwhere(hit):
  param=along[edge_idx,tri_idx]; bary=[1-uu[edge_idx,tri_idx]-vv[edge_idx,tri_idx],uu[edge_idx,tri_idx],vv[edge_idx,tri_idx]]
  point=segments[edge_idx,0]+param*(segments[edge_idx,1]-segments[edge_idx,0])
  point2=np.array(bary)@tris[tri_idx]
  print(label,'edge_vertices',edge_ids[edge_idx].tolist(),'triangle_index',int(tri_idx),'edge_parameter',float(param),'barycentric',bary,'intersection_m',point.tolist(),'residual_m',float(np.linalg.norm(point-point2)))
print('candidates_processed',len(results),'positive_distance_candidates',sum(row[0]>0 for row in results))