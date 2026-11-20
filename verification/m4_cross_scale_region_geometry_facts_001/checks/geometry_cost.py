"""Measure only the candidate's per-row geometry arithmetic on historical inputs."""

import argparse
from fractions import Fraction
import importlib
import json
import math
from pathlib import Path
import runpy
from statistics import median
import sys
import time
import zipfile


def full_cross_and_norm(module, half_u, half_v, _front):
    vector = tuple(4 * (half_u[j] * half_v[k] - half_u[k] * half_v[j])
                   for j, k in ((1, 2), (2, 0), (0, 1)))
    dominant_area = max(map(abs, vector))
    direction = tuple(value / dominant_area for value in vector)
    components = tuple(map(float, direction))
    length = math.hypot(*components)
    return {'area_m2': module._region_rectangle_area(dominant_area, direction, length),
            'unit_normal_world': [component / length for component in components]}


def measure(fn, rows, iterations):
    start = time.process_time_ns()
    for _ in range(iterations):
        for row in rows:
            fn(*row)
    return (time.process_time_ns() - start) / (iterations * len(rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    options = parser.parse_args()
    oracle_path = Path(__file__).with_name('geometry_oracle.py')
    oracle = runpy.run_path(str(oracle_path))
    src = oracle['Sources']()
    src.raw(oracle_path)
    verify = oracle['V']
    dependencies = src.read(verify / 'm4_live_assembly_relation_task_001/PRODUCT_RUN_BINDING.json')
    shared = src.read(verify / 'm5_harness_recovery_001/SHARED_DEPENDENCY.json')
    sys.path[:0] = [str(options.candidate.resolve()), dependencies['dependency_root'], shared['dependency_root']]
    module = importlib.import_module('human_eye_plugin.live_spatial_mcp')
    path = Path(module.__file__).resolve()
    if not path.is_relative_to(options.candidate.resolve()):
        raise ValueError('candidate_projection_source_not_in_requested_install')
    src.raw(path)
    with zipfile.ZipFile(src.archive) as archive:
        producer = oracle['RUNTIME'] / 'slots/P1/product_full/call_001/SERVICE_RESULT.json'
        original = json.loads(src.archived(archive, producer))
    historical_rows = original['facts']['region_task']['rows']
    fields = ('half_edge_u_world_m', 'half_edge_v_world_m', 'front_direction_world')
    rows = [tuple(tuple(map(Fraction, row[field])) for field in fields) for row in historical_rows]
    direct = module._region_geometry_facts

    def alternate(*row):
        return full_cross_and_norm(module, *row)

    if any(direct(*row) != alternate(*row) for row in rows):
        raise ValueError('timed_algorithms_differ_on_frozen_region_inputs')
    for fn in (direct, alternate):
        measure(fn, rows, 150)
    timings = {'dominant_component_ns_per_row': [], 'full_cross_re_normalize_ns_per_row': []}
    methods = list(timings)
    functions = dict(zip(methods, (direct, alternate), strict=True))
    # Windows process CPU ticks are comparatively coarse. Each sample spans
    # several ticks for both implementations while staying small to run.
    repeats, iterations = 9, 5000
    for i in range(repeats):
        for method in methods if i % 2 == 0 else reversed(methods):
            timings[method].append(measure(functions[method], rows, iterations))
    medians = {method: median(values) for method, values in timings.items()}
    src.raw(Path(__file__))
    out = {'scope': 'Process CPU, three exact historical region rows per loop. Input vectors are already parsed.',
           'clock': 'process_time_ns', 'includes_IO_raster_or_model': False, 'repeats': repeats,
           'iterations_per_repetition': iterations,
           'historical_regions': [row['object_name'] for row in historical_rows],
           'same_output_on_measured_rows': True, 'median': medians, 'samples': timings,
           'source_pins': sorted(src.pins.values(), key=lambda row: row['path']), 'passed': True}
    options.output.parent.mkdir(parents=True, exist_ok=True)
    with options.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(out, stream, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)
        stream.write('\n')
    print('GEOMETRY_COST_PASS', medians, oracle['digest'](options.output.read_bytes()))


if __name__ == '__main__':
    main()
