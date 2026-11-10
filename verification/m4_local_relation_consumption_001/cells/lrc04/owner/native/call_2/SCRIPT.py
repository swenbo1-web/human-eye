import bpy, numpy as np, json
objs={o.name:o for o in bpy.context.scene.objects if o.type=='MESH'}
verts={n:np.array([tuple(o.matrix_world@v.co) for v in o.data.vertices]) for n,o in objs.items()}
print(json.dumps([{'name':n,'mesh':o.data.name,'min':verts[n].min(0).tolist(),'max':verts[n].max(0).tolist(),'center':((verts[n].min(0)+verts[n].max(0))/2).tolist()} for n,o in objs.items()],ensure_ascii=False))