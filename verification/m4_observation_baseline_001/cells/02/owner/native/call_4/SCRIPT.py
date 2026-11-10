for name in ['N16','N13','N08','N28','N12','N24','N04','N19']:
 o=objs[name]; print(name,'world_vertices', [tuple(o.matrix_world@p.co) for p in o.data.vertices])
mid=np.array([0.43,0.155]); print('rail_mid_z',(0.6449999809265137+0.2750000059604645)/2)
for name in ['N15','N16','N18','N25']:
 o=objs[name]; v=np.array([tuple(o.matrix_world@p.co) for p in o.data.vertices]); c=(v.min(0)+v.max(0))/2
 print(name,'center',c.tolist(),'pipe_xy_dist',float(np.linalg.norm(c[:2]-mid)))