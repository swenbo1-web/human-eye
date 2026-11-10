print('current_scene_matches',signature({o.name:read_geom(o) for o in bpy.context.scene.objects if o.type=='MESH'})==geom_sig)
a,b=edges_from(v2,f2); triangles=v1[f1]
records=[]
for edge_index,(p0,p1) in enumerate(zip(a,b)):
    direction=p1-p0
    for face_index,tri in enumerate(triangles):
        matrix=np.column_stack((direction,-(tri[1]-tri[0]),-(tri[2]-tri[0])))
        if abs(np.linalg.det(matrix))<1e-18:continue
        t,u,v=np.linalg.solve(matrix,tri[0]-p0)
        if 0<=t<=1 and u>=0 and v>=0 and u+v<=1:
            p=p0+t*direction; q=tri[0]+u*(tri[1]-tri[0])+v*(tri[2]-tri[0])
            records.append({'near_edge_index':edge_index,'target_triangle_index':face_index,'edge_parameter':float(t),'target_triangle_barycentric':[float(1-u-v),float(u),float(v)],'point_world_m':p.tolist(),'residual_m':float(np.linalg.norm(p-q))})
print('near_edge_target_face_intersections',len(records))
print('intersection_evidence',records[:2])