"""Prove the N11-to-N22 whole-object gap using independent exact geometry."""

from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
import json
import math
from pathlib import Path
import runpy


HERE = Path(__file__).resolve().parent
V = HERE.parents[1]
ORACLE = V / 'm5_observe_measure_001/oracle.py'
SOURCE_CHECK = V / 'm5_observe_measure_001/source_contract_r2.py'
TERMINAL = Path('D:/he_m4_cross_scale_pixel_evidence_001/slots/P1/TERMINAL_SOURCE.json')
TERMINAL_SHA = 'a550a7018e07fc8e18204ffe77231b254d93a9558b2114036d2113898120a52b'
ASSET_SHA = '91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85'
SOURCE_SHA = '301caf777d446938497b53d5d49d67279cdcdb4ba2ee03e8aeb7e737c66076b6'
NAMES = ('N11', 'N22')
SELECTORS = [{'name': name} for name in NAMES]
QUERY = {'mode': 'task', 'objects': SELECTORS, 'requested_facts': ['surface_proximity']}
A_MAX = F('67108865/268435456')
B_MIN = F('297963347/1073741824')
DISTANCE = F('29527887/1073741824')
LONGITUDINAL_INDEX = 1
TOLERANCE = F.from_float(1e-9)
BOUNDS = (28, 416, 744)

geometry = runpy.run_path(str(ORACLE))
contracts = runpy.run_path(str(SOURCE_CHECK))
membership = geometry['membership']
triangle_distance_squared = geometry['triangle_distance_squared']
generation = contracts['generation']
geometry_alias = contracts['geometry_alias']


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                             allow_nan=False).encode('utf-8')).hexdigest()


def pin(path, raw=None):
    raw = path.read_bytes() if raw is None else raw
    return {'path': str(path.resolve()), 'bytes': len(raw), 'sha256': sha256(raw).hexdigest()}


def vector(point):
    require(type(point) in (list, tuple) and len(point) == 3 and all(
        type(p) in (int, float) and (type(p) is int or math.isfinite(p)) for p in point),
        'finite_binary64_three_coordinate_point_required')
    return tuple(F(value) for value in point)


def meshes(terminal):
    require(terminal['source']['asset_sha256'] == ASSET_SHA and terminal['source']['frame'] == 1
            and terminal['source']['subframe'] == 0.0 and terminal['source']['scale_length'] == 1.0
            and terminal['source']['source_index_domain'] ==
            'zero_based_object_local_current_evaluated_capture_triangle_rows', 'unfrozen_asset_or_index_domain')
    objects = terminal['objects']
    indexed = {row['name']: row for row in objects}
    require(len(indexed) == len(objects) and len({row['object_id'] for row in objects}) == len(objects),
            'frozen_object_names_and_ids_must_be_unique')
    offsets = [0]
    vertices = 0
    for row in objects:
        mesh = row['evaluated']
        vertices += len(mesh['vertices_world_m'])
        offsets.append(offsets[-1] + len(mesh['triangles']))
    require((len(indexed), vertices, offsets[-1]) == BOUNDS and
            terminal['source_face_offsets'] == offsets, 'frozen_full_source_counts_disagree')
    return indexed


def ordered_mesh(row):
    return {'vertices': row['evaluated']['vertices_world_m'], 'faces': row['evaluated']['triangles']}


def facing_geometry(row, find_extreme):
    data = ordered_mesh(row)
    points = [vector(value) for value in data['vertices']]
    faces = data['faces']
    require(bool(faces) and all(type(face) is list and len(face) == 3 and all(
        type(i) is int and 0 <= i < len(points) for i in face) for face in faces), 'invalid_source_triangles')
    # Every coordinate on a source triangle is a convex combination of its vertices.
    extent = find_extreme(points[i][LONGITUDINAL_INDEX] for face in faces for i in face)
    extrema = [idx for idx, face in enumerate(faces)
               if all(points[i][LONGITUDINAL_INDEX] == extent for i in face)]
    return data, points, extent, extrema


