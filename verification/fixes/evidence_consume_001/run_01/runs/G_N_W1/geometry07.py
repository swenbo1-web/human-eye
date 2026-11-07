import bpy, json
from mathutils import Vector
D=bpy.context.evaluated_depsgraph_get()
for o in bpy.context.scene.objects:
 if o.type!='MESH': continue
 e=o.evaluated_get(D); m=e.to_mesh(); m.calc_loop_triangles()
 vs=[list(e.matrix_world@v.co) for v in m.vertices]
 print(json.dumps({'name':o.name,'modifiers':[(x.name,x.type) for x in o.modifiers],'vertices':vs,'polygons':[list(p.vertices) for p in m.polygons],'triangles':[list(t.vertices) for t in m.loop_triangles]}))
 e.to_mesh_clear()
