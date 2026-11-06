"""Frozen M3 qualification inputs and one attribution run, without Blender."""
from __future__ import annotations

import cProfile
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys
import time
import tracemalloc

import numpy as np

from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin import geometry_safety as geometry
from human_eye_plugin import scene_cache as memo
from human_eye_plugin.runtime_identity import runtime_identity
from human_eye_plugin.task_query import task_result
from verification.test_concave_geometry import box, entity, ring


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'verification/fixes/perf030_001'
BASELINE = '11c8fc7332e530ead2f8fa30d2a35c7eb14e7d15'
FACTS = ['surface_clearance', 'solid_relation', 'nearest_witness']


def prism(sides, identity, center=(0, 0, 0)):
    angles = np.arange(sides) * (2 * math.pi / sides)
    polygon = np.column_stack((.02 * np.cos(angles), .02 * np.sin(angles)))
    vertices = [(x, y, z) for z in (-.01, .01) for x, y in polygon]
    faces = []
    for i in range(1, sides - 1):
        faces.extend(((0, i + 1, i), (sides, sides + i, sides + i + 1)))
    for i in range(sides):
        j = (i + 1) % sides
        faces.extend(((i, j, sides + j), (i, sides + j, sides + i)))
    return entity(identity, np.asarray(vertices) + center, faces)


def cases():
    values = []
    for n in (10, 12, 15):
        values.append((f'prism_{2*n}v_{4*n-4}f_each', 'target',
                       prism(n, 'a'), prism(n, 'b', (0, 0, .039)), .019))
    for n in (32, 40):
        values.append((f'asymmetric_8v12f_vs_{2*n}v{4*n-4}f', 'target',
                       prism(4, 'a'), prism(n, 'b', (0, 0, .039)), .019))
    values.append(('small_box', 'small', box(identity='a'), box((0, 0, .039), identity='b'), .019))
    values.append(('ring_probe', 'witness', box(), ring(), .019))
    angle = .37
    rotation = np.array([[math.cos(angle), -math.sin(angle), 0],
                         [math.sin(angle), math.cos(angle), 0], [0, 0, 1]])
    probe = box()
    rotated = entity('rotated_probe', probe.vertices @ rotation.T, probe.faces)
    expected = .025 - np.max(np.abs(rotated.vertices[:, :2]))
    values.append(('ring_rotated_probe', 'witness', rotated, ring(), float(expected)))
    shift = np.full(3, 1e12)
    moved = entity('probe', probe.vertices + shift, probe.faces)
    reference = ring()
    moved_ring = entity('ring', reference.vertices + shift, reference.faces)
    expected = float((shift[0] + .025) - np.max(moved.vertices[:, 0]))
    values.append(('ring_large_translation', 'witness', moved, moved_ring, expected))
    values.append(('skew_edge_bars', 'edge', box(size=(2, .1, .1), identity='a'),
                   box((0, 0, .2), (.1, 2, .1), identity='b'), .1))
    values.append(('near_boundary_1pm', 'boundary', box((.019 - 1e-12, 0, 0)), ring(), 1e-12))
    values.append(('budget_reject_40v76f_each', 'reject', prism(20, 'a'),
                   prism(20, 'b', (0, 0, .039)), None))
    return [{'name': name, 'group': group, 'meshes': [a.to_dict(), b.to_dict()],
             'expected_clearance_m': expected,
             'oracle': 'analytic represented parallel z planes' if group == 'target' else
                       'analytic box/ring boundary or perpendicular bar edge gap'}
            for name, group, a, b, expected in values]


def meshes(case):
    return [MeshEntity3D.from_dict(value) for value in case['meshes']]


def scene_query(pair):
    scene = {'revision': 'frozen-m3', 'unit': 'm', 'coordinate_frame': 'world',
             'source': 'perf030_001_fixed_meshes', 'meshes': [m.to_dict() for m in pair]}
    query = {'mode': 'task', 'objects': [{'id': m.object_id} for m in pair], 'requested_facts': FACTS}
    return scene, query


def task_call(pair, cache):
    scene, query = scene_query(pair)
    diagnostics = {}
    value = task_result(scene, pair, 'frozen-input', query, cache, lambda _: None, diagnostics=diagnostics)
    return value, diagnostics


def features(pair):
    points = [geometry._surface_vertices(mesh) for mesh in pair]
    triangles = [mesh.vertices[mesh.faces] for mesh in pair]
    edges = []
    for mesh in pair:
        indices = np.concatenate([mesh.faces[:, [0, 1]], mesh.faces[:, [1, 2]], mesh.faces[:, [2, 0]]])
        edges.append(mesh.vertices[np.unique(np.sort(indices, axis=1), axis=0)])
    return points, triangles, edges


def potential_pruning(pair, best):
    points, triangles, edges = features(pair)
    values = []
    for left, right in ((points[0][:, None, :], triangles[1]),
                        (points[1][:, None, :], triangles[0]), (edges[0], edges[1])):
        low_l, high_l = left.min(axis=1), left.max(axis=1)
        low_r, high_r = right.min(axis=1), right.max(axis=1)
        gap = np.maximum(0, np.maximum(low_l[:, None] - high_r, low_r - high_l[:, None]))
        lower = np.einsum('ijk,ijk->ij', gap, gap)
        values.append({'combinations': int(lower.size),
                       'aabb_strictly_above_final_minimum': int(np.sum(lower > best * best + 1e-20))})
    return dict(zip(('a_to_b_point_face', 'b_to_a_point_face', 'edge_edge'), values))