def freeze_truth(terminal_path=TERMINAL):
    terminal_path = Path(terminal_path)
    raw = terminal_path.read_bytes()
    terminal_pin = pin(terminal_path, raw)
    require(terminal_pin['sha256'] == TERMINAL_SHA, 'old_source_terminal_bytes_changed')
    terminal = json.loads(raw)
    indexed = meshes(terminal)
    witness_x, witness_z = F(0), F(1, 2)
    objects, proof = [], []
    for name, extremum, find_extreme in zip(NAMES, (A_MAX, B_MIN), (max, min), strict=True):
        data, points, actual, extrema = facing_geometry(indexed[name], find_extreme)
        require(extremum == actual, 'axis_separation_extremum_changed')
        witness = witness_x, extremum, witness_z
        exact_faces = [idx for idx in extrema if triangle_distance_squared(
            witness, tuple(points[i] for i in data['faces'][idx])) == 0]
        require(bool(exact_faces), 'independent_lower_bound_not_attained_on_source_faces')
        objects.append({'name': name, 'source_triangle_count': len(data['faces']), 'vertex_count': len(points),
                        'ordered_geometry_sha256': digest(data), 'geometry_id': geometry_alias(data),
                        'facing_y_m_exact': str(actual), 'facing_source_triangles': extrema})
        proof.append({'name': name, 'world_m_exact': [str(v) for v in witness],
                      'exact_source_triangles': exact_faces})
    lower_bound = B_MIN - A_MAX
    require(lower_bound == DISTANCE > 0 and F(float(lower_bound)) == lower_bound, 'frozen_gap_changed')
    return {'schema': 'm5-exact-whole-object-gap-truth-v1', 'passed': True, 'asset_sha256': ASSET_SHA,
            'counts': {'objects': BOUNDS[0], 'vertices': BOUNDS[1], 'source_triangles': BOUNDS[2]},
            'terminal_sha256': TERMINAL_SHA, 'measurement_scope': 'whole_objects', 'object_pair': list(NAMES),
            'ordered_objects': objects, 'global_lower_bound_m_exact': str(lower_bound),
            'global_minimum_m_binary64': float(lower_bound), 'direction_a_to_b': [0, 1, 0],
            'attaining_pair': proof, 'particular_point_pair_required': False,
            'publication_tolerance_m': str(TOLERANCE), 'source_pins': [
                terminal_pin, pin(Path(__file__)), pin(ORACLE), pin(SOURCE_CHECK)]}


def full_generation(parent_capture, parent_binding, selected_capture):
    if parent_capture is None and parent_binding is None and selected_capture is None:
        return None
    state = parent_capture['capture_state'] if parent_capture is not None else parent_binding['capture_state']
    full = generation(state)
    if parent_capture is not None and parent_binding is not None:
        require(parent_binding['capture_state'] == state and parent_binding['document_epoch'] ==
                parent_capture['host_identity']['document_epoch'] and
                parent_binding['scene_revision'] == parent_capture['revision'], 'observation_binding_not_same_capture')
    if selected_capture is not None and parent_capture is not None:
        require(generation(selected_capture['capture_state']) == full, 'split_selected_not_same_capture_generation')
        require(selected_capture['host_identity']['document_epoch'] ==
                parent_capture['host_identity']['document_epoch'], 'split_selected_document_epoch_mismatch')
    return list(full)


def check_capture_object(capture, row):
    found = [mesh for mesh in capture['meshes'] if mesh['object_id'] == row['object_id']]
    require(len(found) == 1 and found[0]['name'] == row['name'] and
            capture['host_identity']['object_instances'].get(row['object_id']) == row['instance_id']
            and digest({'vertices': found[0]['vertices'], 'faces': found[0]['faces']}) == digest(ordered_mesh(row)),
            'capture_source_object_instance_or_ordered_geometry_mismatch/' + row['name'])


