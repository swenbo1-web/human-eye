import bpy, json, math, time
from mathutils import Vector
_dg=bpy.context.evaluated_depsgraph_get()
_objs={}
for name in ['Object_01','Object_02']:
    o=bpy.data.objects.get(name)
    if o is None:
        print(json.dumps({'missing':name})); continue
    eo=o.evaluated_get(_dg)
    me=eo.to_mesh()
    me.calc_loop_triangles()
    vs=[eo.matrix_world @ v.co for v in me.vertices]
    ts=[tuple(t.vertices) for t in me.loop_triangles]
    fs=[tuple(p.vertices) for p in me.polygons]
    _objs[name]={'v':vs,'t':ts,'f':fs}
    edge={}
    for fi,f in enumerate(fs):
        for a,b in zip(f,f[1:]+f[:1]):
            k=tuple(sorted((a,b))); edge.setdefault(k,[]).append((a,b,fi))
    counts={str(k):sum(len(v)==k for v in edge.values()) for k in [1,2]}
    bad=sum(len(v)>2 for v in edge.values())
    winding=sum(len(v)==2 and v[0][:2]==v[1][:2] for v in edge.values())
    vol=sum(vs[a].dot(vs[b].cross(vs[c]))/6 for a,b,c in ts)
    deg=sum((vs[b]-vs[a]).cross(vs[c]-vs[a]).length_squared<1e-24 for a,b,c in ts)
    print(json.dumps({'name':name,'type':o.type,'base_counts':[len(o.data.vertices),len(o.data.edges),len(o.data.polygons)] if o.type=='MESH' else None,'evaluated_counts':[len(vs),len(me.edges),len(fs),len(ts)],'bbox_min':[min(v[i] for v in vs) for i in range(3)],'bbox_max':[max(v[i] for v in vs) for i in range(3)],'modifiers':[(m.name,m.type,m.show_viewport) for m in o.modifiers],'matrix_world':[list(row) for row in eo.matrix_world],'edge_face_incidence':counts,'edge_over_2':bad,'inconsistent_winding_edges':winding,'degenerate_triangles':deg,'signed_volume':vol}))
    eo.to_mesh_clear()
print('READ_DONE')
