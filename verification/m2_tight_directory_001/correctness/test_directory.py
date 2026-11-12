"""Directed directory facts, freshness and existing-interface contracts."""

import copy
from contextlib import ExitStack
import hashlib
from fractions import Fraction
import json
from pathlib import Path
import tempfile
import sys
import time
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from human_eye_plugin import blender_host, blender_mcp_host, live_service, live_spatial_mcp as mcp
from human_eye_plugin.query_policy import validate_query
from human_eye_plugin.runtime_identity import runtime_identity
from verification.arch_resident_001 import test_residency_contract as resident
from verification.m2_tight_directory_001.correctness.oracle import assert_packet, raw_rna_objects, tight_bounds, wrong_eight_corner_bounds


ROOT = Path(__file__).resolve().parents[3]
ENGINE = Path(blender_host.__file__).resolve().parents[1]
HOST_SHA = hashlib.sha256(Path(blender_host.__file__).read_bytes()).hexdigest()
EVIDENCE = {}


class DirectoryAdapter:
    timeout_s = 10.

    def __init__(self, backend):
        self.backend = backend
        self.directories = self.full = self.selected = self.writes = 0
        self._readonly_host_source_sha256 = HOST_SHA
        self._readonly_scene_residency_sha256 = hashlib.sha256((ENGINE / 'human_eye_plugin/scene_residency.py').read_bytes()).hexdigest()

    def capture_directory(self, deadline_ns, max_response_bytes):
        self.directories += 1
        return self.backend.capture_directory(deadline_ns, max_response_bytes)

    def capture_scene(self):
        self.full += 1
        return self.backend.capture_scene()

    def capture_task_scene(self, selectors):
        self.selected += 1
        return self.backend.capture_task_scene(selectors)

    def apply_transform(self, *args, **kwargs):
        self.writes += 1
        raise AssertionError("directory must not write")


