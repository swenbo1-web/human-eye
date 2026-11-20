"""Bind original observation sematics, frames and occluders to their actual current source."""

from fractions import Fraction
import json
from pathlib import Path
import runpy


HERE = Path(__file__).resolve().parent
V = HERE.parents[1]
PIXEL_ROOT = V / 'm4_cross_scale_pixel_evidence_001'
PIXEL_PATH = PIXEL_ROOT / 'checks/assess_live.py'
BRIEF_PATH = V / 'm4_dense_region_brief_001/checks/brief_schema.py'
BLOCKER_PATH = V / 'm4_bound_blocker_evidence_001/checks/live_review.py'
PROOF_PATH = BLOCKER_PATH.with_name('geometry_controls.py')
pixel, brief, blocker, proof = (runpy.run_path(str(path)) for path in
                                (PIXEL_PATH, BRIEF_PATH, BLOCKER_PATH, PROOF_PATH))
read, require, verified, digest = (pixel[key] for key in ('read', 'require', 'verified', 'digest'))
prior, checker = pixel['prior'], pixel['checker']


def verify_frames(slot, producer, terminal, truth, images, audit):
    scopes = {scope['scope_id']: scope for scope in producer['scopes']}
    selected, = producer['frames']
    (image_info, png), = images
    frames = producer['constructed_frames']
    local, = [scope for key, scope in scopes.items() if key != 'global']
    rows = {row['object_name']: row for row in producer['facts']['region_task']['rows']}
    checker['local_binding_checks'](local, producer['binding'], rows['N10']['source'], audit)
    require([(frame['scope_id'], frame['view_name']) for frame in frames] ==
            [('global', 'SCENE'), ('global', 'TOP'), (local['scope_id'], 'TOP')]
            and selected == frames[0] and selected['image_ref'] == image_info['ref'],
            'wrong_actual_constructed_or_delivered_frames')
    results = []
    for frame in frames:
        scope = scopes[frame['scope_id']]
        actual_refs = [row['frame_identity'] for row in frames if row['scope_id'] == scope['scope_id']]
        require(actual_refs == scope['frame_refs'] == [row['frame_identity'] for row in scope['steps']]
                == [row['frame_identity'] for row in scope['facts']['observations']],
                'actual_frame_and_scope_history_mismatch')
        results.append(prior['frame_payload'](slot, frame, scope, terminal, truth, png if frame == selected else None))
    expected = [(1489, 546, True), (5026, 0, False), (8835, 0, False)]
    for frame, target, (surface, contrast, qualifies) in zip(results, ('N22', 'N10', 'N10'), expected, strict=True):
        require(frame['independent_pixels'][target] == dict(target_surface_pixels=surface,
                contrasting_boundary_pixels=contrast, qualifies=qualifies), 'independent_actual_pixel_outcome_changed/' + target)
    return results, local['scope_id']


def verify_blockers(body, producer, terminal, truth):
    source = producer['binding']
    task = producer['facts']['region_task']
    internal, public = task['blocker_evidence'], body['blocker_evidence']
    require(set(internal) == {'scope_id', 'binding_sha256', 'source_binding_sha256', 'camera_identity', 'rows'}
            and internal['scope_id'] == 'global'
            and all(internal[key] == source[key] for key in ('binding_sha256', 'source_binding_sha256', 'camera_identity'))
            and set(public) == {'scope_index', 'columns', 'rows', 'meaning'}
            and tuple(public['columns']) == blocker['COLUMNS'] and public['meaning'] == blocker['MEANING'],
            'bad_blocker_schema_or_parent_source')
    ix = blocker['indexed']
    public_scope = dict(zip(body['scopes']['columns'], ix(body['scopes']['rows'], public['scope_index'],
                            'wrong_blocker_global_scope'), strict=True))
    require(public_scope['scope_id'] == 'global' and all(public_scope[key] == source[key] for key in
            ('binding_sha256', 'camera_identity')), 'wrong_public_blocker_parent_scope')
    region_index, target = next((i, row) for i, row in enumerate(task['rows']) if row['object_name'] == 'N11')
    actual_index = body['region_task']['columns'].index('roi_id')
    require(body['region_task']['rows'][region_index][actual_index] == target['roi_id'],
            'blocked_region_index_not_current')
    views = {row['name']: row for row in source['camera_specification']['views']}
    by_name = {row['name']: row for row in terminal['objects']}
    oracle = next(row['finite_direction_proofs'] for row in truth['eligible'] if row['object_name'] == 'N11')
    corners = proof['region_corners'](target)
    observed, names = [], set()
    require(len(internal['rows']) == len(public['rows']) == len(views) == 6, 'need_six_bound_blockers')
    for row, public_row in zip(internal['rows'], public['rows'], strict=True):
        name = row['view_name']
        object_index, face_index = row['blocker_object_index'], row['source_triangle_index']
        require(set(row) == blocker['ORIGINAL_KEYS'] and row['roi_id'] == target['roi_id'] and name not in names
                and name in views and public_row == [region_index, name, object_index, face_index]
                and all(type(index) is int for index in (object_index, face_index, public_row[0])),
                'blocker_table_source_index_or_view_mismatch/' + name)
        obj = ix(source['objects'], object_index, 'out_of_range_blocker_object')
        view = views[name]
        mesh = by_name[obj['object_name']]
        require(obj == dict(zip(body['objects']['columns'], ix(body['objects']['rows'], object_index,
                                         'out_of_range_public_blocker_object'), strict=True))
                and mesh['object_id'] == obj['host_id'] == row['blocker_host_id']
                and mesh['instance_id'] == obj['instance_id'] == row['blocker_instance_id']
                and (object_index != target['object_index'] or face_index not in target['source_triangle_indices']),
                'current_actual_blocker_object_or_instance_mismatch/' + name)
        evaluated = mesh['evaluated']
        face = ix(evaluated['triangles'], face_index, 'out_of_range_current_blocking_triangle')
        points = [ix(evaluated['vertices_world_m'], index, 'out_of_range_blocker_point') for index in face]
        area, screen = proof['independent_overlap'](points, corners, view)
        expected = [hit for hit in oracle[name]['positive_area_occluders']
                    if hit['object_name'] == obj['object_name'] and hit['source_triangle_index'] == face_index]
        require(not oracle[name]['whole_region_clear'] and oracle[name]['direction'] == view['direction_rational']
                and len(expected) == 1 and area == Fraction(expected[0]['rectangle_overlap_fraction']) > 0
                and screen == Fraction(row['overlap_area_screen_exact']) > 0
                and blocker['triangle_key_sha'](points) == row['triangle_geometry_id'],
                'blocker_fails_independent_actual_triangle_overlap/' + name)
        names.add(name)
        observed.append({'view_name': name, 'object': obj['object_name'], 'source_triangle_index': face_index,
                         'target_chart_area_exact': str(area), 'screen_area_exact': str(screen),
                         'triangle_geometry_id': row['triangle_geometry_id']})
    return observed


