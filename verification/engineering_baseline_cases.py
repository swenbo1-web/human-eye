"""Frozen controlled assets and hand-authored source-edge truths, not HE output."""
import copy
import hashlib
import json
from verification.structure_task_representatives import cases as shapes
from verification.nonplanar_patch_fixtures import cases as apertures, source
from verification.nonplanar_dense_fixtures import dense_case, dense_source, local_limit_source


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def loop(vertices):
    return sorted(sorted((vertices[i-1],vertices[i])) for i in range(len(vertices)))


def cases():
    result=[]
    torus=shapes()[0]
    for opened in (False,True):
        obj=dict(object_id='target',world_vertices=torus['vertices'],faces=torus['polygons'][2:] if opened else torus['polygons'])
        result.append(dict(id='opened_torus' if opened else 'closed_torus',objects=[obj],
            expected=dict(boundary_edges=[loop([0,8,9,1])] if opened else [],loose_edges=[],isolated_vertices=[]),
            pixel_truth=None))
    for index,name in ((1,'nonplanar_clear'),(2,'center_blocked'),(3,'feature_blocked')):
        native,_=source(apertures()[index])
        result.append(dict(id=name,objects=native['objects'],
            expected=dict(boundary_edges=[loop([0,1,2,3]),loop([4,5,6,7])],loose_edges=[],isolated_vertices=[]),
            pixel_truth=copy.deepcopy(apertures()[index])))
    native,_=dense_source(dense_case(30))
    begin=8;n=30
    perimeter=([begin+j for j in range(n+1)]+[begin+i*(n+1)+n for i in range(1,n+1)]+
        [begin+n*(n+1)+j for j in range(n-1,-1,-1)]+[begin+i*(n+1) for i in range(n-1,0,-1)])
    result.append(dict(id='dense1808',objects=native['objects'],
        expected=dict(boundary_edges=[loop([0,1,2,3]),loop([4,5,6,7]),loop(perimeter)],loose_edges=[],isolated_vertices=[]),
        pixel_truth=copy.deepcopy(apertures()[1])))
    native,_=local_limit_source()
    result.append(dict(id='local128',objects=native['objects'],
        expected=dict(boundary_edges=[loop([0,1,2,3]),loop([4,5,6,7])],loose_edges=[],isolated_vertices=[]),pixel_truth=None))
    result.append(dict(id='wire_and_isolated',objects=[dict(object_id='target',
        world_vertices=[[0.,0.,0.],[1.,0.,0.],[2.,0.,0.]],faces=[],edges=[[0,1]])],
        expected=dict(boundary_edges=[],loose_edges=[[[0,1]]],isolated_vertices=[[2]]),pixel_truth=None))
    for case in result:
        case['task']=dict(object_id='target',anchor_world_bu=[0.,0.,0.],
            categories=['boundary_edges','loose_edges','isolated_vertices'],include_images=True)
        case['asset_task_sha256']=digest(dict(objects=case['objects'],task=case['task']))
    return result


def validate_facts(case, value):
    """Score complete source members, not totals or producer assertions."""
    if type(value) is not dict or value.get('status')!='observed' or value.get('damage')!='not_inferred':
        raise ValueError('baseline_did_not_deliver_facts')
    found=value.get('facts')
    if type(found) is not dict or set(found)!=set(case['expected']):raise ValueError('category_coverage')
    limit=len(next(o for o in case['objects'] if o['object_id']==case['task']['object_id'])['world_vertices'])
    for name,expected in case['expected'].items():
        actual=found[name]
        if type(actual) is not list:raise ValueError('missing_is_not_zero')
        for group in actual:
            if type(group) is not list or not group:raise ValueError('invalid_group')
            if name!='isolated_vertices' and any(type(edge) is not list or len(edge)!=2 or edge[0]==edge[1] for edge in group):
                raise ValueError('invalid_edge')
            members=group if name=='isolated_vertices' else [v for edge in group for v in edge]
            if any(type(v) is not int or not 0<=v<limit for v in members):raise ValueError('invalid_index')
        if name!='isolated_vertices':
            normalize=lambda groups: sorted(sorted(tuple(sorted(edge)) for edge in group) for group in groups)
        else:normalize=lambda groups:sorted(sorted(group) for group in groups)
        if normalize(actual)!=normalize(expected):raise ValueError('source_members_or_components:'+name)
    return True
