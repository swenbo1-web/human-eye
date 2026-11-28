"""Surface-scan host and bridge contracts using bounded Blender API doubles."""
import contextlib
import io
import json
import math
from pathlib import Path
import time
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from verification.test_m4_capture_001 import fixture, m
from verification.test_blender_mcp_host import _server, _reply
from verification.test_blender_process_residency import client, fixture as delta_fixture
from human_eye_plugin.blender_mcp_host import BlenderMCPHost, RPC_PREFIX
from human_eye_plugin.scene_residency import SceneDeltaDecoder, encode_capture

ROOT = Path(__file__).resolve().parents[1]


def scan(host, threshold=.01, **kwargs):
    return host.capture_surface_scan(threshold,
        kwargs.get('deadline_ns', time.perf_counter_ns()+10_000_000_000),
        kwargs.get('max_response_bytes', 1_000_000))


def resident_fixture(xs=(0., .005, 100.)):
    host, objects = fixture(xs)
    host.bpy.app.handlers = NS(depsgraph_update_post=[], undo_post=[], redo_post=[], load_post=[],
                               persistent=lambda callback: callback)
    return host, objects


class SurfaceScanHostTests(unittest.TestCase):
    def test_empty_singleton_empty_union_and_old_empty_refusal(self):
        for xs in ((), (0.,), (0., 100.)):
            host, objects = fixture(xs or (0.,))
            if not xs:
                host.scene.objects = []
            packet = scan(host)
            self.assertEqual(len(packet['coverage']), len(xs))
            self.assertEqual(len(packet['pairs']), len(xs)*(len(xs)-1)//2)
            self.assertEqual(packet['capture']['meshes'], [])
            self.assertEqual(packet['capture']['capture_scope'], 'surface_scan_candidates')
            self.assertEqual(sum(obj.mesh_calls for obj in objects), 0)
            if not xs:
                with self.assertRaisesRegex(m.BlenderHostError, '1..256'):
                    host.capture_scene()

    def test_bounds_prune_once_union_and_equality_retained(self):
        host, objects = fixture((0., .005, 100.))
        packet = scan(host)
        self.assertEqual(packet['work']['expanded_objects'], 2)
        self.assertEqual([pair['disposition'] for pair in packet['pairs']].count('retained'), 1)
        self.assertEqual(sum(obj.mesh_calls for obj in objects), 0)
        self.assertEqual(packet['work']['residency_delta']['resource_vertices_read'], 9)
        self.assertEqual(packet['work']['residency_delta']['world_vertices_transformed'], 6)
        host, _ = fixture((0., 2.))
        with patch.object(m, '_acquisition_lower', return_value=.01):
            self.assertEqual(scan(host)['pairs'][0]['disposition'], 'retained')

    def test_invalid_bounds_retained_and_bad_source_unknown(self):
        for invalid in (None, [], [(-1., -1., -1.)]*8):
            host, objects = fixture((0., 100.))
            objects[1].bound_box = invalid
            packet = scan(host)
            self.assertEqual(packet['pairs'][0]['disposition'], 'retained')
            self.assertEqual(packet['work']['expanded_objects'], 2)
        variants = ('modifier', 'degenerate', 'nonfinite', 'indices', 'singular', 'invalid_matrix')
        for variant in variants:
            with self.subTest(variant=variant):
                host, objects = fixture((0., 100.))
                obj = objects[1]
                if variant == 'modifier': obj.modifiers = [NS(type='BEVEL', name='bevel')]
                if variant == 'degenerate': obj.data.vertices[2].co = (0., 2., 0.)
                if variant == 'nonfinite': obj.data.vertices[1].co = (0., math.inf, 0.)
                if variant == 'indices': obj.data.loops[1].vertex_index = 100
                if variant == 'singular': obj._matrix_world[1][1] = 0.
                if variant == 'invalid_matrix': obj._matrix_world[1][1] = float('nan')
                packet = scan(host)
                self.assertEqual(packet['pairs'][0]['disposition'], 'unknown_source')
                self.assertEqual(packet['capture']['meshes'], [])
                self.assertTrue(next(row for row in packet['coverage'] if row['object_id']==host.object_id(obj))['reason'])

    def test_hidden_raw_static_and_instance_scope(self):
        host, objects = fixture((0., .005))
        objects[1].hide_viewport = True
        objects[1].is_evaluated = False
        packet = scan(host)
        self.assertEqual(packet['pairs'][0]['disposition'], 'retained')
        self.assertEqual(next(row for row in packet['coverage'] if row['source_mode']=='static_original_hidden')['source_status'], 'supported')
        host.view_layer.depsgraph.object_instances = [NS(is_instance=True)]
        self.assertEqual(scan(host)['scope_issues'], ['evaluated_instances_not_supported'])

    def test_warm_scope_changes_cannot_reuse_complete(self):
        for resident in (False, True):
            for variant in ('evaluated', 'nonmesh_type', 'nonmesh_flag', 'mesh_flag'):
                with self.subTest(resident=resident, variant=variant):
                    host, objects = resident_fixture() if resident else fixture((0., .005, 100.))
                    empty = NS(name='Instancer', name_full='Instancer', type='EMPTY', instance_type='NONE',
                        is_instancer=False, matrix_world=[[float(r==c) for c in range(4)] for r in range(4)],
                        data=None, session_uid=1001)
                    host.scene.objects.append(empty)
                    first = scan(host)
                    if variant == 'evaluated': host.view_layer.depsgraph.object_instances = [NS(is_instance=True)]
                    if variant == 'nonmesh_type': empty.instance_type = 'COLLECTION'
                    if variant == 'nonmesh_flag': empty.is_instancer = True
                    if variant == 'mesh_flag': objects[0].is_instancer = True
                    second = scan(host)
                    self.assertFalse(second['work']['cache_hit'])
                    self.assertNotEqual(first['capture']['revision'], second['capture']['revision'])
                    if variant == 'mesh_flag':
                        self.assertTrue(any(pair['disposition']=='unknown_source' for pair in second['pairs']))
                    else:
                        self.assertTrue(second['scope_issues'])

    def test_exact_local_degeneracy_and_world_rounding_guard(self):
        for scale in (2.**-530, 2.**510):
            host, objects = fixture((0., 100.))
            objects[1].data.vertices = [NS(co=(0., 0., 0.)), NS(co=(0., scale, 0.)), NS(co=(0., 0., scale))]
            packet = scan(host)
            row = next(row for row in packet['coverage'] if row['object_id']==host.object_id(objects[1]))
            self.assertNotEqual(row['reason'], 'degenerate_local_triangle_source')
        host, objects = fixture((0., 100.))
        objects[1]._matrix_world[1][3] = 2.**60
        objects[1]._matrix_world[2][3] = 2.**60
        row = next(row for row in scan(host)['coverage'] if row['object_id']==host.object_id(objects[1]))
        self.assertEqual(row['reason'], 'world_precision_unresolved')
        objects[1]._matrix_world[1][1] = float.fromhex('0x1.fffffffffffffp+1023')
        row = next(row for row in scan(host)['coverage'] if row['object_id']==host.object_id(objects[1]))
        self.assertEqual(row['reason'], 'world_precision_unresolved')

    def test_resident_repeat_pose_name_geometry_epoch_delete_and_delta(self):
        host, objects = resident_fixture()
        first = scan(host)
        wire = host.capture_delta(first)
        decoder = SceneDeltaDecoder()
        self.assertEqual(decoder.apply(wire), first)
        warm = scan(host)
        self.assertTrue(warm['work']['cache_hit'])
        self.assertEqual(warm['work']['residency_delta']['resource_vertices_read'], 0)
        self.assertEqual(host.capture_delta(warm, decoder.baseline())['resources'], [])
        objects[1]._matrix_world[0][3] = .006
        moved = scan(host)
        self.assertEqual(moved['work']['residency_delta']['source_qualification_vertices'], 0)
        self.assertEqual(moved['work']['residency_delta']['world_vertices_transformed'], 3)
        objects[1].name = objects[1].name_full = 'Renamed'
        renamed = scan(host)
        self.assertEqual(renamed['work']['residency_delta']['world_vertices_transformed'], 0)
        self.assertEqual(renamed['work']['residency_delta']['source_qualification_vertices'], 0)
        objects[1].data.vertices[1].co = (0., 1.1, 0.)
        update = NS(id=objects[1].data, is_updated_geometry=True)
        for callback in host.bpy.app.handlers.depsgraph_update_post:
            callback(host.scene, NS(updates=[update]))
        edited = scan(host)
        self.assertEqual(edited['work']['residency_delta']['source_qualification_vertices'], 3)
        removed = objects[1]
        host.scene.objects.remove(removed)
        scan(host)
        self.assertNotIn(host._residency_module.identity(removed), host._residency.source_checks)
        epoch = host._residency.epoch
        for callback in host.bpy.app.handlers.undo_post: callback()
        self.assertGreater(host._residency.epoch, epoch)
        self.assertEqual(host._residency.source_checks, {})

    def test_previously_excluded_source_reads_once_when_entering_union(self):
        host, objects = resident_fixture()
        scan(host)
        key = host._residency_module.identity(objects[2])
        self.assertIn(key, host._residency.source_checks)
        self.assertNotIn(key, host._residency.resources)
        objects[2]._matrix_world[0][3] = .008
        packet = scan(host)
        delta = packet['work']['residency_delta']
        self.assertEqual(packet['work']['expanded_objects'], 3)
        self.assertEqual(delta['source_qualification_vertices'], 0)
        self.assertEqual(delta['resource_vertices_read'], 3)
        self.assertEqual(delta['world_vertices_transformed'], 3)
        self.assertEqual(sum(obj.mesh_calls for obj in objects), 0)

    def test_deadline_bytes_and_same_window_change(self):
        host, _ = fixture((0., .005))
        with self.assertRaisesRegex(m.BlenderHostError, 'deadline_exceeded'): scan(host, deadline_ns=1)
        with self.assertRaisesRegex(m.BlenderHostError, 'document_budget_exceeded'): scan(host, max_response_bytes=1)
        host, objects = fixture((0., .005))
        original = host._scan_local_geometry
        def changed(data, checkpoint, oid):
            result = original(data, checkpoint, oid)
            objects[1].session_uid += 1
            return result
        host._scan_local_geometry = changed
        with self.assertRaisesRegex(m.BlenderHostError, 'source_changed'): scan(host)
        self.assertEqual(sum(obj.assignments for obj in objects), 0)

    def test_256_directory_and_257_refusal(self):
        host, _ = fixture(tuple(100.*i for i in range(256)))
        packet = scan(host, max_response_bytes=10_000_000)
        self.assertEqual(len(packet['pairs']), 32640)
        self.assertEqual(packet['capture']['meshes'], [])
        self.assertEqual(packet['work']['residency_delta']['scan_bound_tests'], 32640)
        host, _ = fixture(tuple(100.*i for i in range(257)))
        with self.assertRaisesRegex(m.BlenderHostError, 'scene_object_budget'):
            scan(host)

    def test_reducer_consumes_bound_exclusion_and_union(self):
        from human_eye_plugin.surface_scan import surface_scan_result
        from human_eye_plugin.scene_cache import SpatialSceneCache
        host, _ = fixture((0., .005, 100.))
        result = surface_scan_result(scan(host), SpatialSceneCache(), lambda *args:None)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['coverage']['total_pairs'], 3)
        self.assertEqual(result['coverage']['bound_excluded'], 2)
        self.assertEqual(result['coverage']['measured_match'], 1)


