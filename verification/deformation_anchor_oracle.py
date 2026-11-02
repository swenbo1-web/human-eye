"""Independent QA of public endpoint anchors, catalog pins and task identity.

No production anchor catalog, selector or geometry function is imported. Decimal
affine arithmetic and NumPy matrix endpoints check the frozen native numbers.
"""
import copy,hashlib,json,math
from decimal import Decimal,localcontext

STABLE_KEYS={'schema','source_ref','operator_pins','coordinate_model','graph','anchors','bounds','completeness','scope'}
PIN_KEYS=('scene_sha256','profile_sha256','worker_sha256','module_sha256','math_sha256','binary_sha256','runtime_source_sha256')


def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def digest(value):return hashlib.sha256(encoded(value)).hexdigest()
def stable_object(name):return 'blender:'+digest(['',name])
def anchor_id(rig_name,bone,endpoint):return 'bone-anchor:'+digest([stable_object(rig_name),bone,endpoint])


def affine_decimal(matrix,point,unit):
    """5000 digits exactly cover three products of finite binary64 scalars."""
    d=lambda x:Decimal(x) if type(x) is int else Decimal.from_float(x)
    with localcontext() as context:
        context.prec=5000
        return [d(unit)*(sum((d(matrix[k][j])*d(point[j]) for j in range(3)),d(matrix[k][3]))) for k in range(3)]


def numeric_projection(values):
    if any(x.copy_abs()>Decimal(1_000_000_000) for x in values):return None,None,'outside_region_coordinate_domain'
    nearest=[float(x) for x in values]
    if any(x and y==0 for x,y in zip(values,nearest)):return None,None,'coordinate_underflow'
    lower=[];upper=[]
    for exact,value in zip(values,nearest):
        binary=Decimal.from_float(value)
        lower.append(value if binary<=exact else math.nextafter(value,-math.inf))
        upper.append(value if binary>=exact else math.nextafter(value,math.inf))
    return nearest,[lower,upper],None


def expected_geometry(packet):
    import numpy as np
    inputs=packet['inputs'];rig=inputs['rig'];evaluated=packet['evaluated'];unit=inputs['unit_scale_m'];matrix=evaluated['rig_matrix_world']
    native_bones={b['name']:b for b in evaluated['bones']};graph=[];anchors=[];crosscheck=0.
    for bone in sorted(rig['bones'],key=lambda b:b['name']):
        head=anchor_id(rig['name'],bone['name'],'head');tail=anchor_id(rig['name'],bone['name'],'tail')
        graph.append(dict(name=bone['name'],parent=bone['parent'],connected=bone['connected'],use_deform=bone['use_deform'],head_anchor_id=head,tail_anchor_id=tail))
        for endpoint,identity in [('head',head),('tail',tail)]:
            native_bone=native_bones[bone['name']];raw=native_bone['pose_'+endpoint];position,interval,reason=numeric_projection(affine_decimal(matrix,raw,unit))
            local=np.array([0.,0.,0.,1.]) if endpoint=='head' else np.array([0.,bone['length'],0.,1.])
            replay=(np.array(matrix)@np.array(native_bone['pose_matrix'])@local)[:3]*unit
            native=(np.array(matrix)@np.r_[raw,1.])[:3]*unit
            crosscheck=max(crosscheck,float(np.max(np.abs(replay-native))))
            if position is not None:np.testing.assert_allclose(native,position,atol=1e-10,rtol=1e-13)
            anchors.append(dict(anchor_id=identity,bone_name=bone['name'],endpoint=endpoint,position_world_m=position,position_interval_world_m=interval,reason=reason))
    mesh=inputs['mesh'];vertices=evaluated['vertices'];used=sorted({i for tri in mesh['triangles'] for i in tri})
    world=[affine_decimal(evaluated['mesh_matrix_world'],vertices[i],unit) for i in used]
    lo=[min(p[k] for p in world) for k in range(3)];hi=[max(p[k] for p in world) for k in range(3)]
    _,lower_interval,low_reason=numeric_projection(lo);_,upper_interval,high_reason=numeric_projection(hi)
    bounds=None if low_reason or high_reason else [lower_interval[0],upper_interval[1]]
    return dict(graph=graph,anchors=anchors,bounds_world_m=bounds,vertices_total=len(vertices),surface_vertices_total=len(used),
        loose_vertices_excluded=len(vertices)-len(used),triangles_total=len(mesh['triangles']),maximum_pose_endpoint_crosscheck=crosscheck)


