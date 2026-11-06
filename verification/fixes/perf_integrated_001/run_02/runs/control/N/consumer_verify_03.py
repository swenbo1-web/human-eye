a=consumer_cache['Object_01']; b=consumer_cache['Object_02']
amin=[min(float(v[k]) for v in a['verts']) for k in range(3)]; amax=[max(float(v[k]) for v in a['verts']) for k in range(3)]
bmin=[min(float(v[k]) for v in b['verts']) for k in range(3)]; bmax=[max(float(v[k]) for v in b['verts']) for k in range(3)]
lo=[max(amin[k],bmin[k]) for k in range(3)]; hi=[min(amax[k],bmax[k]) for k in range(3)]
consumer_interior=[(lo[k]+hi[k])/2 for k in range(3)]
consumer_evidence=[]
for name,d in consumer_cache.items():
    vs=d['verts']; ts=d['tris']; sides=collections.defaultdict(list); signed=[]
    for ti,t in enumerate(ts):
        v0,v1,v2=[tuple(float(q) for q in vs[k]) for k in t]
        u=[v1[k]-v0[k] for k in range(3)];v=[v2[k]-v0[k] for k in range(3)]
        n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
        norm=math.sqrt(sum(q*q for q in n))
        signed.append(sum(n[k]*(consumer_interior[k]-v0[k]) for k in range(3))/norm)
        for axis in range(3):
            if v0[axis]==v1[axis]==v2[axis]: sides[str(axis)+'='+repr(v0[axis])].append(ti)
    changed=[{'index':i,'previous':list(old),'current':list(v)} for i,(old,v) in enumerate(zip(consumer_old_cache[name]['verts'],vs)) if tuple(old)!=tuple(v)]
    consumer_evidence.append({'name':name,'side_triangles':dict(sides),'interior_point_max_outward_signed_plane_distance':max(signed),'changed_vertices':changed})
witness=Vector((amax[0],bmin[1],0))
na=a['bvh'].find_nearest(witness); nb=b['bvh'].find_nearest(witness)
print(json.dumps({'geometry':consumer_evidence,'overlap_interval_min':lo,'overlap_interval_max':hi,'overlap_extents':[hi[k]-lo[k] for k in range(3)],'overlap_volume':math.prod(hi[k]-lo[k] for k in range(3)),'strictly_shared_interior_point':consumer_interior,'bvh_triangle_intersection_pairs':a['bvh'].overlap(b['bvh']),'common_surface_witness':list(witness),'witness_a_surface_distance':na[3],'witness_a_triangle':na[2],'witness_b_surface_distance':nb[3],'witness_b_triangle':nb[2]},ensure_ascii=False))
