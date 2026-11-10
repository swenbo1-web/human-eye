import bpy, json
from mathutils import Vector
objs={o.name:o for o in bpy.context.scene.objects if o.type=='MESH'}
def bounds(o):
 p=[o.matrix_world@v.co for v in o.data.vertices]
 lo=[min(v[i] for v in p) for i in range(3)]; hi=[max(v[i] for v in p) for i in range(3)]
 return {'lo':lo,'hi':hi,'center':[(a+b)/2 for a,b in zip(lo,hi)]}
print(json.dumps({n:{'data':o.data.name,**bounds(o)} for n,o in objs.items()},ensure_ascii=False))
print('camera',[(o.name, list(o.location),o.data.type) for o in bpy.context.scene.objects if o.type=='CAMERA'])