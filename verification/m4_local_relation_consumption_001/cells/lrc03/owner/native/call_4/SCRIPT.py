import math
for name in ['N16','N24','N12','N04','N19','N28']:
 o=objs[name]
 print(name,'world_vertices',[[round(float(c),9) for c in o.matrix_world@v.co] for v in o.data.vertices])
mid=[(bounds(objs['N04'])['center'][i]+bounds(objs['N19'])['center'][i])/2 for i in range(2)]
print('pipe_axis_xy_mid',mid)
for n in ['N15','N18','N25','N16']:
 c=bounds(objs[n])['center']; print(n,'center',c,'xy_radius',math.dist(c[:2],mid))