p=results['Near_017'][1]; tri=gg['v'][gg['t'][1]]
u=tri[1]-tri[0];v=tri[2]-tri[0];w=p-tri[0]
coeff=np.linalg.lstsq(np.stack([u,v],axis=1),w,rcond=None)[0]
print('witness_independent_barycentric',coeff.tolist(),'residual',float(np.linalg.norm(w-coeff[0]*u-coeff[1]*v)))
def crossing(edges,triangles):
 p=edges[:,None,0,:]; direction=edges[:,None,1,:]-p; a=triangles[None,:,0,:]; u=triangles[None,:,1,:]-a; v=triangles[None,:,2,:]-a
 normal=np.cross(u,v); determinant=dot(direction,normal)
 scale=np.linalg.norm(direction,axis=-1)*np.linalg.norm(normal,axis=-1)
 valid=np.abs(determinant)>1e-12*scale
 r=np.divide(dot(a-p,normal),determinant,out=np.zeros_like(determinant),where=valid)
 point=p+r[...,None]*direction; w=point-a
 uu=dot(u,u);uv=dot(u,v);vv=dot(v,v);wu=dot(w,u);wv=dot(w,v);den=uu*vv-uv*uv
 s=np.divide(vv*wu-uv*wv,den,out=np.zeros_like(wu),where=den>1e-30);t=np.divide(uu*wv-uv*wu,den,out=np.zeros_like(wu),where=den>1e-30)
 residual=np.linalg.norm(w-s[...,None]*u-t[...,None]*v,axis=-1)
 hits=valid&(s>=0)&(t>=0)&(s+t<=1)&(r>=0)&(r<=1)&(residual<1e-10)
 inds=np.argwhere(hits)
 if len(inds):
  i,j=inds[0];pt=point[i,j];return (0.,pt,pt,('intersection',int(i),int(j),float(r[i,j]),float(s[i,j]),float(t[i,j])))
 return None
for name,g in geom.items():
 if name!='Target':results[name]=mesh_distance(tg,g)
ranking=sorted(results,key=lambda n:results[n][0])
for name in ranking: print(name,format(np.sqrt(results[name][0]),'.15g'))
print('winner_witness',results[ranking[0]][1].tolist(),results[ranking[0]][2].tolist(),results[ranking[0]][3])