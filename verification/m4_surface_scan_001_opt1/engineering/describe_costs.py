"""Describe all saved cost and memory observations without another product call."""
import argparse
import json
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HERE, save, sha


def distribution(values):
    return dict(values=values, minimum=min(values), median=statistics.median(values), maximum=max(values))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    args = parser.parse_args()
    folder = args.run.resolve()
    assert folder.is_relative_to(HERE)
    started = time.perf_counter_ns()
    result = {'versions': {}, 'source_results': {},
        'peak_scope': 'process-lifetime peak from Windows GetProcessMemoryInfo, not request-local allocation',
        'memory_owner_order': ['owned_Blender', 'installed_product_runtime'],
        'lifecycle_scope': 'same frozen harness through QA, quality and close; ends before final RESULTS serialization/write',
        'span_scope': 'inclusive nested spans, not additive'}
    for version in ('A','B'):
        sequences = []
        for i in range(1,6):
            path = folder/('pair_'+str(i).zfill(2))/version/'RESULTS.json'
            sequences.append(json.loads(path.read_bytes()))
            result['source_results'][str(path)] = sha(path)
        values = {'states': {}, 'startup_QA_and_close': {},
                  'lifecycle_ns': distribution([row['session_wall_ns'] for row in sequences])}
        for stage in sequences[0]['timing_stages_ns']:
            values['startup_QA_and_close'][stage] = distribution([row['timing_stages_ns'][stage] for row in sequences])
        values['startup_QA_and_close']['owned_Blender_close'] = distribution([row['native_close']['elapsed_ns'] for row in sequences])
        for index,state in enumerate(('cold','repeat','edit')):
            rows = [sequence['business'][index] for sequence in sequences]
            metrics = {'client_ns': distribution([row['complete_client_request_ns'] for row in rows]),
                'server_ns': distribution([row['full_service_and_delivery_trace_ns'] for row in rows]),
                'quality_ns': distribution([row['quality_check_ns'] for row in rows]),
                'bridge_TX_bytes': distribution([row['bridge_request_bytes'] for row in rows]),
                'bridge_RX_bytes': distribution([row['bridge_response_bytes'] for row in rows]),
                'memory': {}, 'cache_statistics_available': version == 'B',
                'acquisition_work': [row['diagnostics']['acquisition_work'] for row in rows],
                'kernel_calls': [row['diagnostics']['kernel_calls'] for row in rows],
                'cache_hits': [row['diagnostics']['cache_hits'] for row in rows]}
            for owner, position in (('Blender',0),('product',1)):
                metrics['memory'][owner] = {
                    'working_set_before_bytes': distribution([row['memory_before'][position]['working_set_bytes'] for row in rows]),
                    'working_set_after_bytes': distribution([row['memory_after'][position]['working_set_bytes'] for row in rows]),
                    'lifetime_peak_working_set_after_bytes': distribution([row['memory_after'][position]['peak_working_set_bytes'] for row in rows])}
            if version == 'B':
                metrics['measurement_cache_after'] = [row['diagnostics']['measurement_cache_after'] for row in rows]
            values['states'][state] = metrics
        result['versions'][version] = values
    result['analysis_ns'] = time.perf_counter_ns()-started
    save(folder/'COST_AND_MEMORY.json',result)
    print(json.dumps({'saved':str(folder/'COST_AND_MEMORY.json'),'analysis_ns':result['analysis_ns']}))


if __name__ == '__main__':
    main()
