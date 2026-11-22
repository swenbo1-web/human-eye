"""Verify the original public body and current capture for each ordered holdout pair."""

from pathlib import Path
from runpy import run_path

NS = Path(__file__).resolve().parents[1]
V = NS.parent
T = run_path(str(NS / 'checks/truth.py'))
R = run_path(str(V / 'm3_whole_object_rounded_witness_001/checks/evidence.py'))
D = R['OLD']
G = T['G']
public, fixed_cli, edge_counts = (D['E'][k] for k in ('public', 'fixed_cli', 'edge_counts'))
require, read, TARGET, REFERENCES = (T[k] for k in ('require', 'read', 'TARGET', 'REFERENCES'))
FACT = 'surface_proximity'
IDENTITIES = {
    False: 'd39b0da9913dc31f55944a10b0299c15acc265a2d4d33d77a39e4798c65cb8c7',
    True: '75e6b8b40ccb221c0a7720e19ab29ca0bb8df80f5a57b27e71df2d3e675656f3',
}


def prove_capture(capture, source, names, *, revision):
    host = capture['host_identity']
    roster = capture['meshes']
    rows = {mesh['name']: mesh for mesh in roster}
    require(len(rows) == len(roster) == 2 and rows.keys() == set(names)
            and capture['revision'] == revision and host['capture_scope'] == 'selected_objects'
            and capture['unit'] == 'm' and capture['coordinate_frame'] == 'world'
            and host['object_instances'].keys() == {mesh['object_id'] for mesh in roster},
            'actual_native_capture_roster_revision_or_saved_world_frame_changed')
    current = T['objects'](source)
    refs = {}
    for name in names:
        captured, original = rows[name], current[name]
        object_id = captured['object_id']
        evaluated = original['evaluated']
        require(object_id == original['object_id']
                and host['object_instances'][object_id] == original['instance_id']
                and captured['vertices'] == evaluated['vertices_world_m']
                and captured['faces'] == evaluated['triangles'],
                'actual_capture_ordered_source_arrays_or_object_instance_changed/' + name)
        refs[name] = {'object_id': object_id, 'instance_id': original['instance_id'],
                      'vertices': len(captured['vertices']), 'triangles': len(captured['faces'])}
    return {'scope': 'selected_objects', 'scene_revision': revision, 'whole_object_capture_rows': refs}


