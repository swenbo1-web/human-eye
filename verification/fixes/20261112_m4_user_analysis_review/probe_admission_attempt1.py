"""Pure-kernel capacity probe; no Blender/model/modified product limits.

Two congruent cubes separated by one metre are represented with either 12 or
192 triangles each. This isolates an admission limit, not task difficulty or
performance. Product module bytes are checked against the fixed Git commit.
"""
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import types

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
HERE = Path(__file__).resolve().parent
COMMIT = 'fac9b4373575d653cc96f39f1dcb225300cd5977'
package = types.ModuleType('_fixed_capacity_probe')
package.__path__ = []
sys.modules[package.__name__] = package
sources = {}
for leaf in ('surface_proximity', 'surface_geometry'):
    rel = 'human_eye_plugin/' + leaf + '.py'
    raw = (ROOT / rel).read_bytes()
    fixed = subprocess.check_output(['git', 'show', COMMIT + ':' + rel], cwd=ROOT)
    assert raw == fixed
    name = package.__name__ + '.' + leaf
    mod = types.ModuleType(name)
    mod.__file__ = str(ROOT / rel)
    mod.__package__ = package.__name__
    sys.modules[name] = mod
    setattr(package, leaf, mod)
    exec(compile(raw, mod.__file__, 'exec', dont_inherit=True), mod.__dict__)
    sources[rel] = hashlib.sha256(raw).hexdigest()


def cube(divisions, translation):
    index, points, faces = {}, [], []

    def vertex(p):
        if p not in index:
            index[p] = len(points)
            points.append([float(p[i] + translation[i]) for i in range(3)])
        return index[p]

    for axis in range(3):
        j, k = (axis + 1) % 3, (axis + 2) % 3
        for side in (-1, 1):
            for u in range(divisions):
                for v in range(divisions):
                    quad = []
                    for a, b in ((u, v), (u + 1, v), (u + 1, v + 1), (u, v + 1)):
                        p = [Fraction(0)] * 3
                        p[axis] = Fraction(side)
                        p[j] = Fraction(-1) + Fraction(2 * a, divisions)
                        p[k] = Fraction(-1) + Fraction(2 * b, divisions)
                        quad.append(vertex(tuple(p)))
                    if side < 0:
                        quad.reverse()
                    faces.extend(((quad[0], quad[1], quad[2]), (quad[0], quad[2], quad[3])))
    edges = Counter(tuple(sorted((f[i], f[(i+1) % 3]))) for f in faces for i in range(3))
    assert all(n == 2 for n in edges.values())
    assert len(points) - len(edges) + len(faces) == 2
    # Each quad partitions one of six planar cube faces; the faces cover the
    # same [-1,1]^3 boundary for both subdivisions, without changing the solid.
    return types.SimpleNamespace(vertices=points, faces=faces), {
        'vertices': len(points), 'faces': len(faces), 'edges': len(edges),
        'closed_edge_incidence': True, 'euler_characteristic': 2,
    }


results = []
for subdivisions in (1, 4):
    left, counts = cube(subdivisions, (0, 0, 0))
    right, _ = cube(subdivisions, (3, 0, 0))
    stages = []
    proximity = package.surface_proximity.measure_surface_proximity(left, right, stages.append)
    relation = package.surface_geometry.classify_closed_solids(left, right, stages.append)
    if subdivisions == 1:
        assert proximity['measurement_valid'] is True and proximity['distance_m'] == 1.
        assert relation['measurement_valid'] is True and relation['relation'] == 'separated'
    else:
        assert proximity['measurement_valid'] is False
        assert proximity['reason'] == 'surface_geometry_work_limit'
        assert relation['measurement_valid'] is False
        assert 'surface_geometry_work_limit' in relation['reason']
    results.append(dict(subdivisions=subdivisions, per_object=counts,
        sum_faces=2*counts['faces'], face_product=counts['faces']**2,
        independent_truth={'distance_m': 1., 'relation': 'separated',
            'proof': 'two identical closed cubes [-1,1]^3 and [2,4]x[-1,1]^2'},
        proximity=proximity, relation=relation, checkpoint_calls=len(stages)))

report = dict(commit=COMMIT, sources=sources, passed=True, cases=results,
    scope='Two fixed pure-kernel admission checks. Not a consumer benchmark or large-asset qualification.',
    Blender_calls=0, model_calls=0, changed_limits=False)
(HERE / 'ADMISSION_PROBE.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
print(json.dumps({'passed':True, 'cases':[
    {'faces_each':r['per_object']['faces'], 'face_product':r['face_product'],
     'distance':r['proximity']['distance_m'], 'reason':r['proximity'].get('reason'),
     'relation':r['relation']['relation']} for r in results]}))
