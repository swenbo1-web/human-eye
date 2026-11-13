all_pair_results=[]
for first in range(len(scan_meshes)):
 for second in range(first+1,len(scan_meshes)):
  one,two=scan_meshes[first],scan_meshes[second]
  distance=mesh_distance(one['tri'],two['tri'])*mm_per_unit
  all_pair_results.append((one['name'],two['name'],distance))
full_qualifying=[record for record in all_pair_results if record[2]<=2.0]
print('EXHAUSTIVE_PAIRS',len(all_pair_results),'QUALIFYING',len(full_qualifying),'MATCHES_BROAD_PHASE',full_qualifying==qualifying)
print('EXACT_ZERO_COUNT',sum(record[2]==0 for record in full_qualifying))
print('POSITIVE_UNDER_1_MICRON',[(a,b,d) for a,b,d in full_qualifying if 0<d<0.001])
print('GLOBAL_NEAREST_EXCLUDED',min((r for r in all_pair_results if r[2]>2),key=lambda r:r[2]))
print('EMPTY_MESHES',[m['name'] for m in scan_meshes if len(m['tri'])==0])
print('EDIT_MODE_OBJECTS',[o.name for o in objs if o.mode=='EDIT'])
print('ALL_FINITE',all(np.isfinite(m['tri']).all() for m in scan_meshes))
