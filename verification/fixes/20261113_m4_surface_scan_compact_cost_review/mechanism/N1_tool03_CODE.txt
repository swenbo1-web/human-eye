zero_pairs=[entry for entry in qualifying if entry[2]==0.0]
positive_pairs=[entry for entry in qualifying if entry[2]>0.0]
print('zero_count',len(zero_pairs),'positive_count',len(positive_pairs))
for item in scan:
    triangles=item['triangles']
    if len(triangles):
        areas=np.linalg.norm(np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0]),axis=1)
        if np.any(areas==0) or not np.isfinite(triangles).all(): print('geometry_issue',item['name'])
print('zero_groups')
for first_name in sorted(set(entry[0] for entry in zero_pairs)):
    print(first_name,', '.join(entry[1] for entry in zero_pairs if entry[0]==first_name))
print('positive_pairs')
for first_name,second_name,distance in positive_pairs: print(first_name,second_name,format(distance,'.6f'))
print('nonmesh_scene_objects',[(obj.name,obj.type) for obj in scene.objects if obj.type!='MESH'])
print('finite_distances',all(math.isfinite(entry[2]) for entry in results))