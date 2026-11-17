"""Synthetic protocol, source and cache regressions with no scene raster."""

import base64
import copy
import hashlib
import io
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, 'D:/he_anchor_001/venv/Lib/site-packages')
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'verification'))
from PIL import Image
from human_eye_plugin.live_spatial_mcp import _tool_result, _validate_arguments
from human_eye_plugin.query_policy import validate_query, validate_region_task
from human_eye_plugin.read_context import query_key
_spec = importlib.util.spec_from_file_location('_accepted_active_service_tests',
    ROOT / 'verification/m5_observe_measure_001/legacy_v2_source/test_active_observation_service.py')
_legacy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_legacy)


CONDITIONS = dict(area_min_m2=1/128, area_max_m2=1/32, normal_z_min=.75)


def fixture(directory):
    objects = [dict(object_index=index, host_id='host-' + str(index),
        instance_id='instance-' + str(index), object_name='Object ' + str(index)) for index in range(3)]
    binding = dict(schema='active-observation-host-source-v1', capture_scope='complete_scene_meshes',
        scene_revision='revision', document_epoch='document', geometry_identity='geometry',
        camera_identity='camera-global', binding_sha256='binding-global', source_binding_sha256='source',
        capture_state=dict(instance_id='host', epoch=1, revision=1, selection_key='scene'), objects=objects,
        source='blender', unit='m', coordinate_frame='world', runtime_source_sha256='runtime')
    supports = [dict(roi_id='roi-' + str(index), object_index=index, triangle_indices=[0, 1]) for index in range(3)]
    scope = dict(patch_support=dict(regions=supports, objects=[], schema='active-patch-support-v1'),
                 capture_object_count=3, supported_roi_object_count=3, domain='rectangles',
                 all_objects_participate_in_occlusion=True, objects_without_supported_roi=[])
    rows = []
    for index, host in enumerate(objects):
        source = dict(document_epoch='document', scene_revision='revision', capture_state=binding['capture_state'],
            host_id=host['host_id'], instance_id=host['instance_id'], object_index=index,
            source_triangle_indices=[0, 1], ordered_geometry_sha256=str(index) * 64,
            parent_binding_sha256='binding-global', parent_source_binding_sha256='source')
        rows.append(dict(host, roi_id='roi-' + str(index), source=source, source_triangle_indices=[0, 1],
            center_world_m=[index, 0, 1], half_edge_u_world_m=[.0625, 0, 0],
            half_edge_v_world_m=[0, .0625, 0], front_direction_world=[0, 0, 1],
            status='covered' if index < 2 else 'unknown',
            reason='observed_readable' if index < 2 else 'positive_area_occlusion_all_front_views', complete_witness=None))
    constructed, scopes = [], []
    for ordinal, scope_id in enumerate(('global', 'local-0', 'local-1')):
        local_binding = copy.deepcopy(binding)
        if ordinal:
            local_binding.update(schema='active-observation-region-source-v1',
                camera_identity='camera-' + scope_id, binding_sha256='binding-' + scope_id,
                parent_binding_sha256='binding-global', parent_source_binding_sha256='source',
                region_source=copy.deepcopy(rows[ordinal - 1]['source']))
        views = ('SCENE', 'TOP', 'LEFT', 'RIGHT', 'FRONT', 'BACK') if ordinal == 0 else ('SCENE',)
        observations = []
        for view in views:
            stream = io.BytesIO()
            Image.new('RGB', (512, 512), (40 + ordinal, 80, 120)).save(stream, format='PNG')
            path = directory / (scope_id + '-' + view + '.png')
            path.write_bytes(stream.getvalue())
            frame = dict(scope_id=scope_id, frame_identity='frame-' + scope_id + '-' + view,
                image_ref='image-' + scope_id + '-' + view, view_name=view, image_path=str(path),
                image_sha256=hashlib.sha256(stream.getvalue()).hexdigest(),
                scene_identity='geometry', candidate_identity=local_binding['camera_identity'],
                camera_identity=local_binding['camera_identity'], host_binding_sha256=local_binding['binding_sha256'],
                source_revision='revision')
            constructed.append(frame)
            pixels = [] if ordinal == 0 else [dict(roi_id=rows[ordinal - 1]['roi_id'],
                visible_surface_pixels=100, contrasting_boundary_pixels=20, readable=True, front_facing=True,
                minimum_surface_pixels=16, minimum_boundary_pixels=4, minimum_rgb_boundary_contrast=24,
                visible_pixel_bounds=[1, 1, 10, 10], visible_pixel_anchor=[5, 5])]
            observations.append(dict(scope_id=scope_id, frame_identity=frame['frame_identity'],
                view_name=view, image_ref=frame['image_ref'], image_path=str(path),
                image_sha256=frame['image_sha256'], pixel_rows=pixels,
                readable_roi_ids=[] if not ordinal else [rows[ordinal - 1]['roi_id']]))
        scope_facts = dict(scene_identity='geometry', candidate_identity=local_binding['camera_identity'],
            coverage=dict(covered_roi_ids=[] if not ordinal else [rows[ordinal - 1]['roi_id']]),
            scope=scope, observations=observations, region_evidence=[] if not ordinal else [
                dict(roi_id=rows[ordinal - 1]['roi_id'], complete_witness=dict(view_name='SCENE', pixel_row_index=0))])
        scopes.append(dict(scope_id=scope_id, binding=local_binding, facts=scope_facts,
            frame_refs=[frame['frame_identity'] for frame in constructed if frame['scope_id'] == scope_id], steps=[]))
        if ordinal:
            frame = constructed[-1]
            rows[ordinal - 1]['complete_witness'] = dict(scope_id=scope_id, view_name='SCENE',
                frame_identity=frame['frame_identity'], image_ref=frame['image_ref'], pixel_row_index=0,
                selected_for_delivery=True)
    facts = copy.deepcopy(scopes[0]['facts'])
    facts['region_task'] = dict(schema='active-region-task-v1', conditions=CONDITIONS,
        rows=rows, summary=dict(eligible_region_count=3, locally_verified_region_count=2,
                               selected_image_count=3, unknown_region_count=1))
    return dict(status='partial', result_kind='active_observation', observation_status='locally_observed',
        session_id='synthetic', read_only=True, execution_authority=False, binding=binding, facts=facts,
        scopes=scopes, frames=[constructed[0], constructed[6], constructed[7]], constructed_frames=constructed,
        work=dict(raster_attempts=8, frame_reuses=0))


