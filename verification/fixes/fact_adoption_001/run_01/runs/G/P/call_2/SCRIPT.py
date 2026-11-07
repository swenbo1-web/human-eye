import bpy, json
objs=[bpy.data.objects.get('Object_01'),bpy.data.objects.get('Object_02')]
deps=bpy.context.evaluated_depsgraph_get()
for o in objs:
 e=o.evaluated_get(deps); m=e.to_mesh();m.calc_loop_triangles()
 print(json.dumps({'name':o.name,'type':o.type,'matrix':[[float(x) for x in r] for r in e.matrix_world], 'vertices':len(m.vertices),'edges':len(m.edges),'polygons':len(m.polygons),'triangles':len(m.loop_triangles),'modifiers':[{'name':a.name,'type':a.type,'show_viewport':a.show_viewport} for a in o.modifiers], 'bounds':[[min((e.matrix_world@v.co)[i] for v in m.vertices), max((e.matrix_world@v.co)[i] for v in m.vertices)] for i in range(3)]}))
 e.to_mesh_clear()
