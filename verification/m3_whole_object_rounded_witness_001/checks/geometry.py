"""Independent exact triangle-surface facts for rounded witness qualification."""

from fractions import Fraction as F
import json
from math import isfinite,sqrt
from pathlib import Path
import re
from runpy import run_path


V = Path(__file__).resolve().parents[2]
POINT = run_path(str(V/'m5_observe_measure_001/oracle.py'))
triangle_distance_squared = POINT['triangle_distance_squared']
segment_distance_squared = POINT['segment_distance_squared']
dot,cross,sub = (POINT[k] for k in ('dot','cross','subtract'))
LITERAL = re.compile(r'-?(0|[1-9][0-9]*)(?:/[1-9][0-9]*)?\Z')
REGISTERED_EXACT = {
    'linear_m01_m03':{'squared':'11449/1024','indices':[8,12],
                      'points_m':[['-41/10','-503/160','5/4'],['-67/32','-15/32','5/4']]},
    'linear_m16_m20':{'squared':'3481/50','indices':[2,1],
                      'points_m':[['109/4','-13/4','15/4'],['3197/100','-679/100','193/20']]},
    'tree_n02_n03':{'indices':[38,3]},
}


def require(condition,reason):
    if not condition:
        raise ValueError(reason)


def fraction(value):
    require(type(value) is str and len(value)<=1024 and LITERAL.fullmatch(value),
            'canonical_bounded_rational_coordinate_string_required')
    numeric = F(value)
    require(str(numeric)==value,'reduced_rational_coordinate_string_required')
    return numeric


def vector(point,*,exact=False):
    require(type(point) in (list,tuple) and len(point)==3,'requires_three_world_coordinates')
    if exact:
        return tuple(fraction(v) for v in point)
    require(all(type(v) in (int,float) and isfinite(v) for v in point),'requires_finite_world_display_coordinates')
    return tuple(F(v) for v in point)


def encode(value):
    return json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False)


def canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)


def surface(mesh):
    raw_points = mesh.get('vertices',mesh.get('vertices_world_m'))
    raw_faces = mesh.get('faces',mesh.get('triangles'))
    vertices = tuple(vector(p) for p in raw_points)
    indices = tuple(tuple(row) for row in raw_faces)
    require(indices and all(len(face)==3 and all(type(i) is int and 0<=i<len(vertices) for i in face)
                            for face in indices),'invalid_original_object_local_triangle_rows')
    return vertices,indices


def selected(surface, index):
    vertices,faces = surface
    require(type(index) is int and 0<=index<len(faces),'certificate_triangle_index_outside_current_object')
    return tuple(vertices[i] for i in faces[index])


def exactly_on(point, triangle):
    return triangle_distance_squared(point,triangle)==0


def length_sq(a,b):
    return dot(sub(a,b),sub(a,b))


def at(a, direction, t):
    return tuple(x+t*y for x,y in zip(a,direction,strict=True))


def edges(triangle):
    return tuple(zip(triangle,triangle[1:]+triangle[:1],strict=True))


def edge_pair_distance(a,b,c,d):
    best = min(segment_distance_squared(a,c,d),segment_distance_squared(b,c,d),
               segment_distance_squared(c,a,b),segment_distance_squared(d,a,b))
    u,v,w = sub(b,a),sub(d,c),sub(a,c)
    uu,uv,vv,uw,vw = (dot(x,y) for x,y in ((u,u),(u,v),(v,v),(u,w),(v,w)))
    det = uu*vv-uv*uv
    if det:
        t,s = (uv*vw-vv*uw)/det,(uu*vw-uv*uw)/det
        if 0<=t<=1 and 0<=s<=1:
            best = min(best,length_sq(at(a,u,t),at(c,v,s)))
    return best


def edge_hits_triangle(a,b,triangle):
    x,y,z = triangle
    normal = cross(sub(y,x),sub(z,x))
    signed_a,signed_b = dot(sub(a,x),normal),dot(sub(b,x),normal)
    if signed_a==signed_b or signed_a*signed_b>0:
        return False
    t = signed_a/(signed_a-signed_b)
    return 0<=t<=1 and exactly_on(at(a,sub(b,a),t),triangle)


