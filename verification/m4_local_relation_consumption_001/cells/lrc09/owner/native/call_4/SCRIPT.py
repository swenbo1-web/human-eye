for name in ['N16','N12','N24','N04','N19']:
 print(name,'world_vertices',np.round(worldverts[name],8).tolist())
center=lambda name:(worldverts[name].min(0)+worldverts[name].max(0))/2
mid=(center('N12')[2]+center('N24')[2])/2
pipes=(center('N04')[:2]+center('N19')[:2])/2
back=worldverts['N10'][:,1].max()
print('rail_mid_z',mid,'beam_rear_y',back,'pipes_mid_xy',pipes.tolist())
for name in ['N15','N16','N18','N25']:
 c=center(name); print(name,'center',c.tolist(),'xy_distance',float(np.linalg.norm(c[:2]-pipes)),'conditions',[bool(c[2]<mid),bool(c[1]>back),bool(np.linalg.norm(c[:2]-pipes)<=.70)])
