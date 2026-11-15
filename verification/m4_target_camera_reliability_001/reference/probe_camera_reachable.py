"""One fixed Blender-representable target case, no external host or render."""
import ast
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import types

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-target-001/hefe')
OUT = Path(__file__).parent
COMMIT = '03eb4e2971891dfe0160972cbcf974e3dcf1a21c'
raw = subprocess.check_output(['git', '-C', str(ROOT), 'show', COMMIT + ':human_eye_plugin/blender_host.py'])
assert raw == (ROOT / 'human_eye_plugin/blender_host.py').read_bytes()
assert raw == Path('D:/he_m4_target_001/A/product/human_eye_plugin/blender_host.py').read_bytes()
names = {'BlenderHostError', '_vector', '_dot', '_cross', '_norm',
         '_observation_affine_interval', '_observation_target_cameras'}
tree = ast.parse(raw.decode('utf8'))
ns = {'math': math}
exec(compile(ast.Module(body=[n for n in tree.body if getattr(n, 'name', None) in names],
                        type_ignores=[]), COMMIT + ':blender_host.py', 'exec'), ns)
core_raw = subprocess.check_output(['git', '-C', str(ROOT), 'show', COMMIT + ':human_eye_plugin/active_observation.py'])
core = types.ModuleType('independent_fixed_core')
sys.modules[core.__name__] = core
exec(compile(core_raw, COMMIT + ':active_observation.py', 'exec'), core.__dict__)

def f32(x):
    return struct.unpack('<f', struct.pack('<f', x))[0]

offset = [f32(x) for x in (-877075466392.1636, -55016384309.75553, 494971033492.4662)]
span = f32(.0001)
local = [[0., dy * span, dz * span] for dy, dz in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
matrix = [[float(r == c) for c in range(3)] + [offset[r]] for r in range(3)] + [[0., 0., 0., 1.]]
# Exact same order as _resident_capture and nonresident _capture world map.
points = [[(sum(matrix[r][c] * point[c] for c in range(3)) + matrix[r][3]) * 1.0
           for r in range(3)] for point in local]
assert all(f32(x) == x for point in local for x in point)
assert all(f32(x) == x for row in matrix for x in row)

def bounds(vertices):
    return [[min(p[k] for p in vertices) for k in range(3)],
            [max(p[k] for p in vertices) for k in range(3)]]

def evaluate(vertices):
    camera_plan = ns['_observation_target_cameras'](vertices, [bounds(vertices)])
    objects, triangles, identity = core.geometry({'objects': [{'name': 'Negative-X rectangle',
                'vertices': vertices, 'triangles': [[0, 2, 1], [0, 3, 2]]}]})
    scene = core.prepare_scene_from_parsed(objects, triangles, identity, camera_plan, target_object_index=0)
    left = next(v for v in camera_plan['views'] if v['name'] == 'LEFT')
    ndc = []
    for point in vertices:
        cam = [sum(F(c) * x for c, x in zip(row, [*map(F, point), F(1)])) for row in left['view_matrix']]
        proj = [sum(F(c) * x for c, x in zip(row, cam)) for row in left['projection_matrix']]
        ndc.append([float(x) for x in proj])
    return {'camera_plan': camera_plan, 'region_count': len(scene.regions),
            'classifications': scene.index.classifications, 'facts': scene.short_facts(),
            'LEFT_exact_matrix_NDC': ndc}

world = evaluate(points)
# Same captured finite rectangle, merely translated into a common local frame.
origin_control = evaluate([[x - o for x, o in zip(p, offset)] for p in points])
result = {'schema': 'independent-reachable-camera-counterexample-v1', 'commit': COMMIT,
          'source_sha256': hashlib.sha256(raw).hexdigest(), 'core_sha256': hashlib.sha256(core_raw).hexdigest(),
          'all_local_vertices_and_matrix_elements_are_exact_binary32': True,
          'matrix_world': matrix, 'local_vertices': local, 'world_vertices': points,
          'world_bounds': bounds(points), 'world': world, 'origin_control': origin_control,
          'new_Blender_processes': 0, 'new_rasters': 0, 'new_model_calls': 0,
          'limitation': 'Actual Blender host not started; source _capture scalar world-map sequence reproduced exactly.'}
(OUT / 'camera_reachable.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf8')
print(json.dumps({'matrix_world': matrix, 'world_vertices': points, 'region_count': world['region_count'],
                  'world_classifications': world['classifications'],
                  'origin_classifications': origin_control['classifications'],
                  'LEFT_exact_matrix_NDC': world['LEFT_exact_matrix_NDC']}))
