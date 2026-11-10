for label,gA,gB in [('forward',current['Target'],current['Near_017']),('reverse',current['Near_017'],current['Target'])]:
    va,fa=gA; vb,fb=gB; a,b=edges_from(va,fa); triangles=vb[fb]
    a=a[:,None,:]; direction=b[:,None,:]-a
    v0=triangles[None,:,0,:]; e1=triangles[None,:,1,:]-v0; e2=triangles[None,:,2,:]-v0
    h=np.cross(direction,e2); det=dot(e1,h); inv=np.divide(1.,det,out=np.zeros_like(det),where=det!=0)
    offset=a-v0;s=dot(offset,h)*inv;q=np.cross(offset,e1);t=dot(direction,q)*inv;ray=dot(e2,q)*inv
    ok=(det!=0)&(s>=0)&(t>=0)&(s+t<=1)&(ray>=0)&(ray<=1)
    ids=np.argwhere(ok)
    print(label,'count',len(ids))
    for ii,jj in ids[:4]:
        p=a[ii,0]+ray[ii,jj]*direction[ii,0]; pp=v0[0,jj]+s[ii,jj]*e1[0,jj]+t[ii,jj]*e2[0,jj]
        print('params',int(ii),int(jj),float(det[ii,jj]),float(ray[ii,jj]),float(s[ii,jj]),float(t[ii,jj]),'residual',np.linalg.norm(p-pp))
print('nonintersection_features_distance',[(name, np.sqrt(min(point_face(current['Target'][0],current[name][0][current[name][1]])[0],point_face(current[name][0],current['Target'][0][current['Target'][1]])[0],edge_edge(*edges_from(*current['Target']),*edges_from(*current[name]))[0]))) for name in ['Near_017']])