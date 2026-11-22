"""Independent current-source, public frame, and qualification checks."""

import base64
from fractions import Fraction as F
from functools import lru_cache
from hashlib import sha256
import json
from math import sqrt
from pathlib import Path
from runpy import run_path
import sys
from types import SimpleNamespace


NS = Path(__file__).resolve().parents[1]
V = NS.parent
DENSE = V/'perf050_dense_micro_surface_holdout_recovery_001'
PREVIOUS = V/'perf050_dense_micro_surface_holdout_001'
INSTALLED = V/'m1_region_task_first_packet_projection_001/install/PRODUCT_RUN_BINDING.json'
SOURCE_SHA = '704742071fd1d2722b952e6fa0d4f9a497b8a33ed567ce8f510657d8c1b379fe'
CONDITIONS = {'area_min_m2':19/4096,'area_max_m2':21/4096,'normal_z_min':.75}
BRIEF = 'active-observation-region-task-brief-v2'
VIEWS = {'SCENE':(4,-4,3),'TOP':(0,0,1),'LEFT':(-1,0,1),'RIGHT':(1,0,1),'FRONT':(0,-1,1),'BACK':(0,1,1)}
EPS = F(1,20000)


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_bytes())


def digest(raw):
    return sha256(raw).hexdigest()


def pin(path, slot=None):
    path = Path(path).resolve(strict=True)
    require(slot is None or path.is_relative_to(Path(slot).resolve()), 'artifact_outside_current_owned_slot')
    raw = path.read_bytes()
    return {'path':path.as_posix(),'sha256':digest(raw),'bytes':len(raw)}


@lru_cache(maxsize=None)
def module(path):
    return run_path(str(path))


def normalize_truth(truth):
    """Adapt the sealed exact enumerator to the two retained frame verifiers."""
    if not isinstance(truth,dict):
        truth = read(truth)
    if 'regions' in truth:
        return truth
    exact_conditions = {'area_low_m2_exact':F(19,4096),'area_high_m2_exact':F(21,4096),
                        'normal_z_min_exact':F(3,4)}
    require({key:F(value) for key,value in truth['conditions'].items()}==exact_conditions
            and set(truth['directions'])==VIEWS.keys()
            and all(tuple(truth['directions'][name])==direction for name,direction in VIEWS.items()),
            'sealed_independent_conditions_or_views_changed')
    observed = {row['object_name']:row for row in truth['eligible']}
    by_x = sorted(observed,key=lambda name: F(observed[name]['center_world_m_exact'][0]))
    require(len(observed)==len(truth['eligible'])==3,'sealed_independent_roster_is_not_three_unique_regions')
    roles = dict(zip(('P','Q','R'),by_x,strict=True))
    require(observed[roles['P']]['eligible_complete_views']==[]
            and observed[roles['Q']]['eligible_complete_views']==['LEFT']
            and set(observed[roles['R']]['eligible_complete_views'])==VIEWS.keys()
            and truth['measurement']['source_object']==roles['P']
            and truth['measurement']['reference_object']=='M4_Far_00'
            and F(truth['measurement']['distance_m_exact'])==F(1,4)
            and truth['measurement']['world_direction']==[0,0,1],
            'sealed_independent_role_or_distance_contract_changed')
    frozen = read(truth['reopened_source']['path'])
    source = {row['name']:row['evaluated'] for row in frozen['objects']}
    regions = {}
    for name,row in observed.items():
        vertices = source[name]['vertices_world']
        corners = row['corners_world_m']
        require(row['source_triangle_indices']==[0,1]
                and len({tuple(point) for point in corners})==len(corners)==4
                and all(point in vertices for point in corners)
                and set(row['finite_direction_proofs'])==VIEWS.keys(),
                'independent_faces_corners_or_directions_changed/'+name)
        regions[name] = {**row,'boundary_loop':[vertices.index(point) for point in corners],
                         'corners':corners,'directions':row['finite_direction_proofs']}
    measurement = {**truth['measurement'],'reference':truth['measurement']['reference_object'],
                   'distance_exact_m':truth['measurement']['distance_m_exact']}
    return {**truth,'roles':roles,'regions':regions,'measurement':measurement}


