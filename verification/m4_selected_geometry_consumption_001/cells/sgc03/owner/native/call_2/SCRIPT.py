import bpy, json
from mathutils import Vector
objs={o.name:o for o in bpy.context.scene.objects if o.type=='MESH'}
def worldverts(o): return [o.matrix_world@v.co for v in o.data.vertices]
def bounds(o):
 v=worldverts(o); return [[min(p[i] for p in v) for i in range(3)],[max(p[i] for p in v) for i in range(3)]]
print(json.dumps([{'name':o.name,'mesh':o.data.name,'bounds':bounds(o),'center':[(a+b)/2 for a,b in zip(*bounds(o))]} for o in objs.values()],indent=1))