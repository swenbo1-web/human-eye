target_matrix=np.array(bpy.data.objects['Object_01'].matrix_world,dtype=float)
target_inverse=np.linalg.inv(target_matrix)
for name in names:
 local,world,tri=meshes[name]
 relative=(target_inverse[:3,:3]@world.T).T+target_inverse[:3,3]
 print(name,'target-frame vertices' if name=='Object_03' else 'target-frame bounds', relative.tolist() if name=='Object_03' else [relative.min(axis=0).tolist(),relative.max(axis=0).tolist()])
 edges=np.sort(np.concatenate([tri[:,[0,1]],tri[:,[1,2]],tri[:,[2,0]]]),axis=1)
 _,counts=np.unique(edges,axis=0,return_counts=True)
 print('closed edge incidence',np.unique(counts,return_counts=True),'signed volume',np.einsum('ij,ij->i',world[tri[:,0]],np.cross(world[tri[:,1]],world[tri[:,2]])).sum()/6)
