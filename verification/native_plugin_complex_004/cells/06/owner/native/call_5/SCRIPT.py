print('Near_017 bounds',geom['Near_017'][0].min(0).tolist(),geom['Near_017'][0].max(0).tolist())
print('point/face',point_tri(geom['Target'][0],tb)[0],point_tri(geom['Near_017'][0],ta)[0])
ee=edge_edge(edges(ta),edges(tb));print('edge_distance',math.sqrt(ee[0]),'points',ee[1].tolist(),ee[2].tolist())
for label,es,tris in [('forward',edges(ta),tb),('reverse',edges(tb),ta)]:
 p,pend=es; p=p[:,None,:]; direction=pend[:,None,:]-p; a=tris[None,:,0,:]; u=tris[None,:,1,:]-a; v=tris[None,:,2,:]-a
 h=np.cross(direction,v);det=np.sum(u*h,2); inv=np.divide(1.,det,out=np.zeros_like(det),where=np.abs(det)>1e-25)
 s=p-a; b1=inv*np.sum(s*h,2); cr=np.cross(s,u); b2=inv*np.sum(direction*cr,2); along=inv*np.sum(v*cr,2)
 valid=(np.abs(det)>1e-25)&(b1>=0)&(b2>=0)&(b1+b2<=1)&(along>=0)&(along<=1)
 for row,col in np.argwhere(valid)[:5]:
  ep=p[row,0]+along[row,col]*direction[row,0]; fp=tris[col,0]+b1[row,col]*(tris[col,1]-tris[col,0])+b2[row,col]*(tris[col,2]-tris[col,0])
  print(label,'edge',int(row),'triangle',int(col),'det',det[row,col],'coeff',[along[row,col],b1[row,col],b2[row,col]],'residual',np.linalg.norm(ep-fp))
