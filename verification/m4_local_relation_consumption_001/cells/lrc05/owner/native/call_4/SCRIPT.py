for name in ['N16','N13','N28','N04','N19']:
 o=bpy.data.objects[name]
 pts=np.array([tuple(o.matrix_world@v.co) for v in o.data.vertices])
 print(name,'world vertex coordinate levels', [np.unique(np.round(pts[:,axis],8)).tolist() for axis in range(3)])
mid=np.array([.43,.155])
for name in ['N15','N18','N25','N16']:
 o=bpy.data.objects[name]; pts=np.array([tuple(o.matrix_world@v.co) for v in o.data.vertices]); center=(pts.min(0)+pts.max(0))/2
 print(name,'center',center.tolist(),'XY distance',float(np.linalg.norm(center[:2]-mid)))
