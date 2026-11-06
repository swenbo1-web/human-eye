"""One sealed paired sequence for the sole M3 candidate."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import tracemalloc
from unittest.mock import patch

import numpy as np

from human_eye_plugin import geometry_safety as candidate
from human_eye_plugin import scene_cache
from human_eye_plugin import task_query
from human_eye_plugin.runtime_identity import runtime_identity
from verification.perf030_001_qualification import BASELINE, OUT, features, meshes, task_call


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args]).decode('utf8').strip()


def baseline_module():
    source = subprocess.check_output(['git', 'show', BASELINE + ':human_eye_plugin/geometry_safety.py'])
    spec = importlib.util.spec_from_loader('human_eye_plugin._perf030_baseline', loader=None)
    module = importlib.util.module_from_spec(spec)
    exec(compile(source, 'accepted_E/geometry_safety.py', 'exec'), module.__dict__)
    return module


def changed_pair(case, mode):
    pair = meshes(case)
    if mode == 'pose_miss':
        magnitude = float(np.max(np.abs(pair[0].vertices)))
        step = max(.000001, 2 * float(np.spacing(magnitude)))
        pair[0] = pair[0].translated([0, 0, step])
    elif mode == 'geometry_miss':
        value = pair[0].to_dict()
        vertices = np.asarray(value['vertices'])
        bottom = float(vertices[:, 2].min())
        height = float(np.ptp(vertices[:, 2]))
        magnitude = float(np.max(np.abs(vertices)))
        factor = 1 + max(.0001, 4 * float(np.spacing(magnitude)) / height)
        vertices[:, 2] = bottom + (vertices[:, 2] - bottom) * factor
        value['vertices'] = vertices.tolist()
        pair[0] = type(pair[0]).from_dict(value)
    if mode in ('pose_miss', 'geometry_miss'):
        assert not np.array_equal(pair[0].vertices, np.asarray(case['meshes'][0]['vertices']))
    return pair


def prepared_call(case, mode, entry, module):
    cache = scene_cache.SpatialSceneCache()
    original = meshes(case)
    if mode != 'cold':
        if entry == 'task_result':
            task_call(original, cache)
        else:
            module.measure_pair_geometry(*original, need_clearance=True)
    pair = original if mode == 'hot' else changed_pair(case, mode)
    support_before = [hasattr(mesh, '_certified_convex_shells') for mesh in pair]
    if entry == 'task_result':
        return lambda: task_call(pair, cache), support_before
    return lambda: module.measure_pair_geometry(*pair, need_clearance=True), support_before


@contextmanager
def arm(module):
    with patch.object(task_query, 'measure_pair_geometry', module.measure_pair_geometry):
        yield


def freeze():
    data = {'baseline_product_commit': BASELINE, 'candidate_commit': git('rev-parse', 'HEAD'),
            'candidate_source_sha256': runtime_identity()['source_sha256'],
            'input_sha256': digest(OUT / 'inputs.json'),
            'candidate_geometry_sha256': digest(Path(candidate.__file__)),
            'sequence_sha256': digest(Path(__file__)),
            'preregistered_attribution_commit': '399c24d',
            'arms': ['baseline', 'candidate'], 'single_sequence': True,
            'blocks': 5, 'repeats': 3, 'entries': ['measure_pair_geometry', 'task_result'],
            'modes': ['cold', 'pose_miss', 'geometry_miss', 'hot'],
            'order': 'case -> block -> mode -> entry -> repeat -> alternating arm order by block parity',
            'warmup': 'none except explicit original-pair preparation for miss/hot modes',
            'qualification_decision': '30v/56f scalar median 1.8148ms / full 3.3585ms = 54.0%; eligible',
            'candidate': 'AABB row/column envelopes inside original 64 blocks, original leaves and witness phases'}
    data['environment'] = {'python': sys.version, 'executable': sys.executable,
        'numpy': np.__version__, 'platform': platform.platform(),
        'threads': {key: os.environ.get(key) for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')}}
    data['miss_fixture_correction_before_formal'] = {
        'reason': 'literal 1um translation/1.0001 scaling can round away or scale the world origin at 1e12m',
        'pose': 'focal z translation max(1um,2*spacing(max_abs_focal_vertex))',
        'geometry': 'scale focal z offsets from minimum z by 1+max(0.0001,4*spacing(max_abs_focal_vertex)/height)',
        'proof': 'assert focal represented vertex arrays differ before every miss timing',
        'thresholds_and_cases': 'unchanged from initial inputs.json'}
    (OUT / 'formal_freeze.json').write_text(json.dumps(data, indent=2) + '\n', encoding='utf8')


def run():
    frozen = json.loads((OUT / 'formal_freeze.json').read_text(encoding='utf8'))
    assert git('rev-parse', 'HEAD') == frozen['candidate_commit']
    assert digest(Path(candidate.__file__)) == frozen['candidate_geometry_sha256']
    assert digest(Path(__file__)) == frozen['sequence_sha256']
    assert digest(OUT / 'inputs.json') == frozen['input_sha256']
    assert runtime_identity()['source_sha256'] == frozen['candidate_source_sha256']
    assert all(os.environ.get(key) == '1' for key in frozen['environment']['threads'])
    baseline = baseline_module()
    cases = json.loads((OUT / 'inputs.json').read_text(encoding='utf8'))['cases']
    modules = {'baseline': baseline, 'candidate': candidate}
    with (OUT / 'formal_raw.jsonl').open('x', encoding='utf8') as output:
        for case in cases:
            for block in range(5):
                for mode in frozen['modes']:
                    for entry in frozen['entries']:
                        for repeat in range(3):
                            for name in (['baseline', 'candidate'] if block % 2 == 0 else ['candidate', 'baseline']):
                                module = modules[name]
                                row = {'case': case['name'], 'group': case['group'], 'block': block,
                                       'mode': mode, 'entry': entry, 'repeat': repeat, 'arm': name}
                                with arm(module):
                                    call, row['support_cache_before'] = prepared_call(case, mode, entry, module)
                                    started = time.perf_counter_ns()
                                    try:
                                        value = call()
                                        row['ms'] = (time.perf_counter_ns() - started) / 1e6
                                        if entry == 'task_result':
                                            value, diagnostics = value
                                            row['diagnostics'] = diagnostics
                                            row['status'] = value['status']
                                            row['facts'] = value['facts']
                                        else:
                                            row['measurement'] = value
                                    except Exception as exc:
                                        row.update(ms=(time.perf_counter_ns() - started) / 1e6,
                                                   exception=type(exc).__name__, message=str(exc))
                                output.write(json.dumps(row, allow_nan=False) + '\n')
                                output.flush()
            print('sealed', case['name'], flush=True)


def attribution():
    """Untimed counts and traced peaks, separate from the sealed sequence."""
    baseline = baseline_module()
    cases = json.loads((OUT / 'inputs.json').read_text(encoding='utf8'))['cases']
    rows = []
    for case in cases:
        if case['group'] == 'reject':
            continue
        for name, module in (('baseline', baseline), ('candidate', candidate)):
            row = {'case': case['name'], 'arm': name, 'leaves': []}
            original_pt, original_ee = module._point_triangle_min_sq, module._segment_min_sq
            def point_face(points, triangles):
                row['leaves'].append({'kind': 'point_face', 'rows': len(points), 'columns': len(triangles)})
                return original_pt(points, triangles)
            def edge_edge(a0, a1, b0, b1):
                row['leaves'].append({'kind': 'edge_edge', 'rows': len(a0), 'columns': len(b0)})
                return original_ee(a0, a1, b0, b1)
            with patch.object(module, '_point_triangle_min_sq', point_face), patch.object(module, '_segment_min_sq', edge_edge):
                row['scalar'] = module._surface_distance(*meshes(case))
            if name == 'candidate':
                original_candidates = module._surface_candidates
                row['witness_feature_blocks'] = []
                def witness_candidates(left, right, best):
                    kept_left, kept_right = original_candidates(left, right, best)
                    row['witness_feature_blocks'].append({'kind': 'point_face' if right.shape[1] == 3 else 'edge_edge',
                        'before': len(left) * len(right), 'after': len(kept_left) * len(kept_right)})
                    return kept_left, kept_right
                with patch.object(module, '_surface_candidates', witness_candidates):
                    row['witness'] = module._surface_distance_with_witness(*meshes(case))
                points, triangles, edges = features(meshes(case))
                potential = []
                for left, right in ((points[0][:, None, :], triangles[1]),
                                    (points[1][:, None, :], triangles[0]), (edges[0], edges[1])):
                    low_l, high_l = left.min(axis=1), left.max(axis=1)
                    low_r, high_r = right.min(axis=1), right.max(axis=1)
                    delta = np.maximum(0, np.maximum(low_l[:, None] - high_r, low_r - high_l[:, None]))
                    lower = np.einsum('ijk,ijk->ij', delta, delta)
                    scale = max(np.max(np.abs(left)), np.max(np.abs(right)))
                    margin = 128 * np.finfo(float).eps * scale ** 2
                    potential.append({'total': int(lower.size), 'safely_above_final_minimum':
                        int(np.sum(lower > case['expected_clearance_m'] ** 2 + margin))})
                row['corrected_potential'] = potential
            pair = meshes(case)
            tracemalloc.start()
            module.measure_pair_geometry(*pair, need_clearance=True)
            row['peak_bytes'] = tracemalloc.get_traced_memory()[1]
            tracemalloc.stop()
            rows.append(row)
    (OUT / 'candidate_attribution.json').write_text(json.dumps(rows, indent=2) + '\n', encoding='utf8')


if __name__ == '__main__':
    {'freeze': freeze, 'run': run, 'attribution': attribution}[sys.argv[1]]()
