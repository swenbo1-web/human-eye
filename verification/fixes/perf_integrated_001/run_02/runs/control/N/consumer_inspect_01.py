import bpy, json, math, time
from mathutils import Vector
from mathutils.bvhtree import BVHTree
scene_depsgraph = bpy.context.evaluated_depsgraph_get()
consumer_cache = {}
consumer_summary = []
for name in ['Object_01','Object_02']:
    obj=bpy.data.objects.get(name)
    if obj is None:
        consumer_summary.append({'name':name,'missing':True}); continue
    ev=obj.evaluated_get(scene_depsgraph)
    me=ev.to_mesh()
    me.calc_loop_triangles()
    vs=[obj.matrix_world @ v.co for v in me.vertices]
    ts=[tuple(t.vertices) for t in me.loop_triangles]
    consumer_cache[name]={'verts':vs,'tris':ts,'bvh':BVHTree.FromPolygons(vs,ts,all_triangles=True)}
    consumer_summary.append({'name':name,'type':obj.type,'vertices':len(vs),'triangles':len(ts),'polygons':len(me.polygons),'matrix_world':[list(row) for row in obj.matrix_world],'bbox_min':[min(v[i] for v in vs) for i in range(3)],'bbox_max':[max(v[i] for v in vs) for i in range(3)],'first_verts':[list(v) for v in vs[:12]],'modifiers':[{'name':m.name,'type':m.type} for m in obj.modifiers]})
    ev.to_mesh_clear()
print(json.dumps(consumer_summary,ensure_ascii=False))
