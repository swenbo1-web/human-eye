import bpy,json,math
from mathutils import Vector
dg=bpy.context.evaluated_depsgraph_get()
vs=[]
for name in ['Object_01','Object_02']:
 eo=bpy.data.objects[name].evaluated_get(dg); m=eo.to_mesh()
 vs.append([tuple(float(c) for c in (eo.matrix_world @ v.co)) for v in m.vertices]);eo.to_mesh_clear()
n=(-0.8,0.6,0.0); u=(0.6,0.8,0.0)
dot=lambda x,y:sum(a*b for a,b in zip(x,y))
intervals=[[min(dot(p,n) for p in v),max(dot(p,n) for p in v)] for v in vs]
a=tuple(sum(vs[0][i][k] for i in [2,3,6,7])/4 for k in range(3))
b=tuple(sum(vs[1][i][k] for i in [0,1,4,5])/4 for k in range(3))
d=tuple(y-x for x,y in zip(a,b)); length=math.sqrt(dot(d,d))
print(json.dumps({'normal':n,'support_intervals':intervals,'gap_lower_bound':intervals[1][0]-intervals[0][1],'surface_witness_A':a,'surface_witness_B':b,'witness_distance':length,'unit_direction_A_to_B':tuple(c/length for c in d),'long_axis_intervals':[[min(dot(p,u) for p in v),max(dot(p,u) for p in v)] for v in vs]}))
