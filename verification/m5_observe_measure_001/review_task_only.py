"""Independent saved-only ordinary-task control, with no image construction."""

import argparse
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def checker():
    spec = importlib.util.spec_from_file_location('_m5_task_control_quality', HERE / 'quality_saved_r2.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def audit(slot, expected_binding):
    ql = checker()
    slot = Path(slot)
    result, publication = ql.read(slot / 'RESULT.json'), ql.read(slot / 'PUBLICATION.json')
    ql.require(not result['errors'] and result['passed_before_publication'] and publication['passed_transport_scope'], 'closed_task_only_session_failed')
    expected = ql.read(expected_binding)
    build = ql.read(result['binding_path'])
    ql.require(result['source_sha256'] == build['source_sha256'] == expected['source_sha256'], 'external_frozen_task_only_source')
    ql.require(ql.sha(result['binding_path']) == result['binding_sha256'], 'task_only_install_binding')
    identity = ql.read(slot / 'INITIALIZE.json')['result']['_meta']['human_eye']
    ql.require(identity['source_sha256'] == expected['source_sha256'] and identity['source_kind'] == 'installed_distribution', 'task_only_actual_runtime')
    _, q, _, oracle, source = ql.dependencies()
    captures, materials, steps, host_sha = ql.decode_original_wire(slot, build, ql.asset_manifest(oracle))
    q.validate_source_proof({'expected_source_sha256': expected['source_sha256'],
        'expected_host_source_sha256': next(row['sha256'] for row in build['source_manifest'] if row['path'] == 'human_eye_plugin/blender_host.py'),
        'actual_runtime_identity': identity, 'actual_loaded_host_sha256': host_sha, 'material_pins': materials})
    ql.require(len(result['requests']) == 1, 'one_ordinary_task_request')
    row = result['requests'][0]
    args = row['request']['params']['arguments']
    registered = ql.read(HERE / 'REQUESTS.json')['task_only'][0]['params']['arguments']
    ql.require(args == registered, 'registered_ordinary_task_arguments')
    public = ql.read(row['public_path'])
    producer = row['producer']
    ql.require(ql.sha(producer['path']) == producer['sha256'] and ql.read(producer['path']) == public, 'ordinary_task_actual_full_delivery')
    content = row['response']['result']['content']
    ql.require(row['response']['result']['isError'] is False and len(content) == 1
               and content[0]['type'] == 'text' and json.loads(content[0]['text']) == public, 'ordinary_task_text_only_public_response')
    task = ql.audit_task(public, captures, None, None, oracle, source, ql.F(0), False)
    residuals = ql.load(HERE / 'witness_residuals.py', '_m5_task_only_witness_residuals')
    task['numeric']['relative_displacement_publication'] = residuals.validate(public['facts']['surface_proximity'])
    ql.require('observation_source' not in public['binding'], 'ordinary_task_keeps_ordinary_binding')
    commands = [step for step in steps if step.get('command') is not None]
    capture_commands = [step for step in commands if step['command']['command'].startswith('capture_')]
    ql.require(len(capture_commands) == 1 and capture_commands[0]['command']['command'] == 'capture_task', 'ordinary_task_capture_path')
    audit = [json.loads(line) for line in (slot / 'audit.jsonl').read_bytes().splitlines() if line.strip()]
    ql.require(not [event for event in audit if event.get('event') == 'active_observation_render_attempt'], 'ordinary_task_zero_raster')
    ql.require(not public.get('frames') and not row.get('producer_frames'), 'ordinary_task_zero_product_frames')
    return {'schema': 'm5-ordinary-task-only-review-v1', 'passed_checked_scope': True,
            'slot': str(slot), 'source_sha256': result['source_sha256'], 'task': task,
            'actual_capture_commands': [step['command'] for step in capture_commands],
            'actual_image_blocks': 0, 'actual_product_frames': 0, 'actual_raster_attempts': 0,
            'ordinary_task_binding_preserved': True,
            'input_pins': [{'path': str(path), 'sha256': ql.sha(path)} for path in (
                slot / 'RESULT.json', slot / 'PUBLICATION.json', slot / 'INITIALIZE.json', slot / 'SAVED_WIRE.json',
                slot / 'audit.jsonl', Path(producer['path']), Path(row['public_path']), Path(expected_binding))],
            'checker_sha256': ql.sha(Path(__file__)), 'new_actual_calls': 0, 'new_rasters': 0, 'new_models': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--slot', required=True, type=Path)
    parser.add_argument('--binding', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    review = audit(args.slot, args.binding)
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(review, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'passed_checked_scope': True, 'output_sha256': checker().sha(args.output)}))
