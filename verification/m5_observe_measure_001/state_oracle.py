"""Independent answers for the registered translation and missing-object states."""

from decimal import Decimal, localcontext
from fractions import Fraction as F
import hashlib
import importlib.util
import json
import math
from pathlib import Path


HERE = Path(__file__).resolve().parent


def base_oracle():
    spec = importlib.util.spec_from_file_location('_m5_base_geometry', HERE / 'oracle.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rounded_sqrt(squared):
    with localcontext() as context:
        context.prec = 80
        result = float((Decimal(squared.numerator)/Decimal(squared.denominator)).sqrt())
    low = (F(math.nextafter(result, -math.inf))+F(result))/2
    high = (F(result)+F(math.nextafter(result, math.inf)))/2
    assert low*low < squared < high*high
    return result


def derive(shift):
    oracle = base_oracle()
    objects = oracle.frozen_objects()
    near = objects['M4_Near']
    target = objects['M4_Far_00']
    far = objects['M4_Far_11']
    a = F(near['world_vertices_m'][0][0])
    world = [[float(F(point[0])+shift), float(F(point[1])), float(F(point[2]))]
             for point in target['world_vertices_m']]
    distance = 1+shift-a
    assert all(F(point[0]) >= 1+shift for point in world)
    assert all(F(point[0]) == a for point in near['world_vertices_m'])
    points = {'a': [float(1+shift), 0, 0], 'b': [float(a), 0, 0]}
    assert oracle.membership(points['a'], world, target['triangles'])['exact_source_triangle_indices']
    assert oracle.membership(points['b'], near['world_vertices_m'], near['triangles'])['exact_source_triangle_indices']
    missing_dx = 10-shift
    missing_squared = missing_dx*missing_dx+1
    missing_witness = {'a': [float(2+shift), 0, 2], 'b': [12, 0, 1]}
    assert oracle.membership(missing_witness['a'], world, target['triangles'])['exact_source_triangle_indices']
    assert oracle.membership(missing_witness['b'], far['world_vertices_m'], far['triangles'])['exact_source_triangle_indices']
    assert 11-shift > rounded_sqrt(missing_squared)
    return {'target_translation_x_exact': str(shift), 'target_world_vertices': world,
            'target_source_triangles': target['triangles'], 'main_distance_exact_m': str(distance),
            'main_distance_binary64_m': float(distance), 'main_direction_a_to_b': [-1, 0, 0],
            'one_main_witness': points,
            'vertical_LEFT_geometry': 'positive_area_occlusion' if shift == 0 else 'complete',
            'Near_shadow_maximum_target_z_exact': str(a-shift),
            'vertical_LEFT_proof': (
                'At shift 0 the Near shadow cuts a positive-area triangle.' if shift == 0 else
                'At shift 1/4 the Near shadow maximum z is a-1/4<0 and the Focal shadow maximum z is -1/4. All other occluders have x>=2 and lie behind the LEFT ray. The horizontal target part has x>=the vertical plane and cannot intersect a positive LEFT ray.'),
            'horizontal_geometry_complete_views': ['SCENE', 'TOP', 'LEFT', 'RIGHT', 'FRONT', 'BACK'],
            'pixel_readability': 'Requires the actual frames of this state; no future image result is supplied.',
            'missing_Far11_distance_squared_exact_m2': str(missing_squared),
            'missing_Far11_distance_binary64_m': rounded_sqrt(missing_squared),
            'missing_Far11_one_witness': missing_witness,
            'missing_Far11_proof': 'Vertical target faces have X gap 11-shift. Horizontal faces have X gap 10-shift and Z gap 1; the displayed corner/edge pair attains their joint bound.'}


def main():
    report = {'schema': 'm5-independent-registered-state-truth-v1',
              'states': {'initial': derive(F(0)), 'matrix_changed': derive(F(1, 4)), 'restored': derive(F(0))},
              'state_control_scope': 'Registered world translation X += 1/4 and exact restore. Actual matrices and world points must still be checked from real receipts.',
              'same_distance_does_not_make_an_old_binding_current': True,
              'base_oracle_sha256': hashlib.sha256((HERE / 'oracle.py').read_bytes()).hexdigest(),
              'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'new_actual_calls': 0, 'new_rasters': 0, 'new_models': 0}
    with (HERE / 'scoring/STATE_TRUTH.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'registered_state_truth_ready': True, 'new_actual_calls': 0}))


if __name__ == '__main__':
    main()
