"""Same-object density gradients; retain the original analytic aperture."""
import copy

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
