"""Regression examples for the independent squared-area/signed-normal predicate."""

from fractions import Fraction as F
import json
from pathlib import Path

import expected


def main():
    checks = []
    def check(name, value):
        checks.append(dict(name=name, passed=bool(value)))
    def condition(z, low=1/128, high=1/32):
        return dict(area_min_m2=low, area_max_m2=high, normal_z_min=z)
    area2 = F(1, 64) ** 2
    for normal, z, answer, name in (
            ((0, 0, 1), 1, True, 'up_equal_one'),
            ((0, 0, -1), -1, True, 'down_equal_minus_one'),
            ((1, 0, 0), 0, True, 'horizontal_equal_zero'),
            ((0, 3, 4), .8, True, 'positive_equal_rational'),
            ((0, 3, 4), .8000000000000002, False, 'positive_above'),
            ((0, 3, 4), .7999999999999999, True, 'positive_below'),
            ((0, 3, -4), -.8, True, 'negative_equal_rational'),
            ((0, 3, -4), -.7999999999999999, False, 'negative_threshold_above'),
            ((0, 3, -4), -.8000000000000002, True, 'negative_threshold_below'),
            ((0, 3, -4), 0, False, 'negative_to_zero'),
            ((0, 3, 4), -.9, True, 'positive_to_negative'),
            ((0, 0, 0), -1, False, 'undefined_normal')):
        check(name, expected.qualifies(area2, normal, condition(z)) is answer)
    for low, high, answer, name in (
            (1/64, 1/64, True, 'area_equal_both'),
            (.015625000000000003, 1/32, False, 'area_min_above'),
            (1/128, .015624999999999998, False, 'area_max_below'),
            (0, 1/64, True, 'area_min_zero')):
        check(name, expected.qualifies(area2, (0, 0, 1), condition(.75, low, high)) is answer)
    for value in (True, None, float('nan'), float('inf'), '-1/3'):
        try:
            expected.number(value)
        except ValueError:
            check('reject_number/' + repr(value), True)
        else:
            check('reject_number/' + repr(value), False)
    components, main_set = expected.task_components(expected.fixture(), expected.MAIN)
    check('maximal_components_24', len(components) == 24)
    check('default_exact_three', {row['object_name'] for row in main_set} == {'Obj_02', 'Obj_06', 'Obj_09'})
    _, up_set = expected.task_components(expected.fixture(), condition(1))
    check('unit_up_exact_two', {row['object_name'] for row in up_set} == {'Obj_02', 'Obj_06'})
    moved = expected.fixture(F(1, 4))
    _, moved_set = expected.task_components(moved, expected.MAIN)
    check('translated_task_identity', {row['object_name'] for row in moved_set} == {row['object_name'] for row in main_set})
    check('translated_source_position', next(row for row in moved_set if row['object_name'] == 'Obj_02')['center_world_m'] == [F(1,4), F(0), F(1)])
    result = dict(schema='cross-scale-independent-predicate-controls-v1', passed=all(row['passed'] for row in checks),
                  checks=checks, source_pins=expected.source_pins() + [expected.EXACT.pin(__file__), expected.EXACT.pin(expected.__file__)],
                  actual_operations=dict(Blender=0, MCP=0, raster=0, model=0))
    output = Path(__file__).with_name('PURE_CHECKS.json')
    with output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps(dict(passed=result['passed'], checks=len(checks))))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