def verify_observation(slot, result, producer, terminal, installed, truth):
    body = json.loads(result['content'][0]['text'])
    public, images = brief['verify_brief'](result)
    parent = producer['binding']
    require(public['status'] == producer['status'] == 'complete'
            and public['observation_status'] == producer['observation_status'] == 'region_task_observed'
            and public['read_only'] is producer['read_only'] is True
            and public['execution_authority'] is producer['execution_authority'] is False
            and public['session_id'] == producer['session_id']
            and public['binding'] == {key: val for key, val in parent.items()
                                      if key not in ('schema', 'objects', 'camera_policy', 'camera_specification')},
            'public_observation_or_current_parent_does_not_match_actual_producer')
    task, audit = pixel['current_geometry'](slot, producer, terminal, installed, truth)
    shown = {row['object_name']: row for row in public['region_task']['rows']}
    actual_task = producer['facts']['region_task']
    require(len(shown) == len(public['region_task']['rows']) == 3 and shown.keys() == task.keys()
            and all(public['region_task'][key] == actual_task[key] for key in ('schema', 'summary', 'conditions')),
            'bad_public_region_task_roster_or_summary')
    frames, local_id = verify_frames(slot, producer, terminal, truth, images, audit)
    for name, row in shown.items():
        original = dict(task[name])
        if original['complete_witness'] is not None:
            original['complete_witness'] = {**original['complete_witness'], 'native_content_block_index': 1}
        require((row['status'], row['reason']) == pixel['ROW_OUTCOMES'][name]
                and {key: value for key, value in row.items() if key != 'pixel_shortfall'} == original
                and ('pixel_shortfall' in row) == (name == 'N10'), 'original_and_brief_region_row_mismatch/' + name)
    require(shown['N10']['pixel_shortfall'] == {
        'scope_id': local_id, 'view_name': 'TOP', 'visible_surface_pixels': 8835, 'contrasting_boundary_pixels': 0,
        'minimum_surface_pixels': 16, 'minimum_boundary_pixels': 4, 'minimum_rgb_boundary_contrast': 24,
        'image_delivered': False, 'native_content_block_index': None}
        and set(shown['N11']['view_reasons']['positive_area_occlusion']) == set(truth['directions']),
        'public_shortfall_or_all_six_geometric_occlusion_outcomes_changed')
    witness, = public['witness_pixels']['rows']
    decoded_witness = dict(zip(public['witness_pixels']['columns'], witness, strict=True))
    require(decoded_witness['roi_id'] == shown['N22']['roi_id'] and decoded_witness['frame_identity'] ==
            producer['frames'][0]['frame_identity'] and decoded_witness['visible_surface_pixels'] == 1489
            and decoded_witness['contrasting_boundary_pixels'] == 546, 'public_N22_witness_identity_or_pixels_changed')
    occlusion = verify_blockers(body, producer, terminal, truth)
    counts = producer['work']
    require(counts['raster_attempts'] == counts['raster_completed'] == 3 and counts['capture_calls'] ==
            counts['partition_calls'] == 1 and counts['index_calls'] == 2, 'unexpected_cold_observation_work')
    return {'frames': frames, 'blockers': occlusion, 'public_states': {
                name: {'status': row['status'], 'reason': row['reason'],
                       'triangle_indices': row['source_triangle_indices']} for name, row in shown.items()},
            'pixel_shortfall': shown['N10']['pixel_shortfall'], 'selected_png_sha256': [a['PNG_sha256'] for a, _ in images],
            'producer_work': counts}
