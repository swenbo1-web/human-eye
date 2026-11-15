"""Fixed paired ordinary-camera microbenchmark, without hosts or raster calls."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import time


HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--old-source', type=Path, required=True)
    parser.add_argument('--new-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('_frozen_camera_micro_oracle', HERE / 'camera_numeric.py')
    oracle = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(oracle)
    inputs_blob = (HERE / 'INPUTS.json').read_bytes()
    inputs = json.loads(inputs_blob)
    freeze = json.loads((HERE / 'INPUT_FREEZE.json').read_bytes())
    assert hashlib.sha256(inputs_blob).hexdigest() == freeze['inputs_sha256']
    sources = {'old': args.old_source.read_bytes(), 'new': args.new_source.read_bytes()}
    functions = {arm: oracle.camera_namespace(blob, arm)['_observation_target_cameras'] for arm, blob in sources.items()}
    assert hashlib.sha256(sources['old']).hexdigest() == inputs['baseline_host_sha256']
    plan = inputs['microbenchmark']
    records, warmups = [], []
    started = time.perf_counter_ns()
    for case in inputs['micro_cases']:
        for arm in ('old', 'new'):
            began = time.perf_counter_ns()
            for _ in range(plan['warmups_per_arm_per_case']):
                functions[arm](case['world_vertices'], case['world_bounds'])
            warmups.append({'case': case['id'], 'arm': arm, 'calls': plan['warmups_per_arm_per_case'],
                            'started_ns': began, 'closed_ns': time.perf_counter_ns()})
        for pair, order in enumerate(plan['pair_orders'], 1):
            for arm in order:
                calls = []
                block_started = time.perf_counter_ns()
                for _ in range(plan['calls_per_block']):
                    began = time.perf_counter_ns()
                    result = functions[arm](case['world_vertices'], case['world_bounds'])
                    closed = time.perf_counter_ns()
                    calls.append([began, closed])
                block_closed = time.perf_counter_ns()
                records.append({'case': case['id'], 'target_vertices': len(case['world_vertices']), 'arm': arm,
                                'pair': pair, 'calls': calls, 'block_started_ns': block_started,
                                'block_closed_ns': block_closed,
                                'last_six_spans': [pose['span'] for pose in result['views']]})
    summaries = []
    for case in inputs['micro_cases']:
        ratios = []
        for pair in range(1, len(plan['pair_orders']) + 1):
            blocks = {row['arm']: row for row in records if row['case'] == case['id'] and row['pair'] == pair}
            elapsed = {arm: row['block_closed_ns'] - row['block_started_ns'] for arm, row in blocks.items()}
            ratios.append(elapsed['new'] / elapsed['old'])
        summaries.append({'case': case['id'], 'paired_block_ratios_new_over_old': ratios,
                          'median_paired_ratio': statistics.median(ratios)})
    output = {'schema': 'target-camera-fixed-micro-v1', 'input_sha256': freeze['inputs_sha256'],
              'source_sha256': {arm: hashlib.sha256(blob).hexdigest() for arm, blob in sources.items()},
              'benchmark_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'warmups': warmups, 'records': records, 'summaries': summaries,
              'timed_calls': sum(len(row['calls']) for row in records), 'warmup_calls': sum(row['calls'] for row in warmups),
              'started_ns': started, 'closed_ns': time.perf_counter_ns(),
              'scope': 'Ordinary helper microbenchmark only. No task-level or MCP cost claim.',
              'Blender_starts': 0, 'raster_calls': 0, 'model_calls': 0}
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(output, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'timed_calls': output['timed_calls'], 'warmup_calls': output['warmup_calls'], 'summaries': summaries}))


if __name__ == '__main__':
    main()
