"""Independent consumer for the explicit dense verification capability."""
import json,math
from fractions import Fraction
from verification.nonplanar_local_validation import ExactLocalIndex,binding as independent_binding
from verification.nonplanar_triangle_validation import validate_view,reserved_for

def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]

def dot(a,b):return sum(x*y for x,y in zip(a,b))

def subtract(a,b):return [x-y for x,y in zip(a,b)]

def ray(native,point,direction,allowed_objects=None,*,with_depth=False,allowed_faces=None):
    """3D Moller line intersection; no producer projection or depth routine."""
    hits=[]
    for obj in native['objects']:
        if allowed_objects is not None and obj['object_id'] not in allowed_objects:continue
        triangles=(enumerate(obj['faces']) if allowed_faces is None or obj['object_id'] not in allowed_faces
            else ((index,obj['faces'][index]) for index in allowed_faces[obj['object_id']]))
        for index,face in triangles:
            a,b,c=[obj['world_vertices'][i] for i in face];e1=subtract(b,a);e2=subtract(c,a)
            h=cross(direction,e2);det=dot(e1,h)
            if abs(det)<=1e-12*max(math.hypot(*e1)*math.hypot(*e2),1e-300):continue
            s=subtract(point,a);u=dot(s,h)/det;q=cross(s,e1);v=dot(direction,q)/det
            if min(u,v,1-u-v)<-1e-12:continue
            hits.append((dot(e2,q)/det,obj['object_id'],index))
    if not hits:return []
    depth=max(h[0] for h in hits);eps=1e-9*max(1.,abs(depth))
    return [(obj,index,z) if with_depth else (obj,index) for z,obj,index in hits if depth-z<=eps]

