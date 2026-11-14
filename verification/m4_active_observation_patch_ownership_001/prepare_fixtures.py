"""Freeze split/join world geometry and independent axis-aligned patch answers."""

from fractions import Fraction
import hashlib
import json
from pathlib import Path
import struct
import time


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SOURCE = ROOT / 'verification/m4_active_observation_host_bridge_001/inputs/QA_GEOMETRY.json'
SOURCE_SHA = '6d3772a061dbdde5b2a65317252548f9f2129c12afdb52570e41f19a48ff05bd'


def encoded(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + '\n').encode()


def save(path, value):
    with path.open('xb') as stream:
        stream.write(encoded(value))


def digest(value):
    return hashlib.sha256(json.dumps(value, default=str, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def host_id(name):
    return 'blender:' + hashlib.sha256(json.dumps(['', name], ensure_ascii=False,
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def subtract(a, b):
    return tuple(x - y for x, y in zip(a, b))


def normal(points):
    a, b = subtract(points[1], points[0]), subtract(points[2], points[0])
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def quad_for_axis(vertices, axis, sign):
    low = [min(point[k] for point in vertices) for k in range(3)]
    high = [max(point[k] for point in vertices) for k in range(3)]
    assert low[axis] == high[axis]
    first, second = (axis + 1) % 3, (axis + 2) % 3
    if sign < 0:
        first, second = second, first
    corners = [low.copy() for _ in range(4)]
    corners[1][first] = high[first]
    corners[2][first], corners[2][second] = high[first], high[second]
    corners[3][second] = high[second]
    return tuple(tuple(point) for point in corners)


def main():
    started = time.perf_counter_ns()
    source = SOURCE.read_bytes()
    assert hashlib.sha256(source).hexdigest() == SOURCE_SHA
    old = json.loads(source)
    assert len(old['objects']) == 28
    extra = {'name': 'QA_UnsupportedTriangle',
             'vertices': [['-9/64', '-11/64', '1/32'],
                          ['-7/64', '-11/64', '1/32'],
                          ['-9/64', '-9/64', '1/32']],
             'triangles': [[0, 1, 2]]}
    objects = sorted(old['objects'] + [extra], key=lambda item: host_id(item['name']))
    joined = {'name': 'QA_Joined', 'vertices': [], 'triangles': []}
    patches, source_maps, world_triangles = [], [], []
    for object_index, obj in enumerate(objects):
        vertex_offset, triangle_offset = len(joined['vertices']), len(joined['triangles'])
        joined['vertices'].extend(obj['vertices'])
        joined['triangles'].extend([[index + vertex_offset for index in face] for face in obj['triangles']])
        vertices = [tuple(Fraction(value) for value in point) for point in obj['vertices']]
        for point in vertices:
            for value in point:
                assert Fraction(struct.unpack('<f', struct.pack('<f', float(value)))[0]) == value
        groups = {}
        for index, face in enumerate(obj['triangles']):
            points = tuple(vertices[i] for i in face)
            world_triangles.append([[str(value) for value in point] for point in points])
            n = normal(points)
            axes = [k for k in range(3) if n[k]]
            assert len(axes) == 1
            axis = axes[0]
            assert all(point[axis] == points[0][axis] for point in points)
            groups.setdefault((axis, points[0][axis], 1 if n[axis] > 0 else -1), []).append(index)
        source_maps.append({'name': obj['name'], 'split_object_index': object_index,
                            'host_id': host_id(obj['name']), 'joined_vertex_offset': vertex_offset,
                            'joined_triangle_offset': triangle_offset,
                            'vertices': len(vertices), 'triangles': len(obj['triangles'])})
        if obj['name'] == extra['name']:
            assert len(groups) == 1 and len(obj['triangles']) == 1
            continue
        assert len(groups) == (1 if obj['name'] <= 'Obj_006' else 6)
        for (axis, plane, sign), indices in sorted(groups.items()):
            assert len(indices) == (512 if obj['name'] <= 'Obj_006' else 2)
            points = {vertices[i] for index in indices for i in obj['triangles'][index]}
            quad = quad_for_axis(points, axis, sign)
            patch_normal = normal((quad[0], quad[1], quad[3]))
            area_sum = sum(normal(tuple(vertices[i] for i in obj['triangles'][index]))[axis]
                           for index in indices)
            assert area_sum == 2 * patch_normal[axis]
            patches.append({'roi_id': 'roi_' + digest(quad)[:24],
                'source_object_name': obj['name'], 'axis': axis, 'plane': str(plane),
                'normal_sign': sign, 'quad': [[str(x) for x in point] for point in quad],
                'normal': [str(x) for x in patch_normal],
                'split_object_index': object_index, 'split_triangle_indices': indices,
                'joined_triangle_indices': [index + triangle_offset for index in indices]})
    patches.sort(key=lambda patch: patch['roi_id'])
    assert len(patches) == len({patch['roi_id'] for patch in patches}) == 138
    assert len(joined['vertices']) == 1913 and len(joined['triangles']) == 3337
    joined_world = [[[str(Fraction(x)) for x in joined['vertices'][i]] for i in face]
                    for face in joined['triangles']]
    assert joined_world == world_triangles
    old_bounds = [(min(Fraction(p[k]) for o in old['objects'] for p in o['vertices']),
                   max(Fraction(p[k]) for o in old['objects'] for p in o['vertices'])) for k in range(3)]
    assert all(low <= Fraction(p[k]) <= high for p in extra['vertices']
               for k, (low, high) in enumerate(old_bounds))
    def find(name, axis, sign):
        return next(patch['roi_id'] for patch in patches if patch['source_object_name'] == name
                    and patch['axis'] == axis and patch['normal_sign'] == sign)
    checks = {
        'SCENE_visible_front': {'roi_id': find('Obj_007', 2, 1), 'front_facing': True,
            'surface_pixels': 'positive', 'readable': True,
            'proof': 'The upper square is at the global maximum z. Every SCENE ray toward the eye immediately has greater z than all scene triangles.'},
        'SCENE_hidden_same_object_rear': {'roi_id': find('Obj_001', 2, 1), 'front_facing': True,
            'surface_pixels': 0, 'readable': False, 'occluder_roi_id': find('Obj_007', 2, 1),
            'positive_minimum_z_gap_m': '237/2048',
            'ray_direction': [4, -4, 3], 'XY_shift_at_front_box_bottom': ['79/512', '-79/512'],
            'proof': 'At z=237/2048 each ray from the complete z=0 panel lies strictly inside Obj_007 XY bounds, so the box blocks every panel point with a positive depth separation.'},
        'TOP_visible_front': {'roi_id': find('Obj_008', 2, 1), 'front_facing': True,
            'surface_pixels': 'positive', 'readable': True,
            'proof': 'Axis-aligned upper square is unobstructed in TOP and has positive registered screen area.'},
        'TOP_hidden_same_object_rear': {'roi_id': find('Obj_001', 2, 1), 'front_facing': True,
            'surface_pixels': 0, 'readable': False, 'occluder_roi_id': find('Obj_008', 2, 1),
            'positive_minimum_z_gap_m': '237/2048',
            'proof': 'The entire Obj_001 XY square is strictly inside Obj_008 XY bounds. Every TOP ray meets the box at positive z before reaching z=0.'},
        'all_six_back_facing': {'roi_id': find('Obj_007', 2, -1), 'readable': False,
            'proof': 'Bottom normal has negative z and all six registered target-to-eye directions have positive z.'},
    }
    inputs = HERE / 'inputs'
    inputs.mkdir(exist_ok=False)
    common = {key: value for key, value in old.items() if key != 'objects'}
    save(inputs / 'SPLIT.json', dict(common, objects=objects))
    save(inputs / 'JOINED.json', dict(common, objects=[joined]))
    unsupported = next(row for row in source_maps if row['name'] == extra['name'])
    save(inputs / 'EXPECTED_PATCHES.json', {'schema': 'patch-ownership-independent-axis-oracle-v1',
        'scope': 'Known axis-aligned panel grids and box faces from construction, independent of candidate grouping.',
        'regions': patches, 'source_maps': source_maps, 'checkpoints': checks,
        'supported_triangles': 3336, 'unsupported_triangles': 1,
        'unsupported_split_object_index': unsupported['split_object_index'],
        'unsupported_joined_triangle_index': unsupported['joined_triangle_offset'],
        'expected_patch_count': 138, 'draw_order_world_triangles_sha256': digest(world_triangles),
        'world_triangle_sequence_equal': True, 'old_world_bounds_preserved': True})
    save(inputs / 'FIXTURE.json', {'schema': 'patch-ownership-fixture-v1',
        'original_geometry_path': str(SOURCE), 'original_geometry_sha256': SOURCE_SHA,
        'added_once_before_candidate_execution': extra, 'object_order': 'BlenderSceneHost.object_id sorted order',
        'split_objects': 29, 'joined_objects': 1, 'vertices': 1913, 'triangles': 3337,
        'patches': 138, 'geometry_same_except_object_grouping': True,
        'candidate_geometry_or_raster_functions_called': 0,
        'started_ns': started, 'closed_before_publication_ns': time.perf_counter_ns()})
    print(json.dumps({'patches': 138, 'vertices': 1913, 'triangles': 3337,
                      'new_candidate_calls': 0, 'checkpoints': checks}))


if __name__ == '__main__':
    main()
