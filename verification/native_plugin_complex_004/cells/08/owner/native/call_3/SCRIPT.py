deps=bpy.context.evaluated_depsgraph_get()
geo={}
for obj in bpy.context.scene.objects:
    if obj.type!='MESH': continue
    ev=obj.evaluated_get(deps); mesh=ev.to_mesh(); mesh.calc_loop_triangles()
    verts=np.array([v.co[:] for v in mesh.vertices],dtype=np.float64)
    mat=np.array(ev.matrix_world,dtype=np.float64)
    verts=verts@mat[:3,:3].T+mat[:3,3]
    faces=np.array([t.vertices[:] for t in mesh.loop_triangles],dtype=np.int64)
    geo[obj.name]={'v':verts,'f':faces,'tri':verts[faces],'lo':verts.min(axis=0),'hi':verts.max(axis=0)}
    ev.to_mesh_clear()
tg=geo['Target']
for name,g in geo.items():
    if name=='Target':continue
    gap=np.maximum(np.maximum(tg['lo']-g['hi'],g['lo']-tg['hi']),0)
    g['bound']=float(np.linalg.norm(gap))
print('units',bpy.context.scene.unit_settings.system,bpy.context.scene.unit_settings.scale_length)
print('Target bounds',tg['lo'].tolist(),tg['hi'].tolist())
print('evaluated counts',[(n,len(g['v']),len(g['f'])) for n,g in geo.items()])
print('bounds',sorted([(n,g['bound']) for n,g in geo.items() if n!='Target'],key=lambda x:x[1]))