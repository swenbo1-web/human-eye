"""Public native endpoint anchors over a completely validated small source.

The catalog is a bounded display/selection product, never source admission,
anatomical inference or physical measurement-error certification. A fresh source
must recompute the stable catalog before accepting a file-scoped selection.
"""
import copy,math
from fractions import Fraction as Q
from . import rig_pose as r

MAX_BITS=16384
PIN_FIELDS=('scene_sha256','profile_sha256','worker_sha256','module_sha256','math_sha256','binary_sha256','runtime_source_sha256')
STABLE_FIELDS={'schema','source_ref','operator_pins','coordinate_model','graph','anchors','bounds','completeness','scope'}
COORDINATE_MODEL=dict(coordinate_space='current_world_m',position_model='nearest_binary64_from_exact_binary_affine',
    interval_model='outward_binary64_interval_for_published_numeric_inputs_not_physical_error')
SCOPE=dict(anchor_semantics='native_evaluated_bone_endpoints_only',bounds_semantics='referenced_current_triangle_hulls_not_volume',
    not_inferred=['anatomical_semantics','surface_location','damage','visibility','repair','editing_authority'])


def need(value,reason):r.require(value,'deformation_anchor_'+reason)
def finite(value,maximum=1e308):
    return type(value) is int and abs(value)<=maximum or type(value) is float and math.isfinite(value) and abs(value)<=maximum
def vector(value,maximum=1e308):return type(value) is list and len(value)==3 and all(finite(v,maximum) for v in value)
def limited(value):
    value=Q(value);need(value.numerator.bit_length()<=MAX_BITS and value.denominator.bit_length()<=MAX_BITS,'arithmetic_budget');return value
def budget(value,deadline_ns):
    need(len(r.encoded(value))<=r.MAX_BYTES,'report_byte_budget');r.check_time(deadline_ns);return value


def source_ref(proof):
    need(type(proof) is dict and r.hex_text(proof.get('source_sha256'),64),'proof_shape');s=proof.get('source')
    need(type(s) is dict and r.hex_text(s.get('scene_sha256'),64) and r.text(s.get('object_id'))
        and type(s.get('mesh_identity')) is dict and r.text(s['mesh_identity'].get('object_id')),'proof_shape')
    frame=s.get('frame');need(type(frame) is dict and set(frame)=={'number','subframe'} and type(frame['number']) is int
        and finite(frame['subframe'],1) and 0<=frame['subframe']<1,'proof_shape')
    need(r.hex_text(s.get('document_epoch'),32) and type(s.get('process_id')) is int and s['process_id']>0,'proof_shape')
    return dict(scene_sha256=s['scene_sha256'],rig_object_id=s['object_id'],mesh_object_id=s['mesh_identity']['object_id'],frame=copy.deepcopy(frame))


def matrix(value):
    need(type(value) is list and len(value)==4 and all(type(row) is list and len(row)==4 and all(finite(v,1e12) for v in row) for row in value)
        and value[3]==[0,0,0,1],'proof_shape')
    return [[limited(v) for v in row] for row in value]


def transformed(point,world,unit,deadline_ns):
    need(vector(point),'proof_shape');p=[limited(v) for v in point];out=[]
    for axis in range(3):
        r.check_time(deadline_ns);value=world[axis][3]
        for k in range(3):
            r.check_time(deadline_ns);value=limited(value+limited(world[axis][k]*p[k]))
        out.append(limited(value*unit))
    return out


def outward(value,direction):
    value=limited(value);rounded=float(value)
    need(math.isfinite(rounded),'arithmetic_budget')
    if direction<0 and Q(rounded)>value:rounded=math.nextafter(rounded,-math.inf)
    if direction>0 and Q(rounded)<value:rounded=math.nextafter(rounded,math.inf)
    return rounded


def publish(values):
    if any(abs(v)>1_000_000_000 for v in values):return None,None,'outside_region_coordinate_domain'
    rounded=[float(v) for v in values]
    if any(v and f==0 for v,f in zip(values,rounded)):return None,None,'coordinate_underflow'
    return rounded,[[outward(v,-1) for v in values],[outward(v,1) for v in values]],None


