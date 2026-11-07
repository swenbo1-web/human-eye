import bpy, json, collections
_geom=[]
for o in bpy.context.scene.objects:
 if o.type!='MESH': continue
 me=o.data
 vs=[tuple(o.matrix_world @ v.co) for v in me.vertices]
 fs=[tuple(p.vertices) for p in me.polygons]
 counts=collections.Counter(tuple(sorted((f[i],f[(i+1)%len(f)]))) for f in fs for i in range(len(f)))
 _geom.append((o.name,vs,fs))
 print(json.dumps({'name':o.name,'vertices':vs,'faces':fs,'edge_counts':dict(collections.Counter(counts.values())),'matrix':[list(x) for x in o.matrix_world]},ensure_ascii=False))
