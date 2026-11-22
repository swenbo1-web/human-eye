# Only called on the three disjoint mesh pairs in the diagnostic fixture.
# Enumerate all vertex-face and edge-edge features of each pair of triangles.
import itertools
import json
import math
import numpy as np


def projection_inside(point, triangle):
    a,b,c = triangle
    u,v = b-a,c-a
    normal = np.cross(u,v)
    norm_sq = float(normal @ normal)
    if not norm_sq:
        return None
    foot = point - normal * float((point-a) @ normal) / norm_sq
    w = foot-a
    uu,uv,vv = float(u@u),float(u@v),float(v@v)
    wu,wv = float(w@u),float(w@v)
    s,t = (wu*vv-wv*uv)/norm_sq, (wv*uu-wu*uv)/norm_sq
    return foot if min(s,t,1-s-t)>=-1e-10 else None


def closest_on_edge(point,a,b):
    edge = b-a
    squared = float(edge@edge)
    if squared==0:
        return a
    t = float((point-a)@edge)/squared
    return a+min(1,max(0,t))*edge


def edges(triangle):
    a,b,c = triangle
    return ((a,b),(b,c),(c,a))


def closest_pair(left,right):
    best = (math.inf,None,None)

    def keep(a,b):
        nonlocal best
        squared = float((b-a)@(b-a))
        if squared<best[0]-1e-13:
            best = squared,a,b

    for tri_a,tri_b in itertools.product(left,right):
        for point in tri_a:
            foot = projection_inside(point,tri_b)
            if foot is not None:
                keep(point,foot)
        for point in tri_b:
            foot = projection_inside(point,tri_a)
            if foot is not None:
                keep(foot,point)
        for (a,b),(c,d) in itertools.product(edges(tri_a),edges(tri_b)):
            keep(a,closest_on_edge(a,c,d))
            keep(b,closest_on_edge(b,c,d))
            keep(closest_on_edge(c,a,b),c)
            keep(closest_on_edge(d,a,b),d)
            u,v,w=b-a,d-c,a-c
            uu,uv,vv,uw,vw=(float(x) for x in (u@u,u@v,v@v,u@w,v@w))
            determinant=uu*vv-uv*uv
            if determinant>0:
                s,t=(uv*vw-vv*uw)/determinant,(uu*vw-uv*uw)/determinant
                if 0<=s<=1 and 0<=t<=1:
                    keep(a+s*u,c+t*v)
    return best


def triangles(mesh,faces):
    points=np.asarray(mesh['vertices'],dtype=float)
    return {int(index):points[mesh['faces'][index]] for index in faces}


def memberships(point, faces):
    found=[]
    for index,triangle in faces.items():
        foot = projection_inside(point,triangle)
        if foot is not None and np.linalg.norm(point-foot)<1e-8:
            found.append(index)
    return found


def evaluate(left,right):
    squared,a,b=closest_pair(list(left.values()),list(right.values()))
    distance=math.sqrt(squared)
    return {'distance_m':distance, 'direction_a_to_b':((b-a)/distance).tolist(),
            'a':a.tolist(),'b':b.tolist(),
            'source_triangle_indices':{'a':memberships(a,left),'b':memberships(b,right)}}


measurements={}
for case in qualification_cases:
    first,second=(qualification_raw['meshes'][case[field]] for field in ('target','reference'))
    left=triangles(first,range(len(first['faces'])))
    right=triangles(second,range(len(second['faces'])))
    selected={index:left[index] for index in case['faces']}
    measurements[str(case['id'])]={'selected':evaluate(selected,right),'whole':evaluate(left,right)}
print(json.dumps({'meshes':qualification_raw['meshes'],'frame':qualification_raw['frame'],
                  'scale_length':qualification_raw['scale_length'],'measurements':measurements},
                 separators=(',', ':'),allow_nan=False))
