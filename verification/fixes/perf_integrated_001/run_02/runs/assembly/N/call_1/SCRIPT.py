import bpy, json
from mathutils import Vector
out=[]
for ob in bpy.context.scene.objects:
 if ob.type=='MESH':
  m=ob.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
  vs=[list(ob.matrix_world@v.co) for v in m.vertices]
  out.append({'name':ob.name,'verts':len(vs),'polygons':len(m.polygons),'vertices_world':vs,'polys':[list(p.vertices) for p in m.polygons], 'matrix':[list(r) for r in ob.matrix_world]})
print(json.dumps(out))
