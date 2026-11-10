for name in ['N16','N13','N08','N28']:
 o=objs[name]; print(name,'world vertices', [tuple(round(x,9) for x in (o.matrix_world@v.co)) for v in o.data.vertices])
def bounds(name):
 o=objs[name]; v=np.array([tuple(o.matrix_world@p.co) for p in o.data.vertices]); return v.min(0),v.max(0)
def center(name):
 low,high=bounds(name); return (low+high)/2
mid=(center('N04')[:2]+center('N19')[:2])/2
print('rail mid z',(center('N12')[2]+center('N24')[2])/2,'front beam rear Y',bounds('N10')[1][1],'pipe midpoint XY',mid.tolist())
for name in ['N15','N16','N18','N25']:
 c=center(name); print(name,'center',c.tolist(),'XY distance',float(np.linalg.norm(c[:2]-mid)))