def timed(factory, repeats=3):
    rows = []
    for _ in range(repeats):
        call = factory()
        start = time.perf_counter_ns()
        result = call()
        rows.append((time.perf_counter_ns() - start) / 1e6)
    return {'ms': rows, 'median_ms': float(np.median(rows))}, result


def measure_factory(case):
    pair = meshes(case)
    return lambda: geometry.measure_pair_geometry(*pair, need_clearance=True)


def task_factory(case, hot=False):
    pair, cache = meshes(case), memo.SpatialSceneCache()
    if hot:
        task_call(pair, cache)
    return lambda: task_call(pair, cache)


def freeze():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {'baseline': BASELINE, 'units': 'm', 'coordinate_frame': 'world',
                'facts': FACTS, 'cases': cases(), 'qualification_repeats': 3,
                'formal_gate': {'blocks': 5, 'repeats_per_arm_case_mode_block': 3,
                    'order': 'case order then block, alternating baseline/candidate first by block',
                    'target_median_improvement': .20, 'benefiting_groups': 'at least 4 of 5',
                    'small_hot_median_regression': 'max(0.2ms,2%)', 'p95_regression': 'max(1ms,5%)',
                    'modes': ['cold', 'pose_miss', 'geometry_miss', 'hot'],
                    'pose_miss': 'translate focal by [0,0,0.000001] after priming original pair',
                    'geometry_miss': 'increase focal z coordinates by factor 1.0001 after priming original pair',
                    'construction': 'new pair instances outside timed boundary, no support cache prewarming',
                    'task_boundary': 'task_result plus construction of its scene/query payload inside task_call'}}
    (OUT / 'inputs.json').write_text(json.dumps(manifest, indent=2, allow_nan=False) + '\n', encoding='utf8')


def qualify():
    manifest = json.loads((OUT / 'inputs.json').read_text(encoding='utf8'))
    identity = runtime_identity()
    assert identity['source_sha256'] == 'e59048677b7cc05ac0f15b359e5444de2cc3ccc196994a701e74a2510f144163'
    result = {'baseline': BASELINE, 'identity': identity, 'environment': {
        'python': sys.version, 'executable': sys.executable, 'numpy': np.__version__,
        'platform': platform.platform(), 'cpu_count': os.cpu_count(),
        'threads': {key: os.environ.get(key) for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')}},
        'input_sha256': hashlib.sha256((OUT / 'inputs.json').read_bytes()).hexdigest(), 'cases': []}
    for case in manifest['cases']:
        pair = meshes(case)
        row = {'name': case['name'], 'group': case['group'], 'scale': [geometry._counts(m) for m in pair],
               'budget': geometry.work_budget_status(pair), 'mesh_support_cache_before': [hasattr(m, '_certified_convex_shells') for m in pair]}
        row['measure'], row['measurement'] = timed(lambda: measure_factory(case))
        row['task_cold'], task = timed(lambda: task_factory(case))
        row['task_diagnostics'] = task[1]
        row['task_hot'], hot = timed(lambda: task_factory(case, hot=True))
        row['hot_diagnostics'] = hot[1]
        row['budget_timing'], _ = timed(lambda: lambda: geometry.work_budget_status(pair))
        row['cache_key'], _ = timed(lambda: lambda: memo._digest(memo._encode({
            'algorithm': 'task-query-existing-strict-kernel-v1', 'parameters': {
                'need_clearance': True, 'source': 'perf030_001_fixed_meshes', 'unit': 'm',
                'coordinate_frame': 'world', 'collision_tolerance_m': 1e-9},
            'focal': pair[0].to_dict(), 'reference': pair[1].to_dict()})))
        profile = cProfile.Profile()
        profile.enable()
        profiled = measure_factory(case)()
        profile.disable()
        row['profile'] = [{'file': str(entry.code.co_filename), 'function': entry.code.co_name,
                           'calls': entry.callcount, 'total_ms': entry.totaltime * 1000,
                           'self_ms': entry.inlinetime * 1000}
                          for entry in profile.getstats() if not isinstance(entry.code, str)
                          and any(token in entry.code.co_filename for token in ('geometry_safety', 'spatial_sniffer', 'orthogonal_solid'))]
        tracemalloc.start()
        measure_factory(case)()
        row['measure_tracemalloc_current_peak_bytes'] = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        if profiled['measurement_valid']:
            expected = case['expected_clearance_m']
            row['oracle_pass'] = abs(profiled['signed_clearance_m'] - expected) <= 1e-14
            row['scalar'], _ = timed(lambda: lambda: geometry._surface_distance(*pair))
            row['witness'], witness = timed(lambda: lambda: geometry._surface_distance_with_witness(*pair))
            row['witness_oracle_pass'] = abs(witness[0] - expected) <= 1e-14
            row['aabb_potential'] = potential_pruning(pair, expected)
        result['cases'].append(row)
        print(case['name'], 'measure_ms', row['measure']['median_ms'], 'valid', profiled['measurement_valid'], flush=True)
    (OUT / 'qualification.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf8')


if __name__ == '__main__':
    if sys.argv[1:] == ['freeze']:
        freeze()
    elif sys.argv[1:] == ['qualify']:
        qualify()
    else:
        raise SystemExit('usage: python -m verification.perf030_001_qualification freeze|qualify')
