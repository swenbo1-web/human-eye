"""Independent saved-result replay, with no product or Blender imports."""
from collections import Counter
from fractions import Fraction as F
import hashlib
from itertools import combinations
import json
import math
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
SOURCE = 'b3654f6f943c3fb6feff0011397c0a8c20872e41f35973e6baf53e3a5e277314'
COMMIT = 'c6355a01a4c6ee204a0d676cd9309f02428fe3ba'
TOLERANCE = F(1, 10**10)


def read(path):
    return json.loads(path.read_bytes())


def digest(value):
    return hashlib.sha256(value).hexdigest()


def vector_subtract(a, b):
    return tuple(x-y for x, y in zip(a, b))


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def on_surface(raw_point, triangles):
    point = tuple(F(value) for value in raw_point)
    for triangle in triangles:
        if any(point[axis] < min(p[axis] for p in triangle)-TOLERANCE
               or point[axis] > max(p[axis] for p in triangle)+TOLERANCE
               for axis in range(3)):
            continue
        a, b, c = triangle
        u, v = vector_subtract(b, a), vector_subtract(c, a)
        w = vector_subtract(point, a)
        uu, vv, uv = dot(u, u), dot(v, v), dot(u, v)
        determinant = uu*vv-uv*uv
        assert determinant > 0
        s = (dot(w, u)*vv-dot(w, v)*uv)/determinant
        t = (dot(w, v)*uu-dot(w, u)*uv)/determinant
        barycentric = (1-s-t, s, t)
        clipped = tuple(max(F(0), value) for value in barycentric)
        total = sum(clipped)
        assert total > 0
        projected = tuple(sum(weight*p[axis] for weight, p in zip(clipped, triangle))/total
                          for axis in range(3))
        delta = vector_subtract(point, projected)
        if dot(delta, delta) <= TOLERANCE*TOLERANCE:
            return True
    return False


def check(row, state):
    truth = read(BATCH/'qualification'/(state.upper()+'_TRUTH.json'))
    snapshot = read(BATCH/'qualification'/(state.upper()+'_SNAPSHOT.json'))
    expected = {}
    for pair in truth['pairs']:
        names = tuple(sorted((pair['object_a'], pair['object_b'])))
        assert names not in expected
        square = pair['exact_squared_distance_m2']
        expected[names] = F(int(square['numerator']), int(square['denominator']))
        assert pair['matches_threshold'] == (expected[names] <= F(.002)**2)
    sources, ids = {}, {}
    for obj in snapshot['objects']:
        encoded = json.dumps(['', obj['name']], sort_keys=True,
                             separators=(',', ':'), ensure_ascii=False).encode('utf8')
        ids['blender:'+digest(encoded)] = obj['name']
        vertices = [tuple(F(value) for value in point) for point in obj['vertices_world']]
        sources[obj['name']] = [tuple(vertices[index] for index in face) for face in obj['triangles']]
    assert len(ids) == 24
    assert set(expected) == set(combinations(sorted(sources), 2)) and len(expected) == 276
    body = row['body']
    assert body['status'] == 'complete' and body['threshold_m'] == .002
    assert body['binding']['runtime_source_sha256'] == SOURCE
    actual, counts = {}, Counter()
    for part in row['diagnostics']['dispositions']:
        object_ids = part['object_ids']
        assert len(object_ids) == 2 and object_ids == sorted(set(object_ids))
        names = tuple(sorted(ids[oid] for oid in object_ids))
        assert names in expected and names not in actual
        status = part['status']
        assert status in ('bound_excluded', 'measured_match', 'measured_nonmatch')
        assert (status == 'measured_match') == (expected[names] <= F(.002)**2)
        actual[names] = status
        counts[status] += 1
        if status == 'bound_excluded':
            bound = part['lower_bound_m']
            assert math.isfinite(bound) and bound > .002 and F(bound)**2 <= expected[names]
        else:
            assert math.isfinite(part['distance_m']) and part['distance_m'] >= 0
            assert abs(part['distance_m']-math.sqrt(float(expected[names]))) <= float(TOLERANCE)
    assert set(actual) == set(expected)
    public = set()
    maximum_error = 0.
    for match in body['matches']:
        objects = match['objects']
        assert len(objects) == 2
        assert [obj['id'] for obj in objects] == sorted(set(obj['id'] for obj in objects))
        assert all(ids[obj['id']] == obj['name'] for obj in objects)
        names = tuple(sorted(obj['name'] for obj in objects))
        assert names not in public and actual[names] == 'measured_match'
        public.add(names)
        assert match['witness_status'] == 'measured'
        distance = match['distance_m']
        assert math.isfinite(distance) and distance >= 0
        error = abs(distance-math.sqrt(float(expected[names])))
        assert error <= float(TOLERANCE)
        maximum_error = max(maximum_error, error)
        first, second = match['point_a_world'], match['point_b_world']
        assert on_surface(first, sources[objects[0]['name']])
        assert on_surface(second, sources[objects[1]['name']])
        assert abs(math.dist(first, second)-distance) <= float(TOLERANCE)
    assert public == {pair for pair, square in expected.items() if square <= F(.002)**2}
    for status in ('bound_excluded', 'measured_match', 'measured_nonmatch', 'unknown', 'deferred'):
        assert body['coverage'][status] == counts[status]
    assert body['coverage']['total_pairs'] == len(expected)
    assert body['delivery']['matches_total'] == body['delivery']['delivered_matches'] == len(public)
    return dict(passed=True, state=state, pairs=len(actual), partitions=dict(counts),
                public_distances=len(public), surface_witnesses=2*len(public),
                maximum_public_distance_error_m=maximum_error)


