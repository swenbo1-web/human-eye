import bpy,json
out=[]
for o in bpy.context.scene.objects:
 if o.name.startswith('Object_'):
  me=o.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
  vs=[list(o.matrix_world @ v.co) for v in me.vertices]
  out.append({'name':o.name,'type':o.type,'location':list(o.location),'rotation':list(o.rotation_euler),'scale':list(o.scale),'vertices':len(vs),'faces':len(me.polygons),'bounds':[[min(v[i] for v in vs),max(v[i] for v in vs)] for i in range(3)],'sample_vertices':vs[:12]})
print(json.dumps(out))