def replay(result,native,object_id,edges):
    """Rebuild each proposed view's offsets and independently replay all rays."""
    assert result['selected'] is None or result['selected'] in result['candidates']
    vertices=next(o['world_vertices'] for o in native['objects'] if o['object_id']==object_id)
    faces=next(o['faces'] for o in native['objects'] if o['object_id']==object_id);reserved=0
    assert result['native_binding_sha256']==independent_binding(native,object_id,edges)
    local=ExactLocalIndex(next(o for o in native['objects'] if o['object_id']==object_id),result['max_locality_work'],result['locality_policy'])
    features=local.validate_features(edges,result['sampling_features'])
    index_node_work=0;index_bytes=0;observed_indices=set()
    reservations=result.get('index_build_reservations',[])
    for row in result['candidates']:
        acceleration=row.get('acceleration')
        if not row['samples'] and acceleration is None:continue
        def exact_dot(v,axis):return sum((Fraction(x)*Fraction(y) for x,y in zip(v,axis)),Fraction(0))
        if acceleration is not None:
            bounds={};coordinates={}
            for obj in native['objects']:
                projected=[[exact_dot(v,axis) for v in obj['world_vertices']] for axis in (row['right'],row['up'])]
                coordinates[obj['object_id']]=projected
                bounds[obj['object_id']]=[[min(values),max(values)] for values in projected]
            index_node_work+=validate_view(acceleration,native,row['right'],row['up'],result['native_binding_sha256'],
                coordinates,reservations,observed_indices)
            index_bytes+=sum(len(json.dumps(index,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode())
                for index in acceleration['indices'].values())
            index_bytes+=len(json.dumps(acceleration['queries'],separators=(',',':'),ensure_ascii=True,allow_nan=False).encode())
            if not acceleration['complete']:assert not row['samples'] and not result['search_complete']
        if not row['samples']:continue
        proofs=[local.reconstruct(edge,4*row['span']/128) for edge in edges]
        assert len(row['local_surfaces'])==len(proofs)
        for claimed,rebuilt_proof in zip(row['local_surfaces'],proofs):
            # The exact predicate uses rational squared lengths. Its exported
            # sqrt spelling may differ from the producer's hypot by one ULP.
            expected_limit=rebuilt_proof['max_plane_deviation']
            assert abs(claimed['max_plane_deviation']-expected_limit)<=2*math.ulp(expected_limit)
            assert {k:v for k,v in claimed.items() if k!='max_plane_deviation'}=={
                k:v for k,v in rebuilt_proof.items() if k!='max_plane_deviation'}
        local.reserve(row['tests_reserved'])
        local_by_edge={tuple(sorted(proof['edge'])):proof for proof in proofs}
        if acceleration is None:
            # Keep the original temporary lifetime: do not retain every
            # vertex projection through local proof construction on a fast path.
            bounds={}
            for obj in native['objects']:
                coordinates=[[exact_dot(v,axis) for v in obj['world_vertices']] for axis in (row['right'],row['up'])]
                bounds[obj['object_id']]=[[min(values),max(values)] for values in coordinates]
        sample_index=0;producer_reserved=0
        rebuilt=[];visible=[]
        for feature in features:
            a,b=feature['edge']
            delta=subtract(vertices[b],vertices[a]);x=dot(delta,row['right']);y=dot(delta,row['up']);length=math.sqrt(x*x+y*y)
            assert length>row['span']/64
            off=[row['span']/128/length*(-y*row['right'][k]+x*row['up'][k]) for k in range(3)]
            for num in (1,2,3):
                mid=[(vertices[a][k]*(4-num)+vertices[b][k]*num)/4 for k in range(3)]
                pair=[[mid[k]+sign*off[k] for k in range(3)] for sign in (-1,1)]
                claim=row['samples'][sample_index];sample_index+=1
                native_edge=local.sample_source(feature,num)
                assert claim['edge']==[a,b] and claim['source_edge']==native_edge
                hits=[]
                for side,(point,original_point,ids) in enumerate(zip(pair,claim['pair'],claim['possible_objects'])):
                    # Test the producer's exact binary64 ray origin against an independently
                    # reconstructed exact interval. Rebuilt sample proximity is checked below.
                    q=[exact_dot(original_point,axis) for axis in (row['right'],row['up'])]
                    possible={name for name,box in bounds.items() if all(box[k][0]<=q[k]<=box[k][1] for k in (0,1))}
                    assert len(ids)==len(set(ids)) and set(ids)<=set(bounds) and possible<=set(ids)
                    filters=None
                    if acceleration is not None:
                        ref=claim['index_queries'][side];query=acceleration['queries'][ref]
                        assert query['complete'] and query['point']==original_point and query['possible_objects']==ids
                        filters=query['filters']
                    producer_reserved+=sum(len(filters[o['object_id']]) if filters is not None and o['object_id'] in filters
                        else len(o['faces']) for o in native['objects'] if o['object_id'] in ids)
                    hits.append(ray(native,point,row['direction'],ids,with_depth=True,allowed_faces=filters))
                h0,h1=hits
                proof=local_by_edge[tuple(sorted(native_edge))]
                value=(not h0 and local.validate_hit(proof,pair[1],row['direction'],h1,object_id)
                    or not h1 and local.validate_hit(proof,pair[0],row['direction'],h0,object_id))
                rebuilt.append(pair);visible.append(bool(value))
        assert len(rebuilt)==len(row['samples'])
        for sample,pair,v in zip(row['samples'],rebuilt,visible):
            assert sample['visible']==v
            assert all(abs(x-y)<=row['span']*1e-10 for a,b in zip(sample['pair'],pair) for x,y in zip(a,b))
        assert sum(visible)==row['visible_count']
        assert row['tests_reserved']==2*producer_reserved
        reserved+=row['tests_reserved']
    assert reserved==result['combined_triangle_tests_reserved']<=8192
    assert local.work==result['locality_work_reserved']<=32768
    if 'index_build_reservations' in result:
        by_id={o['object_id']:o for o in native['objects']};units=slots=0
        for entry in reservations:
            assert entry['face_count']==len(by_id[entry['object_id']]['faces'])
            u,n=reserved_for(entry['face_count']);assert entry['build_units_reserved']==u and entry['node_slots_reserved']==n
            units+=u;slots+=n
        assert units==result['index_build_units_reserved']<=65536
        assert slots==result['index_node_slots_reserved']<=4096
        assert index_node_work==result['index_node_tests_reserved']<=result['combined_box_tests_reserved']
        assert index_bytes==result['index_packet_bytes']<=512*1024
    assert result['combined_box_tests_reserved']<=32768 and result['combined_projection_ops_reserved']<=65536
    assert len(result['candidates'])<=4 and result['maximum_images']==2 and result['execution_authority'] is False
    return reserved
