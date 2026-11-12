import numpy as np
from collections import Counter
geo={}
deps=bpy.context.evaluated_depsgraph_get()
for name in ['Target','Part_A','Part_B','Part_C']:
    obj=bpy.data.objects[name].evaluated_get(deps)
    mesh=obj.to_mesh(); mesh.calc_loop_triangles()
    local=np.array([tuple(v.co) for v in mesh.vertices], dtype=np.float64)
    mat=np.array(obj.matrix_world,dtype=np.float64)
    verts=local@mat[:3,:3].T+mat[:3,3]
    tris=np.array([tuple(t.vertices) for t in mesh.loop_triangles],dtype=np.int64)
    edges=Counter(tuple(sorted((int(face[i]),int(face[(i+1)%3])))) for face in tris for i in range(3))
    geo[name]=(verts,tris)
    print(name,'verts',len(verts),'triangles',len(tris),'bounds',verts.min(0).tolist(),verts.max(0).tolist(),'edge_incidence',dict(Counter(edges.values())))
    obj.to_mesh_clear()