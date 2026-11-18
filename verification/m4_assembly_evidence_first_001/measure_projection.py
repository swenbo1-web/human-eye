"""Measure only the candidate's bounded projection from the saved MCP capture."""

import argparse
import cProfile
import hashlib
import json
from pathlib import Path
import pstats
import runpy
import statistics
import sys
import time
import tracemalloc


NS = Path(__file__).resolve().parent
BOOTSTRAP = NS.parent / 'm4_live_assembly_relation_task_001/harness/reused/verified_bootstrap.py'


def measure(binding_file, replay, repetitions):
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise ValueError('use -I -B for this replay')
    binding_raw = binding_file.read_bytes()
    binding = json.loads(binding_raw)
    sys.path.insert(0, binding['dependency_root'])
    guard = runpy.run_path(str(BOOTSTRAP))['bootstrap'](binding)
    from human_eye_plugin.auto_router import _validated_scene
    from human_eye_plugin.runtime_identity import runtime_identity
    from human_eye_plugin.task_query import project_task_capture_evidence

    if runtime_identity()['source_sha256'] != binding['source_sha256']:
        raise ValueError('projection code identity mismatch')
    cases = {}
    for case in ('second_assembly', 'assembly001'):
        folder = replay / case / 'default'
        raw = (folder / 'PUBLIC.json').read_bytes()
        capture = json.loads((folder / 'CAPTURE.json').read_bytes())
        _, meshes, fingerprint, _ = _validated_scene(capture, _task_capture=True, _return_payload=True)
        expected = json.loads((replay / case / 'brief/PUBLIC.json').read_bytes())['capture_evidence']
        timings = []
        checkpoints = []
        for index in range(repetitions + 10):
            arguments = (json.loads(raw), meshes, fingerprint, checkpoints.append)
            start = time.perf_counter_ns()
            result = project_task_capture_evidence(*arguments)
            elapsed = time.perf_counter_ns() - start
            if result.get('capture_evidence') != expected or checkpoints != ['task_capture_evidence_candidate'] * 3:
                raise ValueError('projected evidence differs from installed MCP output')
            checkpoints.clear()
            if index >= 10:
                timings.append(elapsed)
        arguments = (json.loads(raw), meshes, fingerprint, checkpoints.append)
        profile = cProfile.Profile()
        profile.runcall(project_task_capture_evidence, *arguments)
        stats = pstats.Stats(profile).stats
        calls = {}
        for (filename, _, name), (primitive, total, *_) in stats.items():
            if name in ('deepcopy', '_crossing_vertex_indices', '_task_capture_evidence'):
                calls[Path(filename).name + '/' + name] = {'primitive': primitive, 'total': total}
        peaks = []
        for _ in range(11):
            checkpoints.clear()
            arguments = (json.loads(raw), meshes, fingerprint, checkpoints.append)
            tracemalloc.start()
            try:
                result = project_task_capture_evidence(*arguments)
                _, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
            peaks.append(peak)
        timings.sort()
        cases[case] = {'median_ns': statistics.median(timings), 'p95_ns': timings[(len(timings)*95 + 99)//100-1],
                       'min_ns': timings[0], 'samples_ns': timings,
                       'traced_peak_python_bytes_median': statistics.median(peaks), 'peak_samples_bytes': peaks,
                       'profile_calls': calls, 'candidate_checkpoints': len(checkpoints),
                       'geometry_capture_count_inside_projection': 0, 'full_solve_count_inside_projection': 0}
    guard.verify_loaded()
    return {'source_sha256': binding['source_sha256'], 'binding_sha256': hashlib.sha256(binding_raw).hexdigest(),
            'scope': 'Projection only. No normalization, archive, encoding, host I/O or raster in samples. '
                     'Peak samples track Python allocations with instrumentation applied separately.', 'cases': cases}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('binding', type=Path)
    parser.add_argument('replay', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--repetitions', type=int, default=401)
    args = parser.parse_args()
    value = measure(args.binding, args.replay, args.repetitions)
    with args.output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')
