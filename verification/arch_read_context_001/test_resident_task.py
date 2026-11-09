"""Resident task reads through public service.observe, with current host tokens.

No Blender, network, API or subprocess. Historical action bytes stay opaque to
the read path; token-less hosts continue to supply a fresh complete capture.
"""
from __future__ import annotations

import copy
from contextlib import ExitStack
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from human_eye_plugin import auto_router as router
from human_eye_plugin import live_service as service_module
from human_eye_plugin import task_query as task
from human_eye_plugin.live_service import LiveSpatialService
from verification.test_concave_geometry import box, entity
from verification.test_selected_task_query import SelectedHost


def compact(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf8')


def forbidden(*args, **kwargs):
    raise AssertionError('Forbidden duplicate work, action-state I/O or external operation')


def without_trace(value):
    return {key: item for key, item in value.items() if key != 'trace_id'}


class TokenSelectedHost(SelectedHost):
    """Current capture owns its version; there is deliberately no last_token."""
    def __init__(self):
        super().__init__()
        self.capture_instance = 'resident-host-A'
        self.capture_epoch = 1
        self.capture_revision = 1
        self.selection_nonce = ''
        self.emit_token = True
        self.scene = {
            'revision': 'resident-scene', 'unit': 'm', 'coordinate_frame': 'world',
            'source': 'resident-memory-host',
            'meshes': [mesh.to_dict() for mesh in (
                box((0, 0, 0), (2, 2, 2), 'a'),
                box((4, 0, 0), (2, 2, 2), 'b'),
                box((.5, 0, 0), (2, 2, 2), 'c'),
                box((-4, 0, 0), (2, 2, 2), 'd'))],
        }
        self.instances = {item['object_id']: 'instance-' + item['object_id']
                          for item in self.scene['meshes']}

    @property
    def last_token(self):
        raise AssertionError('A previous host token cannot establish currentness')

    def capture_task_scene(self, selectors):
        capture = super().capture_task_scene(selectors)
        if self.emit_token:
            capture['capture_state'] = {
                'instance_id': self.capture_instance, 'epoch': self.capture_epoch,
                'revision': self.capture_revision,
                'selection_key': compact(selectors).decode('utf8') + self.selection_nonce,
            }
        return capture

    def apply_transform(self, *args, **kwargs):
        forbidden()

    def translate(self, oid, delta):
        item = next(item for item in self.scene['meshes'] if item['object_id'] == oid)
        item['vertices'] = [[value + offset for value, offset in zip(vertex, delta)]
                            for vertex in item['vertices']]
        self.capture_revision += 1


class ResidentTaskTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='resident_task_')
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.config_path = self.folder / 'connector.json'
        self.config_path.write_bytes(compact({
            'schema_version': '1.0', 'project_root': str(ROOT), 'enabled': True,
            'quad_size': 64, 'max_sessions': 4, 'state_file': 'actions.json',
            'audit_file': 'audit.jsonl',
        }))
        self.host = TokenSelectedHost()
        self.service = LiveSpatialService(self.config_path, host=self.host)

    def query(self, candidates=('b', 'c', 'd'), *, aabb=True):
        return {'mode': 'task', 'target': {'id': 'a'},
                'candidates': [{'id': oid} for oid in candidates],
                'requested_facts': ['closed_solid_relation', 'surface_proximity'] +
                                   (['aabb'] if aabb else [])}

    def observe(self, query=None, session='read-session'):
        return self.service.observe(session, query=query or self.query(), include_image=False)

    def no_action_io(self, stack):
        for method in ('_locked', '_save', '_runtime'):
            stack.enter_context(patch.object(self.service, method, side_effect=forbidden))
        stack.enter_context(patch.object(service_module, '_read_object', side_effect=forbidden))

    def test_same_token_same_query_warm_skips_normalize_solver_and_action_io(self):
        cold = self.observe()
        self.assertEqual(cold['status'], 'observed')
        with ExitStack() as stack:
            self.no_action_io(stack)
            stack.enter_context(patch.object(service_module, '_validated_scene', side_effect=forbidden))
            stack.enter_context(patch.object(router.MeshEntity3D, 'from_dict', side_effect=forbidden))
            for function in ('task_result', 'classify_closed_solids', 'measure_surface_proximity', 'measure_pair_geometry'):
                stack.enter_context(patch.object(task, function, side_effect=forbidden))
            for function in ('check_task_source', 'check_source_drift'):
                stack.enter_context(patch.object(service_module, function, side_effect=forbidden))
            stack.enter_context(patch.object(Path, 'read_bytes', side_effect=forbidden))
            warm = self.observe()
        self.assertEqual(without_trace(cold), without_trace(warm))
        self.assertEqual(len(self.host.selected_calls), 2, 'Each read must use the current capture token')
        self.assertEqual(self.host.calls, 0)
        self.assertNotIn('capture_state', json.dumps(warm))
        self.assertNotIn('resident-host-A', json.dumps(warm))
        self.assertFalse(self.service.state_path.exists())

    def test_new_aabb_question_reuses_normalized_scene_and_existing_pair_work(self):
        before = self.observe(self.query(aabb=False))
        with ExitStack() as stack:
            stack.enter_context(patch.object(service_module, '_validated_scene', side_effect=forbidden))
            stack.enter_context(patch.object(router.MeshEntity3D, 'from_dict', side_effect=forbidden))
            for function in ('classify_closed_solids', 'measure_surface_proximity', 'measure_pair_geometry'):
                stack.enter_context(patch.object(task, function, side_effect=forbidden))
            after = self.observe(self.query(aabb=True))
        self.assertEqual(after['pairs'], before['pairs'])
        self.assertEqual(after['summary'], before['summary'])
        self.assertEqual(len(after['facts']['aabb']), 4)

    def test_production_warm_read_does_not_repeat_source_disk_checks(self):
        self.service = LiveSpatialService(self.config_path, host=self.host, production_mode=True)
        cold = self.observe()
        self.assertEqual(cold['status'], 'observed')
        with patch.object(service_module, 'check_task_source', side_effect=forbidden), \
                patch.object(service_module, 'check_source_drift', side_effect=forbidden), \
                patch.object(Path, 'read_bytes', side_effect=forbidden):
            warm = self.observe()
        self.assertEqual(without_trace(cold), without_trace(warm))

    def test_new_pair_fact_computes_only_missing_closed_relation(self):
        first = {'mode': 'task', 'objects': [{'id': 'a'}, {'id': 'b'}],
                 'requested_facts': ['surface_proximity']}
        before = self.observe(first)
        next_query = {**first, 'requested_facts': ['surface_proximity', 'closed_solid_relation']}
        with patch.object(service_module, '_validated_scene', side_effect=forbidden), \
                patch.object(task, 'measure_surface_proximity', side_effect=forbidden), \
                patch.object(task, 'classify_closed_solids', wraps=task.classify_closed_solids) as classified:
            after = self.observe(next_query)
        self.assertEqual(classified.call_count, 1)
        self.assertEqual(after['facts']['surface_proximity'], before['facts']['surface_proximity'])
        self.assertEqual(after['facts']['closed_solid_relation']['value'], 'separated')

    def test_revision_update_changes_facts_and_old_results_stay_detached(self):
        old = self.observe(self.query(('b',)))
        self.assertEqual(old['pairs'][0]['separation_gap']['value'], 2.)
        self.host.translate('b', (1, 0, 0))
        with patch.object(service_module, '_validated_scene', wraps=service_module._validated_scene) as normalize:
            current = self.observe(self.query(('b',)))
        self.assertEqual(normalize.call_count, 1)
        self.assertEqual(current['pairs'][0]['separation_gap']['value'], 3.)
        self.assertNotEqual(current['binding']['scene_fingerprint'], old['binding']['scene_fingerprint'])
        self.assertEqual(old['pairs'][0]['separation_gap']['value'], 2.)

    def test_epoch_instance_and_selection_identity_each_invalidate(self):
        self.observe()
        changes = (
            lambda: setattr(self.host, 'capture_epoch', self.host.capture_epoch + 1),
            lambda: setattr(self.host, 'capture_instance', 'resident-host-B'),
            lambda: setattr(self.host, 'selection_nonce', ':new-selection'),
        )
        for change in changes:
            with self.subTest(change=change):
                change()
                with patch.object(service_module, '_validated_scene', wraps=service_module._validated_scene) as normalize:
                    current = self.observe()
                self.assertEqual(normalize.call_count, 1)
                self.assertEqual(current['summary']['penetrating_ids'], ['c'])

    def test_selection_order_and_name_binding_do_not_reuse_wrong_result(self):
        self.observe(self.query(('b', 'c', 'd')))
        reverse = self.observe(self.query(('d', 'c', 'b')))
        self.assertEqual([row['object_id'] for row in reverse['binding']['objects']], ['a', 'd', 'c', 'b'])
        self.assertEqual([pair['object_id'] for pair in reverse['pairs']], ['d', 'c', 'b'])
        self.assertEqual(reverse['summary']['nearest_separated_ids'], ['b', 'd'])
        self.host.scene['meshes'][2]['name'] = 'b'
        self.host.capture_revision += 1
        q = self.query(('b',))
        q['candidates'] = [{'name': 'b'}]
        ambiguous = self.observe(q)
        self.assertEqual(ambiguous['binding']['objects'][1]['reason'], 'object_name_ambiguous')
        self.assertIsNone(ambiguous['summary']['penetrating_ids'])

    def test_tokenless_legacy_host_normalizes_each_current_capture(self):
        self.host.emit_token = False
        with patch.object(service_module, '_validated_scene', wraps=service_module._validated_scene) as normalize:
            cold = self.observe(self.query(('b',)))
            warm = self.observe(self.query(('b',)))
        self.assertEqual(normalize.call_count, 2)
        self.assertEqual(len(self.host.selected_calls), 2)
        self.assertEqual(cold['pairs'], warm['pairs'])
        self.host.translate('b', (1, 0, 0))
        current = self.observe(self.query(('b',)))
        self.assertEqual(current['pairs'][0]['separation_gap']['value'], 3.)

    def test_shared_context_sessions_and_caller_mutation_do_not_poison_results(self):
        initial = self.observe(session='first')
        baseline = copy.deepcopy(without_trace(initial))
        initial['pairs'][0]['separation_gap']['value'] = -999.
        initial['binding']['objects'][0]['name'] = 'caller-mutated'
        initial['summary']['nearest_separated_ids'].append('wrong')
        with patch.object(task, 'task_result', side_effect=forbidden):
            other = self.observe(session='second')
        self.assertEqual(without_trace(other), baseline)
        self.assertNotEqual(initial.get('trace_id'), other.get('trace_id'))

    def test_prepared_action_ledger_is_untouched_by_read(self):
        prepared = self.service.observe('action-session', focal_id='a', reference_id='b', include_image=False)
        self.assertEqual(prepared['status'], 'observed')
        original = self.service.state_path.read_bytes()
        self.assertTrue(json.loads(original)['runtime']['sessions'])
        with ExitStack() as stack:
            self.no_action_io(stack)
            read = self.observe()
        self.assertEqual(read['status'], 'observed')
        self.assertEqual(self.service.state_path.read_bytes(), original)

    def test_pending_committed_quarantine_and_corrupt_action_bytes_are_opaque(self):
        # Deliberately opaque bytes. Their possible action meanings do not need
        # to be validated or cleared by a read-only geometry request.
        variants = (
            compact({'pending': {'operation_id': 'write-1'}, 'committed': {'write-0': {'verified': True}},
                     'runtime': {'quarantine': {'reason': 'uncertain'}}}),
            b'{invalid action ledger\x00',
        )
        for payload in variants:
            with self.subTest(payload=payload):
                self.service.state_path.write_bytes(payload)
                with ExitStack() as stack:
                    self.no_action_io(stack)
                    value = self.observe()
                self.assertEqual(value['status'], 'observed')
                self.assertEqual(self.service.state_path.read_bytes(), payload)

    def test_unknown_surface_and_precise_ties_keep_original_semantics(self):
        self.host.scene['meshes'][2]['vertices'] = box((7, 0, 0), (2, 2, 2), 'c').vertices.tolist()
        self.host.scene['meshes'][2]['faces'] = self.host.scene['meshes'][2]['faces'][:-1]
        self.host.capture_revision += 1
        result = self.observe()
        self.assertEqual(result['status'], 'partial')
        self.assertFalse(result['summary']['penetration_set_complete'])
        self.assertIsNone(result['summary']['nearest_separated_ids'])
        self.assertEqual(result['summary']['best_known_separated_ids'], ['b', 'd'])
        self.assertEqual(result['pairs'][1]['facts']['surface_proximity']['status'], 'measured')
        self.assertEqual(result['pairs'][1]['facts']['closed_solid_relation']['status'], 'unknown')
        with patch.object(task, 'task_result', side_effect=forbidden):
            warm = self.observe()
        self.assertEqual(without_trace(warm), without_trace(result))


if __name__ == '__main__':
    with patch.object(socket, 'socket', side_effect=forbidden), \
            patch.object(socket, 'create_connection', side_effect=forbidden), \
            patch.object(subprocess, 'Popen', side_effect=forbidden):
        unittest.main(verbosity=2)