def verify_pair(reference, reply, producer, capture, source, installed, *, require_source):
    if not isinstance(installed, dict):
        installed = read(installed)
    content, text, packet = public(reply)
    bound = packet['binding']
    names = [TARGET, reference]
    rows = T['objects'](source)
    expected = [{'object_id': rows[name]['object_id'], 'name': name} for name in names]
    require(reference in REFERENCES and G['encode'](packet) == text and packet == producer
            and packet['result_kind'] == 'task_query' and packet['schema_version'] == 'task-query-v3'
            and packet['status'] == 'observed' and packet['execution_authority'] is False
            and packet['pair_order'] == 'A_to_B' and packet['unit'] == 'm'
            and packet['coordinate_frame'] == 'world' and packet['facts'].keys() == {FACT}
            and 'region_ref' not in packet and 'region_source' not in bound
            and bound['objects'] == expected and bound['capture_scope'] == 'selected_objects'
            and bound['selected_count'] == 2 and bound['candidate_count'] == 28
            and bound['runtime_source_sha256'] == installed['source_sha256'] == IDENTITIES[require_source],
            'public_whole_pair_scope_order_or_producer_identity_changed/' + reference)
    require(capture is not None and capture['task_selection']['bindings'] == expected
            and capture['task_selection']['selectors'] == [{'name': name} for name in names]
            and capture['task_selection']['candidate_count'] == 28
            and capture['source'] == bound['source'] == 'blender',
            'actual_current_capture_bound_wrong_ordered_objects')
    current = prove_capture(capture, source, names, revision=bound['scene_revision'])
    fact = packet['facts'][FACT]
    value = fact['value']
    point = value['nearest_witness']
    expected_truth = T['establish'](source, reference)
    anchor = expected_truth['attaining_point_pair']
    require(fact['status'] == fact['direction_status'] == fact['witness_status'] == 'measured'
            and fact['semantics'] == 'current_evaluated_triangle_surfaces_world_metres'
            and value['topology'] == [edge_counts(rows[name]['evaluated']['triangles']) for name in names],
            'unmeasured_world_facts_or_wrong_actual_whole_surface_topology/' + reference)
    require(type(value['distance_m']) is float
            and abs(value['distance_m'] - expected_truth['distance_m']) <= 1e-12
            and all(abs(q - v) <= 1e-12 for q, v in
                    zip(G['vector'](point['direction_a_to_b']), expected_truth['direction_a_to_b'], strict=True))
            and all([float(v) for v in T['vector'](anchor[side])] ==
                    [float(v) for v in G['vector'](point[side])] for side in ('a', 'b')),
            'reported_distance_direction_or_nearest_display_changed/' + reference)

    certificate = None
    if require_source:
        require(len(text.encode()) <= 3072, 'candidate_exceeds_3072_bytes/' + reference)
        certificate = R['verify_certificate'](capture, packet, expect_exact=True, expected_order=names)
        require(certificate['indices'] == expected_truth['registered_source_triangle_indices']
                and [row['exact_point_m'] for row in certificate['exact_points']['sides']] == [anchor['a'], anchor['b']],
                'actual_source_triangles_or_rational_points_differ_from_independent_attaining_features/' + reference)
    else:
        require(R['EXACT'] not in point and R['STRICT'] not in point,
                'old_endpoint_unexpected_source_field')
    display = {side: T['member'](G['vector'](point[side]), T['source_faces'](source, name))
               for side, name in zip(('a', 'b'), names, strict=True)}
    registered = expected_truth['registered_source_triangle_indices']
    require(any(idx not in display[side]['exact_source_triangle_indices']
                for side, idx in zip(('a', 'b'), registered, strict=True)),
            'rounded_only_display_must_not_be_accepted_as_exact_source_proof/' + reference)
    cli = fixed_cli(content, must_preserve=True)
    require(cli['all_six_preserve_full_semantics'], 'fixed_CLI_did_not_preserve_original_body/' + reference)
    return {'passed': True, 'ordered_objects': names, 'scope': 'whole_objects',
            'actual_body_utf8_bytes': len(text.encode()), 'current_capture': current,
            'source_evidence': certificate, 'distance_m': value['distance_m'],
            'a': point['a'], 'b': point['b'], 'direction_a_to_b': point['direction_a_to_b'],
            'display_exact_memberships': display, 'support_proof': expected_truth['support_proof'],
            'meets_0_20m': expected_truth['meets_threshold'], 'fixed_CLI': cli, 'actual_image_blocks': 0}


def verify_qualification(slot, replies, producers, captures, *, binding, require_source, source=None):
    slot = Path(slot).resolve(strict=True)
    first = read(slot / 'initial_capture/TERMINAL_SOURCE.json')
    source = read(slot / 'TERMINAL_SOURCE.json') if source is None else source
    installed = binding if isinstance(binding, dict) else read(binding)
    require(all(tuple(groups) == REFERENCES for groups in (replies, producers, captures)),
            'actual_qualification_pair_sequence_must_be_N04_then_N05')
    geometry = T['verify_source'](source, first)
    pairs = {ref: verify_pair(ref, replies[ref], producers[ref], captures[ref], source, installed,
                              require_source=require_source) for ref in REFERENCES}
    first_capture, last_capture = (captures[ref] for ref in REFERENCES)
    a, b = first_capture['capture_state'], last_capture['capture_state']
    require(all(a[key] == b[key] for key in ('instance_id', 'epoch', 'revision'))
            and a['selection_key'] != b['selection_key']
            and first_capture['host_identity']['document_epoch'] == last_capture['host_identity']['document_epoch']
            and not pairs['N04']['meets_0_20m'] and pairs['N05']['meets_0_20m']
            and pairs['N04']['distance_m'] < pairs['N05']['distance_m'],
            'actual_two_current_pairs_or_threshold_order_detached')
    return {'passed': True, 'pairs': pairs, 'source': geometry, 'threshold_m': 0.2, 'closer_reference': 'N04',
            'actual_image_blocks': 0, 'qualified_same_scene_generation': {key: a[key] for key in
                                                                          ('instance_id', 'epoch', 'revision')}}
