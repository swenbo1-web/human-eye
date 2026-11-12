"""Independent Fraction certificates for public points on bound raw triangles.

Callers must bind raw evaluated input first. No production geometry code is
imported. Position tolerance and measured-distance tolerance remain separate.
"""

from fractions import Fraction as F
import math


def point(values):
    if type(values) not in (list,tuple) or len(values)!=3 or not all(type(x) in (int,float) and math.isfinite(x) for x in values):
        raise ValueError('finite_three_coordinate_point_required')
    return tuple(F(value) for value in values)


def sub(a,b):
    return tuple(x-y for x,y in zip(a,b))


def dot(a,b):
    return sum(x*y for x,y in zip(a,b))


def encoded(value):
    return [value.numerator,value.denominator]


def nearest_on_triangle(p,vertices):
    a,b,c = vertices
    ab,ac,ap = sub(b,a),sub(c,a),sub(p,a)
    aa,bb,cc = dot(ab,ab),dot(ab,ac),dot(ac,ac)
    determinant = aa*cc-bb*bb
    proposals = []
    if determinant>0:
        v = (dot(ap,ab)*cc-dot(ap,ac)*bb)/determinant
        w = (dot(ap,ac)*aa-dot(ap,ab)*bb)/determinant
        if min(1-v-w,v,w)>=0:
            proposals.append((1-v-w,v,w))
    for i,j in ((0,1),(1,2),(2,0)):
        edge = sub(vertices[j],vertices[i])
        squared = dot(edge,edge)
        t = max(F(0),min(F(1),dot(sub(p,vertices[i]),edge)/squared)) if squared else F(0)
        weights = [F(0),F(0),F(0)]
        weights[i],weights[j] = 1-t,t
        proposals.append(tuple(weights))
    result = []
    for weights in proposals:
        q = tuple(sum(weights[j]*vertices[j][axis] for j in range(3)) for axis in range(3))
        delta = sub(p,q)
        result.append((dot(delta,delta),weights,q))
    return min(result,key=lambda item:item[0])


def certify_point(public_point,raw,*,tolerance_m=1e-9):
    p = point(public_point)
    tolerance = F(tolerance_m)
    if tolerance<0:
        raise ValueError('negative_position_tolerance')
    vertices = [point(values) for values in raw['vertices_world']]
    best = None
    for index,triangle in enumerate(raw['triangles']):
        if len(triangle)!=3 or any(type(i) is not int or not 0<=i<len(vertices) for i in triangle):
            raise ValueError('invalid_source_triangle')
        squared,weights,q = nearest_on_triangle(p,[vertices[i] for i in triangle])
        candidate = (squared,index,weights,q)
        if best is None or squared<best[0]:
            best = candidate
        if squared<=tolerance*tolerance:
            break
    if best is None:
        raise ValueError('nonempty_actual_triangles_required')
    squared,index,weights,q = best
    return {'passed':squared<=tolerance*tolerance,'triangle':index,
        'actual_triangle_vertex_indices':list(raw['triangles'][index]),
        'barycentric':[encoded(value) for value in weights],
        'exact_surface_point_world_m':[encoded(value) for value in q],
        'squared_position_error_m2':encoded(squared),'position_tolerance_m':tolerance_m,
        'method':'exact_binary64_rational_point_projection_or_segment_projection_on_actual_triangle'}


def certify_pair(point_a,point_b,distance_m,left_raw,right_raw,*,position_tolerance_m=1e-9,distance_tolerance_m=1e-6):
    a,b = point(point_a),point(point_b)
    if type(distance_m) not in (int,float) or not math.isfinite(distance_m) or distance_m<0:
        raise ValueError('finite_nonnegative_measured_distance_required')
    first = certify_point(point_a,left_raw,tolerance_m=position_tolerance_m)
    second = certify_point(point_b,right_raw,tolerance_m=position_tolerance_m)
    squared = dot(sub(b,a),sub(b,a))
    distance,tolerance = F(distance_m),F(distance_tolerance_m)
    if tolerance<0:
        raise ValueError('negative_distance_tolerance')
    within = max(F(0),distance-tolerance)**2<=squared<=(distance+tolerance)**2
    return {'passed':first['passed'] and second['passed'] and within,
        'point_a':first,'point_b':second,'public_pair_squared_distance_m2':encoded(squared),
        'public_pair_distance_matches_measured_within_tolerance':within,
        'measured_distance_m':distance_m,'distance_tolerance_m':distance_tolerance_m,
        'scope':'surface membership and pair-distance consistency, without independently proving global minimality'}
