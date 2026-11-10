for name in ['N16','N13','N08','N28','N12','N24','N10','N04','N19']:
 o=objs[name]; mat=np.array(o.matrix_world,dtype=float); local=np.array([tuple(v.co) for v in o.data.vertices]); world=local@mat[:3,:3].T+mat[:3,3]
 print(name,'world coordinate levels',[np.unique(np.round(world[:,axis],10)).tolist() for axis in range(3)])
 if name=='N16':
  print('vertices',world.tolist());print('faces',[list(p.vertices) for p in o.data.polygons])
mid=np.array([.43,.155]);
for name in ['N15','N16','N18','N25']:
 o=objs[name]; mat=np.array(o.matrix_world,dtype=float); verts=np.array([tuple(v.co) for v in o.data.vertices])@mat[:3,:3].T+mat[:3,3]; center=(verts.min(0)+verts.max(0))/2
 print('frame',name,'center',center.tolist(),'xy_distance',float(np.linalg.norm(center[:2]-mid)))