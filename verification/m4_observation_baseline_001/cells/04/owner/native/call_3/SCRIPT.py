V={name:np.array([tuple(o.matrix_world@p.co) for p in o.data.vertices],dtype=float) for name,o in objs.items()}
for name in ['N16','N13','N08','N28','N12','N24']:
 o=objs[name]
 print('\n',name,'vertices',[(i,tuple(round(float(x),9) for x in p)) for i,p in enumerate(V[name])])
 print('faces',[tuple(p.vertices) for p in o.data.polygons])
print('frame_selection')
midz=sum((V[n].min(0)[2]+V[n].max(0)[2])/2 for n in ['N12','N24'])/2
rear=V['N10'].max(0)[1]
pipe_mid=sum((V[n].min(0)[:2]+V[n].max(0)[:2])/2 for n in ['N04','N19'])/2
print('rail_mid_z',midz,'beam_rear_y',rear,'pipe_mid_xy',pipe_mid)
for n in ['N15','N16','N18','N25']:
 c=(V[n].min(0)+V[n].max(0))/2
 print(n,'center',c,'distance',np.linalg.norm(c[:2]-pipe_mid),'passes',bool(c[2]<midz),bool(c[1]>rear),bool(np.linalg.norm(c[:2]-pipe_mid)<=.7))