"""Add independent selected-fit camera review to the frozen first saved checker."""

from fractions import Fraction as F
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys
import traceback

HERE = Path(__file__).resolve().parent
NS = HERE.parents[1]
sys.path.insert(0, str(NS / 'oracle'))
import check_saved
import check_pair

CAMERA_REVIEWS = []


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def camera_checks(capture, binding, selected, source_index, audit):
    """Use exact published coefficients and current source coordinates."""
    specification = binding['camera_specification']
    source = capture['meshes'][source_index]
    vertex_indices = sorted({vertex for row in selected for vertex in source['faces'][row]})
    points = [tuple(map(F, source['vertices'][index])) for index in vertex_indices]
    low = [min(point[axis] for point in points) for axis in range(3)]
    high = [max(point[axis] for point in points) for axis in range(3)]
    center = tuple((a + b) / 2 for a, b in zip(low, high))
    audit.check(tuple(map(F, specification['common_center_world_m'])) == center, 'camera_common_center_exact_selected_bbox')
    all_boxes = []
    for mesh in capture['meshes']:
        vertices = [tuple(map(F, point)) for point in mesh['vertices']]
        bounds = [(min(point[axis] for point in vertices), max(point[axis] for point in vertices)) for axis in range(3)]
        all_boxes.extend(itertools.product(*bounds))
    reviews = []
    for pose in specification['views']:
        view = [list(map(F, row)) for row in pose['view_matrix']]
        projection = [list(map(F, row)) for row in pose['projection_matrix']]
        homogeneous = [(*point, F(1)) for point in points]
        camera_points = [[dot(row, point) for row in view] for point in homogeneous]
        ndc = [[dot(row, point) for row in projection] for point in camera_points]
        audit.check(all(-1 <= point[axis] <= 1 for point in ndc for axis in (0, 1)),
                    'camera_exact_selected_vertex_NDC_enclosure/' + pose['name'])
        audit.check(tuple(map(F, pose['target_world_m'])) == center
                    and pose['target_vertices_checked'] == len(points), 'camera_selected_extent_source_count/' + pose['name'])
        right, up = tuple(map(F, pose['right_unit'])), tuple(map(F, pose['up_unit']))
        relative = [tuple(x - c for x, c in zip(point, center)) for point in points]
        projected = [[dot(point, axis) for point in relative] for axis in (right, up)]
        half_unpadded = max(abs(value) for axis in projected for value in axis)
        wanted_span = float(half_unpadded) * 2.2
        audit.check(math.isclose(pose['view_span_m'], wanted_span, rel_tol=1e-13, abs_tol=1e-13)
                    and math.isclose(float(2 / projection[0][0]), wanted_span, rel_tol=1e-13, abs_tol=1e-13),
                    'camera_square_span_selected_projection_with_original_padding/' + pose['name'])
        depths = [-dot(view[2], (*point, F(1))) for point in all_boxes]
        near, far = F(pose['near']), F(pose['far'])
        audit.check(0 < near < min(depths) <= max(depths) < far,
                    'camera_all_scene_box_corner_depth_enclosure/' + pose['name'])
        audit.check(pose['depth_scope'] == 'all_scene_conservative_bounds', 'camera_declared_full_scene_depth_scope/' + pose['name'])
        audit.check(F(pose['min_camera_depth_m']) <= min(depths)
                    and F(pose['max_camera_depth_m']) >= max(depths), 'camera_conservative_published_depth_bounds/' + pose['name'])
        reviews.append(dict(view_name=pose['name'], selected_vertices=len(points),
            selected_source_triangle_indices=selected, selected_center_world_m=list(map(str, center)),
            fitted_span_m=pose['view_span_m'], independent_selected_projected_span_m=wanted_span,
            exact_selected_ndc_bounds=[[str(min(point[axis] for point in ndc)), str(max(point[axis] for point in ndc))] for axis in (0, 1)],
            all_scene_objects=len(capture['meshes']), all_scene_box_corners=len(all_boxes),
            exact_all_scene_depth_bounds_m=[str(min(depths)), str(max(depths))],
            near_m=pose['near'], far_m=pose['far']))
    CAMERA_REVIEWS.append(dict(binding_sha256=binding['binding_sha256'], views=reviews))


def install():
    original_region = check_saved.region_checks

    def selected_region(full, capture, audit):
        source_index, selected, vertices = original_region(full, capture, audit)
        audit.file(__file__)
        camera_checks(capture, full['binding'], selected, source_index, audit)
        return source_index, selected, vertices

    check_saved.region_checks = selected_region


def main():
    install()
    if '--output' not in sys.argv:
        check_pair.main()
        return
    output = Path(sys.argv[sys.argv.index('--output') + 1])
    try:
        check_pair.main()
        result = json.loads(output.read_bytes())
        result['independent_selected_fit_camera_reviews'] = CAMERA_REVIEWS
        result['local_camera_review_required'] = True
        result['local_camera_adapter_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        output.write_text(json.dumps(result, sort_keys=True, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    except Exception as error:
        failure = dict(schema='m4-m5-source-region-selected-fit-camera-review-v1', passed=False,
            error_type=type(error).__name__, error=str(error), traceback=traceback.format_exc(),
            local_camera_review_required=True, new_live_Blender=0, new_raster=0, new_model=0,
            local_camera_adapter_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        output.write_text(json.dumps(failure, sort_keys=True, indent=2) + '\n', encoding='utf8')
        print(json.dumps(dict(passed=False, output=str(output.resolve()), error=str(error))))
        raise


if __name__ == '__main__':
    main()
