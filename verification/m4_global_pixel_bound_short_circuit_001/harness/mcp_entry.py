"""Keep the dense MCP wire and passively count installed pixel-bound calls."""

from functools import wraps
import json
from pathlib import Path
import sys
import time


sys.path.insert(0, str(Path(__file__).resolve().parent))
import budget
from common import PRIOR, load, sha


def count_pixel_bounds(module):
    original = module.pixel_center_upper_bound
    identity = {'path': str(Path(original.__code__.co_filename).resolve())}
    identity['sha256'] = sha(identity['path'])
    calls = []

    @wraps(original)
    def observed(region, objects, pose):
        calls.append({'view_name': pose['name'], 'roi_id': region.roi_id})
        return original(region, objects, pose)

    module.pixel_center_upper_bound = observed

    def snapshot():
        return {'source': identity, 'total': len(calls), 'calls': list(calls)}

    return snapshot


def main():
    entry = load('_pixel_bound_retained_mcp_entry', PRIOR / 'harness/mcp_entry.py')
    if entry.Budget is not budget.Budget:
        raise ValueError('retained_MCP_did_not_bind_current_budget')
    if sys.argv[1:] == ['--dispatch-smoke']:
        if not sys.flags.isolated or not sys.dont_write_bytecode:
            raise ValueError('pinned_interpreter_I_B_required')
        print(json.dumps({'budget': str(Path(budget.__file__).resolve()),
                          'entry': str(Path(entry.__file__).resolve()),
                          'fresh_process_prepared_only': True}))
        return
    original = entry.read_context_metadata
    snapshots = 0
    producer_cpu_start = probe = None

    def metadata(service):
        nonlocal snapshots, producer_cpu_start, probe
        producer_cpu_end = time.process_time_ns()
        receipt = original(service)
        if probe is None:
            from human_eye_plugin import active_observation_region_task

            probe = count_pixel_bounds(active_observation_region_task)
        receipt['pixel_bound_probe'] = probe()
        snapshots += 1
        resources = []
        for key, state in service._read_context._selections.items():
            index = state['prepared'].get('region_task_global_index')
            if index is not None:
                resources.append({'selection_repr': repr(key), 'python_id': id(index), 'type': type(index).__name__,
                                  'scene_identity': index.scene_identity, 'camera_identity': index.candidate_identity,
                                  'regions': len(index.regions), 'views': len(index.view_order),
                                  'partition_rows': len(index.patch_scope)})
        receipt['region_task_global_indexes'] = resources
        if snapshots % 2:
            producer_cpu_start = time.process_time_ns()
        else:
            receipt['producer_window_cpu_ns'] = producer_cpu_end - producer_cpu_start
        return receipt

    entry.read_context_metadata = metadata
    entry.main()


if __name__ == '__main__':
    main()
