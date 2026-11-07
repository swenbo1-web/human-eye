import bpy,json,math
dg=bpy.context.evaluated_depsgraph_get(); out={}; p=(-0.078125,0.05859375,0.0)
dot=lambda a,b:sum(x*y for x,y in zip(a,b))
sub=lambda a,b:tuple(x-y for x,y in zip(a,b))
cross=lambda a,b:(a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
for name in ['Object_01','Object_02']:
 eo=bpy.data.objects[name].evaluated_get(dg);m=eo.to_mesh();m.calc_loop_triangles();v=[tuple(float(c) for c in eo.matrix_world@x.co) for x in m.vertices]
 ds=[]
 for t in m.loop_triangles:
  a,b,c=(v[i] for i in t.vertices);n=cross(sub(b,a),sub(c,a));l=math.sqrt(dot(n,n));ds.append(dot(n,sub(p,a))/l)
 out[name]={'projection_u':[min(dot(x,(.6,.8,0)) for x in v),max(dot(x,(.6,.8,0)) for x in v)],'projection_v':[min(dot(x,(-.8,.6,0)) for x in v),max(dot(x,(-.8,.6,0)) for x in v)],'projection_z':[min(x[2] for x in v),max(x[2] for x in v)],'interior_witness':p,'maximum_outward_face_signed_distance':max(ds),'all_face_distances':ds}
 eo.to_mesh_clear()
print(json.dumps(out))
