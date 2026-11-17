"""Exact no-product preflight for the proposed arbitrary source-face task."""
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
FIXTURE = Path('C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe/verification/m4_global_local_qualification_001/fixture/GEOMETRY.json')


def sub(a, b):
    return tuple(x-y for x,y in zip(a,b))


def dot(a, b):
    return sum(x*y for x,y in zip(a,b))


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])


def clip(poly, distance):
    out = []
    for a,b in zip(poly,poly[1:]+poly[:1]):
        da,db = distance(a),distance(b)
        if da >= 0:
            out.append(a)
        if (da < 0 < db) or (db < 0 < da):
            t = da/(da-db)
            out.append(tuple(x+t*(y-x) for x,y in zip(a,b)))
    return out


def area2(poly):
    return abs(sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(poly,poly[1:]+poly[:1]))) if poly else F(0)


def triangle_visible(objects, name, face_index, direction):
    target = next(o for o in objects if o['name'] == name)
    p,u_point,v_point = [target['vertices'][i] for i in target['faces'][face_index]]
    u,v = sub(u_point,p),sub(v_point,p)
    normal = cross(u,v)
    denom = dot(normal,direction)
    if denom <= 0:
        return dict(visible=False,reason='not_front_facing',normal=list(map(str,normal)),front_dot=str(denom))
    uu,uv,vv = dot(u,u),dot(u,v),dot(v,v)
    gram = uu*vv-uv*uv
    collisions = []
    checked = 0
    for o in objects:
        for fi,face in enumerate(o['faces']):
            if o['name'] == name and fi == face_index:
                continue
            tri = [o['vertices'][i] for i in face]
            if max(dot(normal,sub(q,p)) for q in tri) <= 0:
                checked += 1
                continue
            front = clip(tri,lambda q:dot(normal,sub(q,p)))
            projected = []
            for q in front:
                ray_t = dot(normal,sub(q,p))/denom
                hit = tuple(x-ray_t*d for x,d in zip(q,direction))
                rel = sub(hit,p)
                ru,rv = dot(rel,u),dot(rel,v)
                projected.append(((ru*vv-rv*uv)/gram,(rv*uu-ru*uv)/gram))
            projected = clip(projected,lambda q:q[0])
            projected = clip(projected,lambda q:q[1])
            projected = clip(projected,lambda q:1-q[0]-q[1])
            overlap = area2(projected)
            if overlap:
                collisions.append(dict(object=o['name'],face=fi,projected_barycentric_area2=str(overlap)))
            checked += 1
    return dict(visible=not collisions,positive_area_occluders=collisions,front_dot=str(denom),
                normal=list(map(str,normal)),other_triangles_checked=checked)


