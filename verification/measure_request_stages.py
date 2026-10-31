"""Local request-stage evidence; analytical host fixture, zero provider calls."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.runtime_identity import runtime_identity
from human_eye_plugin.telemetry import RequestTrace, span, summarize_traces
from verification.test_live_service import SelfLockingHost


def run(destination, samples=24):
    destination = Path(destination).resolve()
    if not destination.is_relative_to(ROOT / 'verification/fixes') or samples < 3:
        raise ValueError('Use a new verification/fixes descendant and at least 3 samples')
    destination.mkdir(parents=True, exist_ok=False)
    identity = runtime_identity()
    records, wall_samples = [], []
    with tempfile.TemporaryDirectory(dir=destination) as temporary:
        base = Path(temporary)
        for mode, include_image, dynamic in [('static_text', False, False),
                ('static_image', True, False), ('dynamic_text', False, True),
                ('dynamic_image', True, True)]:
            config_path = base / (mode + '.json')
            config_path.write_text(json.dumps({'schema_version': '1.0',
                'project_root': str(ROOT), 'state_file': mode + '.state.json',
                'audit_file': mode + '.events.jsonl', 'quad_size': 128}), encoding='utf-8')
            host = SelfLockingHost()
            with RequestTrace('benchmark.construct', writer=records.append,
                    implementation_revision=identity['implementation_revision'],
                    experiment_id='p0_request_stage_fixture_20261023',
                    aggregation_key='fixture.service_constructor', scope='benchmark_request') as trace:
                with span('startup.service_construct', kind='startup'):
                    service = LiveSpatialService(config_path, host=host)
                trace.record_usage(source='unavailable')
            for index in range(samples):
                if dynamic:
                    delta = .001 if index % 2 else -.001
                    mesh = host.scene['meshes'][1]
                    for vertex in mesh['vertices']:
                        vertex[0] += delta
                    mesh['pivot_world'][0] += delta
                    host.scene['revision'] = 'r' + str(index + 2)
                began = time.perf_counter_ns()
                with RequestTrace('benchmark.observe', writer=records.append,
                        implementation_revision=identity['implementation_revision'],
                        experiment_id='p0_request_stage_fixture_20261023',
                        trial_id=mode + '_' + str(index),
                        aggregation_key='fixture.' + mode, scope='benchmark_request') as trace:
                    trace.record_usage(source='unavailable')
                    result = service.observe('fixture', focal_id='part', reference_id='base',
                                             include_image=include_image)
                    if result['status'] != 'observed':
                        raise AssertionError(result['status'])
                wall_samples.append({'mode': mode, 'sample': index,
                    'outer_wall_ns': time.perf_counter_ns() - began,
                    'trace_id': trace.trace_id})
            if host.calls:
                raise AssertionError('This benchmark must not execute host mutations')
    (destination / 'request_traces.jsonl').write_text(''.join(json.dumps(record, allow_nan=False)
        + '\n' for record in records), encoding='utf-8')
    report = {'runtime_identity': identity, 'samples_per_mode': samples,
        'request_count': len(records), 'summary': summarize_traces(records),
        'wall_samples': wall_samples,
        'limitations': ['in_memory_analytical_box_host_not_Blender_or_network',
            'provider_usage_unknown_zero_provider_requests_made',
            'process_lifetime_peak_RSS_not_per_request_peak',
            'inclusive_stage_times_must_not_be_added',
            'trace_writer_excluded_outer_wall_includes_writer',
            'constructor_excludes_interpreter_and_module_imports',
            'quad_size_128_does_not_establish_384_or_general_scene_latency']}
    (destination / 'summary.json').write_text(json.dumps(report, indent=2, allow_nan=False)
        + '\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--samples', type=int, default=24)
    args = parser.parse_args()
    result = run(args.output_dir, args.samples)
    print(json.dumps({'request_count': result['request_count'],
        'summary_groups': len(result['summary']['groups']), 'output': str(args.output_dir)}))


if __name__ == '__main__':
    main()