def exact_triangle_distance_squared(a,b):
    """Complete positive-distance feature enumeration including intersection controls."""
    sides_a,sides_b = edges(a),edges(b)
    if any(edge_hits_triangle(p,q,b) for p,q in sides_a) or any(edge_hits_triangle(p,q,a) for p,q in sides_b):
        return F(0)
    closest = min(*(triangle_distance_squared(v,b) for v in a),*(triangle_distance_squared(v,a) for v in b))
    if not closest:
        return F(0)
    return min(closest,*(edge_pair_distance(p,q,r,s) for p,q in sides_a for r,s in sides_b))


def checked_points(surfaces, indices, point_strings, published, *, expect_exact):
    require(type(indices) is list and len(indices)==2 and type(point_strings) is list and len(point_strings)==2,
            'exactly_one_current_source_triangle_and_point_per_endpoint')
    detail,points = [],[]
    display_outside = []
    for side,(mesh,index,values,display) in enumerate(zip(surfaces,indices,point_strings,published,strict=True)):
        actual = selected(mesh,index)
        proof = vector(values,exact=expect_exact)
        shown = vector(display)
        require(exactly_on(proof,actual),'proof_point_not_exactly_on_current_source_triangle/'+str(side))
        if expect_exact:
            require(all(float(p)==float(q) for p,q in zip(proof,shown,strict=True)),
                    'exact_point_does_not_roundtrip_to_original_public_display/'+str(side))
        display_outside.append(not exactly_on(shown,actual))
        detail.append({'index':index,'vertex_indices':list(mesh[1][index]),
                       'exact_point_m':list(map(str,proof)),'display_point_m':list(display)})
        points.append(proof)
    require(not expect_exact or any(display_outside),'rounded_certificate_hides_existing_exact_display_membership')
    return points,{'sides':detail,'original_display_outside_winning_triangle':display_outside}


def prove_global(surfaces,a,b):
    """Use the true source vertices as supports, or check every pair not separated by them."""
    d = sub(b,a)
    provided = dot(d,d)
    triangles = tuple(tuple(selected(mesh,i) for i in range(len(mesh[1]))) for mesh in surfaces)
    scores_a = [max(dot(d,p) for p in row) for row in triangles[0]]
    scores_b = [min(dot(d,p) for p in row) for row in triangles[1]]
    gap = min(scores_b)-max(scores_a)
    count = len(scores_a)*len(scores_b)
    tested = 0
    for tri_a,score_a in zip(triangles[0],scores_a,strict=True):
        for tri_b,score_b in zip(triangles[1],scores_b,strict=True):
            if score_b-score_a>=provided:
                continue
            tested += 1
            require(exact_triangle_distance_squared(tri_a,tri_b)>=provided,
                    'different_current_triangle_pair_has_smaller_exact_distance')
    return {'exact_distance_squared_m2':str(provided),'distance_m':sqrt(provided),
            'method':'global_rational_support_planes' if tested==0 else 'rational_support_and_exact_triangle_features',
            'true_vertex_support_gap':str(gap),'triangle_pairs':count,'pairs_proven_by_support':count-tested,
            'exact_triangle_feature_pairs':tested}


def verify_registered(label, indices, points, proof):
    recipe = REGISTERED_EXACT.get(label)
    if recipe is None:
        return
    require(indices==recipe['indices'],'original_exact_witness_winner_changed/'+label)
    if 'squared' in recipe:
        require(proof['exact_distance_squared_m2']==recipe['squared']
                and [list(map(str,v)) for v in points]==recipe['points_m'],
                'original_exact_winner_world_points_changed/'+label)
    else:
        require(abs(proof['distance_m']-.21368990032710758)<1e-12,
                'actual_tree_holdout_distance_no_longer_matches_its_closed_reference')