class DirectoryTests(unittest.TestCase):
    def host(self, hooks=True):
        resident.Host = blender_host.BlenderSceneHost
        resident.fixture.BlenderSceneHost = blender_host.BlenderSceneHost
        resident.fixture.BlenderHostError = blender_host.BlenderHostError
        resident.fixture._module = blender_host
        host, focal, reference, graph = resident.make_host(hooks=hooks)
        self.addCleanup(host.close_residency)
        host.bpy.app.driver_namespace['_human_eye_document_epoch_v1'] = 'd' * 32
        host.bpy.app.driver_namespace['_human_eye_residency_document_v1'] = 'e' * 32
        focal._matrix_world = resident.fixture.FakeMatrix([[.8, -.6, 0., 2.], [.6, .8, 0., 3.], [0., 0., 1., 4.], [0., 0., 0., 1.]])
        return host, focal, reference, graph

    def directory(self, host, label):
        truth = raw_rna_objects(host)
        value = host.capture_directory(time.perf_counter_ns() + 10_000_000_000, 2_000_000)
        assert_packet(self, value, truth, host_source_sha256=HOST_SHA)
        self.assertEqual(value['binding']['frame'], host.bpy.context.scene.frame_current)
        self.assertEqual(value['binding']['subframe'], host.bpy.context.scene.frame_subframe)
        EVIDENCE[label] = {"packet": copy.deepcopy(value), "raw_oracle_input": truth}
        return value

    def changed(self, before, after):
        keys = ('instance_id', 'epoch', 'revision')
        self.assertNotEqual(tuple(before['capture_state'][key] for key in keys), tuple(after['capture_state'][key] for key in keys))

    def service(self, backend):
        temporary = tempfile.TemporaryDirectory(prefix='directory-')
        self.addCleanup(temporary.cleanup)
        config = Path(temporary.name) / 'config.json'
        config.write_text(json.dumps({'schema_version': '1.0', 'project_root': str(ENGINE), 'enabled': True,
            'quad_size': 64, 'state_file': 'actions.json', 'audit_file': 'audit.jsonl'}), encoding='utf8')
        host = DirectoryAdapter(backend)
        service = live_service.LiveSpatialService(config, host=host)
        return host, service, mcp.LiveSpatialMCPServer(service, default_session_id='directory-default')

    def test_rotated_nonbox_is_tight_and_does_not_use_transformed_local_bbox(self):
        host, focal, _, _ = self.host()
        value = self.directory(host, 'rotated_nonbox_cold')
        source = next(row for row in raw_rna_objects(host) if row['name'] == focal.name)
        tight = tight_bounds(source['vertices_local'], source['matrix_world'], source['unit_scale_m'])
        wrong = wrong_eight_corner_bounds(source['vertices_local'], source['matrix_world'], source['unit_scale_m'])
        self.assertGreater(max(abs(a - b) for a, b in zip(tight['center'], wrong['center'])), .1)
        original_work = host.residency_work()
        self.assertEqual(original_work['triangulations'], 0)
        self.assertFalse(host._residency.resources)
        self.assertFalse(host._residency.wire)
        for obj in host.scene.objects:
            obj.data.calc_loop_triangles = lambda: (_ for _ in ()).throw(AssertionError('directory triangulated'))
        again = host.capture_directory(time.perf_counter_ns() + 10_000_000_000, 2_000_000)
        self.assertIs(value['cache_hit'], False)
        self.assertIs(again['cache_hit'], True)
        # cache_hit reports this acquisition and is excluded from the host digest.
        cold_core = {key: item for key, item in value.items() if key != 'cache_hit'}
        self.assertEqual(cold_core, {key: item for key, item in again.items() if key != 'cache_hit'})
        self.assertEqual(host.residency_work()['triangulations'], original_work['triangulations'])
        again['objects'][0]['bbox_min'][0] = -12345.
        detached = host.capture_directory(time.perf_counter_ns() + 10_000_000_000, 2_000_000)
        self.assertIs(detached['cache_hit'], True)
        self.assertEqual(cold_core, {key: item for key, item in detached.items() if key != 'cache_hit'})

    def test_concave_and_isolated_vertices_all_contribute_to_bounds(self):
        host, focal, reference, graph = self.host()
        polygon = [(-1., -1.), (1., -1.), (1., -.25), (-.25, -.25), (-.25, 1.), (-1., 1.)]
        focal.data.vertices = [NS(co=(x, y, z)) for z in (-.5, .5) for x, y in polygon]
        caps = [(0, 1, 2), (0, 2, 3), (0, 3, 5), (3, 4, 5)]
        faces = [(c, b, a) for a, b, c in caps] + [(a+6, b+6, c+6) for a, b, c in caps]
        for i in range(6):
            j = (i + 1) % 6
            faces.extend(((i, j, j+6), (i, j+6, i+6)))
        focal.data.loop_triangles = [NS(vertices=face) for face in faces]
        focal.data.polygons = [NS(vertices=face, loop_start=i*3, loop_total=3) for i, face in enumerate(faces)]
        focal.data.loops = [NS(vertex_index=index) for face in faces for index in face]
        reference.data.vertices.append(NS(co=(7., -3., 5.)))
        resident.notify_geometry(host, graph, focal)
        resident.notify_geometry(host, graph, reference)
        result = self.directory(host, 'concave_and_isolated')
        row = next(row for row in result['objects'] if row['name'] == reference.name)
        self.assertEqual(row['bbox_max'], [12., 1., 5.])
        self.assertNotIn('resources', result)
        self.assertEqual(host.residency_work()['triangulations'], 0)

    def test_pose_geometry_units_and_frame_refresh_current_directory(self):
        host, focal, _, graph = self.host()
        previous = self.directory(host, 'fresh_initial')
        for label, update in (
            ('pose', lambda: focal._matrix_world[0].__setitem__(3, 7.)),
            ('geometry', lambda: focal.data.vertices[0].__setattr__('co', (2., -1., .25))),
            ('units', lambda: host.scene.unit_settings.__setattr__('scale_length', .125)),
            ('frame', lambda: host.scene.__setattr__('frame_current', 3)),
            ('subframe', lambda: host.scene.__setattr__('frame_subframe', .5)),
        ):
            with self.subTest(change=label):
                update()
                if label == 'geometry':
                    resident.notify_geometry(host, graph, focal, via_data=True)
                current = self.directory(host, 'fresh_' + label)
                self.changed(previous, current)
                previous = current

    def test_rename_delete_replace_and_lifecycle_hooks_invalidate_identity(self):
        host, focal, _, _ = self.host()
        previous = self.directory(host, 'identity_initial')
        focal.name = focal.name_full = 'Renamed'
        renamed = self.directory(host, 'identity_renamed')
        self.changed(previous, renamed)
        host.scene.objects.remove(focal)
        deleted = self.directory(host, 'identity_deleted')
        self.changed(renamed, deleted)
        replacement = resident.prepare_object(resident.fixture.FakeObject('Renamed', (2, 3, 4)), 777)
        host.scene.objects.append(replacement)
        replaced = self.directory(host, 'identity_same_name_replacement')
        self.changed(deleted, replaced)
        old_instances = renamed['binding']['host_identity']['object_instances']
        new_instances = replaced['binding']['host_identity']['object_instances']
        self.assertNotEqual(old_instances, new_instances)
        previous = replaced
        for handler in ('undo_post', 'redo_post', 'load_post'):
            with self.subTest(handler=handler):
                for callback in tuple(getattr(host.bpy.app.handlers, handler)):
                    callback(None)
                current = self.directory(host, 'identity_' + handler)
                self.changed(previous, current)
                self.assertNotEqual(previous['capture_state']['epoch'], current['capture_state']['epoch'])
                previous = current

    def test_no_notification_host_reads_fresh_and_reports_no_capture_state(self):
        host, focal, _, _ = self.host(hooks=False)
        first = self.directory(host, 'no_hooks_before')
        self.assertIsNone(first['capture_state'])
        focal.data.vertices[0].co = (9., -2., .25)
        second = self.directory(host, 'no_hooks_after')
        self.assertIsNone(second['capture_state'])
        self.assertNotEqual(first['objects'], second['objects'])

    def test_midpoint_extremes_use_independent_fraction_rounding_and_host_transform(self):
        smallest = float.fromhex('0x0.0000000000001p-1022')
        largest = sys.float_info.max
        cases = ((smallest, smallest, smallest, (1., 1.)),
                 (smallest, 2*smallest, smallest, (1., 2.)),
                 (largest, largest, largest, (1., 1.)),
                 (-largest, largest, largest, (-1., 1.)))
        for index, (lower, upper, scale, local) in enumerate(cases):
            with self.subTest(endpoints=(lower, upper)):
                exact_center = float((Fraction(lower) + Fraction(upper)) / 2)
                self.assertEqual(blender_host._bounds_midpoint(lower, upper), exact_center)
                host, focal, reference, _ = self.host()
                host.scene.unit_settings.scale_length = scale
                for obj in (focal, reference):
                    obj._matrix_world = resident.fixture.matrix()
                    obj.data.vertices = [NS(co=(value, 0., 0.)) for value in (local[0], local[1], local[0], local[1])]
                packet = host.capture_directory(time.perf_counter_ns() + 10_000_000_000, 2_000_000)
                for row in packet['objects']:
                    self.assertEqual(row['bbox_min'][0], lower)
                    self.assertEqual(row['bbox_max'][0], upper)
                    self.assertEqual(row['center'][0], exact_center)
                EVIDENCE['midpoint_' + str(index)] = {'packet': packet,
                    'Fraction_midpoint_float': exact_center, 'raw_endpoints': [lower, upper]}

    def test_current_scene_switch_has_current_objects_and_generation(self):
        host, _, _, _ = self.host()
        first = self.directory(host, 'scene_before')
        other = resident.prepare_object(resident.fixture.FakeObject('Other', (17, -2, 5)), 801)
        graph = NS(object_instances=[], updates=[])
        layer = NS(update=lambda: None, depsgraph=graph, objects=NS(active=other))
        scene = NS(objects=[other], unit_settings=NS(scale_length=.25), frame_current=2,
                   frame_subframe=0., view_layers=[layer], session_uid=91, name='OtherScene')
        graph.scene_eval = NS(original=scene)
        host.bpy.context.scene, host.bpy.context.view_layer = scene, layer
        host.bpy.context.evaluated_depsgraph_get = lambda: graph
        second = self.directory(host, 'scene_after')
        self.changed(first, second)
        self.assertEqual([row['name'] for row in second['objects']], ['Other'])

    def test_failed_inputs_do_not_return_complete_and_recover_after_restore(self):
        host, focal, _, graph = self.host()
        self.directory(host, 'failure_good_start')
        with self.assertRaises((ValueError, blender_host.BlenderHostError)):
            host.capture_directory(time.perf_counter_ns() - 1, 2_000_000)
        with self.assertRaises((ValueError, blender_host.BlenderHostError)):
            host.capture_directory(time.perf_counter_ns() + 10_000_000_000, 1)
        original = focal.data.vertices
        for label, broken in (('empty', []), ('nonfinite', [NS(co=(float('nan'), 0., 0.))])):
            with self.subTest(broken=label):
                focal.data.vertices = broken
                resident.notify_geometry(host, graph, focal)
                with self.assertRaises((ValueError, blender_host.BlenderHostError)):
                    host.capture_directory(time.perf_counter_ns() + 10_000_000_000, 2_000_000)
                focal.data.vertices = original
                resident.notify_geometry(host, graph, focal)
                self.directory(host, 'recovered_' + label)

    def test_directory_service_is_read_only_and_followup_task_rebinds(self):
        backend, _, _, _ = self.host()
        host, service, server = self.service(backend)
        opaque = b'previous action journal stays opaque to directory\r\n'
        service.state_path.write_bytes(opaque)
        with (patch.object(service, '_locked', side_effect=AssertionError('directory opened action state')),
                patch.object(service._read_context, 'activate', side_effect=AssertionError('directory activated a full capture'))):
            wire = server._call_tool('human_eye_scene_observe', {'query': {'mode': 'directory'}, 'include_image': False})
        self.assertFalse(wire['isError'])
        packet = json.loads(wire['content'][0]['text'])
        assert_packet(self, packet, raw_rna_objects(backend), host_source_sha256=HOST_SHA)
        self.assertEqual((host.directories, host.full, host.selected, host.writes), (1, 0, 0, 0))
        self.assertEqual(service.state_path.read_bytes(), opaque)
        self.assertIsNone(service._read_context._capture)
        selected = server._call_tool('human_eye_scene_observe', {'query': {'mode': 'task', 'objects': [{'id': packet['objects'][0]['object_id']}], 'requested_facts': ['aabb']}, 'include_image': False})
        self.assertFalse(selected['isError'])
        self.assertEqual((host.full, host.selected, host.writes), (0, 1, 0))
        self.assertEqual(service.state_path.read_bytes(), opaque)
        EVIDENCE['service_then_selected'] = {'directory': packet, 'selected': selected}

    def test_schema_and_runtime_directory_scope_reject_before_host(self):
        host, service, server = self.service(self.host()[0])
        valid = {'query': {'mode': 'directory'}, 'include_image': False}
        mcp._validate_arguments('human_eye_scene_observe', valid)
        self.assertEqual(validate_query({'mode': 'directory'}), {'mode': 'directory'})
        invalid = [dict(valid, include_image=True), {'query': {'mode': 'directory'}},
            dict(valid, task_instruction='find the nearest part'), dict(valid, focal_id='a'),
            dict(valid, reference_id='b'), dict(valid, goal={}), dict(valid, scene_delta={}),
            dict(valid, query={'mode': 'directory', 'objects': [{'id': 'a'}]}),
            dict(valid, query={'mode': 'directory', 'geometry': {'objects': [{'id': 'a'}]}})]
        scope_error = 'directory requires include_image=false and no instruction, pair, goal or scene_delta'
        for index, arguments in enumerate(invalid):
            with self.subTest(arguments=arguments):
                before = copy.deepcopy(arguments)
                expected = scope_error if index < 7 else 'directory query accepts only mode'
                with self.assertRaisesRegex(ValueError, '^' + expected + '$'):
                    mcp._validate_arguments('human_eye_scene_observe', arguments)
                response = server.handle_jsonrpc_message({'jsonrpc': '2.0', 'id': index,
                    'method': 'tools/call', 'params': {'name': 'human_eye_scene_observe', 'arguments': arguments}})
                self.assertEqual(response['id'], index)
                wire = response['result']
                self.assertTrue(wire['isError'])
                self.assertEqual(json.loads(wire['content'][0]['text'])['error'], expected)
                self.assertEqual(arguments, before)
                self.assertEqual(host.directories, 0)

    def test_bad_directory_source_binding_fails_then_recovers_without_state_write(self):
        backend, _, _, _ = self.host()
        host, service, server = self.service(backend)
        packet = backend.capture_directory(time.perf_counter_ns() + 10_000_000_000, 2_000_000)
        bad = copy.deepcopy(packet)
        bad['binding']['host_source_sha256'] = '0' * 64
        arguments = {'query': {'mode': 'directory'}, 'include_image': False}
        with patch.object(host, 'capture_directory', return_value=bad):
            response = server.handle_jsonrpc_message({'jsonrpc': '2.0', 'id': 'bad-directory-source',
                'method': 'tools/call', 'params': {'name': 'human_eye_scene_observe', 'arguments': arguments}})
        self.assertEqual(response['id'], 'bad-directory-source')
        rejected = response['result']
        self.assertTrue(rejected['isError'])
        self.assertEqual(json.loads(rejected['content'][0]['text'])['error'], 'directory_source_binding')
        good = server._call_tool('human_eye_scene_observe', arguments)
        self.assertFalse(good['isError'])
        assert_packet(self, json.loads(good['content'][0]['text']), raw_rna_objects(backend), host_source_sha256=HOST_SHA)
        self.assertFalse(service.state_path.exists())
        self.assertEqual(host.writes, 0)
        EVIDENCE['bad_source_then_recovery'] = {'rejected': rejected, 'accepted': good}

    def test_directory_connector_preserves_existing_full_decoder_baseline(self):
        host, _, _, _ = self.host()
        full = host.capture_scene()
        before_resources = {key: row['revision'] for key, row in host._residency.resources.items()}
        before_wire = set(host._residency.wire)
        packet = self.directory(host, 'connector_directory')
        self.assertEqual(before_resources, {key: row['revision'] for key, row in host._residency.resources.items()})
        self.assertEqual(before_wire, set(host._residency.wire))
        connector = blender_mcp_host.BlenderMCPHost(ENGINE)
        self.addCleanup(connector.close)
        first = host.capture_delta(full)
        self.assertEqual(connector._scene_decoder.apply(first), full)
        before = copy.deepcopy(connector._scene_decoder.baseline())
        connector._resident_ready = True
        request_id = 'a' * 32
        def reply(payload):
            envelope = {'protocol_version': '1.0', 'id': request_id, 'result': copy.deepcopy(packet)}
            return {'status': 'success', 'result': {'executed': True,
                'result': blender_mcp_host.RPC_PREFIX + json.dumps(envelope, separators=(',', ':')) + '\n'}}
        with (patch.object(blender_mcp_host.uuid, 'uuid4', return_value=NS(hex=request_id)), patch.object(connector, '_exchange', side_effect=reply),
                patch.object(connector._scene_decoder, 'apply', side_effect=AssertionError('directory used full decoder'))):
            result = connector.capture_directory(time.perf_counter_ns() + 10_000_000_000, 2_000_000)
        self.assertEqual(result, packet)
        self.assertEqual(connector._scene_decoder.baseline(), before)
        self.assertEqual(connector._scene_decoder.apply(host.capture_delta(full, before)), full)
        generated = connector._observation_code('capture_directory', {'deadline_ns': time.perf_counter_ns()+1_000_000_000, 'max_response_bytes': 2_000_000}, request_id)
        self.assertNotIn('_host.capture_delta(', generated)
        EVIDENCE['connector_decoder_baseline'] = {'before': before, 'after': connector._scene_decoder.baseline()}
