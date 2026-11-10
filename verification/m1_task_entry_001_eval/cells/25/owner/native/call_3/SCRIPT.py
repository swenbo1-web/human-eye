import numpy as np
scene=bpy.context.scene
depsgraph=bpy.context.evaluated_depsgraph_get()
geo={}
for obj in objs:
    ev=obj.evaluated_get(depsgraph)
    mesh=ev.to_mesh()
    mesh.calc_loop_triangles()
    local=np.array([tuple(v.co) for v in mesh.vertices],dtype=np.float64)
    matrix=np.array(ev.matrix_world,dtype=np.float64)
    verts=local@matrix[:3,:3].T+matrix[:3,3]
    indices=np.array([tuple(t.vertices) for t in mesh.loop_triangles],dtype=np.int64)
    geo[obj.name]={'v':verts,'f':indices,'tri':verts[indices]}
    print(obj.name,'evaluated',len(verts),len(indices),'bounds',verts.min(axis=0).tolist(),verts.max(axis=0).tolist(),'modifiers',[(m.name,m.type,m.show_viewport) for m in obj.modifiers])
    ev.to_mesh_clear()
print('mm_per_unit',scene.unit_settings.scale_length*1000)
