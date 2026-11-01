"""Attribute source checks without changing their freshness or package state."""
from __future__ import annotations
import argparse
import cProfile
import importlib.util
import io
import json
from pathlib import Path
import pstats
import statistics
import sys
import time


def measure(source: Path, repetitions: int) -> dict:
    source = source.resolve()
    sys.path.insert(0, str(source))
    spec = importlib.util.spec_from_file_location('measured_identity', source/'human_eye_plugin/runtime_identity.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    identity = module.runtime_identity()
    calls = {'distribution': lambda: module._distribution(source),
             'source_manifest': lambda: module._source_manifest(source),
             'source_drift': module.check_source_drift}
    samples = {name: [] for name in calls}
    for _ in range(3):
        assert module.check_source_drift()['compatible']
    for i in range(repetitions):
        for name in (list(calls) if i % 2 == 0 else list(reversed(calls))):
            begin = time.perf_counter_ns()
            result = calls[name]()
            samples[name].append((time.perf_counter_ns()-begin)/1e6)
            if name == 'source_drift':
                assert result['compatible'] and result['check_complete']
    profiler = cProfile.Profile()
    profiler.enable()
    for _ in range(10):
        assert module.check_source_drift()['compatible']
    profiler.disable()
    output = io.StringIO()
    pstats.Stats(profiler, stream=output).strip_dirs().sort_stats('cumulative').print_stats(30)
    stats = {name: {'median_ms': statistics.median(values),
                    'p95_ms': sorted(values)[max(0, (95*len(values)+99)//100-1)],
                    'samples_ms': values} for name, values in samples.items()}
    return {'source': str(source), 'identity': identity, 'repetitions': repetitions,
            'stats': stats, 'profile': output.getvalue(), 'profile_is_not_gate': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--repetitions', type=int, default=50)
    args = parser.parse_args()
    if args.repetitions < 20:
        parser.error('at least 20 repetitions')
    result = measure(args.source, args.repetitions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf8') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps({'build': result['identity']['source_sha256'],
                      'stats': {k: {n: v for n, v in s.items() if n != 'samples_ms'}
                                for k, s in result['stats'].items()}}))