class QueryTests(unittest.TestCase):
    def test_normalization_idempotence_decimal_and_large_int(self):
        value = dict(area_min_m2=0.0, area_max_m2=10**100, normal_z_min=-1.0)
        normalized = validate_region_task(value)
        self.assertIs(type(normalized['area_max_m2']), int)
        self.assertIs(type(normalized['area_min_m2']), int)
        self.assertEqual(validate_region_task(normalized), normalized)
        self.assertEqual(query_key(dict(mode='active_observation', region_task=normalized)),
                         query_key(validate_query(dict(mode='active_observation', region_task=value))))
    def test_invalid_conditions_and_unknown_fields(self):
        for key in CONDITIONS:
            for bad in (True, None, '0.5', float('nan'), float('inf')):
                with self.subTest(key=key, bad=bad), self.assertRaises(ValueError):
                    validate_region_task(dict(CONDITIONS, **{key: bad}))
        for change in (dict(area_min_m2=-1), dict(area_max_m2=0), dict(normal_z_min=1.01), dict(normal_z_min=-1.01)):
            with self.assertRaises(ValueError):
                validate_region_task(dict(CONDITIONS, **change))
    def test_query_combinations_schema_and_cache(self):
        query = dict(mode='active_observation', region_task=CONDITIONS)
        self.assertEqual(validate_query(query), query)
        _validate_arguments('human_eye_scene_observe', dict(query=query))
        with self.assertRaises(ValueError):
            validate_query(dict(query, objects=[dict(name='target')]))
        task = dict(mode='task', objects=[dict(name='A'), dict(name='B')], requested_facts=['surface_proximity'])
        combined = validate_query(dict(query, task_query=task))
        self.assertEqual(combined['task_query'], task)
        altered = validate_query(dict(query, region_task=dict(CONDITIONS, normal_z_min=0)))
        self.assertNotEqual(query_key(query), query_key(altered))


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.value = fixture(self.directory)
    def result(self, **options):
        return _tool_result(self.value, is_error=False, **options)
    def test_repeated_scene_views_native_blocks_and_brief(self):
        result = self.result()
        text = json.loads(result['content'][0]['text'])
        self.assertEqual(text['schema'], 'active-observation-region-task-brief-v1')
        self.assertNotIn('constructed_frames', text)
        self.assertNotIn('facts', text)
        self.assertEqual(len(result['content']), 4)
        self.assertEqual(text['image_delivery']['local_verified_image_count'], 8)
        self.assertEqual(text['image_delivery']['selected_image_count'], 3)
        columns = text['images']['columns']
        self.assertEqual([row[columns.index('view_name')] for row in text['images']['rows']], ['SCENE'] * 3)
        self.assertEqual([row[columns.index('native_content_block_index')] for row in text['images']['rows']], [1, 2, 3])
        self.assertEqual(len(set(row[columns.index('camera_identity')] for row in text['images']['rows'])), 3)
        for index, frame in enumerate(self.value['frames'], 1):
            self.assertEqual(base64.b64decode(result['content'][index]['data']), Path(frame['image_path']).read_bytes())
        for row, index in zip(text['region_task']['rows'][:2], (2, 3)):
            self.assertEqual(row['complete_witness']['native_content_block_index'], index)
    def test_full_preserves_all_construction_and_task_semantics(self):
        full = json.loads(self.result(response_detail='full')['content'][0]['text'])
        brief = json.loads(self.result()['content'][0]['text'])
        self.assertEqual(len(full['constructed_frames']), 8)
        self.assertEqual(full['scopes'], self.value['scopes'])
        self.assertEqual(full['facts']['region_task']['conditions'], brief['region_task']['conditions'])
        self.assertEqual(full['facts']['region_task']['rows'][2], brief['region_task']['rows'][2])
    def test_wrong_source_scope_witness_and_duplicate_reference_rejected(self):
        for kind in ('source', 'scope', 'witness', 'duplicate', 'pixels'):
            original = copy.deepcopy(self.value)
            if kind == 'source':
                self.value['facts']['region_task']['rows'][0]['source']['instance_id'] = 'other'
            if kind == 'scope':
                self.value['scopes'][1]['binding']['camera_identity'] = 'wrong'
            if kind == 'witness':
                self.value['facts']['region_task']['rows'][0]['complete_witness']['image_ref'] = self.value['frames'][0]['image_ref']
            if kind == 'duplicate':
                self.value['frames'][1] = self.value['frames'][0]
            if kind == 'pixels':
                self.value['scopes'][1]['facts']['observations'][0]['pixel_rows'][0]['visible_surface_pixels'] = 15
            with self.subTest(kind=kind), self.assertRaises((ValueError, KeyError)):
                self.result(response_detail='full')
            self.value = original
    def test_postprocess_failure_retains_original_construction(self):
        frozen = copy.deepcopy(self.value)
        with patch('human_eye_plugin.live_spatial_mcp.base64.b64encode', side_effect=ValueError('encoder failed')):
            with self.assertRaisesRegex(ValueError, 'encoder failed'):
                self.result()
        self.assertEqual(self.value, frozen)
        repaired = self.result()
        self.assertEqual(len(repaired['content']), 4)
        self.assertEqual(self.value['work']['raster_attempts'], 8)
    def test_current_core_mock_output_projects_brief_and_full(self):
        path = ROOT / 'verification/m4_cross_scale_discovery_001/core_tests/test_region_task_core.py'
        spec = importlib.util.spec_from_file_location('_cross_core_transport_fixture', path)
        core_fixture = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(core_fixture)
        with patch('human_eye_plugin.active_observation_images.rasterize_attention', side_effect=core_fixture.raster):
            actual = core_fixture.host.observe_capture(core_fixture.capture(), self.directory, region_task=CONDITIONS)
        actual['session_id'] = 'combined-synthetic'
        actual['binding']['runtime_source_sha256'] = 'runtime'
        for scope in actual['scopes']:
            scope['binding']['runtime_source_sha256'] = 'runtime'
        self.value = actual
        brief = json.loads(self.result()['content'][0]['text'])
        full = json.loads(self.result(response_detail='full')['content'][0]['text'])
        self.assertEqual(brief['schema'], 'active-observation-region-task-brief-v1')
        self.assertEqual(brief['region_task']['summary']['observed_region_count'], 2)
        self.assertEqual(brief['region_task']['summary']['unknown_region_count'], 1)
        self.assertEqual(len(full['constructed_frames']), 8)
    def test_region_task_and_whole_objects_measurement_share_source(self):
        from human_eye_plugin.live_service import LiveSpatialService
        path = ROOT / 'verification/m4_cross_scale_discovery_001/core_tests/test_region_task_core.py'
        spec = importlib.util.spec_from_file_location('_cross_joint_transport_fixture', path)
        core_fixture = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(core_fixture)
        packet = core_fixture.capture()
        class Host:
            def capture_scene(self):
                return copy.deepcopy(packet)
        config = self.directory / 'joint_config.json'
        config.write_text(json.dumps(dict(schema_version='1.0', enabled=True, project_root=str(self.directory),
            state_file='state.json', audit_file='audit.jsonl')), encoding='utf8')
        service = LiveSpatialService(config, host=Host())
        task = dict(mode='task', objects=[dict(name='Obj_02'), dict(name='Obj_06')], requested_facts=['surface_proximity'])
        with patch('human_eye_plugin.active_observation_images.rasterize_attention', side_effect=core_fixture.raster):
            actual = service.observe('joint', query=dict(mode='active_observation', region_task=CONDITIONS, task_query=task))
        self.value = actual
        brief = json.loads(self.result()['content'][0]['text'])
        full = json.loads(self.result(response_detail='full')['content'][0]['text'])
        self.assertEqual(brief['task_result'], full['task_result'])
        source = brief['task_result']['binding']['observation_source']
        self.assertEqual(source['measurement_scope'], 'whole_objects')
        self.assertEqual(source['parent_binding_sha256'], actual['binding']['binding_sha256'])
        self.assertEqual(actual['work']['task_query']['supplemental_capture_calls'], 0)