def catalog(proof,*,pins,deadline_ns):
    r.check_time(deadline_ns);ref=source_ref(proof)
    need(type(pins) is dict and set(pins)==set(PIN_FIELDS) and all(r.hex_text(pins[k],64) for k in PIN_FIELDS)
        and pins['scene_sha256']==ref['scene_sha256'],'pins_binding')
    current=proof.get('current');triangles=proof.get('triangles');bones=proof.get('bone_landmarks');unit=proof.get('unit')
    need(type(current) is list and 1<=len(current)<=256 and all(vector(p,10) for p in current)
        and type(triangles) is list and 1<=len(triangles)<=256 and finite(unit,1e6) and unit>0,'proof_shape')
    refs=set()
    for tri in triangles:
        r.check_time(deadline_ns);need(type(tri) is list and len(tri)==3 and all(type(i) is int and 0<=i<len(current) for i in tri)
            and len(set(tri))==3,'proof_shape');refs.update(tri)
    need(type(bones) is list and 1<=len(bones)<=16,'bone_graph');names={}
    for bone in bones:
        r.check_time(deadline_ns)
        need(type(bone) is dict and set(bone)=={'name','parent','connected','use_deform','head','tail'} and r.text(bone['name'])
            and bone['name'] not in names and (bone['parent'] is None or r.text(bone['parent'])) and type(bone['connected']) is bool
            and type(bone['use_deform']) is bool and vector(bone['head']) and vector(bone['tail']),'bone_graph');names[bone['name']]=bone
    for name in names:
        seen=set();node=name
        while node is not None:
            r.check_time(deadline_ns);need(node in names and node not in seen,'bone_graph');seen.add(node);node=names[node]['parent']
    world=matrix(proof.get('world'));rig_world=matrix(proof.get('rig_world'));unit=limited(unit);graph=[];anchors=[]
    for name,bone in sorted(names.items()):
        r.check_time(deadline_ns);ids={}
        for endpoint in ('head','tail'):
            r.check_time(deadline_ns);anchor_id='bone-anchor:'+r.digest([ref['rig_object_id'],name,endpoint]);ids[endpoint]=anchor_id
            exact=transformed(bone[endpoint],rig_world,unit,deadline_ns);position,interval,reason=publish(exact)
            anchors.append(dict(anchor_id=anchor_id,bone_name=name,endpoint=endpoint,position_world_m=position,
                position_interval_world_m=interval,state='available' if reason is None else 'unavailable',reason=reason))
        graph.append(dict(name=name,parent=bone['parent'],connected=bone['connected'],use_deform=bone['use_deform'],
            head_anchor_id=ids['head'],tail_anchor_id=ids['tail']))
    positions=[]
    for index in sorted(refs):
        r.check_time(deadline_ns);positions.append(transformed(current[index],world,unit,deadline_ns))
    low=[min(v[k] for v in positions) for k in range(3)];high=[max(v[k] for v in positions) for k in range(3)]
    _,_,reason=publish(low+high)
    bounds=dict(kind='referenced_current_triangle_hull_aabb',state='available' if reason is None else 'unavailable',reason=reason,
        bounds_world_m=None if reason is not None else [[outward(v,-1) for v in low],[outward(v,1) for v in high]],
        vertices_total=len(current),surface_vertices_total=len(refs),loose_vertices_excluded=len(current)-len(refs),triangles_total=len(triangles))
    available=sum(a['state']=='available' for a in anchors)
    stable=dict(schema='surface-deformation-anchor-catalog-v1',source_ref=ref,operator_pins=copy.deepcopy(pins),coordinate_model=copy.deepcopy(COORDINATE_MODEL),
        graph=graph,anchors=anchors,bounds=bounds,completeness=dict(bones_total=len(bones),anchors_total=len(anchors),anchors_available=available,
            anchors_unavailable=len(anchors)-available,anchors_omitted=0,graph_complete=True,anchors_complete=True),scope=copy.deepcopy(SCOPE))
    need(set(stable)==STABLE_FIELDS,'proof_shape')
    result=dict(stable,catalog_sha256=r.digest(stable),source_sha256=proof['source_sha256'],
        live_capture=dict(source_sha256=proof['source_sha256'],document_epoch=proof['source']['document_epoch'],process_id=proof['source']['process_id']),
        status='observed' if available==len(anchors) and reason is None else 'partial',execution_authority=False,geometry_setters=0,original_file_saved=False)
    return budget(result,deadline_ns)


def half_values(value):
    need(vector(value,1e6) and all(1e-6<=v<=1e6 for v in value),'half_extents');return value[:]


