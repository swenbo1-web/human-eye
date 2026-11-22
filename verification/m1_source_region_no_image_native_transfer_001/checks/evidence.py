"""Check real product packet identities and native evidence against the independent meshes."""

from collections import Counter
from pathlib import Path
from runpy import run_path


NS = Path(__file__).resolve().parents[1]
V = NS.parent
T = run_path(str(NS/'checks/truth.py'))
OLD = run_path(str(V/'m1_source_region_no_image_measurement_consumption_001/checks/evidence.py'))
require,read,pin = (T[key] for key in ('require','read','pin'))
public,fixed_cli,fingerprint,prove_capture = (OLD[key] for key in ('public','fixed_cli','fingerprint','prove_capture'))
FACT = OLD['FACT']
BRIEF,FULL,SELECTED_SCOPE = (OLD[key] for key in ('BRIEF','FULL','SELECTED_SCOPE'))
DOMAIN = T['DOMAIN']


def edge_counts(triangles):
    counts = Counter(tuple(sorted((u,v))) for row in triangles for u,v in zip(row,row[1:]+row[:1]))
    return {'boundary_edge_count':sum(n==1 for n in counts.values()),
            'nonmanifold_edge_count':sum(n>2 for n in counts.values())}


def fact_proof(case, source, scope, fact, mapping=None):
    require(fact['status']==fact['witness_status']==fact['direction_status']=='measured'
            and fact['semantics']=='current_evaluated_triangle_surfaces_world_metres',
            'current_world_distance_direction_or_surface_pair_not_measured')
    value = fact['value']
    witness = value['nearest_witness']
    proof = T['measured'](source,case,scope,{'distance_m':value['distance_m'], **witness},exact=True)
    require(all(proof[key] for key in ('distance_correct','direction_correct','pair_attains')),
            'actual_surface_distance_direction_or_pair_disagrees_with_support_proof/'+scope)
    if mapping is not None:
        require(mapping.keys()=={'a','b'},'both_selected_packet_source_point_maps_required')
        for side,row in mapping.items():
            membership = proof['actual_memberships'][side]
            require(row['status']=='measured' and row['exact_membership'] is True and row['index_domain']==DOMAIN
                    and row['source_triangle_indices']==membership['exact_source_triangle_indices']
                    and row['source_vertex_indices']==membership['exact_source_vertex_indices'],
                    'published_source_membership_not_a_current_evaluated_face_or_vertex/'+side)
    _,config = T['scenario'](case)
    surfaces = T['pair_surfaces'](source,config,scope)
    require(value['topology']==[edge_counts([faces[i] for i in ids]) for _,faces,ids in surfaces],
            'measured_scope_topology_does_not_match_current_triangle_sets')
    return {'distance_m':value['distance_m'],'witness':witness,'source_memberships':proof['actual_memberships'],
            'meets_threshold':proof['independent']['meets_threshold'],
            'measured_packet_has_source_mapping':mapping is not None,'support_proof':proof['independent']['support_proof']}


def require_ordered_identity_rows(bound, rows):
    ordered = bound['objects']
    names = [row['object_name'] for row in ordered]
    require(len(names)==len(set(names))==len(rows)==21 and set(names)==rows.keys()
            and all(item['object_index']==i and item['host_id']==rows[name]['object_id']
                    and item['instance_id']==rows[name]['instance_id']
                    for i,(item,name) in enumerate(zip(ordered,names,strict=True))),
            'complete_scene_source_identity_or_order_is_inconsistent')
    return names


