import json, collections, math
consumer_verify=[]
for name,d in consumer_cache.items():
    vs=d['verts']; ts=d['tris']; edges=collections.Counter(); sides=collections.defaultdict(list)
    volume=0.0
    for ti,t in enumerate(ts):
        a,b,c=[vs[k] for k in t]
        volume+=a.dot(b.cross(c))/6.0
        for i,j in [(t[0],t[1]),(t[1],t[2]),(t[2],t[0])]: edges[tuple(sorted((i,j)))]+=1
        for axis in range(3):
            if a[axis]==b[axis]==c[axis]: sides[str(axis)+'='+repr(float(a[axis]))].append(ti)
    consumer_verify.append({'name':name,'triangles':ts,'closed_edges_twice':all(n==2 for n in edges.values()),'edge_count':len(edges),'side_triangles':dict(sides),'signed_volume':volume})
a=consumer_cache['Object_01']; b=consumer_cache['Object_02']
px=max(v.x for v in a['verts']); qx=min(v.x for v in b['verts'])
p=Vector((px,0,0)); q=Vector((qx,0,0))
print(json.dumps({'geometry':consumer_verify,'bvh_intersection_pairs':a['bvh'].overlap(b['bvh']),'surface_witness_a':list(p),'surface_witness_b':list(q),'witness_a_distance_to_surface':a['bvh'].find_nearest(p)[3],'witness_b_distance_to_surface':b['bvh'].find_nearest(q)[3],'minimum_gap':qx-px,'direction_a_to_b':[1,0,0]},ensure_ascii=False))
