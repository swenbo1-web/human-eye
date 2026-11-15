"""Read actual fresh-B work counters and cross-check original host commands."""

import argparse
import hashlib
import json
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(slot):
    slot = Path(slot)
    result = read(slot / 'RESULT.json')
    wire = read(slot / 'SAVED_WIRE.json')
    requests = result['requests']
    assert len(requests) == 1
    pin = requests[0]['producer']
    assert sha(pin['path']) == pin['sha256']
    full = read(pin['path'])
    work = full['work']
    task_work = work['task_query']
    commands = [step for step in wire['steps'] if step.get('command') is not None]
    capture_commands = [step for step in commands if step['command']['command'].startswith('capture_')]
    assert len(capture_commands) == 1 and capture_commands[0]['command']['command'] == 'capture_active_observation'
    assert task_work['surface_pair_count'] == 1 and task_work['supplemental_capture_calls'] == 0
    assert task_work['supplemental_objects'] == 0 and task_work['additional_raster_attempts'] == 0
    assert task_work['reused_observation_objects'] == 2
    events = [json.loads(line) for line in (slot / 'audit.jsonl').read_bytes().splitlines() if line.strip()]
    rasters = [row for row in events if row.get('event') == 'active_observation_render_attempt']
    assert len(rasters) == work['raster_attempts'] == work['raster_completed'] == 1
    capture = capture_commands[0]
    assert capture['resources_forwarded'] == 6 and capture['resource_vertices_forwarded'] == 1166
    assert capture['resource_faces_forwarded'] == 2052
    resident = work['target_acquisition']['residency_delta']
    assert resident['to_mesh'] == resident['triangulations'] == resident['world_transforms'] == 6
    retained = {key: value for key, value in task_work.items() if key != 'surface_work'}
    return {'schema': 'm5-fresh-B-actual-work-review-v1', 'passed_checked_scope': True,
            'slot': str(slot), 'surface_solver_calls': task_work['surface_pair_count'],
            'additional_detailed_captures': 0, 'additional_rasters': 0,
            'public_business_calls': len(requests), 'product_capture_command_count': len(capture_commands),
            'actual_render_attempt_views': [row['view_name'] for row in rasters],
            'task_work': retained, 'actual_target_residency_delta': resident,
            'actual_initial_forwarded_resources': capture['resources_forwarded'],
            'actual_initial_forwarded_vertices': capture['resource_vertices_forwarded'],
            'actual_initial_forwarded_faces': capture['resource_faces_forwarded'],
            'original_wire_step_count': len(wire['steps']),
            'wire_steps_without_product_command': [step['sequence'] for step in wire['steps'] if step.get('command') is None],
            'scope': 'Fresh combined main request. Nonproduct shutdown/fixture steps are retained separately. Counters do not establish uninstrumented copy counts.',
            'input_pins': [{'path': str(path), 'sha256': sha(path)} for path in (
                slot / 'RESULT.json', slot / 'SAVED_WIRE.json', slot / 'audit.jsonl', Path(pin['path']))],
            'checker_sha256': sha(Path(__file__)), 'new_actual_calls': 0, 'new_rasters': 0, 'new_models': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--slot', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.slot)
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, sort_keys=True, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'passed_checked_scope': True, 'output_sha256': sha(args.output)}))
