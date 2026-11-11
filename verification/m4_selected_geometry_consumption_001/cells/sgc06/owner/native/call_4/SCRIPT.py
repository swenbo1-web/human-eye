def bounds(name):
 ob=objs[name]; verts=np.array([tuple(ob.matrix_world@vert.co) for vert in ob.data.vertices]); return verts.min(0),verts.max(0)
def center(name):
 lower,upper=bounds(name);return (lower+upper)/2
midheight=(center('N12')[2]+center('N24')[2])/2
pipes=(center('N04')[:2]+center('N19')[:2])/2
rear=bounds('N10')[1][1]
print('rail_mid_z',midheight,'beam_rear_y',rear,'pipe_mid_xy',pipes.tolist())
for name in ['N15','N16','N18','N25']:
 c=center(name);dist=np.linalg.norm(c[:2]-pipes)
 print(name,'center',c.tolist(),'distance',dist,'conditions',bool(c[2]<midheight),bool(c[1]>rear),bool(dist<=.70))
print('modifiers',[(name,len(objs[name].modifiers)) for name in objs])
print('N08 gap m',bounds('N16')[0][0]-bounds('N08')[1][0])
print('N13 shared interior box',np.maximum(bounds('N16')[0],bounds('N13')[0]).tolist(),np.minimum(bounds('N16')[1],bounds('N13')[1]).tolist())
print('rod vertical clearances m',0.34800001978874207-0.32500001788139343,0.39500001072883606-0.3720000088214874)
