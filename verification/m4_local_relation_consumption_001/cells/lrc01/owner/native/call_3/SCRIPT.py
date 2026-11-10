for name in ['N16','N13','N08','N28','N12','N24']:
 print('\n',name)
 print('verts',[(i,tuple(float(x) for x in v)) for i,v in enumerate(world[name])])
 print('faces',[tuple(p.vertices) for p in objs[name].data.polygons])
mid=(world['N12'][:,2].min()+world['N12'][:,2].max()+world['N24'][:,2].min()+world['N24'][:,2].max())/4
rear=world['N10'][:,1].max()
pipes=( (world['N04'].min(0)+world['N04'].max(0))/2+(world['N19'].min(0)+world['N19'].max(0))/2)/2
print('mid_z',mid,'beam_rear_y',rear,'pipes_xy',pipes[:2])
for name in ['N15','N16','N18','N25']:
 center=(world[name].min(0)+world[name].max(0))/2
 print(name,'center',center.tolist(),'distance',float(np.linalg.norm(center[:2]-pipes[:2])),'conditions',bool(center[2]<mid),bool(center[1]>rear),bool(np.linalg.norm(center[:2]-pipes[:2])<=0.70))