for n in ['N16','N13','N28','N24','N12']:
 print(n,'vertices',np.round(verts[n],9).tolist())
mid=(verts['N04'].min(0)[:2]+verts['N04'].max(0)[:2]+verts['N19'].min(0)[:2]+verts['N19'].max(0)[:2])/4
print('pipe_mid_XY',mid.tolist())
for n in ['N15','N18','N25','N16']:
 center=(verts[n].min(0)+verts[n].max(0))/2
 print(n,'center',center.tolist(),'XY_distance',float(np.linalg.norm(center[:2]-mid)))