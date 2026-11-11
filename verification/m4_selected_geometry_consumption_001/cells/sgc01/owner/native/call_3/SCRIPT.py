for n in ['N16','N13','N08','N28','N12','N04','N19']:
 o=objs[n];print('\n',n,'matrix',np.round(np.array(o.matrix_world),9).tolist());print('world_vertices',[(i,tuple(round(float(t),9) for t in v)) for i,v in enumerate(verts[n])]);print('polygons',[tuple(p.vertices) for p in o.data.polygons])
mid=(verts['N04'].min(0)+verts['N04'].max(0)+verts['N19'].min(0)+verts['N19'].max(0))/4
print('pipe_mid_xy',mid[:2].tolist())
for n in ['N15','N16','N18','N25']:
 c=(verts[n].min(0)+verts[n].max(0))/2
 print(n,'center',c.tolist(),'radius',float(np.linalg.norm(c[:2]-mid[:2])))