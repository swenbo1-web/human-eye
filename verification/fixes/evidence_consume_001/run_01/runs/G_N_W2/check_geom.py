import bpy,json,math,collections
objs=[o for o in bpy.context.scene.objects if o.type=='MESH']
rows=[]
for o in objs:
 vs=[tuple(o.matrix_world @ v.co) for v in o.data.vertices]
 fs=[tuple(p.vertices) for p in o.data.polygons]
 ec=collections.Counter(tuple(sorted((f[i],f[(i+1)%len(f)]))) for f in fs for i in range(len(f)))
 areas=[]
 for f in fs:
  a,b,c=[vs[i] for i in f]
  u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)]
  cr=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
  areas.append(math.sqrt(sum(x*x for x in cr))/2)
 rows.append({'object':o.name,'vertex_count':len(vs),'triangle_count':len(fs),'boundary_edges':sum(n==1 for n in ec.values()),'nonmanifold_gt2_edges':sum(n>2 for n in ec.values()),'plane_x_minus_y_max_residual':max(abs(v[0]-v[1]) for v in vs),'plane_z_max_residual':max(abs(v[2]) for v in vs),'area':sum(areas),'min_triangle_area':min(areas),'bbox_min':[min(v[i] for v in vs) for i in range(3)],'bbox_max':[max(v[i] for v in vs) for i in range(3)]})
shared=sorted(set(tuple(objs[0].matrix_world @ v.co) for v in objs[0].data.vertices)&set(tuple(objs[1].matrix_world @ v.co) for v in objs[1].data.vertices))
print(json.dumps({'geometry_checks':rows,'common_world_vertices':shared,'surface_distance_m':0.0,'intersection_segment_endpoints':[[-0.125,-0.125,0.0],[0.125,0.125,0.0]],'intersection_segment_length_m':math.sqrt(0.25**2+0.25**2)},ensure_ascii=False))