def selected_proof(case, reply, producer, source, installed, *, capture=None, require_compact=True):
    _,config = T['scenario'](case)
    target,reference,selected = (config[key] for key in ('target','reference','selected'))
    _,text,packet = public(reply)
    user_task = packet['task_result']
    region_ref = packet['region_ref']
    original_task = producer['task_result']
    bound = producer['binding']
    rows = T['objects'](source)
    names = require_ordered_identity_rows(bound,rows)
    actual = rows[target]['evaluated']
    wanted_faces = [actual['triangles'][i] for i in selected]
    vertices = sorted({i for row in wanted_faces for i in row})
    positions = {old:i for i,old in enumerate(vertices)}
    world = [actual['vertices_world_m'][i] for i in vertices]
    mapping = {'index_domain':DOMAIN,'submesh_to_source_triangle_indices':selected,
               'submesh_to_source_vertex_indices':vertices,'triangles_source_vertices':wanted_faces,
               'triangles_submesh_vertices':[[positions[i] for i in row] for row in wanted_faces]}
    ordered = [{'host_id':rows[name]['object_id'],'instance_id':rows[name]['instance_id'],
                'vertices':rows[name]['evaluated']['vertices_world_m'],'faces':rows[name]['evaluated']['triangles']}
               for name in names]
    current_ref = {'schema':'human-eye-source-region-ref-v1','document_epoch':bound['document_epoch'],
                   'host_id':rows[target]['object_id'],'instance_id':rows[target]['instance_id'],
                   'source_triangle_indices':selected,'ordered_geometry_sha256':fingerprint(ordered),
                   'capture_generation':{key:bound['capture_state'][key] for key in ('instance_id','epoch','revision')}}
    current_ref['region_id'] = 'source-region:'+fingerprint(current_ref)
    expected_reference = {'name':reference,'object_id':rows[reference]['object_id'],
                          'instance_id':rows[reference]['instance_id'],'object_index':names.index(reference)}
    region = {'object_name':target,'host_id':current_ref['host_id'],'instance_id':current_ref['instance_id'],
              'index_domain':DOMAIN,'bbox_min_world_m':[min(col) for col in zip(*world)],
              'bbox_max_world_m':[max(col) for col in zip(*world)]}
    require(packet['schema']==(BRIEF if require_compact else FULL)
            and packet['status']==user_task['status']==producer['status']==original_task['status']=='complete'
            and packet['result_kind']=='source_region' and packet['read_only'] is True and packet['execution_authority'] is False
            and bound['runtime_source_sha256']==installed['source_sha256']
            and bound['source']=='blender' and bound['unit']=='m' and bound['coordinate_frame']=='world'
            and bound['capture_scope']=='complete_scene_meshes'
            and packet['observation_status']==producer['observation_status']=='image_not_requested'
            and producer['frames']==producer.get('constructed_frames',[])==[]
            and packet['frames' if not require_compact else 'images']==[]
            and region_ref==producer['region_ref']==original_task['region_ref']==current_ref
            and bound['ordered_geometry_sha256']==current_ref['ordered_geometry_sha256']
            and expected_reference==user_task['reference']==original_task['reference']
            and user_task['measurement_scope']==original_task['measurement_scope']==SELECTED_SCOPE
            and original_task['binding']==bound and all(bound.get(key)==value for key,value in packet['binding'].items())
            and user_task['facts']==original_task['facts'] and user_task['facts'].keys()=={FACT}
            and user_task['source_mapping']['nearest_witness']==original_task['source_mapping']['nearest_witness']
            and mapping==producer['source_mapping']==original_task['source_mapping']['region']
            and producer['facts']['region']=={**region,'source_triangle_indices':selected,
                'source_vertex_indices':vertices,'triangles_source_vertices':wanted_faces,'vertices_world_m':world},
            'current_selected_public_source_scope_binding_or_measurement_changed')
    require(all(packet['image_delivery'][field]==0 for field in
                ('mcp_content_constructed_image_count','local_verified_image_count','new_raster_attempts')),
            'no_image_selected_has_actual_image_or_render')
    if require_compact:
        require(packet['region']=={**region,'source_triangle_count':len(selected),'source_vertex_count':len(vertices)}
                and user_task['unit']=='m' and user_task['coordinate_frame']=='world' and len(text.encode())<=10800,
                'brief_missing_source_world_units_or_exceeds_byte_limit')
    else:
        require(user_task['region_ref']==current_ref and packet['source_mapping']==user_task['source_mapping']['region']==mapping
                and packet['facts']['region']==producer['facts']['region'],'full_lost_exact_source_triangles')
    proof = prove_capture(capture,source,names,revision=bound['scene_revision'],
                         scope='complete_scene_meshes',generation=bound['capture_state'],epoch=bound['document_epoch'])
    return {'schema':packet['schema'],'text_bytes':len(text.encode()),'region_ref':current_ref,
            'ordered_reference':expected_reference,'current_native_capture':proof,
            **fact_proof(case,source,'selected',user_task['facts'][FACT],user_task['source_mapping']['nearest_witness'])}


