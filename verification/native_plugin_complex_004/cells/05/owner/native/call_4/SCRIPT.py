current={obj.name:capture_mesh(obj) for obj in bpy.context.scene.objects if obj.type=='MESH'}
unchanged=set(current)==set(geometry) and all(np.array_equal(current[name][0],geometry[name][0]) for name in current)
print('current_geometry_matches_computation',unchanged)
target_triangles=current['Target'][0]; other_triangles=current['Near_017'][0]
paired_target=np.repeat(target_triangles,len(other_triangles),axis=0)
paired_other=np.tile(other_triangles,(len(target_triangles),1,1))
for edge in range(3):
    found=np.flatnonzero(crosses(paired_target[:,edge],paired_target[:,(edge+1)%3],paired_other))
    if len(found):
        index=int(found[0]); begin=paired_target[index,edge]; end=paired_target[index,(edge+1)%3]; triangle=paired_other[index]
        normal=np.cross(triangle[1]-triangle[0],triangle[2]-triangle[0])
        parameter=np.dot(triangle[0]-begin,normal)/np.dot(end-begin,normal)
        point=begin+parameter*(end-begin)
        first=triangle[1]-triangle[0]; second=triangle[2]-triangle[0]
        bary=np.linalg.lstsq(np.stack([first,second],axis=1),point-triangle[0],rcond=None)[0]
        print('intersection_witness_world_m',point.tolist())
        print('target_triangle',index//len(other_triangles),'edge',edge,'edge_parameter',float(parameter))
        print('Near_017_triangle',index%len(other_triangles),'barycentric',[float(1-bary.sum()),float(bary[0]),float(bary[1])])
        print('plane_residual_m',float(abs(np.dot(point-triangle[0],normal))/np.linalg.norm(normal)))
        break
print('candidate_count',len(results),'strictly_positive_others',sum(distance>0 for distance,name in results))
