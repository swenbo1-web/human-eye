print('triangles_total',sum(len(entry['tri']) for entry in meshes))
print('zero_count',sum(distance==0 for _,_,distance,_,_ in near))
print('nonzero_count',sum(distance>0 for _,_,distance,_,_ in near))
print('excluded_min_lower_mm',min(row[2] for row in excluded))
print('all_finite',all(np.isfinite(entry['tri']).all() for entry in meshes))
for first in range(len(meshes)):
    others=[meshes[second]['name'] for a,second,distance,_,_ in near if a==first and distance==0]
    if others: print(meshes[first]['name'],', '.join(others))