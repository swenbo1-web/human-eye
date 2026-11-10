# Refresh world geometry from current scene, using double precision arithmetic.
for name,obj in objs.items():
 assert np.array_equal(np.array(obj.matrix_world),geo[name]['matrix']) and np.array_equal(np.array([v.co[:] for v in obj.data.vertices]),geo[name]['local'])
 geo[name]['v']=(geo[name]['matrix'][:3,:3]@geo[name]['local'].T).T+geo[name]['matrix'][:3,3]
inv_target=np.linalg.inv(geo['Object_01']['matrix'])
for name in list(objs)[1:]:
 local_to_target=(inv_target[:3,:3]@geo[name]['v'].T).T+inv_target[:3,3]
 geo[name]['target_local']=local_to_target
 print(name,'target-local vertices',local_to_target.tolist())

def point_tri_candidates(points, triangles):
 point=points[:,None,:]; origin=triangles[None,:,0,:]
 side1=triangles[None,:,1,:]-origin; side2=triangles[None,:,2,:]-origin
 normal=np.cross(side1,side2); normal2=np.sum(normal*normal,axis=-1)
 projected=point-normal*(np.sum((point-origin)*normal,axis=-1)/normal2)[...,None]
 rel=projected-origin
 dot11=np.sum(side1*side1,axis=-1); dot12=np.sum(side1*side2,axis=-1); dot22=np.sum(side2*side2,axis=-1)
 dotr1=np.sum(rel*side1,axis=-1); dotr2=np.sum(rel*side2,axis=-1)
 denom=dot11*dot22-dot12*dot12
 bary1=(dot22*dotr1-dot12*dotr2)/denom; bary2=(dot11*dotr2-dot12*dotr1)/denom
 dist2=np.sum((point-projected)**2,axis=-1)
 dist2=np.where((bary1>=-1e-13)&(bary2>=-1e-13)&(bary1+bary2<=1+1e-13),dist2,np.inf)
 index=np.unravel_index(np.argmin(dist2),dist2.shape)
 return float(dist2[index]),points[index[0]],projected[index],('vertex-face',index)
def unique_edges(faces):
 return np.array(sorted({tuple(sorted((int(a),int(b)))) for face in faces for a,b in zip(face,np.roll(face,-1))}))
def surface_distance(first,second):
 va,fa=first['v'],first['f']; vb,fb=second['v'],second['f']
 ca=point_tri_candidates(va,vb[fb]); cb=point_tri_candidates(vb,va[fa]); cb=(cb[0],cb[2],cb[1],cb[3])
 ea,eb=va[unique_edges(fa)],vb[unique_edges(fb)]
 starta=ea[:,None,0,:]; startb=eb[None,:,0,:]
 direca=ea[:,None,1,:]-starta; direcb=eb[None,:,1,:]-startb
 delta=starta-startb
 aa=np.sum(direca*direca,axis=-1); bb=np.sum(direca*direcb,axis=-1); cc=np.sum(direcb*direcb,axis=-1)
 dd=np.sum(direca*delta,axis=-1); ee=np.sum(direcb*delta,axis=-1)
 determinant=aa*cc-bb*bb
 valid=determinant>1e-24
 safe=np.where(valid,determinant,1)
 sa=(bb*ee-cc*dd)/safe; sb=(aa*ee-bb*dd)/safe
 candidates=[]
 for param_a,param_b,mask in [(sa,sb,valid&(sa>=0)&(sa<=1)&(sb>=0)&(sb<=1)),(np.zeros_like(ee),np.clip(ee/cc,0,1),True),(np.ones_like(ee),np.clip((ee+bb)/cc,0,1),True),(np.clip(-dd/aa,0,1),np.zeros_like(dd),True),(np.clip((bb-dd)/aa,0,1),np.ones_like(dd),True)]:
  pa=starta+param_a[...,None]*direca; pb=startb+param_b[...,None]*direcb
  squared=np.where(mask,np.sum((pa-pb)**2,axis=-1),np.inf)
  index=np.unravel_index(np.argmin(squared),squared.shape)
  candidates.append((float(squared[index]),pa[index],pb[index],('edge-edge',index)))
 return min([ca,cb]+candidates,key=lambda candidate:candidate[0])
for name in ['Object_02','Object_04']:
 result=surface_distance(geo['Object_01'],geo[name]); geo[name]['distance_result']=result
 print('DISTANCE',name,math.sqrt(result[0]),'witness target',result[1].tolist(),'candidate',result[2].tolist(),'type',result[3])
 print('witness target local', (inv_target[:3,:3]@result[1]+inv_target[:3,3]).tolist(),(inv_target[:3,:3]@result[2]+inv_target[:3,3]).tolist())
