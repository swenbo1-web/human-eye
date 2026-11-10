for name in ['N16','N13','N08','N28','N12','N24']:
 print('\n',name)
 for index,point in enumerate(verts[name]): print(index, ['%.10f'%coord for coord in point])
 print('faces', [tuple(p.vertices) for p in objs[name].data.polygons])
midz=sum((verts[name].min(0)[2]+verts[name].max(0)[2])/2 for name in ['N12','N24'])/2
pipexy=sum(((verts[name].min(0)+verts[name].max(0))/2)[:2] for name in ['N04','N19'])/2
print('midz',midz,'pipexy',pipexy,'beamrear',verts['N10'].max(0)[1])
for name in ['N15','N16','N18','N25']:
 center=(verts[name].min(0)+verts[name].max(0))/2
 print(name,'center',center,'distance',np.linalg.norm(center[:2]-pipexy),'conditions',bool(center[2]<midz),bool(center[1]>verts['N10'].max(0)[1]),bool(np.linalg.norm(center[:2]-pipexy)<=0.7))