full_results=[]; full_triangle_count=0; maximum_symmetry_error=0.0; tiny_nonzero=[]
for first_index,first in enumerate(scan_meshes):
    for second in scan_meshes[first_index+1:]:
        first_count=len(first['tri']); second_count=len(second['tri'])
        if not first_count or not second_count: continue
        first_tri=np.repeat(first['tri'],second_count,axis=0)
        second_tri=np.tile(second['tri'],(first_count,1,1))
        forward=triangles_squared(first_tri,second_tri)
        backward=triangles_squared(second_tri,first_tri)
        maximum_symmetry_error=max(maximum_symmetry_error,float(np.max(np.abs(forward-backward))))
        full_triangle_count+=len(forward)
        distance=float(np.sqrt(forward.min()))*unit_mm
        if distance<=2+1e-9:
            full_results.append((first['name'],second['name'],distance))
            if 0<distance<1e-9: tiny_nonzero.append((first['name'],second['name'],distance))
print('exhaustive_triangle_pairs',full_triangle_count,'qualifying_pairs',len(full_results),'same_pairs',[(a,b) for a,b,d in full_results]==[(a,b) for a,b,d in scan_results])
print('max_distance_difference_mm',max(abs(first[2]-second[2]) for first,second in zip(full_results,scan_results)))
print('max_symmetry_error_squared_scene_units',maximum_symmetry_error)
print('tiny_nonzero',tiny_nonzero)
print('exact_zero_count',sum(distance==0 for first,second,distance in full_results))
print('closest_excluded_pair')
excluded_min=(float('inf'),None)
for first_index,first in enumerate(scan_meshes):
    for second in scan_meshes[first_index+1:]:
        if (first['name'],second['name']) in {(a,b) for a,b,d in full_results}: continue
        distance=float(np.sqrt(triangles_squared(np.repeat(first['tri'],len(second['tri']),axis=0),np.tile(second['tri'],(len(first['tri']),1,1))).min()))*unit_mm
        if distance<excluded_min[0]: excluded_min=(distance,(first['name'],second['name']))
print(excluded_min)
