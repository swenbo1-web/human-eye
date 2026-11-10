for name in ['N16','N24','N12']:
 obj=bpy.data.objects[name]
 print(name,'world vertices', [tuple(round(float(c),8) for c in (obj.matrix_world @ v.co)) for v in obj.data.vertices])
mid=np.array([0.43,0.155])
for name in ['N15','N18','N25','N16']:
 obj=bpy.data.objects[name]; pts=np.array([tuple(obj.matrix_world @ v.co) for v in obj.data.vertices]); center=(pts.min(0)+pts.max(0))/2
 print(name,'XY_distance_to_pipe_mid_m',float(np.linalg.norm(center[:2]-mid)), 'below_midZ',bool(center[2]<0.46),'behind_frontbeam',bool(center[1]>-0.1025))
