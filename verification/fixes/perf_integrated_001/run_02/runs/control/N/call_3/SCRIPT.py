import bpy, json, math, collections
from mathutils import Vector
from mathutils.bvhtree import BVHTree
consumer_old_cache=consumer_cache
consumer_cache={}
consumer_summary=[]
scene_depsgraph=bpy.context.evaluated_depsgraph_get()
for name in ['Object_01','Object_02']:
    obj=bpy.data.objects.get(name)
    if obj is None:
        consumer_summary.append({'name':name,'missing':True}); continue
    ev=obj.evaluated_get(scene_depsgraph); me=ev.to_mesh(); me.calc_loop_triangles()
    vs=[ev.matrix_world @ v.co for v in me.vertices]; ts=[tuple(t.vertices) for t in me.loop_triangles]
    old=consumer_old_cache.get(name,{})
    same_verts=len(vs)==len(old.get('verts',[])) and all(tuple(a)==tuple(b) for a,b in zip(vs,old.get('verts',[])))
    same_tris=ts==old.get('tris')
    consumer_cache[name]={'verts':vs,'tris':ts,'bvh':BVHTree.FromPolygons(vs,ts,all_triangles=True)}
    edges=collections.Counter(tuple(sorted(e)) for t in ts for e in [(t[0],t[1]),(t[1],t[2]),(t[2],t[0])])
    consumer_summary.append({'name':name,'vertices':len(vs),'triangles':len(ts),'matrix_world':[list(row) for row in ev.matrix_world],'bbox_min':[min(v[i] for v in vs) for i in range(3)],'bbox_max':[max(v[i] for v in vs) for i in range(3)],'first_verts':[list(v) for v in vs[:24]],'first_tris':ts[:24],'old_world_vertices_identical':same_verts,'old_triangles_identical':same_tris,'closed_edges_twice':all(n==2 for n in edges.values()),'modifiers':[{'name':m.name,'type':m.type} for m in obj.modifiers]})
    ev.to_mesh_clear()
print(json.dumps(consumer_summary,ensure_ascii=False))