def verify_binding(task, indexed, selection_capture, parent_binding, parent_capture):
    binding = task['binding']
    packed = binding['objects']
    rows = [indexed[name] for name in NAMES]
    ordered = [{'name': row['name'], 'object_id': row['object_id']} for row in rows]
    require(packed == ordered and binding['candidate_count'] == BOUNDS[0] and binding['selected_count'] == 2
            and binding['runtime_source_sha256'] == SOURCE_SHA and binding['source'] == 'blender'
            and binding['source_status'] == 'loaded_generation' and binding['disk_status'] == 'disk_not_checked',
            'task_binding_not_current_product_scope_or_ordered_object_pair')
    actual_generation = full_generation(parent_capture, parent_binding, selection_capture)
    if parent_capture is not None:
        require(parent_capture.get('capture_scope', 'complete_scene_meshes') ==
                parent_capture['host_identity']['capture_scope'] == 'complete_scene_meshes' and
                len(parent_capture['meshes']) == BOUNDS[0], 'parent_capture_not_full_scope')
        for row in rows:
            check_capture_object(parent_capture, row)
    scope = binding['capture_scope']
    if scope == 'selected_objects':
        require('observation_source' not in binding, 'split_binding_must_not_claim_derived_source')
        key = digest(['task', SELECTORS])
        if selection_capture is not None:
            selected = selection_capture['task_selection']
            require(selection_capture['capture_scope'] == scope and selection_capture['revision'] ==
                    binding['scene_revision'] and selected['selectors'] == SELECTORS and
                    selected['bindings'] == packed and selected['candidate_count'] == BOUNDS[0]
                    and selected['pair_reason'] is None and len(selection_capture['meshes']) == 2,
                    'split_task_revision_or_selection_source_mismatch')
            require(selection_capture['capture_state']['selection_key'] == key, 'split_selection_key_mismatch')
            for row in rows:
                check_capture_object(selection_capture, row)
        return {'scope': scope, 'expected_selection_key': key, 'generation': actual_generation,
                'independent_capture_binding_checked': selection_capture is not None and parent_capture is not None}
    require(scope == 'observation_task_objects' and selection_capture is None, 'unexpected_measurement_capture_scope')
    source = binding['observation_source']
    require(source['schema'] == 'active-observation-task-source-v1'
            and source['measurement_scope'] == 'whole_objects' and source['capture_scope'] == scope
            and source['parent_capture_scope'] == 'complete_scene_meshes', 'joint_whole_object_scope_mismatch')
    if parent_binding is not None:
        require(source['parent_binding_sha256'] == parent_binding['binding_sha256']
                and source['parent_source_binding_sha256'] == parent_binding['source_binding_sha256']
                and parent_binding['capture_scope'] == source['parent_capture_scope'], 'joint_source_parent_binding_mismatch')
    state = source['capture_state']
    require(actual_generation is None or list(generation(state)) == actual_generation, 'joint_source_generation_mismatch')
    by_id = {row['object_id']: row for row in source['objects']}
    require(len(source['objects']) == len(by_id) == 2 and set(by_id) == {row['object_id'] for row in rows},
            'joint_source_object_bijection_mismatch')
    if parent_capture is not None:
        require(list(by_id) == [row['object_id'] for row in parent_capture['meshes']
                                if row['object_id'] in by_id], 'joint_source_parent_order_mismatch')
    for row in rows:
        source_row = by_id[row['object_id']]
        data = ordered_mesh(row)
        count = len(data['faces'])
        require(source_row['instance_id'] == row['instance_id'] and
                source_row['source_triangle_count'] == count and
                source_row['source_triangle_index_ranges'] == [[0, count - 1]]
                and source_row['ordered_geometry_sha256'] == digest(data)
                and source_row['geometry_id'] == geometry_alias(data), 'joint_source_current_whole_geometry_mismatch')
        index = source_row['observation_object_index']
        require(type(index) is int and 0 <= index < BOUNDS[0], 'joint_source_parent_index_invalid')
        if parent_capture is not None:
            require(parent_capture['meshes'][index]['object_id'] == row['object_id'], 'joint_source_parent_index_mismatch')
        if parent_binding is not None and 'objects' in parent_binding:
            expected = parent_binding['objects'][index]
            require((expected['host_id'], expected['instance_id']) ==
                    (row['object_id'], row['instance_id']), 'joint_source_parent_row_mismatch')
    key = digest(['observation_task', source['parent_source_binding_sha256'], QUERY, source['objects']])
    require(state['selection_key'] == key and binding['scene_revision'] == 'observation-task:' + key,
            'joint_derived_selection_key_or_revision_mismatch')
    return {'scope': scope, 'expected_selection_key': key, 'generation': list(generation(state)),
            'independent_capture_binding_checked': parent_binding is not None and parent_capture is not None}


