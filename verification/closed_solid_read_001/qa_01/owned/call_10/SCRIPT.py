# closed_solid_qa_state:changed_current
import json
import math
import re
from decimal import Decimal
rows=[]
for obj in sorted(bpy.context.scene.objects,key=lambda value:value.name):
    if obj.type!='MESH': continue
    matrix=[[float(x) for x in row] for row in obj.matrix_world]
    local=[[float(x) for x in v.co] for v in obj.data.vertices]
    world=[[(sum(matrix[r][k]*p[k] for k in range(3))+matrix[r][3])*float(bpy.context.scene.unit_settings.scale_length) for r in range(3)] for p in local]
    rows.append(dict(name=obj.name,vertices_local=local,matrix_world=matrix,world_vertices=world,faces=[list(p.vertices) for p in obj.data.polygons]))
print('COMPLEX_NATIVE_READBACK:'+json.dumps(dict(unit_scale_m=float(bpy.context.scene.unit_settings.scale_length),objects=rows),separators=(',',':'),allow_nan=False))
