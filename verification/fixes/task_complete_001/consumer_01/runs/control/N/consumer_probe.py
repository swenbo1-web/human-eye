import bpy, math, json, time
from mathutils import Vector
_consumer_t0 = time.monotonic()
_consumer_dg = bpy.context.evaluated_depsgraph_get()
_consumer_geoms = {}
_consumer_info = []
for name in ['Object_01','Object_02']:
    obj = bpy.data.objects.get(name)
    if obj is None:
        _consumer_info.append({'name':name,'missing':True})
        continue
    ev = obj.evaluated_get(_consumer_dg)
    mesh = ev.to_mesh()
    mesh.calc_loop_triangles()
    verts = [tuple(ev.matrix_world @ v.co) for v in mesh.vertices]
    tris = [tuple(t.vertices) for t in mesh.loop_triangles]
    _consumer_geoms[name] = (verts, tris)
    lo = [min(v[i] for v in verts) for i in range(3)]
    hi = [max(v[i] for v in verts) for i in range(3)]
    edge_counts = {}
    for tri in tris:
        for i in range(3):
            edge=tuple(sorted((tri[i],tri[(i+1)%3])))
            edge_counts[edge]=edge_counts.get(edge,0)+1
    _consumer_info.append({'name':name,'type':obj.type,'vertices':len(verts),'triangles':len(tris),'bounds':[lo,hi],'matrix':[list(row) for row in ev.matrix_world],'modifiers':[(m.name,m.type,m.show_viewport) for m in obj.modifiers],'nonmanifold_triangle_edges':sum(n!=2 for n in edge_counts.values()),'sample_vertices':verts[:12]})
    ev.to_mesh_clear()
print(json.dumps({'objects':_consumer_info,'unit_scale':bpy.context.scene.unit_settings.scale_length,'elapsed':time.monotonic()-_consumer_t0}))
