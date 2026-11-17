"""Materialize the pre-result rational recipe without importing product code."""

from fractions import Fraction as F
import argparse
import copy
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
NS = HERE.parent
PRIOR = NS.parent / 'm4_global_local_qualification_001/fixture/GEOMETRY.json'
PRIOR_SHA = '34c4ad599c6ead7548b21300315df25808fa274dad9dccafbf3b5808fee56ad8'


def pin(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, allow_nan=False,
                                    sort_keys=True, indent=2) + '\n', encoding='utf8')


def main(geometry_only=False):
    if pin(PRIOR)['sha256'] != PRIOR_SHA:
        raise ValueError('sealed_original_fixture_changed')
    recipe = copy.deepcopy(json.loads(PRIOR.read_bytes()))
    recipe['schema'] = 'm4-m5-source-region-geometry-v1'
    offsets = [(0, 0, 1), (F(3, 4), 0, 1), (F(3, 4), F(1, 4), 1),
               (F(1, 4), F(1, 4), F(9, 8)), (F(1, 4), F(3, 4), F(9, 8)),
               (0, F(3, 4), 1), (2, 0, F(1, 32)), (2, F(1, 4), F(1, 32))]
    source = next(row for row in recipe['objects'] if row['name'] == 'Obj_07')
    source['vertices_world_m'] = [[str(F(base) + F(value)) for base, value in zip((4, 4, 0), point)]
                                  for point in offsets]
    source['triangles'] = [[0, 1, 2], [0, 2, 3], [0, 3, 4], [0, 4, 5], [1, 6, 7], [1, 7, 2]]
    identity = [[int(i == j) for j in range(4)] for i in range(4)]
    for name, left, right in [('Ref_B', F(11, 2), F(13, 2)), ('Ref_C', F(15, 2), F(17, 2))]:
        points = [(left, 3, 0), (right, 3, 0), (right, 6, 0), (left, 6, 0)]
        recipe['objects'].append(dict(name=name, ordinal=len(recipe['objects']), matrix_world=identity,
            vertices_world_m=[[str(F(value)) for value in point] for point in points],
            triangles=[[0, 1, 2], [0, 2, 3]]))
    recipe['counts'] = dict(objects=11, vertices=64, triangles=62)
    recipe['provenance'] = dict(original_geometry=pin(PRIOR), fixed_recipe='M4_M5_SOURCE_REGION_001_PLAN.md',
                                result_conditioned_tuning=False)
    save(HERE / 'GEOMETRY.json', recipe)
    task = dict(schema='m4-m5-source-region-task-v1', tool='human_eye_scene_observe',
        first_query=dict(mode='source_region', region=dict(object=dict(name='Obj_07'),
            source_triangle_indices=[0, 1, 2, 3]), reference=dict(name='Ref_B'), requested_facts=['surface_proximity']),
        second_query=dict(mode='source_region', region_ref='$first.region_ref',
            reference=dict(name='Ref_C'), requested_facts=['surface_proximity']),
        include_image=True, image_budget=1, detail='full',
        source_domain='evaluated_capture_mesh_object_local_triangle_row',
        selected_source_triangle_indices=[0, 1, 2, 3], whole_source_triangle_indices=[0, 1, 2, 3, 4, 5],
        source_geometry='noncoplanar_concave_L_with_connected_unselected_sloped_wing',
        distances_m=dict(selected_to_B='5/4', selected_to_C='sqrt(137)/4',
            whole_to_B='1/32', whole_to_C='sqrt(2305)/32', selected_translated_x_quarter_to_B='sqrt(5)/2'),
        author_association='The fixture author also authors this product-independent oracle. Root reviews the frozen sources separately.',
        new_model_calls=0)
    save(HERE / 'TASK.json', task)
    if geometry_only:
        print(json.dumps(dict(geometry=pin(HERE / 'GEOMETRY.json'), task=pin(HERE / 'TASK.json'))))
        return
    plan = dict(schema='m4-m5-source-region-build-plan-v1', counts=recipe['counts'],
        output_directory='D:/he_m4_m5_source_region_001/fixture', geometry_path=str((HERE / 'GEOMETRY.json').resolve()),
        preparation_processes=1, raster_attempts=0, source_files_preserved=True,
        inputs=[pin(path) for path in (HERE / 'GEOMETRY.json', Path(__file__), HERE / 'build_asset.py', HERE / 'TASK.json',
                                       NS / 'oracle/static_preflight.py', NS / 'oracle/STATIC_PREFLIGHT.json')])
    save(HERE / 'BUILD_PLAN.json', plan)
    print(json.dumps(dict(geometry=pin(HERE / 'GEOMETRY.json'), plan=pin(HERE / 'BUILD_PLAN.json'))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--geometry-only', action='store_true')
    main(parser.parse_args().geometry_only)
