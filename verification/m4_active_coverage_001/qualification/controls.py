"""Geometry-only controls supplied to the candidate without expected labels."""

import copy
import random


SEED = 704513


def renamed_and_reordered(scene):
    result = copy.deepcopy(scene)
    generator = random.Random(SEED)
    names = ['mesh_' + format(value, '08x') for value in generator.sample(range(2**30), len(result['objects']))]
    for obj, name in zip(result['objects'], names):
        obj['name'] = name
    result['objects'].reverse()
    return result


def permuted_mesh_enumeration(scene):
    result = copy.deepcopy(scene)
    generator = random.Random(SEED)
    for obj in result['objects']:
        order = list(range(len(obj['vertices'])))
        generator.shuffle(order)
        inverse = {old: new for new, old in enumerate(order)}
        obj['vertices'] = [obj['vertices'][old] for old in order]
        obj['triangles'] = [[inverse[vertex] for vertex in face] for face in obj['triangles']]
        generator.shuffle(obj['triangles'])
    return result


def off_center_scene():
    """A separate box occludes an interior corner region of a front-facing quad."""
    quad = {'name': 'mesh_alpha',
            'vertices': [['-1', '-1', '0'], ['1', '-1', '0'], ['1', '1', '0'], ['-1', '1', '0']],
            'triangles': [[0, 1, 2], [0, 2, 3]]}
    vertices = [['3/4', '3/4', '1/4'], ['7/8', '3/4', '1/4'],
                ['7/8', '7/8', '1/4'], ['3/4', '7/8', '1/4'],
                ['3/4', '3/4', '1/2'], ['7/8', '3/4', '1/2'],
                ['7/8', '7/8', '1/2'], ['3/4', '7/8', '1/2']]
    faces = [[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
             [0, 4, 7], [0, 7, 3], [1, 2, 6], [1, 6, 5],
             [0, 1, 5], [0, 5, 4], [3, 7, 6], [3, 6, 2]]
    return {'schema': 'active-coverage-geometric-control-v1', 'unit': 'm', 'coordinate_frame': 'world',
            'objects': [quad, {'name': 'mesh_beta', 'vertices': vertices, 'triangles': faces}]}


def off_center_camera():
    """One full-scene orthographic control camera looking from +Z."""
    pose = {'name': 'SCENE', 'projection': 'orthographic', 'size_px': [512, 512],
            'direction_rational': [0, 0, 1], 'target_to_eye_direction_rational': [0, 0, 1],
            'target_to_eye_unit': [0, 0, 1], 'eye_to_scene_unit': [0, 0, -1],
            'view_matrix': [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, -4], [0, 0, 0, 1]],
            'projection_matrix': [['2/3', 0, 0, 0], [0, '2/3', 0, 0],
                                  [0, 0, '-2/5', '-7/5'], [0, 0, 0, 1]],
            'eye': [0, 0, 4], 'target': [0, 0, 0], 'near': 1, 'far': 6, 'span': 3}
    return {'directions': ['SCENE'], 'views': [pose]}