def verify_measurement(task, terminal, *, truth=None, selection_capture=None, parent_binding=None, parent_capture=None):
    """Validate an actual split task or a nested joint task against original mesh triangles."""
    truth = freeze_truth() if truth is None else truth
    indexed = meshes(terminal)
    require(truth['terminal_sha256'] == TERMINAL_SHA and truth['global_lower_bound_m_exact'] == str(DISTANCE)
            and truth['object_pair'] == list(NAMES), 'reference_truth_binding_mismatch')
    require(task['schema_version'] == 'task-query-v3' and task['result_kind'] == 'task_query'
            and task['status'] == 'observed' and task['unit'] == 'm' and task['coordinate_frame'] == 'world'
            and task['pair_order'] == 'A_to_B' and task['execution_authority'] is False,
            'task_result_not_current_read_only_world_measurement')
    binding = verify_binding(task, indexed, selection_capture, parent_binding, parent_capture)
    require(set(task['facts']) == {'surface_proximity'}, 'unexpected_task_fact_set')
    gap = task['facts']['surface_proximity']
    require(gap['status'] == gap['witness_status'] == gap['direction_status'] == 'measured'
            and gap['semantics'] == 'current_evaluated_triangle_surfaces_world_metres',
            'surface_proximity_not_measured_with_current_world_semantics')
    value = gap['value']
    numeric = value['distance_m']
    require(type(numeric) in (int, float) and numeric == float(DISTANCE),
            'published_whole_object_minimum_does_not_match_exact_bound')
    witness = value['nearest_witness']
    points = [vector(witness[endpoint]) for endpoint in ('a', 'b')]
    displacement = [hi - lo for lo, hi in zip(*points, strict=True)]
    require(sum((actual - exact)**2 for actual, exact in zip(displacement, (F(0), DISTANCE, F(0)), strict=True))
            <= TOLERANCE**2, 'published_nearest_point_displacement_mismatch')
    require(vector(witness['direction_a_to_b']) == (F(0), F(1), F(0)), 'published_A_to_B_axis_mismatch')
    results = []
    for known, name, point in zip(truth['ordered_objects'], NAMES, points, strict=True):
        data = ordered_mesh(indexed[name])
        require(known['name'] == name and known['ordered_geometry_sha256'] == digest(data),
                'current_object_source_changed_from_frozen_geometry/' + name)
        checked = membership(point, data['vertices'], data['faces'])
        require(bool(checked['within_publication_tolerance_source_triangle_indices']),
                'published_nearest_point_outside_current_source_triangles/' + name)
        require(abs(point[LONGITUDINAL_INDEX] - F(known['facing_y_m_exact'])) <= TOLERANCE,
                'published_nearest_point_off_separating_face/' + name)
        results.append({'name': name, 'object_id': indexed[name]['object_id'],
                        'instance_id': indexed[name]['instance_id'], 'source_triangle_count': len(data['faces']), **checked})
    return {'passed': True, 'distance_m': numeric, 'distance_exact_m': str(DISTANCE), 'direction_a_to_b': [0, 1, 0],
            'nearest_witness': witness, 'displacement_exact_m': [str(v) for v in displacement],
            'measurement_scope': 'whole_objects', 'serialized_pair_order': list(NAMES),
            'bindings': binding, 'current_source_membership': results}


