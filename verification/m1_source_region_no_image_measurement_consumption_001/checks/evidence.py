"""Validate the actual selected/whole qualification with independent current triangles."""

import json
from pathlib import Path
from runpy import run_path


NS = Path(__file__).resolve().parents[1]
V = NS.parent
T = run_path(str(NS/'checks/truth.py'))
DOMAIN,TARGET,REFERENCE = (T[k] for k in ('DOMAIN','TARGET','REFERENCE'))
require,read,pin,fingerprint = (T[k] for k in ('require','read','pin','fingerprint'))
FULL = 'human-eye-source-region-observation-v1'
BRIEF = 'source-region-brief-v2'
SELECTED_SCOPE = 'complete_selected_source_triangle_union_to_reference_triangle_surface'
FACT = 'surface_proximity'


def public(reply):
    result = reply['result'] if 'result' in reply else reply
    require(result['isError'] is False and len(result['content'])==1
            and result['content'][0]['type']=='text','no_image_qualification_requires_one_successful_text_block')
    text = result['content'][0]['text']
    return result,text,json.loads(text)


def fixed_cli(reply, *, must_preserve):
    # The same Codex-versioned replay policy and exact byte controls used by the prior held-out task.
    result, text, _ = public(reply)
    holdout = run_path(str(V/'m1_region_task_first_packet_consumption_holdout_001/checks/evidence.py'))
    proof = holdout['fixed_cli'](result,require_all=must_preserve)
    require(len(proof['stages'])==6,'reserved_three_headers_two_stages_not_executed')
    return {**proof,'actual_body_utf8_bytes':len(text.encode()),
            'all_six_preserve_full_semantics':all(row['exact'] for row in proof['stages'])}


def prove_capture(capture, source, required_names, *, revision, scope, generation=None, epoch=None):
    if capture is None:
        return None  # The caller can bind raw WIRE in the outer qualification verifier.
    host = capture['host_identity']
    current = T['meshes'](source)
    meshes = capture['meshes']
    wanted = {row['name']:row for row in meshes}
    require(len(wanted)==len(meshes) and wanted.keys()==set(required_names)
            and capture['revision']==revision and host['capture_scope']==scope
            and capture['unit']=='m' and capture['coordinate_frame']=='world',
            'actual_native_capture_roster_revision_or_saved_world_frame_changed')
    if generation is not None:
        require(capture['capture_state']==generation and host['document_epoch']==epoch,
                'actual_native_capture_generation_not_current_region')
    refs = {}
    for name,row in wanted.items():
        original = current[name]
        evaluated = original['evaluated']
        require(row['object_id']==original['object_id']
                and host['object_instances'][row['object_id']]==original['instance_id']
                and row['vertices']==evaluated['vertices_world_m'] and row['faces']==evaluated['triangles'],
                'actual_capture_ordered_source_arrays_or_object_instance_changed/'+name)
        refs[name] = {'object_id':row['object_id'],'instance_id':original['instance_id'],
                      'vertices':len(row['vertices']),'triangles':len(row['faces'])}
    return {'scope':scope,'scene_revision':revision,'whole_object_capture_rows':refs}


def measured(source, scope, fact, mapping=None):
    require(fact['status']==fact['witness_status']==fact['direction_status']=='measured'
            and fact['semantics']=='current_evaluated_triangle_surfaces_world_metres',
            'public_conveyance_did_not_deliver_measured_world_distance_direction_and_points')
    value = fact['value']
    witness = value['nearest_witness']
    faces = {}
    if mapping is not None:
        require(mapping.keys()=={'a','b'},'selected_packet_missing_one_point_source_mapping')
        faces = {side:row['source_triangle_indices'] for side,row in mapping.items()}
    independent = T['check_measurement'](source,scope,{
        'distance_m':value['distance_m'], **witness,'source_triangle_indices':faces},exact=True)
    require(all(independent[k] for k in ('distance_correct','world_direction_correct','actual_attaining_pair')),
            'actual_reported_distance_or_points_do_not_attain_independent_lower_bound/'+scope)
    meanings = independent['reported_memberships']
    if mapping is not None:
        for side,row in mapping.items():
            require(row['status']=='measured' and row['exact_membership'] is True and row['index_domain']==DOMAIN
                    and row['source_triangle_indices']==meanings[side]['exact_source_triangle_indices']
                    and row['source_vertex_indices']==meanings[side]['exact_source_vertex_indices'],
                    'published_point_source_mapping_is_not_exact_current_membership/'+side)
    expected_topology = [{'boundary_edge_count':4 if scope=='selected' else 0,'nonmanifold_edge_count':0},
                         {'boundary_edge_count':0,'nonmanifold_edge_count':0}]
    require(value['topology']==expected_topology,'wrong_selected_or_whole_surface_topology/'+scope)
    return {'independent':independent,'point_pair_and_direction':witness,'distance_m':value['distance_m'],
            'actual_source_mapping_delivered':mapping is not None,'topology':value['topology']}


