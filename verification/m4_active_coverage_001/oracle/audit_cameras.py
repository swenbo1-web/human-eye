"""Independent public-camera/whole-geometry checks using scalar matrix math."""

from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROUND_OFF_BOUND = 64 * math.ulp(1.0)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dot(first, second):
    return sum(x * y for x, y in zip(first, second))


def cross(first, second):
    return (first[1] * second[2] - first[2] * second[1],
            first[2] * second[0] - first[0] * second[2],
            first[0] * second[1] - first[1] * second[0])


def normalized(value):
    length = math.sqrt(dot(value, value))
    return tuple(component / length for component in value)


def multiply(matrix, value):
    return tuple(dot(row, value) for row in matrix)


def main():
    scene_path = HERE / 'original/SCENE_GEOMETRY_RATIONAL.json'
    task_path = HERE / 'original/TASK_SPEC.json'
    camera_path = BATCH / 'inputs/CAMERAS.json'
    binary_path = BATCH / 'render/BINARY64_GEOMETRY.json'
    scene, task, cameras, binary = [json.loads(path.read_bytes()) for path in
                                  (scene_path, task_path, camera_path, binary_path)]
    checks = []

    def check(label, value):
        checks.append({'check': label, 'passed': bool(value)})

    check('geometry_source_identity', cameras['source_geometry_file_sha256'] == sha(scene_path))
    check('direction_source_identity', cameras['source_task_spec_file_sha256'] == sha(task_path))
    check('six_registered_camera_order', [pose['name'] for pose in cameras['views']] == list(task['directions']))
    actual_objects = {mesh['name']: mesh for mesh in binary['objects']}
    points = []
    for mesh in scene['objects']:
        converted = [tuple(float(Fraction(value)) for value in vertex) for vertex in mesh['vertices']]
        expected_hex = [[value.hex() for value in vertex] for vertex in converted]
        actual = actual_objects[mesh['name']]
        check('binary64_vertices_' + str(len(points)), actual['vertices_binary64_hex'] == expected_hex
              and actual['triangles'] == mesh['triangles'])
        points.extend(converted)
    check('all_scene_objects_and_vertices_preserved', len(actual_objects) == len(scene['objects']) == 28 and len(points) == 200)
    center = tuple((min(point[axis] for point in points) + max(point[axis] for point in points)) / 2 for axis in range(3))
    pose_reports = []
    for pose in cameras['views']:
        name = pose['name']
        direction = tuple(task['directions'][name])
        d = normalized(direction)
        forward = tuple(-value for value in d)
        seed = (0.0, 1.0, 0.0) if name == 'TOP' else (0.0, 0.0, 1.0)
        right = normalized(cross(forward, seed))
        up = cross(right, forward)
        errors = [abs(first - second) for actual, expected in (
            (pose['target_to_eye_unit'], d), (pose['eye_to_scene_unit'], forward),
            (pose['right_unit'], right), (pose['up_unit'], up), (pose['target'], center))
            for first, second in zip(actual, expected)]
        actual_eye_direction = normalized(tuple(pose['eye'][axis] - center[axis] for axis in range(3)))
        errors.extend(abs(first - second) for first, second in zip(actual_eye_direction, d))
        errors.extend(abs(pose['view_matrix'][axis][component] - expected[component])
                      for axis, expected in enumerate((right, up, d)) for component in range(3))
        check(name + '_basis_and_eye_convention', max(errors) <= ROUND_OFF_BOUND
              and tuple(pose['direction_rational']) == direction and pose['up_seed'] == list(seed))
        projected = [(dot(right, tuple(point[axis] - center[axis] for axis in range(3))),
                      dot(up, tuple(point[axis] - center[axis] for axis in range(3)))) for point in points]
        symmetric_halfspan = max(abs(value) for point in projected for value in point)
        expected_halfspan = symmetric_halfspan * 1.10
        check(name + '_symmetric_five_percent_each_side', abs(pose['half_span_m'] - expected_halfspan) <= ROUND_OFF_BOUND
              and abs(pose['span'] - 2 * expected_halfspan) <= ROUND_OFF_BOUND)
        check(name + '_full_square_orthographic_camera', pose['size_px'] == [512, 512]
              and pose['projection'] == 'orthographic' and pose['projection_matrix'][3] == [0.0, 0.0, 0.0, 1.0]
              and pose['projection_matrix'][0][0] == pose['projection_matrix'][1][1])
        depths, ndc = [], []
        for point in points:
            camera_point = multiply(pose['view_matrix'], (*point, 1.0))
            clip = multiply(pose['projection_matrix'], camera_point)
            assert clip[3] > 0
            ndc.append(tuple(value / clip[3] for value in clip[:3]))
            depths.append(-camera_point[2])
        included = all(-1.0 <= coordinate <= 1.0 for point in ndc for coordinate in point)
        check(name + '_strict_closed_frustum_all_geometry_no_epsilon', included)
        check(name + '_near_far_contain_all_geometry', pose['near'] == 0.08
              and 0 < pose['near'] < min(depths) <= max(depths) < pose['far'])
        endpoint_ndc = []
        for depth in (pose['near'], pose['far']):
            clip = multiply(pose['projection_matrix'], (0.0, 0.0, -depth, 1.0))
            endpoint_ndc.append(clip[2] / clip[3])
        pose_reports.append({'name': name, 'all_200_vertices_closed_frustum': included,
            'minimum_ndc_margin': min(1 - abs(value) for point in ndc for value in point),
            'camera_depth_range_m': [min(depths), max(depths)], 'max_basis_roundoff': max(errors),
            'near_far_scalar_endpoint_NDC_z': endpoint_ndc,
            'endpoint_scope': 'Raw floating matrix evaluation recorded separately. Scene inclusion uses strict comparisons without epsilon.'})
    render_check_path = BATCH / 'render/INPUT_CHECK.json'
    render_check = json.loads(render_check_path.read_bytes())
    clip_source = Path(render_check['clipping_source_path'])
    check('separate_renderer_closed_clip_boundary_evidence_bound', render_check['passed'] is True
          and len(render_check['clip_boundary_controls']) == 6
          and all(row['boundary_retained'] and row['one_ulp_outside_rejected'] for row in render_check['clip_boundary_controls'])
          and render_check['frozen_cameras_sha256'] == sha(camera_path)
          and sha(clip_source) == render_check['clipping_source_sha256']
          and render_check['geometry_tolerance_added'] == 0)
    result = {'passed': all(row['passed'] for row in checks), 'checks': checks, 'views': pose_reports,
        'geometry_points_checked': len(points), 'camera_count': len(cameras['views']),
        'convention': 'direction_rational points from scene to eye. Optical forward is opposite. View basis rows right,up,+scene_to_eye. NDC clipping boundaries are closed.',
        'floating_basis_comparison_bound': ROUND_OFF_BOUND,
        'scope': 'Basis roundoff comparison is separate from geometry/frustum acceptance. Full-scene NDC containment has no added tolerance. ROI visibility answers and pixel readability are separate.',
        'separate_renderer_boundary_checks': {'source_result_sha256': sha(render_check_path),
            'renderer_authored_check_count': render_check['check_count'],
            'clipping_source_sha256': sha(clip_source),
            'scope': 'Recorded clipping controls from the renderer agent are reused with source binding. They are not counted as additional independent oracle visibility trials.'},
        'inputs_sha256': {str(path.resolve()): sha(path) for path in
                          (scene_path, task_path, camera_path, binary_path, render_check_path, clip_source, Path(__file__))},
        'new_model_Blender_product_API_runs': 0}
    (HERE / 'CAMERA_CHECK.json').write_text(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2) + '\n',
                                          encoding='utf8', newline='\n')
    print(json.dumps({'passed': result['passed'], 'checks': len(checks), 'cameras': 6, 'vertices_per_camera': 200}))


if __name__ == '__main__':
    main()
