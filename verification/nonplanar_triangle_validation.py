"""Independent exact index/partition and pruning-certificate checker.

It neither builds nor traverses using the producer's projection intervals.
"""
from fractions import Fraction as Q
import math


def reserved_for(count):
    height=0;capacity=8
    while capacity<count:height+=1;capacity*=2
    slots=2**(height+1)-1
    return count*(height+3)+slots,slots


def validate_index(index,obj,right,up,binding,coordinates,reservations):
    assert index['schema']=='projected-triangle-bvh-v1' and index['leaf_size']==8
    assert index['object_id']==obj['object_id'] and index['source_binding']==binding
    assert index['right']==right and index['up']==up
    count=len(obj['faces']);assert index['face_count']==count and index['vertex_count']==len(obj['world_vertices'])
    units,slots=reserved_for(count)
    assert index['build_units_reserved']==units and index['node_slots_reserved']==slots
    reservation=index['reservation_index'];assert type(reservation) is int and 0<=reservation<len(reservations)
    assert reservations[reservation]=={'object_id':obj['object_id'],'face_count':count,'right':right,'up':up,
        'build_units_reserved':units,'node_slots_reserved':slots}
    nodes=index['nodes'];assert type(nodes) is list and 1<=len(nodes)<=slots
    seen=set();faces=[];pending=[0]
    while pending:
        number=pending.pop();assert type(number) is int and 0<=number<len(nodes) and number not in seen
        seen.add(number);node=nodes[number]
        assert type(node) is list and len(node)==7
        assert all(type(v) in (int,float) and math.isfinite(v) for v in node[:4])
        assert node[0]<=node[2] and node[1]<=node[3]
        left,right_id=node[4:6];assert type(left) is int and type(right_id) is int
        if left==-1:
            assert right_id==-1 and type(node[6]) is list and 1<=len(node[6])<=8
            assert node[6]==sorted(set(node[6]))
            for face_id in node[6]:
                assert type(face_id) is int and 0<=face_id<count
                faces.append(face_id)
                face=obj['faces'][face_id]
                for axis in (0,1):
                    low=min(coordinates[axis][v] for v in face);high=max(coordinates[axis][v] for v in face)
                    pad=Q('4e-12')*(high-low)
                    assert Q(node[axis])<=low-pad and Q(node[axis+2])>=high+pad
        else:
            assert node[6]==[] and 0<=left<len(nodes) and 0<=right_id<len(nodes) and left!=right_id
            for child_id in (left,right_id):
                child=nodes[child_id]
                assert len(child)==7
                assert all(node[k]<=child[k] and node[k+2]>=child[k+2] for k in (0,1))
                pending.append(child_id)
    assert len(seen)==len(nodes) and len(faces)==count and sorted(faces)==list(range(count))


def validate_query(index,query,name,right,up):
    trace=query['traces'][name];claimed=query['filters'][name]
    assert type(trace) is list and type(claimed) is list and claimed==sorted(set(claimed))
    point=query['point'];assert len(point)==3
    projected=[sum((Q(v)*Q(a) for v,a in zip(point,axis)),Q(0)) for axis in (right,up)]
    records={}
    for number,active in trace:
        assert type(number) is int and 0<=number<len(index['nodes']) and number not in records
        assert type(active) is bool;records[number]=active
    assert 0 in records or not query['complete']
    covered=set();pending=[0];visited=set()
    while pending:
        number=pending.pop()
        if number not in records:
            assert query['complete'] is False
            continue
        visited.add(number);node=index['nodes'][number];active=records[number]
        if not active:
            assert any(projected[k]<Q(node[k]) or projected[k]>Q(node[k+2]) for k in (0,1))
        elif node[4]==-1:covered.update(node[6])
        else:pending.extend((node[4],node[5]))
    assert visited==set(records) and sorted(covered)==claimed
    return 2*len(trace)


def validate_view(acceleration,native,right,up,binding,coordinates,reservations,observed):
    if acceleration is None:return 0
    assert acceleration['schema']=='triangle-index-view-v1'
    assert type(acceleration['complete']) is bool
    by_id={o['object_id']:o for o in native['objects']}
    indices=acceleration['indices'];assert set(indices)<=set(by_id)
    for name,index in indices.items():
        validate_index(index,by_id[name],right,up,binding,coordinates[name],reservations)
        assert index['reservation_index'] not in observed
        observed.add(index['reservation_index'])
    work=0
    for query in acceleration['queries']:
        assert type(query['complete']) is bool
        expected=set(query['possible_objects'])&set(indices)
        assert set(query['filters'])==set(query['traces'])
        assert set(query['traces'])<=expected
        if query['complete']:assert set(query['traces'])==expected
        else:assert acceleration['complete'] is False
        for name in query['traces']:work+=validate_query(indices[name],query,name,right,up)
    return work
