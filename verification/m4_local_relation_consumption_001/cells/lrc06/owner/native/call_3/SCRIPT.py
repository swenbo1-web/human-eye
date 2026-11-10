world={n:np.array([tuple(o.matrix_world @ p.co) for p in o.data.vertices]) for n,o in objs.items()}
for name in ['N16','N13','N08','N28','N12','N04','N19']:
 o=objs[name]; print('\n',name,'vertices',world[name].tolist());print('faces',[list(p.vertices) for p in o.data.polygons])
mid=( (world['N12'].min(0)+world['N12'].max(0))[2]/2+(world['N24'].min(0)+world['N24'].max(0))[2]/2)/2
pipe_mid=np.mean([(world[n].min(0)+world[n].max(0))[:2]/2 for n in ['N04','N19']],axis=0)
print('height threshold',mid,'beam rear',world['N10'][:,1].max(),'pipe midpoint',pipe_mid.tolist())
for n in ['N15','N16','N18','N25']:
 c=(world[n].min(0)+world[n].max(0))/2;print(n,'center',c.tolist(),'pipe XY distance',np.linalg.norm(c[:2]-pipe_mid))