def controls(truth, terminal):
    indexed = meshes(terminal)
    bindings = [{'name': name, 'object_id': indexed[name]['object_id']} for name in NAMES]
    selected_ids = {row['object_id'] for row in bindings}
    parent_rows = [{'host_id': obj['object_id'], 'instance_id': obj['instance_id']}
                   for obj in terminal['objects']]
    def capture(objects):
        return {'meshes': [{'name': obj['name'], 'object_id': obj['object_id'], **ordered_mesh(obj)}
                           for obj in objects],
                'host_identity': {'document_epoch': 'controls', 'object_instances': {
                    obj['object_id']: obj['instance_id'] for obj in objects}}}
    state = {'instance_id': 'controls', 'epoch': 1, 'revision': 1}
    parent_capture = {**capture(terminal['objects']), 'revision': 'blender:control_parent',
                      'capture_state': {**state, 'selection_key': digest(['scene', list(indexed)])}}
    parent_capture['host_identity']['capture_scope'] = 'complete_scene_meshes'
    parent_binding = {'binding_sha256': '1' * 64, 'source_binding_sha256': '2' * 64,
                      'capture_scope': 'complete_scene_meshes', 'document_epoch': 'controls',
                      'scene_revision': parent_capture['revision'],
                      'capture_state': parent_capture['capture_state'], 'objects': parent_rows}
    selection_capture = {**capture([indexed[name] for name in NAMES]),
                         'capture_scope': 'selected_objects', 'revision': 'blender:controls',
                         'capture_state': {**state, 'selection_key': digest(['task', SELECTORS])},
                         'task_selection': {'selectors': SELECTORS, 'bindings': bindings,
                                            'pair_reason': None, 'candidate_count': BOUNDS[0]}}
    left, right = [[float(F(v)) for v in row['world_m_exact']] for row in truth['attaining_pair']]
    split = {'schema_version': 'task-query-v3', 'result_kind': 'task_query', 'status': 'observed',
             'unit': 'm', 'coordinate_frame': 'world', 'pair_order': 'A_to_B', 'execution_authority': False,
             'facts': {'surface_proximity': {'status': 'measured', 'witness_status': 'measured',
                       'direction_status': 'measured', 'semantics': 'current_evaluated_triangle_surfaces_world_metres',
                       'value': {'distance_m': float(DISTANCE), 'nearest_witness': {
                           'a': left, 'b': right, 'direction_a_to_b': [0, 1, 0]}}}},
             'binding': {'objects': bindings, 'candidate_count': BOUNDS[0], 'selected_count': 2,
                         'runtime_source_sha256': SOURCE_SHA, 'source': 'blender', 'source_status': 'loaded_generation',
                         'disk_status': 'disk_not_checked', 'scene_revision': selection_capture['revision'],
                         'capture_scope': 'selected_objects'}}
    kwargs = {'truth': truth, 'parent_binding': parent_binding, 'parent_capture': parent_capture}
    split_result = verify_measurement(split, terminal, selection_capture=selection_capture, **kwargs)
    joint = deepcopy(split)
    source_objects = []
    for idx, obj in enumerate(terminal['objects']):
        if obj['object_id'] not in selected_ids:
            continue
        data = ordered_mesh(obj)
        count = len(data['faces'])
        source_objects.append({'object_id': obj['object_id'], 'instance_id': obj['instance_id'],
                               'ordered_geometry_sha256': digest(data), 'geometry_id': geometry_alias(data),
                               'observation_object_index': idx, 'source_triangle_count': count,
                               'source_triangle_index_ranges': [[0, count - 1]]})
    key = digest(['observation_task', parent_binding['source_binding_sha256'], QUERY, source_objects])
    joint['binding'].update(capture_scope='observation_task_objects', scene_revision='observation-task:' + key,
                            observation_source={'schema': 'active-observation-task-source-v1',
                                'measurement_scope': 'whole_objects', 'capture_scope': 'observation_task_objects',
                                'parent_capture_scope': 'complete_scene_meshes',
                                'parent_binding_sha256': parent_binding['binding_sha256'],
                                'parent_source_binding_sha256': parent_binding['source_binding_sha256'],
                                'capture_state': {**state, 'selection_key': key}, 'objects': source_objects})
    joint_result = verify_measurement(joint, terminal, **kwargs)
    alternative = deepcopy(joint)
    point_pair = alternative['facts']['surface_proximity']['value']['nearest_witness']
    for endpoint in ('a', 'b'):
        point_pair[endpoint][0], point_pair[endpoint][2] = 0.375, 0.49
    alternative_result = verify_measurement(alternative, terminal, **kwargs)

    negative_cases = [
        ('wrong_distance', ['facts', 'surface_proximity', 'value', 'distance_m'], 0.01,
         'published_whole_object_minimum_does_not_match_exact_bound'),
        ('false_point_tangent', ['facts', 'surface_proximity', 'value', 'nearest_witness', 'a', 0], 0.125,
         'published_nearest_point_displacement_mismatch'),
        ('direction_reversed', ['facts', 'surface_proximity', 'value', 'nearest_witness', 'direction_a_to_b'], [0, -1, 0],
         'published_A_to_B_axis_mismatch'),
        ('wrong_whole_scope', ['binding', 'observation_source', 'measurement_scope'], 'surface_subset',
         'joint_whole_object_scope_mismatch'),
        ('parent_source_changed', ['binding', 'observation_source', 'parent_source_binding_sha256'], '0' * 64,
         'joint_source_parent_binding_mismatch'),
        ('wrong_frame_generation', ['binding', 'observation_source', 'capture_state', 'revision'], 2,
         'joint_source_generation_mismatch'),
        ('wrong_instance', ['binding', 'observation_source', 'objects', 0, 'instance_id'], 'stale',
         'joint_source_current_whole_geometry_mismatch'),
        ('omitted_last_source_face', ['binding', 'observation_source', 'objects', 0, 'source_triangle_index_ranges'],
         [[0, 10]], 'joint_source_current_whole_geometry_mismatch'),
        ('wrong_parent_index', ['binding', 'observation_source', 'objects', 0, 'observation_object_index'], 30,
         'joint_source_parent_index_invalid'),
        ('wrong_joint_selection_key', ['binding', 'observation_source', 'capture_state', 'selection_key'], 'x',
         'joint_derived_selection_key_or_revision_mismatch'),
    ]
    checks = []
    for name, fields, value, expected_reason in negative_cases:
        false = deepcopy(joint)
        entry = false
        for field in fields[:-1]:
            entry = entry[field]
        entry[fields[-1]] = value
        try:
            verify_measurement(false, terminal, **kwargs)
        except ValueError as error:
            require(str(error) == expected_reason, 'control_rejected_for_wrong_reason/' + name)
            checks.append({'case': name, 'reason': str(error)})
        else:
            raise ValueError('negative_control_not_refused/' + name)
    false_capture = deepcopy(selection_capture)
    false_capture['capture_state']['selection_key'] = key
    try:
        verify_measurement(split, terminal, selection_capture=false_capture, **kwargs)
    except ValueError as error:
        require(str(error) == 'split_selection_key_mismatch', 'control_split_invalid_selection')
        checks.append({'case': 'used_joint_key_for_split', 'reason': str(error)})
    else:
        raise ValueError('negative_control_not_refused/split_selection')

    false_pair = deepcopy(joint)
    points = false_pair['facts']['surface_proximity']['value']['nearest_witness']
    for endpoint in ('a', 'b'):
        points[endpoint][0] = 1.0
    try:
        verify_measurement(false_pair, terminal, **kwargs)
    except ValueError as error:
        require(str(error) == 'published_nearest_point_outside_current_source_triangles/N11',
                'control_rejected_for_wrong_reason/off_mesh_minimum')
        checks.append({'case': 'same_distance_but_off_mesh_pair', 'reason': str(error)})
    else:
        raise ValueError('negative_control_not_refused/off_mesh_minimum')

    return {'synthetic_wire_control_only': True, 'split': split_result, 'joint': joint_result,
            'alternate_closest_pair': alternative_result, 'negative_results': checks}


def write_truth(output=HERE / 'MEASUREMENT_TRUTH.json'):
    result = freeze_truth()
    result['controls'] = controls(result, json.loads(TERMINAL.read_bytes()))
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, sort_keys=True, indent=2, ensure_ascii=False)
        stream.write('\n')
    return result


if __name__ == '__main__':
    receipt = write_truth()
    print('Exact source gap:', receipt['global_lower_bound_m_exact'],
          receipt['global_minimum_m_binary64'], 'm, +Y')
    print('Current-source numeric and binding controls:',
          len(receipt['controls']['negative_results']), 'negative plus 3 positive')
