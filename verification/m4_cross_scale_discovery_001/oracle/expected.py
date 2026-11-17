"""Independent exact task predicate, reusing the sealed topology oracle."""

from fractions import Fraction as F
import hashlib
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
PRIOR = HERE.parents[1] / 'm4_global_local_qualification_001'
PINS = {
    'oracle/static_oracle.py': '019242f0d881dff998daca74ec5303bda86b202233e207da966b9773673d87f2',
    'fixture/GEOMETRY.json': '34c4ad599c6ead7548b21300315df25808fa274dad9dccafbf3b5808fee56ad8',
    'oracle/STATIC_QUALIFICATION.json': '549fda4551f5b54c873e59b9c0fa83bea0599966c414e5eaea5a2368ec0cacca',
}
for relative, digest in PINS.items():
    if hashlib.sha256((PRIOR / relative).read_bytes()).hexdigest() != digest:
        raise ValueError('sealed_independent_input_changed/' + relative)
SPEC = importlib.util.spec_from_file_location('_sealed_cross_scale_topology', PRIOR / 'oracle/static_oracle.py')
EXACT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXACT)

MAIN = dict(area_min_m2=1/128, area_max_m2=1/32, normal_z_min=3/4)


def number(value):
    if type(value) is int:
        return F(value)
    if type(value) is not float or not value == value or abs(value) == float('inf'):
        raise ValueError('finite_JSON_number_required')
    return F(str(value))


def qualifies(area_squared, normal, conditions):
    lower, upper, threshold = [number(conditions[key]) for key in ('area_min_m2', 'area_max_m2', 'normal_z_min')]
    if not 0 <= lower <= upper or not -1 <= threshold <= 1:
        raise ValueError('task_condition_range')
    if not lower * lower <= area_squared <= upper * upper:
        return False
    squared = sum(value * value for value in normal)
    if squared == 0:
        return False
    z = normal[2]
    if z >= 0 and threshold <= 0:
        return True
    if z < 0 and threshold >= 0:
        return False
    if z >= 0:
        return z * z >= threshold * threshold * squared
    return z * z <= threshold * threshold * squared


def task_components(objects, conditions):
    components = [row for obj in objects for row in EXACT.component_analysis(obj['name'], obj['vertices'], obj['triangles'])]
    eligible = [row for row in components if row['rectangle_supported'] and qualifies(
        row['area_squared_m4'], row['plane_normal_integer'], conditions)]
    return components, eligible


def fixture(translate_open_x=F(0)):
    objects = EXACT.read_objects(json.loads((PRIOR / 'fixture/GEOMETRY.json').read_bytes()))
    if translate_open_x:
        for obj in objects:
            if obj['name'] == 'Obj_02':
                obj['vertices'] = [tuple(value + (translate_open_x if axis == 0 else 0) for axis, value in enumerate(point))
                                   for point in obj['vertices']]
    return objects


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, default=str, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def ordered_geometry(mesh):
    return fingerprint(dict(vertices=mesh['vertices'], faces=mesh['faces']))


def source_pins():
    return [EXACT.pin(PRIOR / relative) for relative in PINS]
