"""Audit the twelve closed formal slots without running a product entry point."""

import argparse
from fractions import Fraction
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_fixed_slot(path, row, preregistration, intent, checker):
    result = checker.read(path / 'RESULT.json')
    owner = checker.read(path / 'OWNER_BINDING.json')
    assert result['label'] == row['label'] and result['variant'] == row['variant']
    assert result['phase'] == 'formal' and result['passed'] is True and result['errors'] == []
    source = intent[row['variant'] + '_source_sha256']
    assert result['source_sha256'] == source
    assert result['binding_sha256'] == intent[row['variant'] + '_binding_sha256']
    asset = next(asset for asset in preregistration['assets'] if asset['name'] == row['input'])
    assert result['asset'] == asset
    assert checker.sha(asset['asset']) == asset['asset_sha256']
    assert checker.sha(asset['geometry']) == asset['geometry_sha256']
    assert result['public_request_budget_s'] == preregistration['public_deadline_s'] == 30
    assert result['blender_timeout_s'] == preregistration['Blender_timeout_s'] == 30
    assert result['original_lifecycle_deadline_ns'] - result['started_ns'] <= preregistration['lifecycle_s']*1_000_000_000
    assert result['session_closed_ns'] <= result['original_lifecycle_deadline_ns']
    assert result['MCP_runtime_exit']['confirmed'] and result['MCP_runtime_exit']['exit_code'] == 0
    assert result['stdio_close']['confirmed'] and result['stdio_close']['exit_code'] == 0
    assert result['native_close']['process_reaped'] and result['native_close']['exit_code'] == 0
    assert result['native_final']['source_file_unchanged'] and result['native_final']['protected_files_unchanged']
    assert result['native_close']['source_file_unchanged'] and result['native_close']['protected_files_unchanged']
    closed = result['native_final']['closed']
    assert closed['initial_geometry_fingerprint'] == closed['final_geometry_fingerprint']
    assert checker.sha(path / 'native/input.blend') == asset['asset_sha256']
    requests = [checker.read(path / f'REQUEST_{index:02}.json') for index in range(1, 5)]
    assert requests == intent['requests_per_input'][row['input']]
    expected_main = {'id': 'target_observation', 'jsonrpc': '2.0', 'method': 'tools/call',
        'params': {'name': 'human_eye_scene_observe', 'arguments': {
            'query': {'mode': 'active_observation', 'objects': [{'name': 'M4_Far_00'}]},
            'include_image': True, 'response_detail': 'full', 'session_id': preregistration['requests']['session_id']}}}
    expected_readback = {'id': 'source_readback', 'jsonrpc': '2.0', 'method': 'tools/call',
        'params': {'name': 'human_eye_scene_observe', 'arguments': {
            'query': {'mode': 'task', 'objects': [{'name': 'M4_Far_00'}], 'requested_facts': ['aabb']},
            'include_image': False, 'session_id': preregistration['requests']['session_id']}}}
    assert requests == [expected_main, {'id': 'after_active_ping', 'jsonrpc': '2.0', 'method': 'ping'},
                        expected_readback, {'id': 'after_readback_ping', 'jsonrpc': '2.0', 'method': 'ping'}]
    frozen = checker.read(HERE / 'reference/FROZEN_GEOMETRY.json')
    originals = {obj['name']: obj for obj in frozen['objects']}
    expected_names = set(originals) if row['input'] == 'main' else {'M4_Far_00'}
    manifest = owner['asset_manifest']
    assert manifest['asset_sha256'] == asset['asset_sha256']
    assert {obj['object_name'] for obj in manifest['objects']} == expected_names
    assert len(manifest['objects']) == len(expected_names)
    for obj in manifest['objects']:
        original = originals[obj['object_name']]
        assert obj['object_id'] == original['reference_object_id']
        assert obj['asset_key'] == row['input'] + '/' + obj['object_name']
        assert obj['vertices_world'] == [[float(Fraction(value)) for value in point] for point in original['world_vertices_m']]
        assert obj['triangles'] == original['triangles']
    cache = {}
    captures = [(pin, checker.decode_capture(pin, cache)) for pin in owner['captures']]
    assert [pin['role'] for pin, _ in captures] == ['main_target_capture', 'post_main_source_readback']
    main, readback = [capture for _, capture in captures]
    assert [pin['command']['command'] for pin, _ in captures] == ['capture_active_observation', 'capture_task']
    assert len(readback['meshes']) == 1
    target_main = next(mesh for mesh in main['meshes'] if mesh['name'] == 'M4_Far_00')
    target_readback = readback['meshes'][0]
    assert target_readback == target_main
    assert main['host_identity']['document_epoch'] == readback['host_identity']['document_epoch']
    for key in ('instance_id', 'epoch', 'revision'):
        assert main['capture_state'][key] == readback['capture_state'][key]
    wire_files = sorted((path / 'native/WIRE').glob('*/REQUEST.bin'))
    wire_requests = [checker.read(item) for item in wire_files]
    assert len(wire_requests) == 3 and wire_requests[-1] == {'type': 'close'}
    assert all(item['type'] == 'execute_code' for item in wire_requests[:2])
    return {'label': row['label'], 'input': row['input'], 'variant': row['variant'], 'pair': row['pair'],
            'source_sha256': source, 'fixed_asset_sha256': asset['asset_sha256'],
            'fixed_requests_equal': True, 'same_current_target_in_actual_readback': True,
            'owned_geometry_and_original_blend_unchanged': True, 'original_processes_closed': True,
            'capture_instance': main['capture_state']['instance_id'],
            'started_ns': result['started_ns'], 'closed_ns': result['session_closed_ns'],
            'result_sha256': checker.sha(path / 'RESULT.json'), 'owner_binding_sha256': checker.sha(path / 'OWNER_BINDING.json')}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--formal', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    checker = load(HERE / 'quality_saved.py', '_formal_saved_quality')
    comparison = load(HERE / 'compare_saved.py', '_formal_saved_comparison')
    viewport = load(HERE / 'viewport_oracle.py', '_formal_independent_viewport')
    preregistration = checker.read(HERE / 'PREREGISTRATION.json')
    gate = checker.read(HERE / 'FORMAL_GATE.json')
    intent = checker.read(args.formal / 'INTENT.json')
    result = checker.read(args.formal / 'RESULT.json')
    assert gate['formal_allowed'] is True
    assert gate['preregistration_sha256'] == intent['preregistration_sha256'] == checker.sha(HERE / 'PREREGISTRATION.json')
    assert intent['formal_schedule'] == preregistration['formal_schedule']
    expected = [dict(input=kind, label=variant + str(pair) + '_' + kind, pair=pair, variant=variant)
                for kind in ('main', 'target_only')
                for variant, pair in (('A', 1), ('B', 1), ('B', 2), ('A', 2), ('A', 3), ('B', 3))]
    assert intent['formal_schedule'] == expected and len(expected) == 12
    assert intent['formal_slots'] == result['planned_slots'] == 12
    assert intent['retries'] == result['retries'] == intent['replacement_samples'] == result['replacement_samples'] == 0
    assert result['remaining_not_dispatched'] == []
    assert len(result['dispatches']) == len(result['results']) == 12
    assert len({row['label'] for row in result['dispatches']}) == 12
    assert [row['label'] for row in result['dispatches']] == [row['label'] for row in expected]
    assert [row['label'] for row in result['results']] == [row['label'] for row in expected]
    assert {path.name for path in args.formal.iterdir() if path.is_dir()} == {row['label'] for row in expected}
    assert intent['A_source_sha256'] == gate['A_source_sha256'] == preregistration['A_source_sha256']
    assert intent['B_source_sha256'] == gate['B_source_sha256']
    assert intent['assets_sha256'] == gate['assets_manifest_sha256'] == preregistration['assets_manifest_sha256']
    fixed = []
    for row, dispatch, reported in zip(expected, result['dispatches'], result['results']):
        path = args.formal / row['label']
        assert dispatch['asset'] == reported['asset'] == row['input']
        assert dispatch['pair'] == reported['pair'] == row['pair']
        assert dispatch['variant'] == reported['variant'] == row['variant']
        assert Path(dispatch['output']).resolve() == path.resolve()
        assert Path(reported['result']).resolve() == (path / 'RESULT.json').resolve()
        assert reported['result_sha256'] == checker.sha(path / 'RESULT.json')
        assert reported['passed_operationally'] is True
        fixed.append(check_fixed_slot(path, row, preregistration, intent, checker))
    assert len({row['capture_instance'] for row in fixed}) == 12
    assert all(left['closed_ns'] <= right['started_ns'] for left, right in zip(fixed, fixed[1:]))
    records = []
    for kind in ('main', 'target_only'):
        for pair in (1, 2, 3):
            record = comparison.compare_pair(args.formal / f'A{pair}_{kind}', args.formal / f'B{pair}_{kind}', kind, checker, viewport)
            record['pair'] = pair
            records.append(record)
    assert len(records) == 6 and all(row['passed_checked_scope'] for row in records)
    image_count = sum(len(row[arm]['frames']) for row in records for arm in ('A', 'B'))
    assert image_count == 18
    pins = [HERE / name for name in ('PREREGISTRATION.json', 'FORMAL_GATE.json', 'COMPARISON_CONTRACT.json',
            'quality_saved.py', 'compare_saved.py', 'viewport_oracle.py', 'ANALYTIC_REVIEW.json')]
    pins += [args.formal / 'INTENT.json', args.formal / 'RESULT.json']
    output = {'schema': 'target-002-formal-saved-quality-v1', 'passed_checked_scope': True,
              'qualification': 'PASS', 'formal_slots': 12, 'formal_pairs': 6, 'original_main_frames': image_count,
              'retries': 0, 'replacement_samples': 0, 'diagnostic_images_used': 0,
              'fixed_request_source_asset_and_lifecycle': fixed, 'records': records,
              'fresh_source_instances_validated_before_asset_owner_mapping': True,
              'entire_target_facts_and_six_view_classifications_equal': True,
              'actual_selected_views_and_cameras_equal': True,
              'RGB_depth_asset_owner_source_face_patch_buffers_equal': True,
              'B_main_each_14_to_6_objects_3478_to_1166_vertices_6148_to_2052_faces': True,
              'B_main_all_eight_excluded_bounds_independently_outside_six_views': True,
              'normalization_contract': 'Scope acquisition differences are individually audited under COMPARISON_CONTRACT. Every retained source is validated before normalization.',
              'performance_gate': 'not_evaluated_by_this_quality_checker',
              'checker_sha256': checker.sha(Path(__file__)),
              'input_pins': [{'path': str(path), 'sha256': checker.sha(path)} for path in pins],
              'new_Blender_starts': 0, 'new_rasters': 0, 'new_product_observations': 0, 'new_model_calls': 0}
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(output, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'passed_checked_scope': True, 'slots': 12, 'pairs': 6, 'actual_frames': image_count,
                      'new_rasters': 0, 'performance_gate': 'not_evaluated'}))


if __name__ == '__main__':
    main()
