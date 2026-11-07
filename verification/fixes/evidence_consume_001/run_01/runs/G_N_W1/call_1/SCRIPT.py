import bpy, json
from mathutils import Vector
objs=[o for o in bpy.context.scene.objects if o.type=='MESH']
print(json.dumps({'objects':[{'name':o.name,'vertices':len(o.data.vertices),'polygons':len(o.data.polygons),'location':list(o.location),'scale':list(o.scale),'bounds':[[min((o.matrix_world@Vector(c))[i] for c in o.bound_box),max((o.matrix_world@Vector(c))[i] for c in o.bound_box)] for i in range(3)]} for o in objs]}))