def whole_proof(case, reply, producer, source, installed, *, capture=None):
    _,config = T['scenario'](case)
    _,text,packet = public(reply)
    rows = T['objects'](source)
    names = [config['target'],config['reference']]
    bound = packet['binding']
    expected = [{'object_id':rows[name]['object_id'],'name':name} for name in names]
    require(packet==producer and packet['result_kind']=='task_query' and packet['schema_version']=='task-query-v3'
            and packet['execution_authority'] is False and packet['status']=='observed'
            and packet['unit']=='m' and packet['coordinate_frame']=='world' and packet['pair_order']=='A_to_B'
            and packet['facts'].keys()=={FACT} and 'region_ref' not in packet and 'region_source' not in bound
            and bound['source']=='blender' and bound['runtime_source_sha256']==installed['source_sha256']
            and bound['objects']==expected,'whole_query_does_not_bind_the_two_complete_current_objects_in_order')
    scope = bound.get('capture_scope','complete_scene_meshes')
    if scope=='selected_objects':
        require(bound['selected_count']==2 and bound['candidate_count']==21,'whole_object_subset_count_changed')
        capture_names = names
    else:
        require(scope=='complete_scene_meshes' and capture is not None,'whole_scene_fallback_requires_bound_raw_capture')
        capture_names = list(rows)
    proof = prove_capture(capture,source,capture_names,revision=bound['scene_revision'],scope=scope)
    return {'schema':packet['schema_version'],'text_bytes':len(text.encode()),'ordered_objects':expected,
            'current_native_capture':proof,**fact_proof(case,source,'whole',packet['facts'][FACT])}


def verify_product_case(case, slot, selected_reply, selected_producer, whole_reply, whole_producer, *,
                        binding, source=None, selected_capture=None, whole_capture=None):
    slot = Path(slot).resolve(strict=True)
    first = read(slot/'initial_capture/TERMINAL_SOURCE.json')
    source = read(slot/'TERMINAL_SOURCE.json') if source is None else source
    installed = binding if isinstance(binding,dict) else read(binding)
    independent = T['verify_source'](source,first)
    selected = selected_proof(case,selected_reply,selected_producer,source,installed,capture=selected_capture)
    whole = whole_proof(case,whole_reply,whole_producer,source,installed,capture=whole_capture)
    require(selected['meets_threshold'] is True and whole['meets_threshold'] is False,
            'case_threshold_scope_reversal_not_proven')
    return {'passed':True,'case':T['scenario'](case)[0],'source':independent,'selected':selected,'whole':whole,
            'fixed_CLI':{'selected':fixed_cli(selected_reply,must_preserve=True),
                         'whole':fixed_cli(whole_reply,must_preserve=True)},'image_blocks':0}


def verify_native_case(case, source, payload):
    """Native probe must name and supply both entire evaluated objects in source order."""
    case,config = T['scenario'](case)
    ordered = [config['target'],config['reference']]
    rows = T['objects'](source)
    series = payload['measurements']
    if case in series:
        # The real qualification's single ordinary script returns all three
        # cases. The caller binds that script to the frozen request.
        series = series[case]
    else:
        require(payload['target']==ordered[0] and payload['reference']==ordered[1]
                and payload['selected_source_triangle_indices']==config['selected'],
                'native_declared_wrong_name_scope_or_reference')
    require(payload.get('unit','m')=='m' and payload.get('coordinate_frame','world')=='world'
            and set(ordered)<=payload['meshes'].keys() and series.keys()==set(T['SCOPES']),
            'native_declared_wrong_name_scope_unit_or_reference')
    for name in ordered:
        data = payload['meshes'][name]
        current = rows[name]['evaluated']
        require(data.get('vertices_world_m',data.get('vertices'))==current['vertices_world_m']
                and data.get('triangles',data.get('faces'))==current['triangles'],
                'native_did_not_read_actual_full_current_ordered_source/'+name)
    proofs = {}
    for scope,raw in series.items():
        proof = T['measured'](source,case,scope,raw)
        require(all(proof[key] for key in ('distance_correct','direction_correct','pair_attains','stated_source_memberships_correct')),
                'native_current_surface_pair_or_report_not_independently_attained/'+scope)
        proofs[scope] = proof
    return {'passed':True,'case':case,'ordered_names':ordered,'native_current_ordered_arrays':True,'measurements':proofs}