def verify_source(source, truth):
    """Check every current native/evaluated row against the independently sealed reopen."""
    truth = normalize_truth(truth)
    require(truth['reopened_source']['sha256'] == pin(truth['reopened_source']['path'])['sha256'],
            'independent_reopened_source_bytes_changed')
    frozen = read(truth['reopened_source']['path'])
    stamp = source['source']
    rows = source['objects']
    owned, expected = ({row['name']:row for row in doc['objects']} for doc in (source,frozen))
    require(stamp['asset_sha256'] == truth['asset']['sha256']
            and (stamp['frame'],stamp['subframe'],stamp['scale_length']) == (1,0,1)
            and stamp['unit_settings']['scale_length'] == 1
            and len(rows) == len(owned) == len(expected) and owned.keys() == expected.keys(),
            'actual_fixture_identity_frame_units_or_roster_changed')
    require(source['display_object_mask'] == [True]*len(rows)
            and all(row['visible_get'] is True for row in rows)
            and len({row['object_id'] for row in rows}) == len({row['instance_id'] for row in rows}) == len(rows),
            'complete_current_display_or_object_instance_identity_missing')
    for name,row in owned.items():
        for stage in ('native','evaluated'):
            actual, old = row[stage], expected[name][stage]
            require(actual['triangles'] == old['triangles']
                    and actual['vertices_world_m'] == old.get('vertices_world_m',old.get('vertices_world')),
                    'ordered_same_fixture_mesh_changed/'+name+'/'+stage)
    return owned


def producer_capture(slot,binding,source,*, require_full=True):
    installed = read(INSTALLED)
    require(installed['source_sha256'] == SOURCE_SHA, 'installed_candidate_source_identity_changed')
    handle = module(V/'m4_cross_scale_discovery_001/oracle/check_saved.py')
    audit = handle['Audit']()
    captures,_ = handle['decode_captures'](Path(slot),installed,audit)
    capture = handle['current_capture'](captures,binding,audit)
    if require_full:
        handle['source_binding_checks'](capture,binding,installed,audit)
    current = {row['name']:row for row in source['objects']}
    rows = capture['meshes']
    require(len(rows) == len(current) and {row['name'] for row in rows} == current.keys(),
            'actual_producer_capture_is_not_full_current_geometry')
    for mesh in rows:
        same = current[mesh['name']]
        require(mesh['object_id'] == same['object_id']
                and capture['host_identity']['object_instances'][mesh['object_id']] == same['instance_id']
                and mesh['vertices'] == same['evaluated']['vertices_world_m']
                and mesh['faces'] == same['evaluated']['triangles'],
                'actual_producer_capture_not_current_evaluated_source/'+mesh['name'])
    return capture


def result(reply):
    body = reply['result'] if 'result' in reply else reply
    require(body.get('isError') is False and body['content'] and body['content'][0]['type']=='text',
            'actual_public_result_is_not_successful')
    return body


def document(reply):
    return json.loads(result(reply)['content'][0]['text'])


def records(table):
    names = table['columns']
    require(len(names) == len(set(names)),'duplicate_compact_column_names')
    return [dict(zip(names,row,strict=True)) for row in table['rows']]


def values(point):
    require(len(point) == 3 and all(type(value) in (int,float,str,F) for value in point),
            'world_point_not_three_finite_values')
    return tuple(F(str(value)) for value in point)


def dot(a,b):
    return sum(x*y for x,y in zip(a,b,strict=True))


def cross(a,b):
    return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])


def nearby(a,b):
    return all(abs(x-y) <= EPS for x,y in zip(values(a),values(b),strict=True))


def exact_direction(a,b):
    a,b = values(a),values(b)
    na,nb = sqrt(dot(a,a)),sqrt(dot(b,b))
    return bool(na and nb and dot(a,b)>0
                and all(abs(float(x)/na-float(y)/nb)<=1e-12 for x,y in zip(a,b,strict=True)))


def frame_rows(slot,device):
    if device is None:
        items = read(Path(slot)/'DEVICE_EVIDENCE.json')['frames']
        result = {row['ref']:row for row in items}
        require(len(result) == len(items),'duplicate_same_slot_frame_refs')
        return result
    return device.by_ref


