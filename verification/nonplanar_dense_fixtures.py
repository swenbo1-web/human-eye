"""Same-object density gradients; retain the original analytic aperture."""
import copy
import math

from verification.nonplanar_local_fixtures import local_cases,local_source
from verification.nonplanar_patch_fixtures import cases,transform


def dense_case(n,kind='remote'):
    return dict(cases()[1],id='same_object_'+kind+'_'+str(n),grid_n=n,
        grid_kind=kind,want=kind=='remote',pairs=12 if kind=='remote' else 0)


def dense_source(case):
    native,edges=local_source(case)
    n=case.get('grid_n')
    if n is None:return native,edges
    obj=native['objects'][0];begin=len(obj['world_vertices'])
    for i in range(n+1):
        for j in range(n+1):
            x,y=-1+2*i/n,-1+2*j/n
            obj['world_vertices'].append(transform([100.,x,y] if case['grid_kind']=='remote' else [x,y,.2]))
    for i in range(n):
        for j in range(n):
            a=begin+i*(n+1)+j;b=a+n+1
            obj['faces'] += [[a,b,b+1],[a,b+1,a+1]]
    return native,edges


def dense_cases():
    return local_cases()+[dense_case(n) for n in (3,4,5,6,9,10,12,16,24,30)]+[
        dense_case(n,'blocker') for n in (12,30)]


def local_limit_source(refinements=61):
    """A thin legal ring; 61 subdivisions visit 128 faces, 62 exceeds it.

    Refine the largest-area bottom triangle without moving its original edges.
    This valid complete search deliberately does not earn a detail image: the
    surface is too thin for the offset samples. It still exercises full replay.
    """
    native, edges = dense_source(cases()[0])
    obj = native['objects'][0]
    obj['world_vertices'] = [transform(v) for v in [
        [-.0201,-.1001,0.],[.0201,-.1001,0.],[.0201,.1001,0.],[-.0201,.1001,0.],
        [-.02,-.1,0.],[.02,-.1,0.],[.02,.1,0.],[-.02,.1,0.]]]
    pool = [0, 1]
    def area(index):
        a, b, c = [obj['world_vertices'][j] for j in obj['faces'][index]]
        u = [b[k]-a[k] for k in range(3)]; v = [c[k]-a[k] for k in range(3)]
        return math.hypot(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
    for _ in range(refinements):
        index = max(pool, key=area)
        a, b, c = obj['faces'][index]; point = len(obj['world_vertices'])
        obj['world_vertices'].append([sum(obj['world_vertices'][j][k] for j in (a,b,c))/3 for k in range(3)])
        obj['faces'][index] = [a,b,point]; first = len(obj['faces'])
        obj['faces'] += [[b,c,point],[c,a,point]]; pool += [first,first+1]
    return native, edges
