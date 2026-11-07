import bpy, bmesh, json
cert={}
n=(2/3,-1/3,2/3)
for name in ('Object_01','Object_02'):
    o=bpy.data.objects[name]
    bm=bmesh.new();bm.from_mesh(o.data)
    vals=[sum(n[i]*(o.matrix_world@v.co)[i] for i in range(3)) for v in o.data.vertices]
    hist={}
    for e in bm.edges:
        k=len(e.link_faces);hist[k]=hist.get(k,0)+1
    cert[name]={'projection_min':min(vals),'projection_max':max(vals),'projection_values':vals,'face_incidence_histogram':hist,'bmesh_boundary_edges':sum(e.is_boundary for e in bm.edges),'bmesh_not_is_manifold_edges':sum(not e.is_manifold for e in bm.edges),'more_than_two_faces_edges':sum(len(e.link_faces)>2 for e in bm.edges)}
    bm.free()
print(json.dumps({'normal':n,'certificate':cert}))