def independently_positive(source, target, blocker, face, view):
    """Prove this exact finite ray shadow, without requiring a particular nearer winner."""
    objects = {row['name']:row for row in source['objects']}
    if blocker not in objects or type(face) is not int:
        return False
    mesh = objects[blocker]['evaluated']
    if not 0 <= face < len(mesh['triangles']):
        return False
    target_source = objects[target['object_name']]['evaluated']
    geom = [{'name':target['object_name'],'vertices':[values(p) for p in target_source['vertices_world_m']],
             'triangles':target_source['triangles']},
            {'name':blocker,'vertices':[values(p) for p in mesh['vertices_world_m']],
             'triangles':[mesh['triangles'][face]]}]
    if blocker == target['object_name']:
        return False  # Separate blocker objects are part of this fixed fixture.
    check = module(V/'m4_cross_scale_discovery_001/oracle/geometry_witness.py')['prove']
    region = {'object_name':target['object_name'],'source_triangle_indices':target['source_triangle_indices'],
              'boundary_loops':[target['boundary_loop']],
              'plane_normal_integer':target['plane_normal_integer']}
    try:
        check(geom,region,VIEWS[view])
    except ValueError as error:
        if str(error) == 'positive_area_front_occluder/'+blocker+'/0':
            return True
        raise
    return False


def verify_blockers(packet,task,parent,source,truth):
    target = truth['roles']['P']
    region = truth['regions'][target]
    regions = task['rows']
    idx, = [i for i,row in enumerate(regions) if row['object_name'] == target]
    reported = regions[idx]
    require(reported['status'] == 'unknown' and reported['complete_witness'] is None
            and reported['reason'] == 'positive_area_occlusion_all_front_views'
            and set(reported['view_reasons']['positive_area_occlusion']) == VIEWS.keys(),
            'occluded_target_has_no_valid_six_forward_unknown')
    evidence = task['blocker_evidence']
    require(all(evidence[key] == parent[key] for key in ('binding_sha256','source_binding_sha256','camera_identity'))
            and evidence['scope_id'] == 'global', 'occlusion_producer_wrong_parent_scope')
    production = evidence['rows']
    require(len(production) == len(VIEWS) and {e['view_name'] for e in production} == VIEWS.keys(),
            'exactly_six_named_blockers_required')
    compact = records(packet['blocker_evidence']) if packet.get('schema') == BRIEF else None
    if compact is not None:
        expected_public = [{'region_index':idx,'view_name':row['view_name'],
                            'blocker_object_index':row['blocker_object_index'],
                            'source_triangle_index':row['source_triangle_index']} for row in production]
        require(compact == expected_public,'public_sparse_named_blockers_differ_from_current_producer')
    proof = {}
    for row in production:
        index = row['blocker_object_index']
        require(type(index) is int and 0 <= index < len(parent['objects']) and row['roi_id'] == reported['roi_id'],
                'blocker_index_or_region_origin_changed')
        entity = parent['objects'][index]
        name, direction, face = entity['object_name'],row['view_name'],row['source_triangle_index']
        require(entity['object_index'] == index and entity['host_id'] == row['blocker_host_id']
                and entity['instance_id'] == row['blocker_instance_id']
                and F(row['overlap_area_screen_exact'])>0
                and independently_positive(source,region,name,face,direction),
                'named_occluder_has_no_bound_positive_shaded_area/'+direction)
        independently_accepted = {(r['object_name'],r['source_triangle_index'])
                                  for r in region['directions'][direction]['positive_area_occluders']}
        require((name,face) in independently_accepted,'actual_source_does_not_match_independent_shadow/'+direction)
        proof[direction] = {'object_name':name,'source_triangle_index':face,
                            'positive_overlap':True,'screen_area_reported':row['overlap_area_screen_exact']}
    return proof


def verify_frame_proof(slot,row,producer,capture,source,target,truth,*,public_read=None):
    checker = module(DENSE/'qualification/frame.py')
    parent = producer['binding']
    frame, = [f for f in producer['frames'] if f['image_ref'] == row['ref']]
    scope, = [sc['binding'] for sc in producer['scopes'] if sc['scope_id'] == row['scope_id']]
    return checker['prove_frame'](slot,row,frame,scope,capture,source,target,content=public_read,
                                  geometry=truth,parent=parent if row['scope_id']!='global' else None)


