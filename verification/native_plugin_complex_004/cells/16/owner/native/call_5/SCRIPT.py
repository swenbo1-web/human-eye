current_names={o.name for o in bpy.context.scene.objects if o.type=='MESH'}
unchanged=current_names==set(geometry)
for obj in [o for o in bpy.context.scene.objects if o.type=='MESH']:
 evaluated=obj.evaluated_get(depsgraph);matrix=np.array(evaluated.matrix_world,dtype=np.float64)
 vertices=np.array([tuple(v.co) for v in evaluated.data.vertices],dtype=np.float64)@matrix[:3,:3].T+matrix[:3,3]
 unchanged=unchanged and np.array_equal(vertices,geometry[obj.name]['v']) and np.array_equal(np.array([tuple(p.vertices) for p in evaluated.data.polygons]),geometry[obj.name]['f'])
print('current_scene_matches_geometry_cache',unchanged)
result=results['Near_017'];edge_index,face_index=result[3]
starts,ends=edges_of(target['t']);start=starts[edge_index];end=ends[edge_index]
triangle=geometry['Near_017']['t'][face_index]
system=np.column_stack([end-start,-(triangle[1]-triangle[0]),-(triangle[2]-triangle[0])])
parameter,bary_u,bary_v=np.linalg.solve(system,triangle[0]-start)
point_a=start+parameter*(end-start)
point_b=triangle[0]+bary_u*(triangle[1]-triangle[0])+bary_v*(triangle[2]-triangle[0])
print('intersection_target_triangle_zero_based',edge_index//3,'edge_local',edge_index%3,'vertex_indices',target['f'][edge_index//3].tolist())
print('intersection_near_triangle_zero_based',face_index,'vertex_indices',geometry['Near_017']['f'][face_index].tolist())
print('segment_parameter',format(parameter,'.16g'),'triangle_barycentric',[1-bary_u-bary_v,bary_u,bary_v])
print('world_intersection_m',[float(c) for c in point_a])
print('witness_residual_m',float(np.linalg.norm(point_a-point_b)))
print('candidate_count',len(results),'positive_distance_count',sum(r[0]>0 for r in results.values()),'unresolved',0)
