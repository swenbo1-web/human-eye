for n in ['N16','N13','N08','N28','N12','N04','N19']:
 o=objs[n]; print('\n',n,'vertices',[(i,tuple(round(float(c),9) for c in p)) for i,p in enumerate(verts[n])]); print('faces',[tuple(p.vertices) for p in o.data.polygons])
mid=(verts['N12'][:,2].min()+verts['N12'][:,2].max()+verts['N24'][:,2].min()+verts['N24'][:,2].max())/4
pipe_mid=((verts['N04'].min(0)+verts['N04'].max(0))/2+(verts['N19'].min(0)+verts['N19'].max(0))/2)/2
print('height threshold',mid,'pipe midpoint',pipe_mid[:2],'beam back',verts['N10'][:,1].max())
for n in ['N15','N16','N18','N25']:
 c=(verts[n].min(0)+verts[n].max(0))/2; print(n,'center',c.tolist(),'distanceXY',np.linalg.norm(c[:2]-pipe_mid[:2]),'conditions',bool(c[2]<mid),bool(c[1]>verts['N10'][:,1].max()),bool(np.linalg.norm(c[:2]-pipe_mid[:2])<=.7))