def anchor_value(directory,anchor_id):
    need(type(anchor_id) is str and anchor_id.startswith('bone-anchor:') and r.hex_text(anchor_id[len('bone-anchor:'):],64),'anchor_id')
    found=next((a for a in directory['anchors'] if a['anchor_id']==anchor_id),None);need(found is not None,'unknown_anchor')
    need(found['state']=='available','anchor_unavailable');return found


def box(anchor,half):
    center=anchor['position_world_m'];low=[limited(Q(c)-Q(h)) for c,h in zip(center,half)];high=[limited(Q(c)+Q(h)) for c,h in zip(center,half)]
    need(all(abs(v)<=1_000_000_000 for v in low+high),'box_domain')
    bounds=[[outward(v,-1) for v in low],[outward(v,1) for v in high]]
    need(all(bounds[0][k]<bounds[1][k] and abs(bounds[0][k])<=1e9 and abs(bounds[1][k])<=1e9 for k in range(3)),'box_domain')
    return dict(kind='closed_aabb',coordinate_space='current_world_m',bounds=bounds)


def bind_selection(proof,selection,*,pins,deadline_ns):
    r.check_time(deadline_ns)
    need(type(selection) is dict and set(selection)=={'schema','source_ref','catalog_sha256','anchor_id','half_extents_m'}
        and selection['schema']=='surface-deformation-anchor-selection-v1' and r.hex_text(selection['catalog_sha256'],64),'selection_fields')
    ref=selection['source_ref'];need(type(ref) is dict and set(ref)=={'scene_sha256','rig_object_id','mesh_object_id','frame'}
        and r.hex_text(ref['scene_sha256'],64) and r.text(ref['rig_object_id']) and r.text(ref['mesh_object_id']),'source_fields')
    frame=ref['frame'];need(type(frame) is dict and set(frame)=={'number','subframe'} and type(frame['number']) is int
        and finite(frame['subframe'],1) and 0<=frame['subframe']<1,'frame')
    need(ref==source_ref(proof),'stale_selection');half=half_values(selection['half_extents_m'])
    directory=catalog(proof,pins=pins,deadline_ns=deadline_ns);need(selection['catalog_sha256']==directory['catalog_sha256'],'stale_catalog')
    anchor=anchor_value(directory,selection['anchor_id']);box(anchor,half)
    result=dict(schema='surface-deformation-anchor-query-v1',expected_source_sha256=proof['source_sha256'],catalog_sha256=directory['catalog_sha256'],
        anchor_id=selection['anchor_id'],half_extents_m=half)
    r.check_time(deadline_ns);return result


def resolve(proof,query,*,pins,deadline_ns):
    r.check_time(deadline_ns)
    need(type(query) is dict and set(query)=={'schema','expected_source_sha256','catalog_sha256','anchor_id','half_extents_m'}
        and query['schema']=='surface-deformation-anchor-query-v1' and r.hex_text(query['expected_source_sha256'],64)
        and r.hex_text(query['catalog_sha256'],64),'query_fields')
    need(type(proof) is dict and r.hex_text(proof.get('source_sha256'),64),'proof_shape')
    need(query['expected_source_sha256']==proof['source_sha256'],'stale_source');half=half_values(query['half_extents_m'])
    directory=catalog(proof,pins=pins,deadline_ns=deadline_ns);need(query['catalog_sha256']==directory['catalog_sha256'],'stale_catalog')
    anchor=anchor_value(directory,query['anchor_id']);region=box(anchor,half)
    region_query=dict(schema='surface-deformation-region-query-v1',expected_source_sha256=proof['source_sha256'],region=region)
    trace=dict(schema='surface-deformation-anchor-query-result-v1',source_sha256=proof['source_sha256'],catalog_sha256=directory['catalog_sha256'],
        anchor_id=anchor['anchor_id'],bone_name=anchor['bone_name'],endpoint=anchor['endpoint'],center_world_m=copy.deepcopy(anchor['position_world_m']),
        center_interval_world_m=copy.deepcopy(anchor['position_interval_world_m']),half_extents_m=half[:],region=copy.deepcopy(region),coordinate_space='current_world_m',
        position_model=COORDINATE_MODEL['position_model'],box_model='exact_binary64_center_plus_minus_half_outward_binary64',
        metric_scope='whole_original_triangles_not_clipped_integrals',anchor_semantics='native_evaluated_bone_endpoint_not_anatomical_semantics')
    budget(trace,deadline_ns);return region_query,trace
