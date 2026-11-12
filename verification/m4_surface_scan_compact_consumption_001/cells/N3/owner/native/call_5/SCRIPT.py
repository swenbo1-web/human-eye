full_results=[]
for first in range(len(geom)):
 for second in range(first+1,len(geom)):
  distance,method=surface_distance(geom[first]['triangles'],geom[second]['triangles'])
  full_results.append((first,second,distance,method))
full_qualifying=[row for row in full_results if row[2]<=threshold]
print('full_pair_count',len(full_results),'qualifying',len(full_qualifying),'same_pairs',[(a,b) for a,b,_,_ in full_qualifying]==[(a,b) for a,b,_,_ in qualifying])
print('zero_count',sum(d==0 for _,_,d,_ in full_qualifying),'positive_count',sum(d>0 for _,_,d,_ in full_qualifying))
print('empty_meshes',[g['name'] for g in geom if not len(g['triangles'])])
print('degenerate_triangles',sum(int(np.count_nonzero(np.linalg.norm(np.cross(g['triangles'][:,1]-g['triangles'][:,0],g['triangles'][:,2]-g['triangles'][:,0]),axis=1)==0)) for g in geom))
print('nearest_excluded_mm',min(d for _,_,d,_ in full_results if d>threshold)*1000)
print('grouped')
for first in range(len(geom)):
 rows=[f"{geom[second]['name']}: {distance*1000:.3f}" if distance else f"{geom[second]['name']}: 0" for aa,second,distance,_ in full_qualifying if aa==first]
 if rows:print(geom[first]['name'],'; '.join(rows))