def main():
    raw = FIXTURE.read_bytes()
    old = json.loads(raw)
    objects = [dict(name=o['name'],vertices=[tuple(map(F,p)) for p in o['vertices_world_m']],faces=o['triangles'])
               for o in old['objects']]
    offsets = [(0,0,1),(F(3,4),0,1),(F(3,4),F(1,4),1),(F(1,4),F(1,4),F(9,8)),
               (F(1,4),F(3,4),F(9,8)),(0,F(3,4),1),(2,0,F(1,32)),(2,F(1,4),F(1,32))]
    a = dict(name='Obj_07',vertices=[tuple(F(base)+F(value) for base,value in zip((4,4,0),p)) for p in offsets],
             faces=[(0,1,2),(0,2,3),(0,3,4),(0,4,5),(1,6,7),(1,7,2)])
    objects = [a if o['name']=='Obj_07' else o for o in objects]
    for name,x0,x1 in [('Ref_B',F(11,2),F(13,2)),('Ref_C',F(15,2),F(17,2))]:
        objects.append(dict(name=name,vertices=[(x0,F(3),F(0)),(x1,F(3),F(0)),(x1,F(6),F(0)),(x0,F(6),F(0))],
                            faces=[(0,1,2),(0,2,3)]))
    selected = list(range(4))
    used = sorted({i for fi in selected for i in a['faces'][fi]})
    vertices = [a['vertices'][i] for i in used]
    normals = [cross(sub(a['vertices'][face[1]],a['vertices'][face[0]]),
                     sub(a['vertices'][face[2]],a['vertices'][face[0]])) for face in a['faces'][:4]]
    noncoplanar = any(dot(normals[0],sub(p,vertices[0])) != 0 for p in vertices)
    direction = (F(4),F(-4),F(3))
    visibility = [dict(face=fi,**triangle_visible(objects,'Obj_07',fi,direction)) for fi in selected]
    distance = dict(region_to_B_squared=F(25,16),region_to_C_squared=F(137,16),
                    whole_A_to_B_squared=F(1,1024),whole_A_to_C_squared=F(2305,1024))
    lower_region_B = (F(11,2)-max(p[0] for p in vertices))**2+min(p[2] for p in vertices)**2
    lower_region_C = (F(15,2)-max(p[0] for p in vertices))**2+min(p[2] for p in vertices)**2
    lower_whole_B = min(p[2] for p in a['vertices'])**2
    lower_whole_C = (F(15,2)-max(p[0] for p in a['vertices']))**2+min(p[2] for p in a['vertices'])**2
    computed = dict(region_to_B_squared=lower_region_B,region_to_C_squared=lower_region_C,
                    whole_A_to_B_squared=lower_whole_B,whole_A_to_C_squared=lower_whole_C)
    assert computed == distance
    # Explicit pairs attain each lower bound on both represented source sets.
    witnesses = dict(region_to_B=(a['vertices'][1],(F(11,2),F(4),F(0))),
        region_to_C=(a['vertices'][1],(F(15,2),F(4),F(0))),
        whole_A_to_B=(a['vertices'][6],(F(6),F(4),F(0))),
        whole_A_to_C=(a['vertices'][6],(F(15,2),F(4),F(0))))
    for key,(p,q) in witnesses.items():
        assert dot(sub(p,q),sub(p,q)) == distance[key+'_squared']
        assert F(3) <= q[1] <= F(6) and q[2] == 0
    assert noncoplanar and len(used) == 6
    # XY boundary is the concave L, with exact sign-changing turns.
    boundary = a['vertices'][:6]
    turns = [cross(sub(boundary[(i+1)%6],boundary[i]),sub(boundary[(i+2)%6],boundary[(i+1)%6]))[2]
             for i in range(6)]
    assert any(t>0 for t in turns) and any(t<0 for t in turns)
    result = dict(status='passed' if all(v['visible'] for v in visibility) else 'geometry_not_realized',
        fixed_original_geometry_sha256=hashlib.sha256(raw).hexdigest(),new_recipe_tuned_after_result=False,
        objects=len(objects),vertices=sum(len(o['vertices']) for o in objects),triangles=sum(len(o['faces']) for o in objects),
        selected_source_face_rows=selected,source_region_vertex_rows=used,source_region_noncoplanar=noncoplanar,
        xy_boundary_concave=True,region_to_B='5/4',region_to_C='sqrt(137)/4',whole_A_to_B='1/32',whole_A_to_C='sqrt(2305)/32',
        distance_squared={k:str(v) for k,v in distance.items()},
        lower_bound_method='axiswise separation on all source points and convex triangle interiors; explicit attaining source vertex and reference-face point',
        attaining_pairs={k:[[str(x) for x in p],[str(x) for x in q]] for k,(p,q) in witnesses.items()},
        SCENE_direction=[4,-4,3],selected_triangle_visibility=visibility,
        visibility_scope='full current scene including own unselected tab and both added reference planes; exact positive-front clipping, Gram projection and triangle intersection',
        actual_local_camera_and_pixel_readability='unrun',new_live_Blender=0,new_raster=0,new_model=0)
    (OUT/'NEXT_REGION_PREFLIGHT.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
