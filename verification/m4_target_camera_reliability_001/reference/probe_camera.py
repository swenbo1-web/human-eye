"""Independent fixed-source pure camera probe. No Blender, raster, or model calls."""
import ast
from fractions import Fraction as F
import hashlib
import itertools
import json
import math
from pathlib import Path
import random
import subprocess
import sys
import types

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-target-001/hefe')
OUT = Path(__file__).parent
COMMIT = '03eb4e2971891dfe0160972cbcf974e3dcf1a21c'
REL = 'human_eye_plugin/blender_host.py'
raw = subprocess.check_output(['git', '-C', str(ROOT), 'show', COMMIT + ':' + REL])
assert raw == (ROOT / REL).read_bytes()
assert raw == (Path('D:/he_m4_target_001/A/product') / REL).read_bytes()
names = {'BlenderHostError', '_vector', '_dot', '_cross', '_norm',
         '_observation_affine_interval', '_observation_target_cameras'}
tree = ast.parse(raw.decode('utf8'), filename=COMMIT + ':' + REL)
nodes = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names]
assert {node.name for node in nodes} == names
ns = {'math': math}
exec(compile(ast.Module(body=nodes, type_ignores=[]), COMMIT + ':' + REL, 'exec'), ns)

def box(points):
    return [[min(p[k] for p in points) for k in range(3)],
            [max(p[k] for p in points) for k in range(3)]]

def exact_project(pose, point):
    hom = [F(x) for x in point] + [F(1)]
    camera = [sum(F(v) * x for v, x in zip(row, hom)) for row in pose['view_matrix']]
    return [sum(F(v) * x for v, x in zip(row, camera)) for row in pose['projection_matrix']]

rng = random.Random(101511)
counts = {'accepted': 0, 'rejected': 0, 'accepted_clipped': 0, 'cases': 0}
first = None
for magnitude in (0., 1e6, 1e8, 1e10, 1e11, 1e12):
    for span in (1., .01, .001, .0001):
        for run in range(16):
            offset = [magnitude * rng.uniform(-1, 1) for _ in range(3)]
            # Non-degenerate axis-aligned square, exactly represented binary64 source points.
            points = [[offset[0] + dx * span, offset[1] + dy * span, offset[2]]
                      for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            counts['cases'] += 1
            try:
                cameras = ns['_observation_target_cameras'](points, [box(points)])
            except ns['BlenderHostError']:
                counts['rejected'] += 1
                continue
            counts['accepted'] += 1
            clipped = []
            for pose in cameras['views']:
                coords = [exact_project(pose, point) for point in points]
                if any(abs(value[k]) > value[3] for value in coords for k in (0, 1)):
                    clipped.append({'view': pose['name'], 'xy': [[float(v) for v in c[:2]] for c in coords],
                                    'view_matrix': pose['view_matrix'], 'projection_matrix': pose['projection_matrix']})
            if clipped:
                counts['accepted_clipped'] += 1
                if first is None:
                    first = {'offset': offset, 'span': span, 'points': points, 'bounds': box(points), 'clipped': clipped,
                             'camera_plan': cameras}

# Independent rational corner extrema check of interval helper at 64 random finite boxes.
interval_checks = []
for i in range(64):
    low = [rng.uniform(-1e12, 1e12) for _ in range(3)]
    bounds = [low, [x + rng.uniform(0, 1e6) for x in low]]
    coefficients = [rng.uniform(-1, 1) for _ in range(3)]
    translation = rng.uniform(-1e12, 1e12)
    interval = ns['_observation_affine_interval'](bounds, coefficients, translation)
    assert interval is not None
    values = [sum(F(c) * F(x) for c, x in zip(coefficients, point)) + F(translation)
              for point in itertools.product(*zip(*bounds))]
    interval_checks.append(F(interval[0]) <= min(values) <= max(values) <= F(interval[1]))

result = {'schema': 'independent-target-camera-probe-v1', 'commit': COMMIT,
          'source_sha256': hashlib.sha256(raw).hexdigest(), 'source_bytes_match_A_install': True,
          'counter': counts, 'first_clipped': first, 'interval_corner_checks': interval_checks,
          'new_Blender_processes': 0, 'new_rasters': 0, 'new_model_calls': 0,
          'scope': 'pure host camera function, exact rational projection of emitted binary64 matrices'}

# The -X-facing square has exactly one front-facing view (LEFT). Test a
# bounded, predeclared 64-case set rather than rendering or changing fixtures.
raw_core = subprocess.check_output(['git', '-C', str(ROOT), 'show', COMMIT + ':human_eye_plugin/active_observation.py'])
module = types.ModuleType('independent_active_observation_core')
module.__file__ = COMMIT + ':human_eye_plugin/active_observation.py'
sys.modules[module.__name__] = module
exec(compile(raw_core, module.__file__, 'exec'), module.__dict__)
left_counterexample = None
rng_left = random.Random(101512)
for index in range(64):
    offset = [1e12 * rng_left.uniform(-1, 1) for _ in range(3)]
    points = [[offset[0], offset[1] + dy * .0001, offset[2] + dz * .0001]
              for dy, dz in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    try:
        plan = ns['_observation_target_cameras'](points, [box(points)])
    except ns['BlenderHostError']:
        continue
    left = next(p for p in plan['views'] if p['name'] == 'LEFT')
    if not any(abs(value[k]) > value[3] for value in [exact_project(left, p) for p in points] for k in (0, 1)):
        continue
    scene = {'objects': [{'name': 'Independent negative-X rectangle', 'vertices': points,
                          'triangles': [[0, 2, 1], [0, 3, 2]]}]}
    local_points = [[x - o for x, o in zip(point, offset)] for point in points]
    local_scene = {'objects': [dict(scene['objects'][0], vertices=local_points)]}
    local_plan = ns['_observation_target_cameras'](local_points, [box(local_points)])
    prepared = module.prepare_scene(scene, plan)
    prepared_local = module.prepare_scene(local_scene, local_plan)
    left_counterexample = {'case_index': index, 'offset': offset, 'points': points,
                           'local_points': local_points, 'camera_plan': plan,
                           'classifications_world': prepared.index.classifications,
                           'classifications_local': prepared_local.index.classifications,
                           'facts_world': prepared.short_facts(), 'facts_local': prepared_local.short_facts()}
    break
result['negative_X_rectangle_counterexample'] = left_counterexample
result['core_source_sha256'] = hashlib.sha256(raw_core).hexdigest()
(OUT / 'camera_probe.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf8')
print(json.dumps({'counter': counts, 'interval_checks_passed': sum(interval_checks),
                  'negative_X_rectangle_counterexample': None if left_counterexample is None else {
                      k: left_counterexample[k] for k in ('case_index', 'offset', 'points',
                                                        'classifications_world', 'classifications_local')}}))