def main():
    sequence = read(BATCH/'engineering/run_01/sequence_01/RESULTS.json')
    process = read(BATCH/'engineering/process_01/RESULTS.json')
    assert sequence['passed'] and process['passed']
    assert [row['state'] for row in sequence['business']] == ['cold', 'repeat', 'edit']
    results = [dict(label='sequence_01/'+row['state'],
                    **check(row, 'edit' if row['state'] == 'edit' else 'base'))
               for row in sequence['business']]
    results.append(dict(label='process_01/base', **check(process, 'base')))
    actor_relative = 'verification/native_plugin_complex_003/actor.py'
    actor = ROOT/actor_relative
    committed = subprocess.check_output(['git', 'show', COMMIT+':'+actor_relative], cwd=ROOT)
    assert committed == actor.read_bytes()
    current_inputs = read(HERE/'ENGINEERING_REVIEW_INPUTS.json')
    current_inputs['actor_transitive_dependency'] = dict(path=actor_relative, commit=COMMIT,
        current_sha256=digest(actor.read_bytes()), commit_sha256=digest(committed), bytes_equal=True)
    current_inputs['saved_result_recheck'] = dict(passed=True, rows=results,
        all_pair_dispositions=sum(row['pairs'] for row in results),
        public_distances=sum(row['public_distances'] for row in results),
        surface_witnesses=sum(row['surface_witnesses'] for row in results),
        source_result_files=[dict(path=str(path.relative_to(ROOT)), sha256=digest(path.read_bytes()))
            for path in (BATCH/'engineering/run_01/sequence_01/RESULTS.json',
                         BATCH/'engineering/process_01/RESULTS.json')])
    assert not any(name.startswith(('human_eye_plugin', 'human_eye_module1_operators')) for name in sys.modules)
    current_inputs.update(product_imports=0, product_calls=0, Blender_starts=0)
    (HERE/'ENGINEERING_REVIEW_INPUTS.json').write_text(json.dumps(current_inputs, indent=2)+'\n',
                                                   encoding='utf8')
    print(json.dumps(current_inputs['saved_result_recheck']))


if __name__ == '__main__':
    main()
