import json as _j, os as _os
def _scale_snapshot():
 rows=[]
 for o in sorted(bpy.context.scene.objects,key=lambda o:o.name):
  if o.type!='MESH':continue
  local=[[float(c) for c in v.co] for v in o.data.vertices];mat=[[float(v) for v in r] for r in o.matrix_world]
  rows.append({'logical_id':o.get('scale_logical_id'),'name':o.name,'vertices_local':local,'matrix_world':mat,'vertices_world':[[sum(mat[j][i]*p[i] for i in range(3))+mat[j][3] for j in range(3)] for p in local],'triangles':[list(p.vertices) for p in o.data.polygons]})
 return {'unit_scale_m':float(bpy.context.scene.unit_settings.scale_length),'objects':rows}
_os.environ['SCALE_OWNED_INPUT']=bpy.data.filepath
print(_j.dumps(_scale_snapshot(),allow_nan=False,separators=(',',':')))
