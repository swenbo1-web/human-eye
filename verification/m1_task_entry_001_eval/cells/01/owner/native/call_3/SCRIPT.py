dg=bpy.context.evaluated_depsgraph_get()
geom={}
for name in names:
 obj=bpy.data.objects[name].evaluated_get(dg); mesh=obj.to_mesh(); mesh.calc_loop_triangles()
 local=np.array([v.co[:] for v in mesh.vertices],dtype=np.float64)
 matrix=np.array(obj.matrix_world,dtype=np.float64)
 vertices=local@matrix[:3,:3].T+matrix[:3,3]
 triangles=np.array([t.vertices[:] for t in mesh.loop_triangles],dtype=int)
 edges=np.unique(np.sort(np.concatenate([triangles[:,[0,1]],triangles[:,[1,2]],triangles[:,[2,0]]]),axis=1),axis=0)
 geom[name]={'v':vertices,'f':triangles,'e':edges,'tri':vertices[triangles]}
 print(name,'bbox_mm',vertices.min(axis=0)*1000,vertices.max(axis=0)*1000,'triangles',len(triangles),'modifiers',[(m.name,m.type) for m in obj.modifiers])
 obj.to_mesh_clear()
def solid_angles(points,tris):
 rel=tris[None,:,:,:]-points[:,None,None,:]
 lengths=np.linalg.norm(rel,axis=-1)
 numerator=np.einsum('pti,pti->pt',rel[:,:,0],np.cross(rel[:,:,1],rel[:,:,2]))
 denominator=lengths.prod(axis=-1)+np.einsum('pti,pti->pt',rel[:,:,0],rel[:,:,1])*lengths[:,:,2]+np.einsum('pti,pti->pt',rel[:,:,1],rel[:,:,2])*lengths[:,:,0]+np.einsum('pti,pti->pt',rel[:,:,2],rel[:,:,0])*lengths[:,:,1]
 return np.sum(2*np.arctan2(numerator,denominator),axis=1)/(4*np.pi)
for name in names[1:]:
 target=geom['Part_49']; candidate=geom[name]
 print(name,'vertex_winding_in_target',np.round(solid_angles(candidate['v'],target['tri']),5).tolist())
 print(name,'target_winding_range',np.min(solid_angles(target['v'],candidate['tri'])),np.max(solid_angles(target['v'],candidate['tri'])))