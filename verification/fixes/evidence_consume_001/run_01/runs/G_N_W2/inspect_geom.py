import bpy, json
print(json.dumps({'objects':[{'name':o.name,'type':o.type,'vertices':len(o.data.vertices) if o.type=='MESH' else None,'polygons':len(o.data.polygons) if o.type=='MESH' else None,'location':list(o.location),'scale':list(o.scale),'modifiers':[m.type for m in o.modifiers]} for o in bpy.context.scene.objects]},ensure_ascii=False))
