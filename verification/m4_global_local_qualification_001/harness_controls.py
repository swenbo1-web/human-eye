"""Exercise only the new source and budget guards, without opening Blender."""

import copy
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile


HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    driver = load('_source_guard_controls', HERE / 'harness/run_slot.py')
    ledger = load('_budget_guard_controls', HERE / 'harness/budget.py')
    geometry = json.loads((HERE / 'fixture/GEOMETRY.json').read_bytes())
    source = dict(source=dict(scale_length=1), objects=[dict(name=row['name'], triangles=row['triangles'],
        vertices=[[float(Fraction(value)) for value in point] for point in row['vertices_world_m']])
        for row in geometry['objects']])
    checks = []
    def check(name, value):
        checks.append(dict(name=name, passed=bool(value)))
    def rejects(name, operation):
        try:
            operation()
        except (ValueError, RuntimeError):
            check(name, True)
        else:
            check(name, False)

    driver.validate_source(source, geometry)
    check('exact_frozen_world_points_and_order', True)
    for name in ('unit', 'vertex', 'face_order', 'object_set'):
        altered = copy.deepcopy(source)
        if name == 'unit':
            altered['source']['scale_length'] = .01
        if name == 'vertex':
            altered['objects'][0]['vertices'][0][0] += .125
        if name == 'face_order':
            altered['objects'][0]['triangles'].reverse()
        if name == 'object_set':
            altered['objects'].pop()
        rejects('reject_' + name, lambda: driver.validate_source(altered, geometry))
    with tempfile.TemporaryDirectory(prefix='m4_global_local_budget_') as temporary:
        budget = ledger.Budget(Path(temporary))
        for label in ('global', 'local_open', 'local_covered'):
            start = budget.reserve('Blender_start', label)
            budget.settle_start(start, pid=123, spawn_status='synthetic_not_actual', outcome='guard_test')
            for index in range(6):
                token = budget.reserve('raster_attempt', label)
                budget.settle_rasters(token, actual=1, lower_bound=1, evidence=dict(synthetic=True), outcome='guard_test')
            rejects('reject_seventh_view/' + label, lambda: budget.reserve('raster_attempt', label))
        rejects('reject_fourth_qualification_start', lambda: budget.reserve('Blender_start', 'fourth'))
        rejects('reject_nineteenth_raster', lambda: budget.reserve('raster_attempt', 'fourth'))
        rejects('reject_model_consumer', lambda: budget.reserve('consumer_task', 'global'))
        counts = budget.snapshot()['counts']
        check('synthetic_limits_exact', counts['Blender_start_attempts'] == 3 and counts['all_raster_actual'] == 18)
    paths = [HERE / 'harness/run_slot.py', HERE / 'harness/budget.py', HERE / 'harness_controls.py', HERE / 'fixture/GEOMETRY.json']
    record = dict(schema='m4-global-local-harness-controls-v1', passed=all(row['passed'] for row in checks),
                  checks=checks, actual_Blender=0, actual_raster=0, actual_model=0,
                  input_pins=[dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()) for path in paths])
    with (HERE / 'HARNESS_CONTROLS.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(record, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps(dict(passed=record['passed'], checks=len(checks), actual_operations=0)))
    if not record['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
