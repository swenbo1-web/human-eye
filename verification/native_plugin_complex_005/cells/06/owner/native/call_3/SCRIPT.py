deps=bpy.context.evaluated_depsgraph_get()
geom={}
for obj in objs:
 ev=obj.evaluated_get(deps); mesh=ev.to_mesh(); mesh.calc_loop_triangles()
 mat=np.array(ev.matrix_world,dtype=np.float64)
 vv=np.array([v.co[:] for v in mesh.vertices],dtype=np.float64)
 vv=vv@mat[:3,:3].T+mat[:3,3]
 tt=np.array([t.vertices[:] for t in mesh.loop_triangles],dtype=np.int64)
 ee=np.unique(np.sort(np.concatenate([tt[:,[0,1]],tt[:,[1,2]],tt[:,[2,0]]]),axis=1),axis=0)
 geom[obj.name]={'v':vv,'t':tt,'e':ee,'lo':vv.min(axis=0),'hi':vv.max(axis=0)}
 ev.to_mesh_clear()
tg=geom['Target']
for name,g in geom.items():
 if name=='Target': print(name,'bounds',g['lo'].tolist(),g['hi'].tolist());continue
 delta=np.maximum(0,np.maximum(tg['lo']-g['hi'],g['lo']-tg['hi']))
 g['lb']=float(np.linalg.norm(delta))
print('aabb_lower_bounds',sorted([(n,g['lb']) for n,g in geom.items() if n!='Target'],key=lambda x:x[1]))
print('unit',bpy.context.scene.unit_settings.system,bpy.context.scene.unit_settings.scale_length)