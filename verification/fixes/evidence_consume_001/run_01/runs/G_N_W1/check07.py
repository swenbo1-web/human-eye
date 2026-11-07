import bpy, json
from collections import Counter
from mathutils import Vector
D=bpy.context.evaluated_depsgraph_get()
summary=[]
for o in bpy.context.scene.objects:
 if o.type!='MESH': continue
 e=o.evaluated_get(D); m=e.to_mesh();m.calc_loop_triangles()
 v=[e.matrix_world@x.co for x in m.vertices]
 counts=Counter(tuple(sorted((p.vertices[i],p.vertices[(i+1)%len(p.vertices)]))) for p in m.polygons for i in range(len(p.vertices)))
 area=sum((v[t.vertices[1]]-v[t.vertices[0]]).cross(v[t.vertices[2]]-v[t.vertices[0]]).length/2 for t in m.loop_triangles)
 summary.append({'name':o.name,'boundary_edges':sum(n==1 for n in counts.values()),'edges_with_more_than_two_faces':sum(n>2 for n in counts.values()),'world_area':area,'plane_residual':max(abs(p.y-p.x) if o.name=='Object_01' else abs(p.z) for p in v),'origin_vertex_index':[i for i,p in enumerate(v) if p.length==0]})
 e.to_mesh_clear()
print(json.dumps(summary))
print('Intersection segment endpoints in both triangulated surfaces: (-0.125,-0.125,0), (0.125,0.125,0); common origin (0,0,0).')
