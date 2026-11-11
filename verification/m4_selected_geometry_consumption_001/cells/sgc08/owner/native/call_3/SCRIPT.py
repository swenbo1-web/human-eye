world={name:np.array([tuple(o.matrix_world @ p.co) for p in o.data.vertices],dtype=float) for name,o in objs.items()}
for name in ['N16','N13','N08','N28','N12','N24']:
 o=objs[name]
 print(name,'matrix', [list(row) for row in o.matrix_world], 'modifiers',[(m.name,m.type) for m in o.modifiers])
 print('vertices',world[name].tolist()); print('faces',[list(p.vertices) for p in o.data.polygons])
mid=(world['N04'].min(0)+world['N04'].max(0)+world['N19'].min(0)+world['N19'].max(0))/4
print('pipe midpoint',mid)
for name in ['N15','N16','N18','N25']:
 c=(world[name].min(0)+world[name].max(0))/2
 print(name,'center',c.tolist(),'radial',np.linalg.norm(c[:2]-mid[:2]))
print('camera',[(o.name, list(o.location),list(o.rotation_euler),o.data.type,o.data.ortho_scale) for o in bpy.context.scene.objects if o.type=='CAMERA'])