"""Shared qualification and evidence checks for this exact transfer fixture."""

import io
import math
from pathlib import Path
import runpy
import sys


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
ORACLE = runpy.run_path(str(NS / 'truth/oracle.py'))
FORMAL = runpy.run_path(str(V / 'm4_cross_scale_live_task_formal_001/scoring/formal.py'))
PIXELS = runpy.run_path(str(V / 'm4_source_region_active_view_001/checks/evidence.py'))
MEMBER = runpy.run_path(str(V / 'm5_observe_measure_001/oracle.py'))['membership']
TERMINAL = ORACLE['TERMINAL']
read, pin, checked, coordinates, F = (ORACLE[key] for key in ('read', 'pin', 'checked', 'coordinates', 'F'))
TARGETS = ('M09', 'M03')
SELECTORS = [{'name': name} for name in TARGETS]
REGION_QUERY = {'mode': 'source_region',
                'region': {'object': SELECTORS[0], 'source_triangle_indices': [0, 1]},
                'reference': SELECTORS[1], 'requested_facts': ['surface_proximity']}
LEGACY = {'mode': 'task', 'objects': SELECTORS, 'requested_facts': ['surface_proximity']}
SET = {'mode': 'task', 'target': SELECTORS[0], 'candidates': SELECTORS[1:],
       'requested_facts': ['surface_proximity', 'spatial_relation']}
INSTALL_PATH = V / 'm1_source_region_final_image_001/install/PRODUCT_RUN_BINDING.json'


def library(product=False):
    install = read(INSTALL_PATH)
    if product:
        sys.path.insert(0, install['install_root'])
    sys.path.insert(0, install['dependency_root'])
    return install


def same_geometry(source, terminal):
    wanted = {obj['name']: obj for obj in coordinates(terminal['objects'])}
    expected = {obj['name']: obj for obj in coordinates(read(TERMINAL)['objects'])}
    checked(wanted == expected, 'terminal_evaluated_geometry_changed')
    if source is not None:
        selected = {mesh['name']: {'name': mesh['name'], 'triangles': mesh['faces'],
                    'vertices': [tuple(map(F, point)) for point in mesh['vertices']]}
                    for mesh in source['meshes']}
        checked(selected and selected.keys() <= wanted.keys() and
                all(row == wanted[name] for name, row in selected.items()),
                'actual_capture_differs_from_whole_ordered_source')
    return wanted


def frame_geometry(frame, terminal, png, arrays, truth):
    import numpy as np
    from PIL import Image

    region = truth['region']
    pose = frame['pose']
    direction = frame['direction_rational']
    checked(direction == pose['direction_rational'], 'recorded_camera_direction_changed')
    with np.load(io.BytesIO(arrays), allow_pickle=False) as values, Image.open(io.BytesIO(png)) as image:
        checked(image.format == 'PNG' and image.size == (512, 512) and
                np.array_equal(np.asarray(image.convert('RGB')), values['color'][:, :, :3]),
                'original_png_not_the_archived_frame_color')
        surface, boundary, points = FORMAL['pixels'](frame, region, terminal, values)
        index = frame['object_names'].index(region['object_name'])
        delta = frame['source_face_offsets'][index]
        metrics = PIXELS['split_pixels'](values['color'][:, :, :3], values['owners'],
            values['triangle_ids'] - delta, region['source_triangle_indices'], index)
        checked((surface, boundary) == (metrics['surface'], metrics['contrast']), 'pixel_checks_disagree')
        mask = ((values['owners'] == index) &
                np.isin(values['triangle_ids'] - delta, region['source_triangle_indices']))
        passes_frame = bool(not (mask[0].any() or mask[-1].any() or mask[:, 0].any() or mask[:, -1].any()))
    proof = next((proof for proof in region['finite_direction_proofs'].values()
                  if proof['direction'] == direction), None)
    if proof is None:
        old = runpy.run_path(str(ORACLE['OLDER'] / 'oracle.py'))
        topology, geometry = old['helpers']()
        objects = sorted(coordinates(terminal['objects']), key=lambda row: row['name'])
        normal = region['plane_normal_integer']
        hits = old['occluders'](objects, region, direction, geometry) if ORACLE['dot'](normal, direction) > 0 else None
        proof = {'whole_region_clear': hits == [], 'positive_area_occluders': hits}
    in_view = FORMAL['in_frame'](pose, points, direction) and passes_frame
    readable = (proof['whole_region_clear'] and in_view and metrics['visible_source_ids'] == [0, 1]
                and surface >= 16 and boundary >= 4)
    return {'qualifies': readable, 'camera': frame['view'], 'direction': direction,
            'source_triangles': metrics['visible_source_ids'], 'all_corners_in_frame': in_view,
            'surface_pixels': surface, 'contrasting_boundary_pixels': boundary, 'geometry': proof}


def measure_body(value, objects):
    """Validate actual legacy and pair-set proximity, including witness membership."""
    binding = value['binding']
    bound = binding['objects']
    checked(value['result_kind'] == 'task_query' and value['execution_authority'] is False and
            value['unit'] == 'm' and value['coordinate_frame'] == 'world' and
            [row['name'] for row in bound] == list(TARGETS), 'unexpected_whole_object_task_response')
    schema = value['schema_version']
    if schema in ('task-query-set-v1', 'task-query-set-v2'):
        pair, = value['pairs']
        checked(value['scope'] == 'explicit_target_candidates' and value['pair_order'] == 'target_to_candidate'
                and pair['object_id'] == bound[1]['object_id'] and pair['candidate_index'] == 0,
                'task_set_pair_scope_changed')
        facts = pair['facts']
    else:
        checked(schema == 'task-query-v3' and value['pair_order'] == 'A_to_B', 'unsupported_task_measurement_schema')
        facts = value['facts']
    fact = facts['surface_proximity']
    points = fact['value']
    witness = points['nearest_witness']
    members = [MEMBER(tuple(map(F, witness[key])), objects[name]['vertices'], objects[name]['triangles'])
               for key, name in zip(('a', 'b'), TARGETS, strict=True)]
    delta = ORACLE['sub'](witness['b'], witness['a'])

    def accurate(actual, expected):
        return all(math.isclose(a, b, rel_tol=0, abs_tol=1e-12) for a, b in zip(actual, expected, strict=True))

    distance = float(ORACLE['DISTANCE'])
    checked(fact['status'] == 'measured' and math.isclose(points['distance_m'], distance, rel_tol=0, abs_tol=1e-12)
            and accurate(witness['direction_a_to_b'], (0, 0, 1)) and accurate(delta, (0, 0, distance))
            and all(row['within_publication_tolerance_source_triangle_indices'] for row in members),
            'reported_whole_measurement_or_surface_witness_invalid')
    return {'schema': schema, 'binding_scope': binding.get('capture_scope', 'complete_scene_meshes'),
            'bound': bound, 'fact': fact, 'witness_membership': members}
