import numpy as np
D=bpy.context.evaluated_depsgraph_get()
geom={}
for o in s.objects:
    if o.type!='MESH': continue
    eo=o.evaluated_get(D); me=eo.to_mesh(); me.calc_loop_triangles()
    mat=np.array(eo.matrix_world,dtype=np.float64)
    verts=np.array([tuple(v.co) for v in me.vertices],dtype=np.float64)
    verts=verts@mat[:3,:3].T+mat[:3,3]
    faces=np.array([tuple(t.vertices) for t in me.loop_triangles],dtype=np.int64)
    geom[o.name]=(verts,faces,verts[faces])
    eo.to_mesh_clear()
    print(o.name,'triangles',len(faces),'world_bounds',verts.min(axis=0).tolist(),verts.max(axis=0).tolist(),'modifiers',[(m.name,m.type,m.show_viewport) for m in o.modifiers])
