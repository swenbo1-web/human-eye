import bpy, json, time
from mathutils import Vector
out = {}
for name in ['Object_01','Object_02']:
    o=bpy.data.objects.get(name)
    if o is None:
        out[name]={'missing':True};continue
    dg=bpy.context.evaluated_depsgraph_get()
    ev=o.evaluated_get(dg)
    me=ev.to_mesh()
    me.calc_loop_triangles()
    vs=[tuple(ev.matrix_world@v.co) for v in me.vertices]
    tris=[tuple(t.vertices) for t in me.loop_triangles]
    ec={}
    for p in me.polygons:
        v=list(p.vertices)
        for a,b in zip(v,v[1:]+v[:1]):
            k=tuple(sorted((a,b)));ec[k]=ec.get(k,0)+1
    counts=[ec.get(tuple(sorted(e.vertices)),0) for e in me.edges]
    globals()[name]={'vertices':vs,'triangles':tris,'edges':[tuple(e.vertices) for e in me.edges]}
    out[name]={'type':o.type,'vertices':len(vs),'triangles':len(tris),'polygons':len(me.polygons),'edges':len(counts),'boundary_edges':sum(c==1 for c in counts),'nonmanifold_edges':sum(c!=2 for c in counts),'loose_edges':sum(c==0 for c in counts),'bounds':[[min(v[i] for v in vs),max(v[i] for v in vs)] for i in range(3)],'matrix':[list(row) for row in ev.matrix_world],'modifiers':[(m.name,m.type,m.show_viewport) for m in o.modifiers]}
    ev.to_mesh_clear()
print(json.dumps(out))
