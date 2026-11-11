for name in ['N16','N13','N08','N28','N12','N04']:
 o=objs[name]
 print('\n',name,'matrix', [list(row) for row in o.matrix_world])
 print('vertices',[(i,tuple(o.matrix_world@p.co)) for i,p in enumerate(o.data.vertices)])
 print('faces',[tuple(p.vertices) for p in o.data.polygons])
