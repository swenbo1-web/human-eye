"""Private scan resource dependencies and legacy delta compatibility."""
from copy import deepcopy
import json
import math
from pathlib import Path
import tempfile
import unittest

from human_eye_plugin.blender_mcp_host import BlenderMCPHost
from human_eye_plugin.blender_process import BlenderProcessHost
from human_eye_plugin.scene_residency import (
    SceneDeltaDecoder, SurfaceScanDependencies, encode_capture,
)


def fixture(*, offset=0., revision=1, resource_revision=1, epoch=1,
            document='doc-a', incarnation='instance-a', scale=1., local_change=0.,
            object_a='a', name_a='First', matrix_zero=0.):
    objects = []
    bindings = {}
    for oid, name, x, resource_name, changed in (
            (object_a, name_a, offset, 'resource-a', local_change),
            ('b', 'Second', 2., 'resource-b', 0.)):
        local = [[changed, 0., 0.], [0., 1., 0.], [0., 0., 1.]]
        matrix = [[1., matrix_zero, 0., x], [0., 1., 0., 0.],
                  [0., 0., 1., 0.], [0., 0., 0., 1.]]
        resource = dict(resource_id=resource_name,
            revision=resource_revision if resource_name == 'resource-a' else 1,
            vertices_local=local, faces=[[0, 1, 2]], edges=[])
        objects.append(dict(object_id=oid, name=name, vertices=[], faces=[], edges=[]))
        bindings[oid] = (resource, matrix, scale)
    identity = dict(schema_version='1.0', document_epoch=document,
        capture_scope='surface_scan_candidates', object_instances={object_a: incarnation, 'b': 'instance-b'})
    scene = dict(revision=str(revision), capture_scope='surface_scan_candidates',
        unit='m', coordinate_frame='world', source='blender', meshes=objects,
        host_identity=identity, capture_state=dict(instance_id='owned-host', epoch=epoch,
            revision=revision, selection_key='surface_scan'))
    payload = dict(protocol='single-read-surface-scan-v1', capture=scene,
        binding=dict(host_source_sha256='a'*64,
            host_identity=dict(identity, capture_scope='complete_scene_meshes')))
    return payload, bindings


def decode(decoder, *, baseline=None, **options):
    payload, bindings = fixture(**options)
    return decoder.apply(encode_capture(payload, baseline, bindings))


