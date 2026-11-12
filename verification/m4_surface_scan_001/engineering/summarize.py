"""Summarize saved engineering runs without importing or invoking the product."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HERE, save, sha


def distribution(values):
    assert len(values) == 5
    return {'n': 5, 'values': values, 'minimum': min(values), 'median': statistics.median(values),
            'maximum': max(values)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main-run', type=Path, required=True)
    parser.add_argument('--process-run', type=Path)
    args = parser.parse_args()
    main_run = args.main_run.resolve()
    assert main_run.is_relative_to(HERE)
    sequences = [json.loads((main_run / ('sequence_' + str(i).zfill(2)) / 'RESULTS.json').read_bytes())
                 for i in range(1, 6)]
    summary = {'main_sequences': 5, 'states': {}, 'inputs': {},
               'all_main_passed': all(row['passed'] for row in sequences),
               'timing_semantics': 'client wall includes actual ordinary MCP delivery; spans are inclusive and must not be summed',
               'memory_semantics': 'Windows and service peaks are process lifetime peaks; per-request before/after working sets also retained',
               'QA_instrumentation': 'M2 wire and work meter enabled identically for all main sequences',
               'statistical_scope': 'five fixed engineering sequences; no model efficacy or tail-distribution claim'}
    for i in range(1, 6):
        path = main_run / ('sequence_' + str(i).zfill(2)) / 'RESULTS.json'
        summary['inputs'][str(path)] = sha(path)
    for state in ('cold', 'repeat', 'edit'):
        rows = [next(row for row in sequence['business'] if row['state'] == state) for sequence in sequences]
        metrics = {}
        for key in ('complete_client_request_ns', 'full_service_and_delivery_trace_ns', 'actual_host_RPC',
                    'bridge_request_bytes', 'bridge_response_bytes'):
            if all(key in row for row in rows):
                metrics[key] = distribution([row[key] for row in rows])
        for key in ('kernel_calls', 'pair_calls', 'cache_hits', 'normalization_requests',
                    'normalizations', 'continuation_hits'):
            if all(key in row.get('diagnostics', {}) for row in rows):
                metrics[key] = distribution([row['diagnostics'][key] for row in rows])
        summary['states'][state] = {'metrics': metrics,
            'verifications': [row.get('verification') for row in rows],
            'errors': [row['errors'] for row in rows],
            'acquisition_work': [row.get('diagnostics', {}).get('acquisition_work') for row in rows],
            'result_cache_hit': [row.get('diagnostics', {}).get('result_cache_hit') for row in rows]}
    summary['startup'] = {key: distribution([row['timing_stages_ns'][key] for row in sequences])
                           for key in ('owned_Blender_start', 'product_start_and_metadata')
                           if all(key in row['timing_stages_ns'] for row in sequences)}
    if args.process_run is not None:
        directed = args.process_run.resolve() / 'RESULTS.json'
        process = json.loads(directed.read_bytes())
        summary['other_host_directed'] = {'path': str(directed), 'sha256': sha(directed),
            'passed': process['passed'], 'included_in_main_statistics': False}
    save(main_run / 'ENGINEERING_SUMMARY.json', summary)
    print(json.dumps({'all_main_passed': summary['all_main_passed'],
                      'summary': str(main_run / 'ENGINEERING_SUMMARY.json')}))


if __name__ == '__main__':
    main()