def validate_selected(reply, producer, source, installed, *, require_compact, capture=None):
    _,text,packet = public(reply)
    task = packet['task_result']
    bound = producer['binding']
    original = producer['task_result']
    complete = T['meshes'](source)
    registered = bound['objects']
    names = [row['object_name'] for row in registered]
    require(len(names)==len(set(names))==21 and set(names)==complete.keys()
            and all(item['object_index']==i and item['host_id']==complete[name]['object_id']
                    and item['instance_id']==complete[name]['instance_id']
                    for i,(item,name) in enumerate(zip(registered,names,strict=True)))
            and bound['runtime_source_sha256']==installed['source_sha256']
            and bound['unit']=='m' and bound['coordinate_frame']=='world' and bound['source']=='blender'
            and bound['capture_scope']=='complete_scene_meshes',
            'selected_producer_not_bound_to_exact_current_full_scene_sources')
    ref = {
        'schema':'human-eye-source-region-ref-v1',
        'document_epoch':bound['document_epoch'],
        'host_id':complete[TARGET]['object_id'],
        'instance_id':complete[TARGET]['instance_id'],
        'capture_generation':{key:bound['capture_state'][key] for key in ('instance_id','epoch','revision')},
        'source_triangle_indices':[6,7],
        'ordered_geometry_sha256':fingerprint([
            {'host_id':complete[name]['object_id'],'instance_id':complete[name]['instance_id'],
             'vertices':complete[name]['evaluated']['vertices_world_m'],'faces':complete[name]['evaluated']['triangles']}
            for name in names]),
    }
    ref['region_id']='source-region:'+fingerprint(ref)
    reference = {'name':REFERENCE,'object_id':complete[REFERENCE]['object_id'],
                 'instance_id':complete[REFERENCE]['instance_id'],'object_index':names.index(REFERENCE)}
    require(packet['schema']==(BRIEF if require_compact else FULL) and packet['read_only'] is True
            and packet['execution_authority'] is False and packet['result_kind']=='source_region'
            and packet['status']==task['status']==original['status']==producer['status']=='complete'
            and packet['observation_status']==producer['observation_status']=='image_not_requested'
            and ref==packet['region_ref']==producer['region_ref']==original['region_ref']
            and bound['ordered_geometry_sha256']==ref['ordered_geometry_sha256']
            and packet['frames' if not require_compact else 'images']==[] and producer['frames']==[]
            and producer.get('constructed_frames',[])==[] and task['measurement_scope']==original['measurement_scope']==SELECTED_SCOPE
            and task['reference']==original['reference']==reference and original['binding']==bound
            and all(bound[key]==value for key,value in packet['binding'].items())
            and {FACT}==task['facts'].keys()==original['facts'].keys() and task['facts']==original['facts']
            and task['source_mapping']['nearest_witness']==original['source_mapping']['nearest_witness'],
            'selected_scope_capture_reference_name_measurement_or_projection_identity_changed')
    require(all(packet['image_delivery'][key]==0 for key in
                ('mcp_content_constructed_image_count','local_verified_image_count','new_raster_attempts')),
            'no_image_selected_has_native_render_work_or_attachment')
    mesh = complete[TARGET]['evaluated']
    source_rows = [mesh['triangles'][i] for i in (6,7)]
    vertices = sorted({i for row in source_rows for i in row})
    pos = {j:i for i,j in enumerate(vertices)}
    world = [mesh['vertices_world_m'][j] for j in vertices]
    from_source = {'index_domain':DOMAIN,'submesh_to_source_triangle_indices':[6,7],
                   'submesh_to_source_vertex_indices':vertices,'triangles_source_vertices':source_rows,
                   'triangles_submesh_vertices':[[pos[j] for j in row] for row in source_rows]}
    region = {'object_name':TARGET,'host_id':ref['host_id'],'instance_id':ref['instance_id'],'index_domain':DOMAIN,
              'bbox_min_world_m':[min(coord) for coord in zip(*world)],
              'bbox_max_world_m':[max(coord) for coord in zip(*world)]}
    require(from_source==producer['source_mapping']==original['source_mapping']['region']
            and producer['facts']['region']=={**region,'source_triangle_indices':[6,7],
                'source_vertex_indices':vertices,'triangles_source_vertices':source_rows,'vertices_world_m':world},
            'complete_selected_mesh_source_rows_differ_from_frozen_current_mesh')
    if require_compact:
        require(packet['region']=={**region,'source_triangle_count':2,'source_vertex_count':len(vertices)}
                and task['unit']=='m' and task['coordinate_frame']=='world' and len(text.encode())<=10800,
                'selected_compact_missing_scope_world_units_or_actual_body_over_10800')
    else:
        require(task['region_ref']==ref and packet['source_mapping']==task['source_mapping']['region']==from_source
                and packet['facts']['region']==producer['facts']['region'],
                'selected_full_lost_original_diagnostic_topology')
    return {'schema':packet['schema'],'body_UTF8_bytes':len(text.encode()),'region_ref':ref,
            'ordered_reference':reference,'measure_scope':SELECTED_SCOPE,
            'current_capture':prove_capture(capture,source,names,revision=bound['scene_revision'],
                   scope='complete_scene_meshes',generation=bound['capture_state'],epoch=bound['document_epoch']),
            **measured(source,'selected',task['facts'][FACT],task['source_mapping']['nearest_witness'])}