class ScanDependencyTests(unittest.TestCase):
    def token(self, decoder, payload):
        token = decoder.surface_scan_dependencies(payload)
        self.assertIs(type(token), SurfaceScanDependencies)
        self.assertTrue(token.matches_capture(payload))
        return token

    def test_private_typed_readonly_token_and_json_payload(self):
        decoder = SceneDeltaDecoder()
        payload = decode(decoder)
        token = self.token(decoder, payload)
        self.assertEqual(set(token.objects), {'a', 'b'})
        self.assertIsNone(decoder._surface_scan_binding)
        self.assertIsNone(decoder.surface_scan_dependencies(payload))
        self.assertNotIn('_scene_resource', json.dumps(payload))
        self.assertNotIn('SurfaceScanDependencies', json.dumps(payload))
        with self.assertRaises(TypeError):
            token.objects['a'] = ()
        with self.assertRaises(AttributeError):
            token.objects = {}
        with self.assertRaisesRegex(ValueError, 'dependency_authority'):
            SurfaceScanDependencies(None, payload, {})

    def test_wrong_capture_and_changed_metadata_cannot_claim_old_token(self):
        decoder = SceneDeltaDecoder()
        payload = decode(decoder)
        self.assertIsNone(decoder.surface_scan_dependencies(deepcopy(payload)))
        token = self.token(decoder, payload)
        self.assertFalse(token.matches_capture(deepcopy(payload)))
        for change in ('epoch', 'incarnation', 'document', 'host_source'):
            decoder = SceneDeltaDecoder()
            payload = decode(decoder)
            if change == 'epoch':
                payload['capture']['capture_state']['epoch'] += 1
            elif change == 'incarnation':
                payload['capture']['host_identity']['object_instances']['a'] = 'replacement'
            elif change == 'document':
                payload['binding']['host_identity']['document_epoch'] = 'new-document'
            else:
                payload['binding']['host_source_sha256'] = 'b'*64
            self.assertIsNone(decoder.surface_scan_dependencies(payload), change)

    def test_repeat_keeps_dependencies_and_pose_changes_only_one(self):
        decoder = SceneDeltaDecoder()
        first = self.token(decoder, decode(decoder)).objects
        baseline = decoder.baseline()
        repeated = self.token(decoder, decode(decoder, baseline=baseline, revision=2)).objects
        self.assertEqual(dict(first), dict(repeated))
        edited = self.token(decoder, decode(decoder, baseline=baseline, revision=3, offset=.25)).objects
        self.assertNotEqual(first['a'], edited['a'])
        self.assertEqual(first['b'], edited['b'])
        self.assertEqual(decoder.work_totals()['transformed_vertices'], 9)

    def test_geometry_changed_same_face_count_has_new_resource_dependency(self):
        decoder = SceneDeltaDecoder()
        first = self.token(decoder, decode(decoder)).objects
        edited = decode(decoder, baseline=decoder.baseline(), resource_revision=2,
                        local_change=.125, revision=2)
        second = self.token(decoder, edited).objects
        self.assertNotEqual(first['a'], second['a'])
        self.assertEqual(first['b'], second['b'])
        self.assertEqual(edited['capture']['meshes'][0]['vertices'][0][0], .125)

    def test_conflicting_same_resource_version_is_rejected_atomically(self):
        decoder = SceneDeltaDecoder()
        self.token(decoder, decode(decoder))
        before = decoder.baseline()
        serial = decoder._resource_serial
        for value in (.125, -0.):
            packet, bindings = fixture(local_change=value)
            wire = encode_capture(packet, None, bindings)
            with self.assertRaisesRegex(ValueError, 'immutable_resource_rebound'):
                decoder.apply(wire)
            self.assertEqual(decoder.baseline(), before)
            self.assertEqual(decoder._resource_serial, serial)
            self.assertIsNone(decoder._surface_scan_binding)

    def test_identical_version_retransmission_keeps_dependencies(self):
        decoder = SceneDeltaDecoder()
        first = self.token(decoder, decode(decoder)).objects
        second = self.token(decoder, decode(decoder, revision=2)).objects
        self.assertEqual(dict(first), dict(second))

    def test_trimmed_resource_return_does_not_reuse_old_admission(self):
        decoder = SceneDeltaDecoder()
        first = self.token(decoder, decode(decoder)).objects
        packet, bindings = fixture(revision=2)
        packet['capture']['meshes'].pop(0)
        packet['capture']['host_identity']['object_instances'].pop('a')
        wire = encode_capture(packet, decoder.baseline(), {'b': bindings['b']})
        decoder.apply(wire)
        self.assertNotIn('resource-a', decoder._resource_admissions)
        returned = self.token(decoder, decode(decoder, baseline=decoder.baseline(),
            local_change=.125, revision=3)).objects
        self.assertNotEqual(first['a'], returned['a'])
        self.assertEqual(first['b'], returned['b'])

    def test_generic_same_version_replacement_keeps_legacy_behavior(self):
        decoder = SceneDeltaDecoder()
        first = self.token(decoder, decode(decoder)).objects
        packet, bindings = fixture(local_change=.125, revision=2)
        packet.pop('protocol')
        generic = decoder.apply(encode_capture(packet, None, bindings))
        self.assertEqual(generic['capture']['meshes'][0]['vertices'][0][0], .125)
        self.assertIsNone(decoder.surface_scan_dependencies(generic))
        updated = self.token(decoder, decode(decoder, baseline=decoder.baseline(),
            local_change=.125, revision=3)).objects
        self.assertNotEqual(first['a'], updated['a'])

    def test_document_epoch_incarnation_unit_and_host_reset_dependencies(self):
        for change in (dict(epoch=2), dict(document='doc-b'),
                       dict(incarnation='replacement'), dict(scale=.01)):
            with self.subTest(change=change):
                decoder = SceneDeltaDecoder()
                first = self.token(decoder, decode(decoder)).objects
                next_payload = decode(decoder, baseline=decoder.baseline(), revision=2, **change)
                second = self.token(decoder, next_payload).objects
                self.assertNotEqual(first['a'], second['a'])
        first_decoder, second_decoder = SceneDeltaDecoder(), SceneDeltaDecoder()
        first = self.token(first_decoder, decode(first_decoder)).objects
        second = self.token(second_decoder, decode(second_decoder)).objects
        self.assertNotEqual(first['a'], second['a'])

    def test_rename_keeps_geometry_dependency_and_replacement_changes_it(self):
        decoder = SceneDeltaDecoder()
        first = self.token(decoder, decode(decoder)).objects
        renamed = self.token(decoder, decode(decoder, baseline=decoder.baseline(), revision=2,
            object_a='renamed-a', name_a='Renamed')).objects
        self.assertEqual(first['a'], renamed['renamed-a'])
        replaced = self.token(decoder, decode(decoder, baseline=decoder.baseline(), revision=3,
            incarnation='new-instance-a')).objects
        self.assertNotEqual(first['a'], replaced['a'])

    def test_signed_zero_pose_is_part_of_dependency(self):
        decoder = SceneDeltaDecoder()
        first = self.token(decoder, decode(decoder, matrix_zero=0.)).objects
        second = self.token(decoder, decode(decoder, baseline=decoder.baseline(),
            matrix_zero=-0., revision=2)).objects
        self.assertNotEqual(first['a'], second['a'])

    def test_plain_or_missing_binding_cannot_enable_fast_key(self):
        decoder = SceneDeltaDecoder()
        first = decode(decoder)
        plain = deepcopy(first)
        plain['_surface_scan_dependencies'] = {'a': 'invented'}
        result = decoder.apply(plain)
        self.assertIsNone(decoder.surface_scan_dependencies(result))
        self.assertIsNone(decoder.surface_scan_dependencies(first))
        packet, bindings = fixture()
        packet['capture'].pop('host_identity')
        result = decoder.apply(encode_capture(packet, None, bindings))
        self.assertIsNone(decoder.surface_scan_dependencies(result))

    def test_both_host_getters_delegate_and_plain_process_falls_back(self):
        for cls in (BlenderMCPHost, BlenderProcessHost):
            host = object.__new__(cls)
            host._scene_decoder = SceneDeltaDecoder()
            payload = decode(host._scene_decoder)
            self.assertIs(type(host.surface_scan_dependencies(payload)), SurfaceScanDependencies)
            self.assertIsNone(host.surface_scan_dependencies(payload))
        host = object.__new__(BlenderProcessHost)
        host._scene_decoder = None
        self.assertIsNone(host.surface_scan_dependencies({}))

    def test_process_delta_through_ordinary_service_reuses_only_unchanged_pair(self):
        from human_eye_plugin.live_service import LiveSpatialService
        from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer
        from verification.test_surface_scan_host import resident_fixture
        from verification.test_blender_process_residency import client
        native, objects = resident_fixture((0., .005, .009))
        host = client()
        commands = []
        def request(command, params, **options):
            commands.append(command)
            self.assertEqual(command, 'capture_surface_scan')
            capture = native.capture_surface_scan(params['threshold_m'], params['deadline_ns'],
                                                   params['max_response_bytes'])
            return native.capture_delta(capture, params['_scene_baseline'])
        host._request = request
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root/'config.json'
            config.write_text(json.dumps(dict(schema_version='1.0', enabled=True,
                project_root=str(root), state_file='state.json', audit_file='audit.jsonl',
                request_budget_s=10.)), encoding='utf8')
            service = LiveSpatialService(config, host=host)
            events = []
            service.record_event = lambda event, **fields: events.append((event, fields))
            server = LiveSpatialMCPServer(service)
            def observe(label):
                answer = server.handle_jsonrpc_message(dict(jsonrpc='2.0', id=label,
                    method='tools/call', params=dict(name='human_eye_scene_observe', arguments=dict(
                        query=dict(mode='surface_scan', threshold_m=.02)))))
                self.assertNotIn('error', answer)
                self.assertFalse(answer['result']['isError'], answer)
                return json.loads(answer['result']['content'][0]['text'])
            cold = observe('cold')
            repeated = observe('repeat')
            objects[0]._matrix_world[0][3] = .001
            edited = observe('edit')
            work = [fields['task_work'] for event, fields in events if event == 'observe']
            self.assertEqual([row['kernel_calls'] for row in work], [3, 0, 2])
            self.assertEqual([row['cache_hits'] for row in work], [0, 0, 1])
            self.assertEqual(commands, ['capture_surface_scan']*3)
            self.assertEqual(cold['matches'], repeated['matches'])
            self.assertNotEqual(cold['binding']['scene_revision'], edited['binding']['scene_revision'])
            positions = {obj.name: float(obj._matrix_world[0][3]) for obj in objects}
            self.assertEqual(edited['coverage']['total_pairs'], 3)
            self.assertEqual(edited['status'], 'complete')
            for match in edited['matches']:
                left, right = match['objects']
                self.assertAlmostEqual(match['point_a_world'][0], positions[left['name']])
                self.assertAlmostEqual(match['point_b_world'][0], positions[right['name']])
                expected = abs(positions[left['name']]-positions[right['name']])
                self.assertAlmostEqual(match['distance_m'], expected)
                self.assertAlmostEqual(math.dist(match['point_a_world'], match['point_b_world']), expected)


if __name__ == '__main__':
    unittest.main()
