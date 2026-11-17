"""Read-only independent R1 review controls, without image or raster work."""

import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import tempfile
from fractions import Fraction as F
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT), 'D:/he_anchor_001/venv/Lib/site-packages']
from human_eye_plugin import active_observation_host as host
from human_eye_plugin import active_observation_region_task as core
from human_eye_plugin.active_observation import Region
from human_eye_plugin.live_spatial_mcp import _tool_result


def load_fixture():
    path = HERE.parent / 'core_tests/test_region_task_core.py'
    spec = importlib.util.spec_from_file_location('_r1_independent_transport_fixture', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def text_controls():
    fixture = load_fixture()
    rows = []
    conditions = [('text_only_three', fixture.TASK),
                  ('empty_task', dict(area_min_m2=1_000_000, area_max_m2=2_000_000, normal_z_min=1))]
    with tempfile.TemporaryDirectory() as directory:
        with patch('human_eye_plugin.active_observation_images.rasterize_attention',
                   side_effect=AssertionError('text-only must not raster')):
            for name, condition in conditions:
                value = host.observe_capture(fixture.capture(), directory, region_task=condition, include_image=False)
                value['session_id'] = name
                value['binding']['runtime_source_sha256'] = 'synthetic-transport-current'
                for scope in value['scopes']:
                    scope['binding']['runtime_source_sha256'] = 'synthetic-transport-current'
                for detail in ('brief', 'full'):
                    result = _tool_result(value, is_error=False, response_detail=detail)
                    assert len(result['content']) == 1
                    public = json.loads(result['content'][0]['text'])
                    task = public['region_task'] if detail == 'brief' else public['facts']['region_task']
                    expected = 3 if name == 'text_only_three' else 0
                    assert task['summary']['eligible_region_count'] == expected
                    assert all(row['complete_witness'] is None for row in task['rows'])
                    assert task['summary']['constructed_image_count'] == 0
                    rows.append(dict(case=name, detail=detail, passed=True,
                                     regions=expected, native_image_blocks=0, raster_attempts=0))
    return rows


def screen_rectangle(x0, x1, y0, y1, z=-.5):
    points = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    vertices = tuple((F(2)*F(x)/511-1, 1-F(2)*F(y)/511, F(z)) for x, y in points)
    faces = ((0, 1, 2), (0, 2, 3))
    region = Region('independent', 0, 'plane', (0, 1), vertices, (0, 0, -1))
    return region, ((vertices, faces, None, 'plane'),)


def matrix_pose():
    identity = [[float(i == j) for j in range(4)] for i in range(4)]
    return dict(name='TOP', projection='orthographic', size_px=[512, 512],
                view_matrix=identity, projection_matrix=identity)


def projection_controls():
    results = []
    examples = [('exact_16_interior', (200, 204, 200, 204), 16),
                ('exact_16_boundary', (200.5, 203.5, 200.5, 203.5), 16),
                ('exact_15_interior', (200.25, 203.25, 100.25, 105.25), 15),
                ('zero_centres_small', (200.01, 200.02, 200.01, 200.02), 0)]
    for name, coordinates, expected_centres in examples:
        region, objects = screen_rectangle(*coordinates)
        bound = core.pixel_center_upper_bound(region, objects, matrix_pose())
        x0, x1, y0, y1 = map(F, coordinates)
        exact = sum(x0 <= F(x)+F(1, 2) <= x1 and y0 <= F(y)+F(1, 2) <= y1
                    for x in range(190, 212) for y in range(90, 212))
        assert exact == expected_centres
        assert bound['status'] == 'bounded' and bound['upper_bound'] >= exact
        if expected_centres >= 16:
            assert bound['upper_bound'] >= 16
        if expected_centres == 15:
            assert bound['upper_bound'] == 15
        assert bound['actual_observation'] is False
        results.append(dict(case=name, exact_geometric_centres=exact, bound=bound, passed=True))
    region, objects = screen_rectangle(200, 204, 200, 204)
    pose = matrix_pose()
    pose['view_matrix'] = [[.8, -.6, 0., 0.], [.6, .8, 0., 0.], [0., 0., 1., 0.], [0., 0., 0., 1.]]
    inclined = core.pixel_center_upper_bound(region, objects, pose)
    assert inclined['status'] == 'bounded' and inclined['upper_bound'] >= 16
    results.append(dict(case='rotated_projected_bbox_conservative', bound=inclined, passed=True))
    for name, coordinates in [('clip_boundary', (0, 4, 200, 204)),
                              ('outside_clip', (-1, 4, 200, 204)),
                              ('degenerate', (200, 200, 200, 204)),
                              ('nearly_degenerate', (200, math.nextafter(200., math.inf), 200, 204))]:
        region, objects = screen_rectangle(*coordinates)
        bound = core.pixel_center_upper_bound(region, objects, matrix_pose())
        assert bound['status'] == 'unknown' and bound['upper_bound'] is None
        results.append(dict(case=name, bound=bound, passed=True))
    left = 200.5 + 1e-11
    region, objects = screen_rectangle(left, 203.5, 200.5, 203.5)
    bound = core.pixel_center_upper_bound(region, objects, matrix_pose())
    exact_negative_lambda = (F(200.5) - F(left)) / (F(203.5) - F(left))
    assert -F(1e-10) < exact_negative_lambda < 0
    assert bound['status'] == 'bounded' and bound['pixel_index_ranges'][0][0] <= 200
    results.append(dict(case='barycentric_tolerance_outside_exact_edge', passed=True, bound=bound,
        exact_negative_lambda=str(exact_negative_lambda), pixel_center_x=200.5,
        premise='Exact geometric bbox excludes this centre. The accepted-lambda tolerance enclosure includes it.'))
    return results


def skip_controls():
    rows = []
    for name, bounds, expected in [('all_below', [15, 15], 1), ('one_exact_16', [1, 16], 3),
                                    ('one_unknown', [1, None], 3), ('one_large', [1, 100], 3)]:
        session = SimpleNamespace(regions=[SimpleNamespace(roi_id='a'), SimpleNamespace(roi_id='b')],
            objects=(), state=SimpleNamespace(observed_views={}, covered_mask=0),
            cameras=dict(views=[dict(name=view) for view in ('SCENE', 'TOP', 'LEFT')]))
        session.index = SimpleNamespace(view_masks=dict(SCENE=3, TOP=3, LEFT=3),
            classifications={view: {roi: dict(complete=True, status='complete') for roi in ('a', 'b')}
                             for view in ('SCENE', 'TOP', 'LEFT')})
        session.summary = lambda: dict(covered_roi_ids=[])
        class Images:
            def __init__(self, *arguments, **keywords):
                pass
            def render_view(self, view):
                return dict(view_name=view, image_sha256='sha-' + view, patch_mapping_identity='patch',
                    owner_schema='owner', owner_mapping_identity='mapping', frame_identity='frame-' + view,
                    PNG_bytes=0, compressed_array_file_bytes=0, array_payload_bytes=0, buffers={})
            def observe_frame(self, frame):
                session.state.observed_views[frame['view_name']] = dict(actual=True)
                return dict(stages={}, update={}, summary={})
        def bound(region, objects, pose):
            result = bounds[0 if region.roi_id == 'a' else 1]
            return dict(roi_id=region.roi_id, status='unknown' if result is None else 'bounded', upper_bound=result,
                        actual_observation=False)
        work = {key: 0 for key in ('patch_mapping_calls', 'raster_attempts', 'raster_completed', 'PNG_bytes',
            'NPZ_bytes', 'array_payload_bytes', 'local_verified_images', 'pixel_bound_region_calls', 'global_views_skipped')}
        binding = dict(binding_sha256='binding', scene_revision='revision', camera_identity='camera')
        def facts(current, *arguments):
            return dict(actual_observed_views=list(current.state.observed_views))
        with patch.object(core, 'ActiveObservationImages', Images), patch.object(core, '_facts', facts), \
                patch.object(core, 'pixel_center_upper_bound', side_effect=bound) as prediction:
            scope, frames = core._render_scope(session, (), binding, 'global', {'a', 'b'}, Path('.'),
                                               work, {}, None, None, True)
        assert len(frames) == expected and frames[0]['view_name'] == 'SCENE'
        assert 'SCENE' not in [row['view_name'] for row in scope['skipped_views']]
        assert set(session.state.observed_views) == {frame['view_name'] for frame in frames}
        assert all(not row['actual_observation'] for row in scope['skipped_views'])
        if name == 'all_below':
            assert len(scope['skipped_views']) == 2 and prediction.call_count == 4
        else:
            assert scope['skipped_views'] == []
        rows.append(dict(case=name, passed=True, constructed_frame_metadata=len(frames),
                         image_constructions=0, observed_views=list(session.state.observed_views),
                         skipped_views=scope['skipped_views']))
    return rows


if __name__ == '__main__':
    result = dict(schema='cross-scale-transport-r1-readonly-controls-v1', text_controls=text_controls(),
        projection_controls=projection_controls(), skip_controls=skip_controls(),
        actual_Blender=0, production_raster_calls=0, synthetic_PNG_saves=0, paid_model_calls=0)
    paths = [Path(__file__).resolve(), ROOT / 'human_eye_plugin/live_spatial_mcp.py',
             ROOT / 'human_eye_plugin/active_observation_region_task.py']
    result['input_pins'] = [dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()) for path in paths]
    (HERE / 'R1_READONLY_CONTROLS.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf8')
    print(json.dumps(dict(passed=True, text_cases=len(result['text_controls']),
        projection_cases=len(result['projection_controls']), skip_cases=len(result['skip_controls']), new_image_work=0)))
