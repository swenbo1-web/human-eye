import numpy as np
_deps=bpy.context.evaluated_depsgraph_get()
_geo={}
for obj in scene.objects:
    if obj.type!='MESH': continue
    evaluated=obj.evaluated_get(_deps)
    mesh=evaluated.to_mesh()
    mesh.calc_loop_triangles()
    matrix=np.array(evaluated.matrix_world,dtype=np.float64)
    local=np.array([v.co[:] for v in mesh.vertices],dtype=np.float64)
    vertices=local@matrix[:3,:3].T+matrix[:3,3]
    faces=np.array([tuple(t.vertices) for t in mesh.loop_triangles],dtype=np.int64)
    _geo[obj.name]=(vertices,faces)
    print(obj.name,'evaluated vertices/triangles',len(vertices),len(faces),'bbox',vertices.min(axis=0).tolist(),vertices.max(axis=0).tolist(),'modifiers',[(m.name,m.type) for m in obj.modifiers])
    evaluated.to_mesh_clear()
