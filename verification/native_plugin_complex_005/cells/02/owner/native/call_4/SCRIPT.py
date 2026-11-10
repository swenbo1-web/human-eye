def closest_pt_tri(point, tri):
 a,b,c=tri; ab=b-a; ac=c-a; ap=point-a
 d1=np.dot(ab,ap); d2=np.dot(ac,ap)
 if d1<=0 and d2<=0:return a
 bp=point-b; d3=np.dot(ab,bp); d4=np.dot(ac,bp)
 if d3>=0 and d4<=d3:return b
 vc=d1*d4-d3*d2
 if vc<=0 and d1>=0 and d3<=0:return a+(d1/(d1-d3))*ab
 cp=point-c; d5=np.dot(ab,cp); d6=np.dot(ac,cp)
 if d6>=0 and d5<=d6:return c
 vb=d5*d2-d1*d6
 if vb<=0 and d2>=0 and d6<=0:return a+(d2/(d2-d6))*ac
 va=d3*d6-d5*d4
 if va<=0 and (d4-d3)>=0 and (d5-d6)>=0:return b+((d4-d3)/((d4-d3)+(d5-d6)))*(c-b)
 denom=1/(va+vb+vc);return a+ab*(vb*denom)+ac*(vc*denom)
def closest_segments(p1,q1,p2,q2):
 d1=q1-p1; d2=q2-p2; r=p1-p2
 aa=np.dot(d1,d1); ee=np.dot(d2,d2); ff=np.dot(d2,r); cc=np.dot(d1,r); bb=np.dot(d1,d2); den=aa*ee-bb*bb
 ss=np.clip((bb*ff-cc*ee)/den,0,1) if den>1e-28 else 0.
 tt=(bb*ss+ff)/ee
 if tt<0:tt=0.;ss=np.clip(-cc/aa,0,1)
 elif tt>1:tt=1.;ss=np.clip((bb-cc)/aa,0,1)
 return p1+ss*d1,p2+tt*d2
def mesh_surface_distance(first,second):
 va,ta=first['v'],first['t']; vb,tb=second['v'],second['t']; best=(float('inf'),None,None,None)
 def check(pa,pb,kind):
  nonlocal best
  ds=np.dot(pa-pb,pa-pb)
  if ds<best[0]:best=(ds,pa.copy(),pb.copy(),kind)
 for ia,pa in enumerate(va):
  for it,tri in enumerate(vb[tb]):check(pa,closest_pt_tri(pa,tri),('vertex-face',ia,it))
 for ib,pb in enumerate(vb):
  for it,tri in enumerate(va[ta]):check(closest_pt_tri(pb,tri),pb,('face-vertex',it,ib))
 ea=sorted({tuple(sorted((int(a),int(b)))) for tri in ta for a,b in zip(tri,np.roll(tri,-1))})
 eb=sorted({tuple(sorted((int(a),int(b)))) for tri in tb for a,b in zip(tri,np.roll(tri,-1))})
 for edgea in ea:
  for edgeb in eb:
   pa,pb=closest_segments(*va[list(edgea)],*vb[list(edgeb)]);check(pa,pb,('edge-edge',edgea,edgeb))
 return math.sqrt(best[0]),best[1],best[2],best[3]
inv_target=np.linalg.inv(data['Object_01']['mat'])
for name in ['Object_02','Object_03','Object_04']:
 v=data[name]['v']; in_target=v@inv_target[:3,:3].T+inv_target[:3,3]
 print(name,'target-frame bounds',in_target.min(0).tolist(),in_target.max(0).tolist(),'target-frame center',in_target.mean(0).tolist())
 if name!='Object_03':
  distance,pa,pb,feature=mesh_surface_distance(data['Object_01'],data[name])
  print('global surface distance',format(distance,'.12f'),'world target witness',pa.tolist(),'candidate witness',pb.tolist(),'features',feature)
 else:
  center=v.mean(0); mind=min(np.linalg.norm(center-closest_pt_tri(center,tri)) for tri in data['Object_01']['v'][data['Object_01']['t']])
  print('candidate center world',center.tolist(),'nearest target surface distance',format(mind,'.12f'),'target frame vertices',in_target.tolist())
