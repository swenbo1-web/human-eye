"""Private prepared-pair identity regression on the saved two-cube control."""
import hashlib
import json
from pathlib import Path
import sys
import time
import types


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def load_geometry(name, geometry_path):
    package = types.ModuleType(name)
    package.__path__ = []
    sys.modules[name] = package
    for part, path in (('surface_proximity', ROOT / 'human_eye_plugin/surface_proximity.py'),
                       ('surface_geometry', geometry_path)):
        module = types.ModuleType(name + '.' + part)
        module.__package__ = name
        module.__file__ = str(path)
        sys.modules[module.__name__] = module
        setattr(package, part, module)
        exec(compile(path.read_bytes(), str(path), 'exec', dont_inherit=True), module.__dict__)
    return package


def main():
    snapshot = json.loads((ROOT / 'verification/spatial_task_qualification_001/entry/run_01/ACTUAL_SNAPSHOT.json').read_bytes())
    objects = {row['name']: row for row in snapshot['objects']}
    left, right = [types.SimpleNamespace(vertices=objects[name]['vertices_world'], faces=objects[name]['triangles'])
                   for name in ('Control_A', 'Control_B')]
    contained = types.SimpleNamespace(vertices=[[10 + .25*(p[0]-13), .25*p[1], .25*p[2]]
                                                for p in right.vertices], faces=right.faces)
    rows = []
    for label in ('before', 'after'):
        package = load_geometry('_m3_binding_' + label, HERE / ('surface_geometry.py.' + label))
        deadline = time.perf_counter_ns() + 30_000_000_000

        def checkpoint(stage):
            if time.perf_counter_ns() >= deadline:
                raise TimeoutError('original_30s_binding_check')

        exact, closed = package.surface_proximity, package.surface_geometry
        prep_work = exact._Work(checkpoint, {})
        records, topology = exact._admit((left, right), prep_work)
        origin, factor, triangles = exact._integer_frame(records, prep_work)
        pair = (records, topology, origin, factor, triangles)
        wrong_work = {}
        wrong_holder = {}
        wrong = closed.classify_closed_solids(left, contained, checkpoint,
            diagnostics=wrong_work, prepared_pair=pair, prepared_holder=wrong_holder)
        row = {'version': label, 'wrong_candidate_result': wrong,
               'holder_targets_current_candidate': wrong_holder['pair'][0][1][0] is contained}
        if label == 'after':
            valid_work = {}
            row['valid_same_pair'] = closed.classify_closed_solids(left, right, checkpoint,
                diagnostics=valid_work, prepared_pair=pair)
            huge = types.SimpleNamespace(vertices=left.vertices * 600, faces=left.faces)
            stale = {'pair': pair, 'trees': object(), 'boundary_contact': object()}
            row['early_rejection'] = closed.classify_closed_solids(huge, right, checkpoint, prepared_holder=stale)
            row['stale_holder_cleared'] = not stale
        rows.append(row)
    passed = (rows[0]['wrong_candidate_result']['relation'] == 'separated'
              and rows[1]['wrong_candidate_result']['relation'] == 'penetrating'
              and rows[1]['holder_targets_current_candidate']
              and rows[1]['wrong_candidate_result']['work']['prepared_pair_reused'] is False
              and rows[1]['valid_same_pair']['work']['prepared_pair_reused'] is True
              and rows[1]['early_rejection']['reason'] == 'closed_solid_vertex_budget'
              and rows[1]['stale_holder_cleared'])
    report = {'scope': 'deterministic private prepared-pair binding fix, zero G508 repeats',
              'passed': passed, 'rows': rows, 'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'Blender_starts': 0, 'models': 0, 'business_calls': 0}
    with (HERE / 'RESULTS.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed': passed, 'before_wrong_relation': rows[0]['wrong_candidate_result']['relation'],
                      'after_relation': rows[1]['wrong_candidate_result']['relation']}))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