class SurfaceScanTransportTests(unittest.TestCase):
    def test_mcp_fixed_code_and_typed_transport(self):
        host, _ = fixture((0., .005))
        connector = BlenderMCPHost(ROOT)
        params = dict(threshold_m=.01, deadline_ns=time.perf_counter_ns()+10_000_000_000, max_response_bytes=1_000_000)
        code = connector._code('capture_surface_scan', params, 'scan-request')
        with contextlib.redirect_stdout(io.StringIO()) as output:
            exec(compile(code, '<typed-scan>', 'exec'), {'bpy':host.bpy})
        response = json.loads(output.getvalue()[len(RPC_PREFIX):])
        self.assertNotIn('error', response, response)
        with _server(lambda request: _reply(request, response['result'])) as (port, requests):
            transport = BlenderMCPHost(ROOT, port=port)
            with transport.observation_transaction():
                self.assertEqual(transport.capture_surface_scan(**params)['protocol'], 'single-read-surface-scan-v1')
        self.assertEqual(requests[0][1]['command'], 'capture_surface_scan')

    def test_owned_delta_deadline_and_inputs(self):
        host = client()
        scene, bindings = delta_fixture()
        calls = []
        def request(command, params, **kwargs):
            calls.append((command, params, kwargs))
            return encode_capture(dict(capture=scene), params['_scene_baseline'], bindings)
        host._request = request
        self.assertEqual(host.capture_surface_scan(.01, time.perf_counter_ns()+1_000_000_000, 100000)['capture'], scene)
        self.assertEqual(calls[-1][0], 'capture_surface_scan')
        self.assertIsNone(calls[-1][1]['_scene_baseline'])
        for value in (True, -1., float('inf'), float('nan'), 2**4096):
            with self.assertRaisesRegex(ValueError, 'surface_scan_threshold'):
                host.capture_surface_scan(value, time.perf_counter_ns()+1_000_000_000, 100000)


if __name__ == '__main__':
    unittest.main()
