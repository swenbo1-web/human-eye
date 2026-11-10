def winding(points,verts,tris):
 vectors=verts[tris][None,:,:,:]-np.asarray(points)[:,None,None,:]
 lengths=np.linalg.norm(vectors,axis=-1)
 aa,bb,cc=vectors[:,:,0],vectors[:,:,1],vectors[:,:,2]
 numerator=np.einsum('pij,pij->pi',aa,np.cross(bb,cc))
 denom=lengths[:,:,0]*lengths[:,:,1]*lengths[:,:,2]+np.einsum('pij,pij->pi',aa,bb)*lengths[:,:,2]+np.einsum('pij,pij->pi',bb,cc)*lengths[:,:,0]+np.einsum('pij,pij->pi',cc,aa)*lengths[:,:,1]
 return np.sum(2*np.arctan2(numerator,denom),axis=1)/(4*np.pi)
basev,baset=meshes['Part_49']
basebvh=BVHTree.FromPolygons(basev.tolist(),baset.tolist(),all_triangles=True,epsilon=0.0)
for name in names[1:]:
 verts,tris=meshes[name]
 bvh=BVHTree.FromPolygons(verts.tolist(),tris.tolist(),all_triangles=True,epsilon=0.0)
 weights=winding(np.concatenate([verts,verts[tris].mean(axis=1),verts.mean(axis=0)[None,:]]),basev,baset)
 print(name,'bvh overlaps',len(basebvh.overlap(bvh)),'winding range',weights.min(),weights.max(),'vertex windings',np.round(weights[:len(verts)],5).tolist(),'center',weights[-1])
