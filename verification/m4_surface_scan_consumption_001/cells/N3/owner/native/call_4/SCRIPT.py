full_results=[]; full_triangle_pairs=0; near_excluded=[]; discrepancy=[]
for first_index,first in enumerate(mesh_cache):
 for second in mesh_cache[first_index+1:]:
  count0=len(first['tri']);count1=len(second['tri'])
  if not count0 or not count1: continue
  triangles0=np.repeat(first['tri'],count1,axis=0)
  triangles1=np.tile(second['tri'],(count0,1,1))
  values=triangle_pair_sq(triangles0,triangles1)
  full_triangle_pairs+=len(values)
  distance=float(np.sqrt(values.min()))*scale_mm
  if distance<=2.0:
   full_results.append((first['name'],second['name'],distance))
  else: near_excluded.append((distance,first['name'],second['name']))
lookup={(first,second):distance for first,second,distance in results}
for first,second,distance in full_results:
 if (first,second) not in lookup or abs(distance-lookup[first,second])>1e-8:discrepancy.append((first,second,distance,lookup.get((first,second))))
print('exhaustive_object_pairs',len(full_results)+len(near_excluded),'exhaustive_triangle_pairs',full_triangle_pairs,'qualifying',len(full_results),'zero',sum(distance==0 for _,_,distance in full_results),'discrepancies',discrepancy)
print('nearest_excluded',sorted(near_excluded)[:5])
print('positive_distances')
for first,second,distance in full_results:
 if distance>0:print(first,second,f'{distance:.6f}')
print('zero_groups')
for first in [item['name'] for item in mesh_cache]:
 partners=[second for name,second,distance in full_results if name==first and distance==0]
 if partners: print(first,', '.join(partners))