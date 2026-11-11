for name in ['N16','N12','N24','N04','N19']:
 print(name,'vertices',np.round(verts[name],7).tolist())
p=np.array([.43,.155]);
for name in ['N15','N16','N18','N25']:
 a=verts[name]; c=(a.min(0)+a.max(0))/2
 print(name,'center',c.tolist(),'XY_distance_to_pipes_midpoint',float(np.linalg.norm(c[:2]-p)))