def verify_discovery(slot, reply, producer, source, truth, *, expected, device=None):
    """Bind complete raw or compact qualification to raw current source and both witnesses."""
    slot = Path(slot).resolve(strict=True)
    truth = normalize_truth(truth)
    view = result(reply)
    packet = document(reply)
    brief = packet.get('schema') == BRIEF
    require((expected == 'brief' and brief) or (expected == 'full' and not brief), 'unexpected_actual_discovery_projection')
    require(producer['read_only'] is True and producer['execution_authority'] is False
            and packet['read_only'] is True and packet['execution_authority'] is False,
            'qualification_discovery_is_not_read_only')
    verify_source(source,truth)
    host = producer['binding']
    capture = producer_capture(slot,host,source)
    task = producer['facts']['region_task']
    if brief:
        decoder = module(V/'m4_dense_region_brief_001/checks/brief_schema.py')['decode_body']
        decoded = decoder(packet,len(view['content']))['region_task']
        require(decoded['conditions']==task['conditions']==CONDITIONS and decoded['summary']==task['summary'],
                'brief_region_task_conditions_or_summary_differ')
        fields = ('object_name','roi_id','source_triangle_indices','source','center_world_m','front_direction_world',
                  'half_edge_u_world_m','half_edge_v_world_m','status','reason','view_reasons')
        require(all(all(a[key]==b[key] for key in fields)
                    for a,b in zip(decoded['rows'],task['rows'],strict=True))
                and all(host[key]==value for key,value in packet['binding'].items()),
                'brief_current_facts_differ_from_raw_producer')
        public_frames = {row['image_ref']:row for row in records(packet['frames'])}
        names = records(packet['objects'])
        require(names==host['objects'],'brief_current_objects_differ_from_actual_parent')
        scopes = records(packet['scopes'])
        by_scope = {row['scope_id']:row['binding'] for row in producer['scopes']}
        require(set(by_scope)=={row['scope_id'] for row in scopes}
                and all(all(by_scope[row['scope_id']][key]==row[key] for key in ('camera_identity','binding_sha256'))
                        for row in scopes),'brief_frames_do_not_share_current_bound_scopes')
        for frame in producer['frames']:
            row = public_frames[frame['image_ref']]
            require(all(row[key]==frame[key] for key in ('view_name','frame_identity','image_sha256'))
                    and scopes[row['scope_index']]['scope_id']==frame['scope_id'],
                    'brief_original_frame_scope_or_identity_disagrees')
    else:
        public_parent = {key:value for key,value in host.items() if key!='camera_specification'}
        require(packet['binding']==public_parent and packet['facts']==producer['facts'] and packet['frames']==producer['frames']
                and packet['scopes']==producer['scopes'] and task['conditions']==CONDITIONS,
                'full_qualification_response_changed_producer_facts_or_scope')
    regions = {row['object_name']:row for row in task['rows']}
    require(len(regions)==len(task['rows'])==3 and regions.keys()==truth['regions'].keys()
            and task['summary']['observed_region_count']==2 and task['summary']['unknown_region_count']==1,
            'actual_current_full_scene_candidate_set_does_not_match_independent_truth')
    for name,row in regions.items():
        expected_region = truth['regions'][name]
        mesh, = [m for m in capture['meshes'] if m['name']==name]
        ordered = digest(json.dumps({'vertices':mesh['vertices'],'faces':mesh['faces']},
                          sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode())
        require(row['source_triangle_indices']==expected_region['source_triangle_indices']
                and values(row['center_world_m'])==values(expected_region['center_world_m'])
                and exact_direction(row['front_direction_world'],expected_region['plane_normal_integer'])
                and row['source']['ordered_geometry_sha256']==ordered,
                'producer_region_order_center_normal_or_current_faces_changed/'+name)
    proofs = verify_blockers(packet,task,host,source,truth)
    rows = frame_rows(slot,device)
    declaration = module(DENSE/'checks/evidence.py')['frame_declarations']
    merged = {(ref,position,sha,path) for ref,position,sha,path in declaration(view)}
    delivered = {}
    for ref,position,sha,path in merged:
        require(ref in rows and 0 < position < len(view['content']),'discovery_frame_declaration_not_registered')
        block = view['content'][position]
        row = rows[ref]
        original = pin(row['PNG'],slot)
        require(block['type']=='image' and block['mimeType']=='image/png'
                and base64.b64decode(block['data'],validate=True)==Path(original['path']).read_bytes()
                and original['sha256']==sha==row['PNG_sha256']
                and (path is None or Path(path).resolve(strict=True)==Path(original['path'])),
                'actual_discovery_image_block_frame_or_path_mismatch')
        delivered[ref] = {'image_ref':ref,'frame_identity':row['frame_identity'],'scope_id':row['scope_id'],
                          'view':row['view_name'],'PNG':original,'content_block_index':position}
    require(len(delivered) == sum(e['type']=='image' for e in view['content'])
            and len({d['content_block_index'] for d in delivered.values()}) == len(delivered),
            'public_raw_image_frame_count_or_order_contract_changed')
    witnesses = {}
    for role in ('Q','R'):
        name = truth['roles'][role]
        witness = regions[name]['complete_witness']
        require(isinstance(witness,dict) and witness['selected_for_delivery'] is True
                and regions[name]['status']=='covered','current_positive_region_has_no_native_witness/'+role)
        ref = witness['image_ref']
        require(ref in delivered,'positive_witness_png_not_delivered/'+role)
        receipt = delivered[ref]
        require(all(receipt[key]==witness[key] for key in ('frame_identity','scope_id'))
                and receipt['view']==witness['view_name'],'current_witness_reference_or_scope_wrong/'+role)
        proof = verify_frame_proof(slot,rows[ref],producer,capture,source,name,truth)
        require(proof['complete'],'actual_current_region_not_complete_and_readable/'+role)
        observation, = [item for item in producer['facts']['observations']
                        if item['frame_identity']==witness['frame_identity']]
        pixel = observation['pixel_rows'][witness['pixel_row_index']]
        require(pixel['roi_id']==regions[name]['roi_id']
                and pixel['visible_surface_pixels']==proof['selected_surface_pixels']
                and pixel['contrasting_boundary_pixels']==proof['contrasting_boundary_pixels'],
                'actual_producer_witness_pixel_counts_disagree_with_original_arrays/'+role)
        if brief:
            public, = [item for item in records(packet['witnesses'])
                       if decoded['rows'][item['region_index']]['object_name']==name]
            require(public['visible_surface_pixels']==proof['selected_surface_pixels']
                    and public['contrasting_boundary_pixels']==proof['contrasting_boundary_pixels']
                    and public['pixel_row_index']==witness['pixel_row_index'],
                    'brief_witness_pixel_counts_disagree_with_original_arrays/'+role)
        witnesses[role]=proof
    global_scene, = [item for item in delivered.values() if item['scope_id']=='global' and item['view']=='SCENE']
    r = witnesses['R']
    q = witnesses['Q']
    low = verify_frame_proof(slot,rows[global_scene['image_ref']],producer,capture,source,truth['roles']['R'],truth)
    require(low['geometrically_unoccluded'] and low['selected_surface_pixels']<16 and not low['complete']
            and r['view']=='SCENE' and r['scope_id']!='global' and r['frame_identity'] != global_scene['frame_identity']
            and not truth['regions'][truth['roles']['Q']]['directions']['SCENE']['whole_region_clear'] and q['view']!='SCENE',
            'known_low_pixel_or_alternate_view_qualification_not_realized')
    return {'passed':True,'projection':'brief' if brief else 'full','binding':host,'row_names':list(regions),
            'delivered_frames':sorted(delivered.values(),key=lambda row:row['content_block_index']),
            'witnesses':witnesses,'global_R_shortfall':low,'P_blockers':proofs,
            'independent_RIGHT_depth_order':truth['right_blocker_order'],
            'summary':task['summary'],'complete_witness_ref_distinct_from_same_name_global':True}


def verify_readback(slot,reply,expected_frames,*,device=None):
    slot = Path(slot).resolve(strict=True)
    content = result(reply)
    check = module(DENSE/'checks/evidence.py')['frame_declarations']
    rows = frame_rows(slot,device)
    wanted = {frame['image_ref']:frame for frame in expected_frames}
    proof = {}
    for ref,position,sha,path in check(content):
        require(ref in wanted and ref in rows and path is not None and ref not in proof,'bad_readback_scope_or_path')
        expected = wanted[ref]
        row = rows[ref]
        file = pin(path,slot)
        block = content['content'][position]
        require(file == expected['PNG'] and row['frame_identity']==expected['frame_identity']
                and row['scope_id']==expected['scope_id'] and sha==file['sha256']
                and block['type']=='image' and block['mimeType']=='image/png'
                and base64.b64decode(block['data'],validate=True)==Path(file['path']).read_bytes(),
                'closed_original_readback_frame_scope_or_bytes_changed')
        proof[ref] = {'image_ref':ref,'PNG':file,'scope_id':row['scope_id'],'frame_identity':row['frame_identity']}
    require(proof.keys()==wanted.keys() and len(proof)==sum(block['type']=='image' for block in content['content']),
            'not_every_expected_current_original_was_read_back')
    return proof


def measured(measurement,source,truth):
    truth = normalize_truth(truth)
    name = truth['roles']['P']
    expected = truth['measurement']
    require(measurement['object_name']==name and measurement['reference']==expected['reference']
            and not measurement.get('wrong_scope'),'wrong_actual_selected_measurement_or_whole_reference')
    distance = F(str(measurement['distance_m']))
    wanted = F(str(expected['distance_exact_m']))
    a,b = values(measurement['a']),values(measurement['b'])
    delta = tuple(y-x for x,y in zip(a,b,strict=True))
    by_name = {row['name']:row['evaluated'] for row in source['objects']}
    check = module(V/'m5_observe_measure_001/oracle.py')['triangle_distance_squared']
    membership = {}
    for target,indices,point in ((name,truth['regions'][name]['source_triangle_indices'],a),
                                 (expected['reference'],range(len(by_name[expected['reference']]['triangles'])),b)):
        mesh = by_name[target]
        near = [i for i in indices if check(point,tuple(values(mesh['vertices_world_m'][v])
                               for v in mesh['triangles'][i]))<=EPS*EPS]
        require(bool(near),'point_not_on_actual_requested_surface/'+target)
        membership[target] = near
    require(abs(distance-wanted)<=EPS and nearby(delta,[0,0,wanted]) and nearby(measurement['direction_world'],[0,0,1])
            and abs(sqrt(dot(delta,delta))-float(wanted))<=float(EPS),'actual_pair_does_not_attain_bound_and_direction')
    return {'distance_m':str(distance),'direction_world':measurement['direction_world'],
            'point_pair':[measurement['a'],measurement['b']],'actual_source_face_membership':membership}


def verify_measurement(reply,producer,parent_binding,source,truth):
    truth = normalize_truth(truth)
    view = result(reply)
    packet = document(reply)
    task,ref = packet['task_result'],packet['region_ref']
    target = truth['roles']['P']
    original, = [item for item in parent_binding['objects'] if item['object_name']==target]
    require(packet['schema']=='source-region-brief-v2' and view['content'][0]['type']=='text'
            and len(view['content'])==1 and packet['images']==[] and packet['read_only'] is True
            and packet['execution_authority'] is False and packet['region']['object_name']==target
            and ref==producer['region_ref']==producer['task_result']['region_ref']
            and ('region_ref' not in task or task['region_ref']==ref)
            and ref['source_triangle_indices']==truth['regions'][target]['source_triangle_indices']
            and all(ref[key]==original[key] for key in ('host_id','instance_id'))
            and ref['document_epoch']==parent_binding['document_epoch']
            and all(ref['capture_generation'][field]==parent_binding['capture_state'][field]
                    for field in ('instance_id','epoch','revision'))
            and task['measurement_scope']=='complete_selected_source_triangle_union_to_reference_triangle_surface',
            'actual_measurement_not_bound_to_same_current_selected_source')
    fact = task['facts']['surface_proximity']
    witness = fact['value']['nearest_witness']
    require(fact['status']=='measured' and all(task['source_mapping']['nearest_witness'][key]['exact_membership'] is True
                                             for key in ('a','b')), 'independent_selected_source_measurement_not_measured')
    return measured({'object_name':target,'reference':task['reference']['name'],'distance_m':fact['value']['distance_m'],
                     'a':witness['a'],'b':witness['b'],'direction_world':witness['direction_a_to_b']},source,truth)


def fixed_cli(reply,*,require_all):
    view = result(reply)
    helpers,limits = module(V/'m4_cross_scale_live_qualification_001/checks/delivery.py')['budget_helpers']()
    require((limits['MCP_bytes'],limits['history_approximate_tokens'])==(12000,3000),'fixed_CLI_profile_changed')
    checks = []
    for seconds,head in zip(('0.0000','10.0000','100.0000'),(33,34,35),strict=True):
        original = helpers['model_items'](view,seconds)
        upto = helpers['truncate_items'](original,12000)
        retained = helpers['truncate_items'](upto,3000,token_mode=True)
        require(len(original[0]['text'].encode())==head,'fixed_header_length_changed')
        images = [item for item in original if item['type']=='input_image']
        for label,current in (('MCP',upto),('history',retained)):
            same_image = [item for item in current if item['type']=='input_image']==images
            same = original==current
            require(same_image and (same or not require_all),'fixed_budget_lost_required_actual_packet_or_original_PNG')
            checks.append({'head_bytes':head,'phase':label,'exact':same,'original_images_exact':same_image,
                           'text_bytes':sum(len(item['text'].encode()) for item in current[1:] if item['type']=='input_text')})
    return {'passed':True,'require_all_fields':require_all,'original_text_bytes':sum(
            len(block['text'].encode()) for block in view['content'] if block['type']=='text'),'stages':checks}


def verify_closed(slot,raw,truth=None):
    """Recheck the actual closed worker, copy, independent captures and current provenance."""
    slot = Path(slot).resolve(strict=True)
    truth = normalize_truth(truth if truth is not None else slot.parent.parent/'fixture/TRUTH.json')
    require(raw['label']==slot.name and raw['closure_verification']['passed']
            and raw['independent_before_after']['passed'] and raw['asset_sha256']==truth['asset']['sha256'],
            'same_slot_generic_closure_or_independent_sources_not_confirmed')
    formal = module(V/'m4_cross_scale_live_task_formal_001/scoring/formal.py')
    asset = Path(truth['asset']['path']).resolve(strict=True)
    copy = (slot/'native/input.blend').resolve(strict=True)
    start,ready,close = formal['generic_process'](slot,asset,copy,raw['asset_sha256'],raw['owned_deadline_ns'])
    files = (slot/'initial_capture/TERMINAL_SOURCE.json',slot/'TERMINAL_SOURCE.json')
    first,last = (formal['read_capture'](slot,file,raw[key],start['pid'],raw['asset_sha256'])
                  for file,key in zip(files,('initial_source','terminal_source'),strict=True))
    keys = ('source','objects','source_face_offsets','display_object_mask','display_scope','layer_collections','scene_cameras')
    require(all(first[key]==last[key] for key in keys)
            and start['created_after_ns'] <= first['started_ns'] <= raw['ready_ns'] <= raw['cleanup_started_ns']
            <= last['started_ns'] <= close['closed_ns'] <= raw['owned_deadline_ns'],
            'owned_initial_or_terminal_scene_time_geometry_or_display_changed')
    verify_source(first,truth)
    verify_source(last,truth)
    return last,{'passed':True,'pid':start['pid'],'unchanged_fingerprint':ready['initial_fingerprint'],
                 'initial':pin(files[0],slot),'terminal':pin(files[1],slot),
                 'source_copy':pin(copy,slot),'source_asset':pin(asset)}


def public_tools(slot,published):
    inherited = module(DENSE/'checks/evidence.py')['formal_wires']
    namespace = inherited.__globals__
    original = namespace['NS']
    namespace['NS'] = NS
    try:
        return inherited(slot,published)
    finally:
        namespace['NS'] = original


def review_product_frame(slot,row,target,source,truth,tools):
    for attempt in tools['attempts']:
        pinned = (attempt['product'] or {}).get('producer_delivery')
        if pinned is None:
            continue
        producer = read(pinned['path']['path'])
        if any(frame['image_ref']==row['ref'] for frame in producer.get('frames',[])):
            actual = producer_capture(slot,producer['binding'],source)
            return verify_frame_proof(slot,row,producer,actual,source,target,truth)
    raise ValueError('linked_image_has_no_current_producer_frame_capture/'+row['ref'])


def frame_evidence(slot,source,truth,tools,links):
    frame_file = read(slot/'DEVICE_EVIDENCE.json')
    require(frame_file['asset_sha256']==truth['asset']['sha256'] and frame_file['label']==slot.name,
            'frame_manifest_not_current_slot_or_asset')
    frames = frame_file['frames']
    dense = module(DENSE/'checks/evidence.py')
    deliveries = dense['frame_deliveries'](slot,frames,tools)
    native = module(PREVIOUS/'qualification/native.py')
    available = {}
    for row in frames:
        hits = deliveries[row['ref']]
        if not hits:
            continue
        scores = {}
        for role in ('R','Q'):
            target = truth['roles'][role]
            try:
                if row['origin']=='product':
                    scores[role] = review_product_frame(slot,row,target,source,truth,tools)
                else:
                    require(row['origin']=='common_native','unexpected_qualified_image_route')
                    owner = SimpleNamespace(runtime=SimpleNamespace(device=SimpleNamespace(by_ref={row['ref']:row})))
                    scores[role] = native['prove_image'](slot,owner,row['ref'],target,source=source,geometry=truth)
            except (ValueError,TypeError,KeyError,OSError,ImportError) as error:
                scores[role] = {'complete':False,'issue':str(error)}
        available[row['ref']] = {'post_close_png':pin(row['PNG'],slot),'by_role':scores,
                                 'actual_deliveries':hits,'frame_ref':row['ref']}
    linked = {}
    for link in links:
        path = Path(link)
        if not path.is_absolute() or not path.is_file():
            continue
        candidates = [entry for entry in available.values() if Path(entry['post_close_png']['path'])==path.resolve()]
        if len(candidates)==1:
            linked[link] = candidates[0]
    return available,linked


def load_slot(slot,truth=None):
    """Extract the closed formal original, exact frame receipts and first-packet exposure."""
    slot = Path(slot).resolve(strict=True)
    truth = normalize_truth(truth if truth is not None else slot.parent.parent/'fixture/TRUTH.json')
    installed = read(INSTALLED)
    if installed['dependency_root'] not in sys.path:
        sys.path.insert(0,installed['dependency_root'])
    dense = module(DENSE/'checks/evidence.py')
    previous_score = module(V/'m1_source_region_first_packet_consumption_001/checks/score.py')
    raw,pub = dense['publication'](slot)
    require(raw['status']==pub['status']=='completed' and raw['model_consumers']==1,
            'no_completed_formal_consumer_to_score')
    source,closure = verify_closed(slot,raw,truth)
    answer = dense['closed_answer'](slot,raw)
    tools = public_tools(slot,pub)
    links = list(previous_score['final_links'](answer['text']))
    frames,linked = frame_evidence(slot,source,truth,tools,links)
    matching = []
    aliases = {}
    for row in tools['attempts']:
        args = read(row['TX']['path'])['params']['arguments']
        query = args.get('query') or {}
        if (not row['is_error'] and row['model_visible_as_public_CLI_tool_result']
                and row['tool']=='human_eye_scene_observe' and query.get('mode')=='active_observation'
                and query.get('region_task')==CONDITIONS and args.get('include_image',True)):
            reply = result(read(row['RX']['path']))
            packet = document(reply)
            archive = (row['product'] or {}).get('producer_delivery')
            if archive:
                producer = read(archive['path']['path'])
                producer_capture(slot,producer['binding'],source)
                for candidate in producer['facts']['region_task']['rows']:
                    region = truth['regions'].get(candidate['object_name'])
                    if region and candidate['source_triangle_indices']==region['source_triangle_indices']:
                        aliases.setdefault(candidate['object_name'],{})[candidate['roi_id']] = candidate['source_triangle_indices']
            matching.append({'attempt':row['attempt'],'original_arguments':args,
                'projection':'brief' if packet.get('schema')==BRIEF else 'full',
                'published_body_sha256':digest(reply['content'][0]['text'].encode()),
                'original_text_bytes':row['text_UTF8_bytes'],'actual_images':row['image_blocks'],'original_packet':row['RX'],
                'fixed_history_whole':row.get('fixed_history_whole')})
    return {'slot':slot.name,'answer':answer,'closed_source':closure,'available_frames':frames,'link_frames':linked,
            'truth':truth,'source':source,'actual_attempts':tools['attempts'],
            'first_matching_task':matching[0] if matching else None,'matching_task_requests':matching,
            'budget':raw['budget'],'roi_aliases':aliases}
