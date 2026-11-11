for name in ['N16','N13','N28']:
 obj=objects[name]
 print(name,'world_vertices',[tuple(round(float(component),9) for component in (obj.matrix_world @ vertex.co)) for vertex in obj.data.vertices])
mid_xy=np.array([0.43,0.155])
for name in ['N15','N16','N18','N25']:
 obj=objects[name]; points=np.array([tuple(obj.matrix_world @ vertex.co) for vertex in obj.data.vertices]); center=(points.min(0)+points.max(0))/2
 print(name,'center',center.tolist(),'pipe_midpoint_xy_distance',float(np.linalg.norm(center[:2]-mid_xy)))
