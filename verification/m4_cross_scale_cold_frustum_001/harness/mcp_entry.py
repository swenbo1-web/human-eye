"""Retain the original installed MCP entry with passive preparation evidence."""

from pathlib import Path
import sys
import time


sys.path.insert(0, str(Path(__file__).resolve().parent))
import budget  # Bind before the retained entry imports its ledger.
from common import PRIOR, load


def main():
    entry = load('_cold_frustum_retained_mcp_entry', PRIOR / 'harness/mcp_entry.py')
    original = entry.read_context_metadata
    snapshots = 0
    producer_cpu_start = None

    def metadata(service):
        nonlocal producer_cpu_start, snapshots
        producer_cpu_end = time.process_time_ns()
        receipt = original(service)
        snapshots += 1
        resources = []
        for key, state in service._read_context._selections.items():
            index = state['prepared'].get('region_task_global_index')
            if index is None:
                continue
            row = {'selection_repr': repr(key), 'python_id': id(index), 'type': type(index).__name__,
                   'scene_identity': index.scene_identity, 'camera_identity': index.candidate_identity,
                   'regions': len(index.regions), 'views': len(index.view_order),
                   'partition_rows': len(index.patch_scope)}
            resources.append(row)
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
