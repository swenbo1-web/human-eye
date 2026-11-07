import bpy, math, json
_oldq2 = _previous
bpy.context.view_layer.update()
_dg3=bpy.context.evaluated_depsgraph_get()
_dg3.update()
_current3={}
for _name in ['Object_01','Object_02']:
    _obj=bpy.data.objects[_name]
    _ev=_obj.evaluated_get(_dg3)
    _mesh=_ev.to_mesh()
    _mesh.calc_loop_triangles()
    _current3[_name]=([tuple(_ev.matrix_world @ v.co) for v in _mesh.vertices],[tuple(t.vertices) for t in _mesh.loop_triangles])
    _ev.to_mesh_clear()
_v1,_t1=_current3['Object_01']
_v2,_t2=_current3['Object_02']
_lo1=[min(v[i] for v in _v1) for i in range(3)]
_hi1=[max(v[i] for v in _v1) for i in range(3)]
_lo2=[min(v[i] for v in _v2) for i in range(3)]
_hi2=[max(v[i] for v in _v2) for i in range(3)]
_olo=[max(_lo1[i],_lo2[i]) for i in range(3)]
_ohi=[min(_hi1[i],_hi2[i]) for i in range(3)]
_inside=[(_olo[i]+_ohi[i])/2 for i in range(3)]
def _plane_evidence(verts,tris,point):
    result=[]
    for ti,t in enumerate(tris):
        a,b,c=[verts[j] for j in t]
        u=[b[i]-a[i] for i in range(3)]
        v=[c[i]-a[i] for i in range(3)]
        n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
        length=math.sqrt(sum(x*x for x in n))
        n=[x/length for x in n]
        d=sum(n[i]*(point[i]-a[i]) for i in range(3))
        result.append({'triangle':ti,'outward_normal':n,'point_signed_distance_m':d})
    return result
_changed={}
for _name in ['Object_01','Object_02']:
    _oldv,_oldt=_oldq2[_name]
    _newv,_newt=_current3[_name]
    _changed[_name]={'triangle_indices_unchanged':_oldt==_newt,'changed_vertices':[{'index':i,'old':_oldv[i],'current':v} for i,v in enumerate(_newv) if v!=_oldv[i]]}
_crossing=[_hi1[0],_hi2[1],0.0]
print(json.dumps({'changes_from_question2_cache':_changed,'shared_strict_interior_point_m':_inside,'point_vs_current_triangle_planes_01':_plane_evidence(_v1,_t1,_inside),'point_vs_current_triangle_planes_02':_plane_evidence(_v2,_t2,_inside),'actual_box_overlap_bounds_m':[_olo,_ohi],'overlap_x_thickness_m':_ohi[0]-_olo[0],'surface_crossing_point_m':_crossing,'surface_crossing_triangles_01':[{'index':i,'vertices':[_v1[j] for j in t]} for i,t in enumerate(_t1) if all(_v1[j][0]==_hi1[0] for j in t)],'surface_crossing_triangles_02':[{'index':i,'vertices':[_v2[j] for j in t]} for i,t in enumerate(_t2) if all(_v2[j][1]==_hi2[1] for j in t)]}))
_consumer_geoms=_current3