def validate_whole(reply, producer, source, installed, *, capture=None):
    _,text,packet = public(reply)
    bound = packet['binding']
    objects = T['meshes'](source)
    expected = [{'object_id':objects[name]['object_id'],'name':name} for name in (TARGET,REFERENCE)]
    require(packet==producer and packet['result_kind']=='task_query' and packet['schema_version']=='task-query-v3'
            and packet['status']=='observed' and packet['execution_authority'] is False
            and packet['unit']=='m' and packet['coordinate_frame']=='world' and packet['pair_order']=='A_to_B'
            and packet['facts'].keys()=={FACT} and 'region_ref' not in packet
            and bound['source']=='blender' and bound['runtime_source_sha256']==installed['source_sha256']
            and bound['capture_scope']=='selected_objects' and 'region_source' not in bound
            and bound['objects']==expected and bound['selected_count']==2 and bound['candidate_count']==21,
            'whole_pair_does_not_use_complete_current_objects_in_request_order')
    current = prove_capture(capture,source,(TARGET,REFERENCE),revision=bound['scene_revision'],
                            scope='selected_objects')
    return {'schema':packet['schema_version'],'body_UTF8_bytes':len(text.encode()),'ordered_objects':expected,
            'measure_scope':'whole_objects','current_capture':current,**measured(source,'whole',packet['facts'][FACT])}


def verify_qualification(slot, selected_reply, selected_producer, whole_reply, whole_producer, *,
                         binding, require_compact, source=None, selected_capture=None, whole_capture=None):
    slot = Path(slot).resolve(strict=True)
    first = read(slot/'initial_capture/TERMINAL_SOURCE.json')
    source = read(slot/'TERMINAL_SOURCE.json') if source is None else source
    installed = binding if isinstance(binding,dict) else read(binding)
    scene = T['verify_source'](source,first)
    selected = validate_selected(selected_reply,selected_producer,source,installed,
                                 require_compact=require_compact,capture=selected_capture)
    whole = validate_whole(whole_reply,whole_producer,source,installed,capture=whole_capture)
    require(selected['distance_m']>2>whole['distance_m'],'qualification_did_not_reproduce_threshold_reversal')
    return {'passed':True,'source':scene,'selected':selected,'whole':whole,
            'fixed_CLI':{'selected':fixed_cli(selected_reply,must_preserve=require_compact),
                         'whole':fixed_cli(whole_reply,must_preserve=True)},
            'threshold_2m':{'selected_meets':True,'whole_meets':False},'new_image_blocks':0}
