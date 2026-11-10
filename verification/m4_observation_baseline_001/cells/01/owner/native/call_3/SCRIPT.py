for n in ['N16','N13','N08','N28','N12','N24']:
 o=meshes[n];print('\n',n,'matrix',[[round(x,9) for x in row] for row in o.matrix_world]); print('vertices',world[n].tolist());print('faces',[list(p.vertices) for p in o.data.polygons])
mid=np.mean([(world[n].min(0)+world[n].max(0))/2 for n in ['N04','N19']],axis=0)
print('pipes XY',mid[:2])
for n in ['N15','N16','N18','N25']:
 c=(world[n].min(0)+world[n].max(0))/2
 print(n,'center',c.tolist(),'XYdist',np.linalg.norm(c[:2]-mid[:2]))