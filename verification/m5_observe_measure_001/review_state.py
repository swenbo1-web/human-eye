"""Independent saved audit of the one registered unsaved matrix-control job."""

import argparse
import copy
from fractions import Fraction as F
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def module():
    spec = importlib.util.spec_from_file_location('_m5_state_quality', HERE / 'state_quality_saved.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def audit(slot, expected_binding):
    ql = module()
    slot = Path(slot)
    result = ql.read(slot / 'RESULT.json')
    require = ql.require
    require(result['source_sha256'] == ql.read(expected_binding)['source_sha256'], 'external_frozen_final_B_identity')
    registered = ql.read(HERE / 'STATE_REQUESTS.json')
    order = registered['order']
    require([Path(row['public_path']).parent.name for row in result['requests']] == order, 'registered_five_state_requests')
    for label, row in zip(order, result['requests']):
        actual = copy.deepcopy(row['request'])
        expected = copy.deepcopy(registered['requests'][label])
        require(actual.pop('id') == 'm5_' + label, 'actual_state_request_id')
        expected.pop('id')
        require(actual == expected, 'actual_registered_state_request_arguments')
    states, arrays = {}, {}
    for label in order:
        shift = F(1, 4) if label == 'matrix_changed_main_brief' else F(0)
        review, buffers = ql.audit_slot(slot, 'B', translation=shift,
                                         missing=label == 'initial_missing_brief', business_label=label)
        states[label], arrays[label] = review, buffers
    require(states['initial_main_brief']['observations'][0]['public_detail'] == 'brief', 'actual_default_brief_delivery')
    require(states['initial_main_full']['observations'][0]['public_detail'] == 'full', 'actual_full_formatter_delivery')
    initial = states['initial_main_brief']['observations'][0]
    changed = states['matrix_changed_main_brief']['observations'][0]
    restored = states['restored_main_brief']['observations'][0]
    require(initial['binding_sha256'] != changed['binding_sha256']
            and initial['binding_sha256'] != restored['binding_sha256']
            and changed['binding_sha256'] != restored['binding_sha256'], 'state_changed_and_restored_current_binding')
    source = ql.load(HERE / 'source_contract_r2.py', '_m5_state_source')
    generations = [source.generation(row['capture_state']) for row in (initial, changed, restored)]
    require(len(set(generations)) == 3, 'old_generation_cannot_become_current_after_restore')
    require(len({row[0] for row in generations}) == 1, 'one_owned_host_instance')

    move_path = slot / 'native/M5_MATRIX_MOVE_RECEIPT.json'
    restore_path = slot / 'native/M5_MATRIX_RESTORE_RECEIPT.json'
    move_record, restore_record = ql.read(move_path), ql.read(restore_path)
    move, restore = move_record['response']['result'], restore_record['response']['result']
    identity = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    translated = copy.deepcopy(identity)
    translated[0][3] = .25
    truth = ql.read(HERE / 'scoring/STATE_TRUTH.json')['states']
    require(move['matrix_before'] == identity and move['matrix_after'] == translated,
            'actual_move_matrix_readback')
    require(restore['matrix_before'] == translated and restore['matrix_after'] == identity,
            'actual_restore_matrix_readback')
    require(move['world_before'] == restore['world_after'] == truth['initial']['target_world_vertices'], 'actual_initial_restored_world_points')
    require(move['world_after'] == restore['world_before'] == truth['matrix_changed']['target_world_vertices'], 'actual_changed_world_points')
    require(move['vertex_count'] == restore['vertex_count'] == 293, 'all_target_vertices_in_actual_readback')
    require(move['before_fingerprint'] == restore['after_fingerprint']
            and move['after_fingerprint'] == restore['before_fingerprint']
            and move['before_fingerprint'] != move['after_fingerprint'], 'actual_full_scene_fingerprint_restore')
    require(move['test_matrix_setters'] == restore['test_matrix_setters'] == 1
            and move['product_setters'] == restore['product_setters'] == 0
            and move['source_asset_saved'] is restore['source_asset_saved'] is False, 'fixture_only_two_unsaved_matrix_operations')
    fixture_wire = []
    for directory in sorted((slot / 'native/WIRE').glob('[0-9]*')):
        request = ql.read(directory / 'REQUEST.bin')
        if request.get('type') in ('qa_m5_matrix_move', 'qa_m5_matrix_restore'):
            response = ql.read(directory / 'RESPONSE.bin')
            fixture_wire.append({'type': request['type'], 'request': str(directory / 'REQUEST.bin'),
                                 'response': str(directory / 'RESPONSE.bin'), 'actual_response': response})
    require([row['type'] for row in fixture_wire] == ['qa_m5_matrix_move', 'qa_m5_matrix_restore'], 'actual_two_fixture_wire_operations')
    require([row['actual_response'] for row in fixture_wire] == [move_record['response'], restore_record['response']], 'receipt_equal_original_fixture_wire_response')
    for row in fixture_wire:
        row.pop('actual_response')
    control = ql.read(slot / 'STATE_CONTROL.json')
    require(control['registered_order'] == control['completed_order'] == order
            and control['actual_fixture_matrix_setters'] == 2 and control['product_setters'] == 0
            and control['source_asset_saved'] is False, 'registered_state_control_complete')
    _, q, _, _, _ = ql.dependencies()
    restored_pixels = []
    require(len(arrays['initial_main_brief']) == len(arrays['restored_main_brief']), 'restored_frame_count')
    for left, right in zip(arrays['initial_main_brief'], arrays['restored_main_brief']):
        comparison = q.compare_normalized_buffers(left, right)
        require(comparison['equal'], 'restored_RGB_depth_owner_sourceface_exact_equality')
        restored_pixels.append(comparison)
    for label in ('initial_main_full', 'initial_missing_brief'):
        require(len(arrays[label]) == len(arrays['initial_main_brief']), 'cached_initial_frame_count')
        for left, right in zip(arrays['initial_main_brief'], arrays[label]):
            require(q.compare_normalized_buffers(left, right)['equal'], 'initial_cached_frame_stays_current')
    supplemental = states['initial_missing_brief']['task']['source_binding']['objects']
    missing_rows = [row for row in supplemental if row['observation_object_index'] is None]
    require(len(missing_rows) == 1 and missing_rows[0]['source_triangle_count'] == 512, 'only_Far11_missing_source_supplement')
    return {'schema': 'm5-actual-matrix-state-review-v1', 'passed_checked_scope': True,
            'slot': str(slot), 'states': states, 'actual_current_generations': [list(row) for row in generations],
            'actual_matrix_control': {'move': move, 'restore': restore, 'original_wire': fixture_wire,
                                      'fixture_matrix_setters': 2, 'product_setters': 0, 'source_asset_saved': False},
            'restored_all_saved_buffers': restored_pixels, 'actual_public_full_delivery': True,
            'missing_source_read_only_for_Far11': missing_rows,
            'equal_geometry_after_restore_does_not_revalidate_old_binding': True,
            'input_pins': [{'path': str(path), 'sha256': ql.sha(path)} for path in (
                move_path, restore_path, slot / 'STATE_CONTROL.json', HERE / 'STATE_REQUESTS.json', Path(expected_binding))],
            'checker_sha256': ql.sha(Path(__file__)), 'state_quality_checker_sha256': ql.sha(HERE / 'state_quality_saved.py'),
            'new_actual_calls': 0, 'new_models': 0, 'new_rasters': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--slot', required=True, type=Path)
    parser.add_argument('--binding', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    report = audit(args.slot, args.binding)
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'passed_checked_scope': True, 'output_sha256': module().sha(args.output)}))
