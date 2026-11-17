"""Synthetic service and native delivery regressions with zero scene raster."""
import base64
import copy
from contextlib import ExitStack
import hashlib
import io
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image

from human_eye_plugin.active_observation_host import source_binding
from human_eye_plugin.live_service import LiveSpatialService, RequestBudgetError
from human_eye_plugin.live_spatial_mcp import (
    LIVE_MCP_TOOLS_SCHEMA, LiveSpatialMCPServer, _tool_result, _validate_arguments,
)
from human_eye_plugin.query_policy import validate_query


QUERY = dict(mode='source_region', region=dict(object=dict(name='A'), source_triangle_indices=[0, 1]),
             reference=dict(name='B'), requested_facts=['surface_proximity'])


def capture():
    return dict(unit='m', coordinate_frame='world', source='blender', revision='revision-1',
        host_identity=dict(schema_version='1.0', document_epoch='d' * 64,
            capture_scope='complete_scene_meshes', object_instances={name: 'instance-' + name for name in 'ABC'}),
        capture_state=dict(instance_id='host', epoch=1, revision=1, selection_key='all'),
        meshes=[dict(object_id=name, name=name, vertices=[[0, 0, 0], [1, 0, 0], [0, 1, 0]],
                     faces=[[0, 1, 2]]) for name in 'ABC'])


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def region_ref(current, indices=(0, 1)):
    generation = {key: current['capture_state'][key] for key in ('instance_id', 'epoch', 'revision')}
    value = dict(schema='human-eye-source-region-ref-v1', document_epoch='d' * 64,
        host_id='A', instance_id='instance-A', capture_generation=generation,
        ordered_geometry_sha256=digest(current['meshes']), source_triangle_indices=list(indices))
    return dict(value, region_id='source-region:' + digest(value))


def frame(directory):
    stream = io.BytesIO()
    Image.new('RGB', (512, 512), (40, 80, 120)).save(stream, format='PNG')
    path = directory / 'synthetic.png'
    path.write_bytes(stream.getvalue())
    return dict(image_path=str(path), image_sha256=hashlib.sha256(stream.getvalue()).hexdigest(),
        image_ref='synthetic-image', frame_identity='synthetic-frame', view_name='SCENE',
        pose=dict(view_matrix=[[1]]), arrays=dict(depth={'path': 'synthetic-array'}))


class QueryTests(unittest.TestCase):
    def test_normalization_and_schema(self):
        query = copy.deepcopy(QUERY)
        query['region']['source_triangle_indices'] = [3, 0, 2]
        normalized = validate_query(query)
        self.assertEqual(normalized['region']['source_triangle_indices'], [0, 2, 3])
        self.assertEqual(validate_query(normalized), normalized)
        ref_query = dict(mode='source_region', region_ref=region_ref(capture()), reference=dict(name='C'),
                         requested_facts=['surface_proximity'])
        self.assertEqual(validate_query(ref_query), ref_query)
        _validate_arguments('human_eye_scene_observe', dict(query=ref_query))
        schema = LIVE_MCP_TOOLS_SCHEMA[0]['inputSchema']['properties']['query']
        self.assertIn('source_region', schema['properties']['mode']['enum'])

    def test_invalid_queries(self):
        for changes in (dict(region_ref={}), dict(reference={}), dict(requested_facts=[]),
                        dict(requested_facts=['closed_solid_relation']), dict(camera='SCENE')):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_query(dict(QUERY, **changes))
        for indices in ([], [0, 0], [True], [-1], [1.0], '0'):
            query = copy.deepcopy(QUERY)
            query['region']['source_triangle_indices'] = indices
            with self.subTest(indices=indices), self.assertRaises(ValueError):
                validate_query(query)
        for extra in (dict(focal_id='A'), dict(reference_id='B'), dict(goal={}),
                      dict(task_instruction='measure'), dict(scene_delta={})):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                _validate_arguments('human_eye_scene_observe', dict(query=QUERY, **extra))


class ServiceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        config = self.directory / 'live.json'
        config.write_text(json.dumps(dict(schema_version='1.0', enabled=True,
            project_root=str(self.directory), state_file='state.json', audit_file='audit.jsonl')))
        self.current = capture()
        self.capture_calls = 0
        self.prepare_calls = 0
        self.measure_calls = 0
        self.render_calls = 0
        self.validations = 0
        self.events = []
        self.synthetic_frame = frame(self.directory)
        self.host = SimpleNamespace(capture_scene=self.capture_scene)
        self.service = LiveSpatialService(config, host=self.host)
        self.service.record_event = lambda event, **fields: self.events.append((event, fields))

    def capture_scene(self):
        self.capture_calls += 1
        return copy.deepcopy(self.current)

    def validate_ref(self, current, reference, check_budget, **options):
        self.validations += 1
        check_budget('synthetic_ref_validation')
        if reference != region_ref(current, reference['source_triangle_indices']):
            raise ValueError('source_region_ref_capture_generation_changed')

    def prepare(self, current, query, check_budget, **options):
        self.prepare_calls += 1
        indices = query.get('region', query.get('region_ref'))['source_triangle_indices']
        binding = source_binding(current)
        binding.update(camera_specification=dict(views=['synthetic-camera']), binding_sha256=digest(binding))
        return SimpleNamespace(region_ref=region_ref(current, indices), binding=binding, saved=None, preparation_stages={})

    def observe_core(self, prepared, directory, *, include_image, construction_callback, check_budget):
        hit = include_image and prepared.saved is not None
        if include_image and not hit:
            construction_callback('SCENE')
            self.render_calls += 1
            prepared.saved = dict(self.synthetic_frame, host_binding_sha256=prepared.binding['binding_sha256'])
        indices = prepared.region_ref['source_triangle_indices']
        return dict(result_kind='source_region', status='complete' if include_image else 'predicted',
            region_ref=copy.deepcopy(prepared.region_ref), binding=copy.deepcopy(prepared.binding),
            facts=dict(region=dict(source_triangle_indices=indices), visibility=dict(
                visible_source_triangle_indices=indices[:1] if include_image else [],
                unseen_source_triangle_indices=indices[1:] if include_image else indices,
                complete_witness=None)),
            frames=[copy.deepcopy(prepared.saved)] if include_image else [],
            work=dict(raster_attempts=int(include_image and not hit), frame_reuses=int(hit)), stages={},
            read_only=True, execution_authority=False)

    def measure(self, prepared, reference, cache, check_budget, diagnostics):
        self.measure_calls += 1
        diagnostics['surface_pair_count'] = 1
        return dict(schema='synthetic-measurement', status='complete', region_ref=copy.deepcopy(prepared.region_ref),
            reference=dict(object_id=reference['name'], name=reference['name']), measurement_scope=dict(kind='complete_selected_source_triangles',
                source_triangle_indices=prepared.region_ref['source_triangle_indices']),
            facts=dict(surface_proximity=dict(status='measured', value=dict(distance_m=1.25,
                nearest_witness=dict(a=[0, 0, 1.25], b=[0, 0, 0], direction_a_to_b=[0, 0, -1])))),
            binding=copy.deepcopy(prepared.binding), source_mapping=dict(source_triangle_indices=prepared.region_ref['source_triangle_indices']))

    def patches(self):
        stack = ExitStack()
        stack.enter_context(patch('human_eye_plugin.source_region.prepare_region', side_effect=self.prepare))
        stack.enter_context(patch('human_eye_plugin.source_region.validate_region_ref', side_effect=self.validate_ref))
        stack.enter_context(patch('human_eye_plugin.source_region.observe_region', side_effect=self.observe_core))
        stack.enter_context(patch('human_eye_plugin.source_region.measure_region', side_effect=self.measure))
        stack.enter_context(patch.object(self.service, '_locked', side_effect=AssertionError('write path used')))
        stack.enter_context(patch('human_eye_plugin.live_service.render_scene_canvas', side_effect=AssertionError('old raster used')))
        return stack

    def observe(self, query=None, **options):
        return self.service.observe('synthetic', query=QUERY if query is None else query, **options)

    def test_reference_switch_reuses_prepare_frame_and_distinct_measurements(self):
        with self.patches():
            first = self.observe()
            second_query = dict(mode='source_region', region_ref=first['region_ref'], reference=dict(name='C'),
                                requested_facts=['surface_proximity'])
            second = self.observe(second_query)
            repeated = self.observe(second_query)
            explicit = self.observe()
        self.assertEqual((self.capture_calls, self.prepare_calls, self.measure_calls, self.render_calls), (4, 1, 2, 1))
        self.assertEqual(self.validations, 2)
        self.assertEqual(first['frames'], second['frames'])
        self.assertEqual(second['work']['frame_reuses'], 1)
        self.assertFalse(second['work']['task_query']['result_cache_hit'])
        self.assertTrue(repeated['work']['task_query']['result_cache_hit'])
        self.assertTrue(explicit['work']['prepare_cache_hit'])
        self.assertFalse((self.directory / 'state.json').exists())

    def test_region_and_scene_generation_invalidate_resources(self):
        with self.patches():
            initial = self.observe()
            different = copy.deepcopy(QUERY)
            different['region']['source_triangle_indices'] = [1]
            self.observe(different)
            self.current['capture_state']['revision'] = 2
            self.current['meshes'][2]['vertices'][0][0] = 2
            with self.assertRaisesRegex(ValueError, 'capture_generation_changed'):
                self.observe(dict(mode='source_region', region_ref=initial['region_ref'], reference=dict(name='C'),
                                  requested_facts=['surface_proximity']))
            fresh = self.observe()
            self.assertNotEqual(fresh['region_ref'], initial['region_ref'])
            self.assertEqual((self.prepare_calls, self.render_calls), (3, 3))

    def test_text_then_image_reuses_preparation(self):
        with self.patches():
            text = self.observe(include_image=False)
            image = self.observe()
        self.assertEqual(text['frames'], [])
        self.assertEqual((self.prepare_calls, self.measure_calls, self.render_calls), (1, 1, 1))
        self.assertEqual(image['work']['prepare_calls'], 0)

    def test_reference_or_occluder_geometry_changes_invalidate_same_generation_frame(self):
        with self.patches():
            previous = self.observe()
            for index in (1, 2):
                self.current['meshes'][index]['vertices'][0][0] += .25
                current = self.observe()
                self.assertNotEqual(current['region_ref'], previous['region_ref'])
                self.assertFalse(current['work']['prepare_cache_hit'])
                with self.assertRaisesRegex(ValueError, 'capture_generation_changed'):
                    self.observe(dict(mode='source_region', region_ref=previous['region_ref'],
                        reference=dict(name='C'), requested_facts=['surface_proximity']))
                previous = current
        self.assertEqual((self.prepare_calls, self.render_calls), (3, 3))

    def test_cancellation_during_measurement_leaves_frame_reusable_and_result_uncached(self):
        with self.patches():
            with patch('human_eye_plugin.source_region.measure_region', side_effect=InterruptedError('cancelled')):
                with self.assertRaisesRegex(InterruptedError, 'cancelled'):
                    self.observe()
            recovered = self.observe()
        self.assertFalse(recovered['work']['task_query']['result_cache_hit'])
        self.assertEqual(recovered['work']['frame_reuses'], 1)
        self.assertEqual((self.prepare_calls, self.render_calls, self.measure_calls), (1, 1, 1))

    def test_deadline_prevents_raster_and_no_failed_measurement_is_cached(self):
        check = self.service._check_request_budget
        def expire(stage, **options):
            if stage == 'before_source_region_raster':
                raise RequestBudgetError('expired', stage)
            return check(stage, **options)
        with self.patches():
            with patch.object(self.service, '_check_request_budget', side_effect=expire):
                with self.assertRaises(RequestBudgetError):
                    self.observe()
            self.assertEqual((self.render_calls, self.measure_calls), (0, 0))
            recovered = self.observe()
        self.assertEqual((self.prepare_calls, self.render_calls, self.measure_calls), (1, 1, 1))
        self.assertEqual(recovered['work']['raster_attempts'], 1)

    def test_failed_raster_attempt_is_recorded_and_retry_reuses_preparation(self):
        def fail(prepared, directory, **options):
            options['construction_callback']('SCENE')
            raise RuntimeError('synthetic raster failure')
        with self.patches():
            with patch('human_eye_plugin.source_region.observe_region', side_effect=fail):
                with self.assertRaisesRegex(RuntimeError, 'synthetic raster failure'):
                    self.observe()
            recovered = self.observe()
        failed = [fields for event, fields in self.events if event == 'source_region_failed']
        self.assertEqual(failed[0]['task_work']['raster_attempts'], 1)
        self.assertEqual(recovered['work']['prepare_calls'], 0)

    def test_brief_full_native_bytes_mapping_and_unknown(self):
        with self.patches():
            value = self.observe()
        brief = _tool_result(value, is_error=False)
        full = _tool_result(value, is_error=False, response_detail='full')
        text = json.loads(brief['content'][0]['text'])
        detailed = json.loads(full['content'][0]['text'])
        self.assertEqual(text['schema'], 'source-region-brief-v1')
        self.assertEqual(text['region_ref'], detailed['region_ref'])
        self.assertEqual(text['images'][0]['image_block_index'], 1)
        self.assertEqual(text['region']['source_triangle_indices'], [0, 1])
        self.assertEqual(text['unknowns'][0]['source_triangle_indices'], [1])
        self.assertIsNone(text['visibility']['complete_witness'])
        self.assertEqual(text['task_result']['facts']['surface_proximity']['value']['distance_m'], 1.25)
        self.assertIn('camera_specification', detailed['binding'])
        self.assertIn('pose', detailed['frames'][0])
        self.assertIn('arrays', detailed['frames'][0])
        self.assertEqual(base64.b64decode(brief['content'][1]['data']), Path(value['frames'][0]['image_path']).read_bytes())
        self.assertEqual(brief['content'][1:], full['content'][1:])

    def test_transport_failure_retains_prepared_frame_and_mcp_entry_works(self):
        server = LiveSpatialMCPServer(self.service)
        with self.patches():
            value = self.observe()
            with patch('human_eye_plugin.live_spatial_mcp._public_native_png', side_effect=ValueError('encoding control')):
                with self.assertRaisesRegex(ValueError, 'encoding control'):
                    _tool_result(value, is_error=False)
            response = server._call_tool('human_eye_scene_observe', dict(query=QUERY))
        self.assertFalse(response['isError'])
        self.assertEqual(json.loads(response['content'][0]['text'])['schema'], 'source-region-brief-v1')
        self.assertEqual((self.prepare_calls, self.render_calls, self.measure_calls), (1, 1, 1))

    def test_bad_source_mapping_and_png_hash_refuse_both_details(self):
        with self.patches():
            value = self.observe()
        for detail in ('brief', 'full'):
            bad = copy.deepcopy(value)
            bad['facts']['region']['source_triangle_indices'] = [9]
            with self.subTest(detail=detail), self.assertRaises(ValueError):
                _tool_result(bad, is_error=False, response_detail=detail)
        bad = copy.deepcopy(value)
        bad['frames'][0]['image_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            _tool_result(bad, is_error=False)

    def test_accepted_cross_scale_core_output_projects_brief_and_full(self):
        root = Path(__file__).resolve().parents[3]
        path = root / 'verification/m4_cross_scale_discovery_001/core_tests/test_region_task_core.py'
        spec = importlib.util.spec_from_file_location('_source_region_cross_scale_fixture', path)
        fixture = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fixture)
        with patch('human_eye_plugin.active_observation_images.rasterize_attention', side_effect=fixture.raster):
            actual = fixture.host.observe_capture(fixture.capture(), self.directory, region_task=fixture.TASK)
        actual['session_id'] = 'cross-scale-synthetic'
        actual['binding']['runtime_source_sha256'] = 'runtime'
        for scope in actual['scopes']:
            scope['binding']['runtime_source_sha256'] = 'runtime'
        brief = json.loads(_tool_result(actual, is_error=False)['content'][0]['text'])
        full = json.loads(_tool_result(actual, is_error=False, response_detail='full')['content'][0]['text'])
        self.assertEqual(brief['region_task']['summary']['observed_region_count'], 2)
        self.assertEqual(brief['region_task']['summary']['unknown_region_count'], 1)
        self.assertEqual(len(full['constructed_frames']), 3)

    def test_real_region_core_and_service_normal_mcp_entry_with_mocked_pixels(self):
        root = Path(__file__).resolve().parents[3]
        path = root / 'verification/m4_m5_source_region_001/core_tests/test_source_region_core.py'
        spec = importlib.util.spec_from_file_location('_source_region_service_core_fixture', path)
        fixture = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fixture)
        self.current = fixture.captured()
        def raster(meshes, view, projection, size, **options):
            index = next(index for index, mesh in enumerate(meshes) if mesh.name == 'Obj_07')
            prepared = SimpleNamespace(meshes=meshes, object_index=index, source_triangle_indices=(0, 1, 2, 3))
            return fixture.buffers(prepared, size)
        server = LiveSpatialMCPServer(self.service)
        with patch('human_eye_plugin.active_observation_images.rasterize_attention', side_effect=raster) as rendered:
            first_content = server._call_tool('human_eye_scene_observe', dict(query=fixture.query()))
            first = json.loads(first_content['content'][0]['text'])
            second_query = dict(mode='source_region', region_ref=first['region_ref'], reference=dict(name='Ref_C'),
                                requested_facts=['surface_proximity'])
            second_content = server._call_tool('human_eye_scene_observe', dict(query=second_query, response_detail='full'))
            second = json.loads(second_content['content'][0]['text'])
        self.assertEqual(rendered.call_count, 1)
        self.assertEqual(len(rendered.call_args.args[0]), 11)
        self.assertEqual(first['task_result']['facts']['surface_proximity']['value']['distance_m'], 1.25)
        self.assertAlmostEqual(second['task_result']['facts']['surface_proximity']['value']['distance_m'], 137 ** .5 / 4)
        self.assertEqual(second['work']['prepare_calls'], 0)
        self.assertEqual(second['work']['raster_attempts'], 0)
        self.assertEqual(first_content['content'][1:], second_content['content'][1:])
        self.assertIn('complete_surface_visibility', [row['reason'] for row in first['unknowns']])
        self.assertEqual(second['source_mapping']['submesh_to_source_triangle_indices'], [0, 1, 2, 3])


if __name__ == '__main__':
    unittest.main()