def verify_catalog(catalog,packet):
    expected=expected_geometry(packet);rig=packet['inputs']['rig'];mesh=packet['inputs']['mesh'];i=packet['identity']
    assert catalog['schema']=='surface-deformation-anchor-catalog-v1'
    assert catalog['source_ref']==dict(scene_sha256=i['scene_sha256'],rig_object_id=stable_object(rig['name']),mesh_object_id=stable_object(mesh['name']),frame=packet['inputs']['frame'])
    assert catalog['operator_pins']=={key:i[key] for key in PIN_KEYS}
    assert catalog['catalog_sha256']==digest({key:catalog[key] for key in STABLE_KEYS})
    assert catalog['source_sha256']==packet['source_sha256']
    assert catalog['live_capture']=={key:(packet['source_sha256'] if key=='source_sha256' else i[key]) for key in ('source_sha256','document_epoch','process_id')}
    assert catalog['graph']==expected['graph'] and len(catalog['anchors'])==len(expected['anchors'])
    for got,wanted in zip(catalog['anchors'],expected['anchors']):
        for key in wanted:assert got[key]==wanted[key],(key,got,wanted)
        assert got['state']==('available' if wanted['reason'] is None else 'unavailable')
    assert catalog['coordinate_model']==dict(coordinate_space='current_world_m',position_model='nearest_binary64_from_exact_binary_affine',
        interval_model='outward_binary64_interval_for_published_numeric_inputs_not_physical_error')
    assert catalog['scope']==dict(anchor_semantics='native_evaluated_bone_endpoints_only',bounds_semantics='referenced_current_triangle_hulls_not_volume',
        not_inferred=['anatomical_semantics','surface_location','damage','visibility','repair','editing_authority'])
    counts=catalog['completeness'];assert counts['bones_total']==len(rig['bones']) and counts['anchors_total']==2*len(rig['bones'])
    assert counts['anchors_available']==sum(x['reason'] is None for x in expected['anchors']) and counts['anchors_unavailable']==sum(x['reason'] is not None for x in expected['anchors'])
    assert counts['anchors_omitted']==0 and counts['graph_complete'] is True and counts['anchors_complete'] is True
    b=catalog['bounds'];assert b['kind']=='referenced_current_triangle_hull_aabb' and b['bounds_world_m']==expected['bounds_world_m']
    for key in ('vertices_total','surface_vertices_total','loose_vertices_excluded','triangles_total'):assert b[key]==expected[key]
    assert catalog['execution_authority'] is False and catalog['geometry_setters']==0 and catalog['original_file_saved'] is False
    return expected


def resolve_task(catalog,target):
    """Task relation fixes identity independently of matching point positions."""
    graph=catalog['graph']
    if target=='elbow_semantics_without_mapping':return dict(state='unsupported_semantics',anchor_id=None)
    if target.startswith('unique_'):
        endpoint='head' if target.endswith('_head') else 'tail'
        want_nonroot=target.startswith('unique_nonroot_');matches=[b for b in graph if (b['parent'] is not None)==want_nonroot]
    elif target.startswith('named_'):
        name,endpoint=target[len('named_'):].rsplit('_',1);matches=[b for b in graph if b['name']==name]
    else:raise AssertionError('unknown registered task relation')
    if not matches:return dict(state='not_found',anchor_id=None)
    if len(matches)!=1:return dict(state='ambiguous',anchor_id=None)
    return dict(state='selected',anchor_id=matches[0][endpoint+'_anchor_id'])


def selection(catalog,identity,half):
    return dict(schema='surface-deformation-anchor-selection-v1',source_ref=copy.deepcopy(catalog['source_ref']),catalog_sha256=catalog['catalog_sha256'],
        anchor_id=identity,half_extents_m=copy.deepcopy(half))


def expected_box(anchor,half):
    from fractions import Fraction as F
    out=[]
    for sign in (-1,1):
        values=[]
        for coordinate,size in zip(anchor['position_world_m'],half):
            exact=F(coordinate)+sign*F(size);binary=float(exact)
            if (sign==-1 and F(binary)>exact) or (sign==1 and F(binary)<exact):binary=math.nextafter(binary,-math.inf if sign==-1 else math.inf)
            values.append(binary)
        out.append(values)
    return dict(kind='closed_aabb',coordinate_space='current_world_m',bounds=out)