class RegionCacheTests(unittest.TestCase):
    setUp = _legacy.ActiveObservationServiceTests.setUp
    patches = _legacy.ActiveObservationServiceTests.patches
    source_binding = staticmethod(_legacy.ActiveObservationServiceTests.source_binding)
    compute = _legacy.ActiveObservationServiceTests.compute
    def compute_region(self, capture, output_directory, *, region_task, **options):
        result = self.compute(capture, output_directory, **options)
        result['scopes'] = [dict(binding=copy.deepcopy(result['binding']))]
        result['conditions'] = region_task
        return result
    def test_region_conditions_cache_keys_and_source_change(self):
        with self.patches(), patch('human_eye_plugin.active_observation_host.observe_capture', side_effect=self.compute_region):
            query = dict(mode='active_observation', region_task=CONDITIONS)
            first = self.service.observe('unit', query=query)
            second = self.service.observe('unit', query=query)
            self.assertEqual(self.compute_calls, 1)
            self.assertTrue(second['work']['result_cache_hit'])
            different = self.service.observe('unit', query=dict(query, region_task=dict(CONDITIONS, normal_z_min=0)))
            self.assertEqual(self.compute_calls, 2)
            self.assertFalse(different['work']['result_cache_hit'])
            self.host.capture['capture_state']['revision'] = 2
            changed = self.service.observe('unit', query=query)
            self.assertEqual(self.compute_calls, 3)
            self.assertFalse(changed['work']['result_cache_hit'])
            self.assertEqual(first['conditions'], CONDITIONS)


if __name__ == '__main__':
    unittest.main()
