bpy.context.view_layer.update()
consumer_dg=bpy.context.evaluated_depsgraph_get(); consumer_dg.update()
consumer_current={}; consumer_check=[]
for name in ['Object_01','Object_02']:
    obj=bpy.data.objects[name]; ev=obj.evaluated_get(consumer_dg); me=ev.to_mesh(); me.calc_loop_triangles()
    vs=[ev.matrix_world@v.co for v in me.vertices]; ts=[tuple(t.vertices) for t in me.loop_triangles]
    same=(ts==consumer_cache[name]['tris'] and len(vs)==len(consumer_cache[name]['verts']) and all(tuple(x)==tuple(y) for x,y in zip(vs,consumer_cache[name]['verts'])))
    sides=collections.defaultdict(list)
    for ti,t in enumerate(ts):
        for axis in range(3):
            vals=[float(vs[k][axis]) for k in t]
            if len(set(vals))==1: sides[str(axis)+'='+repr(vals[0])].append(ti)
    consumer_current[name]={'verts':vs,'tris':ts,'bvh':BVHTree.FromPolygons(vs,ts,all_triangles=True)}
    consumer_check.append({'name':name,'evaluated_geometry_identical_after_update':same,'side_triangles':dict(sides),'original_mesh_vertex_count':len(obj.data.vertices),'original_mesh_polygon_count':len(obj.data.polygons)})
    ev.to_mesh_clear()
consumer_cache=consumer_current
a=consumer_cache['Object_01']; b=consumer_cache['Object_02']
px=max(v.x for v in a['verts']); qx=min(v.x for v in b['verts']); p=Vector((px,0,0));q=Vector((qx,0,0))
print(json.dumps({'current_evidence':consumer_check,'bvh_intersection_pairs':a['bvh'].overlap(b['bvh']),'surface_witness_a':list(p),'surface_witness_b':list(q),'witness_a_distance_to_surface':a['bvh'].find_nearest(p)[3],'witness_b_distance_to_surface':b['bvh'].find_nearest(q)[3],'minimum_gap':qx-px,'direction_a_to_b':[1,0,0]},ensure_ascii=False))
