"""Retain the original installed MCP entry with passive preparation evidence."""

from dataclasses import is_dataclass
from fractions import Fraction
from pathlib import Path
import sys
import time


sys.path.insert(0, str(Path(__file__).resolve().parent))
import budget  # Bind before the retained entry imports its ledger.
from common import PRIOR, load


def graph_size(index):
    seen, pending, size = set(), [index], 0
    started = time.perf_counter_ns()
    cpu_started = time.process_time_ns()
    while pending:
        value = pending.pop()
        identity = id(value)
        if identity in seen:
            continue
        seen.add(identity)
        size += sys.getsizeof(value)
        if isinstance(value, dict):
            pending.extend(value.keys())
            pending.extend(value.values())
        elif isinstance(value, (tuple, list, set, frozenset)):
            pending.extend(value)
        elif isinstance(value, Fraction):
            pending.extend((value.numerator, value.denominator))
        elif is_dataclass(value):
            pending.append(vars(value))
    return {'bytes': size, 'objects': len(seen), 'wall_ns': time.perf_counter_ns() - started,
            'cpu_ns': time.process_time_ns() - cpu_started,
            'scope': 'Deduplicated reachable Python objects from the index. Shared atoms are counted once; no RSS claim.'}


def main():
    entry = load('_index_reuse_retained_mcp_entry', PRIOR / 'harness/mcp_entry.py')
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
            # Measure once after the third producer return. Earlier RPCs only
            # retain constant-size identity metadata.
            if snapshots == 6:
                row['python_graph'] = graph_size(index)
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
