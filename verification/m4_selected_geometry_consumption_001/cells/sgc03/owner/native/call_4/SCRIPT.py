import math
for name in ['N24','N12','N04','N19']:
 o=objs[name]
 print(name,'local vertices', [tuple(round(float(c),6) for c in v.co) for v in o.data.vertices], 'matrix', [list(r) for r in o.matrix_world])
mid=(.43,.155)
for name in ['N15','N18','N25','N16']:
 lo,hi=bounds(objs[name]); c=[(a+b)/2 for a,b in zip(lo,hi)]
 print(name,'center',c,'pipe_midpoint_XY_distance',math.hypot(c[0]-mid[0],c[1]-mid[1]))