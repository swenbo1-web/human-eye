for name in ['N16','N12','N24']:
 o=meshes[name]; a=coords(o)
 print(name,'world vertices',a.round(9).tolist())
mid=(coords(meshes['N04']).min(0)+coords(meshes['N04']).max(0)+coords(meshes['N19']).min(0)+coords(meshes['N19']).max(0))/4
print('pipe midpoint XY',mid[:2].tolist())
for name in ['N15','N16','N18','N25']:
 a=coords(meshes[name]); c=(a.min(0)+a.max(0))/2
 print(name,'center',c.tolist(),'xy_distance_to_pipes',float(np.linalg.norm(c[:2]-mid[:2])))
