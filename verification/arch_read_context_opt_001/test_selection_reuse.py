"""Bounded resident selection/result reuse through public service.observe."""
from __future__ import annotations

import copy
from pathlib import Path
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from human_eye_plugin import live_service as service_module, task_query as task
from verification.arch_read_context_001 import test_resident_task as base
TokenSelectedHost = base.TokenSelectedHost
forbidden = base.forbidden
without_trace = base.without_trace


def pair_query(left='a', right='b', facts=('aabb', 'surface_proximity'), *, names=False):
    field = 'name' if names else 'id'
    return {'mode': 'task', 'objects': [{field: left}, {field: right}],
            'requested_facts': list(facts)}


class SetKeyHost(TokenSelectedHost):
    """A host may identify retained resources without encoding selector order."""
    def capture_task_scene(self, selectors):
        value = super().capture_task_scene(selectors)
        value['capture_state']['selection_key'] = 'same-resource-set'
        return value


class SelectionReuseTests(unittest.TestCase):
    setUp = base.ResidentTaskTests.setUp
    query = base.ResidentTaskTests.query
    observe = base.ResidentTaskTests.observe

    def count_sequence(self, queries):
        with patch.object(service_module, '_validated_scene', wraps=service_module._validated_scene) as normalized, \
                patch.object(task, 'task_result', wraps=task.task_result) as result:
            values = [self.observe(query) for query in queries[:2]]
            self.assertEqual((normalized.call_count, result.call_count), (2, 2))
            with patch.object(task, 'classify_closed_solids', side_effect=forbidden), \
                    patch.object(task, 'measure_surface_proximity', side_effect=forbidden), \
                    patch.object(task, 'measure_pair_geometry', side_effect=forbidden):
                values.append(self.observe(queries[2]))
            self.assertEqual((normalized.call_count, result.call_count), (2, 2))
        self.assertEqual(without_trace(values[0]), without_trace(values[2]))
        self.assertEqual(len(self.host.selected_calls), 3)
        return values

    def test_ab_ad_ab_reuses_normalized_scene_and_result(self):
        first = self.query(('b',))
        values = self.count_sequence([first, self.query(('d',)), first])
        self.assertEqual([row['object_id'] for row in values[2]['binding']['objects']], ['a', 'b'])
        self.assertEqual(len(self.service._read_context._selections), 2)

    def test_ab_abc_ab_reuses_subset_when_switching_back(self):
        first = self.query(('b',))
        values = self.count_sequence([first, self.query(('b', 'c')), first])
        self.assertEqual(values[1]['summary']['penetrating_ids'], ['c'])
        self.assertEqual(len(values[2]['pairs']), 1)

    def test_ordered_selectors_and_aliases_do_not_share_wrong_binding(self):
        self.host = SetKeyHost()
        self.service.host = self.host
        ab = pair_query('a', 'b')
        ba = pair_query('b', 'a', names=True)
        values = self.count_sequence([ab, ba, ab])
        self.assertEqual([row['object_id'] for row in values[1]['binding']['objects']], ['b', 'a'])
        first = values[0]['facts']['surface_proximity']['value']['nearest_witness']['direction_a_to_b']
        reverse = values[1]['facts']['surface_proximity']['value']['nearest_witness']['direction_a_to_b']
        self.assertEqual(first, [1., 0., 0.])
        self.assertEqual(reverse, [-1., 0., 0.])
        # Same object order but different raw selector syntax also remains a
        # separate capture binding; a name is never an ID alias.
        by_name = pair_query('a', 'b', names=True)
        with patch.object(service_module, '_validated_scene', wraps=service_module._validated_scene) as normalized:
            alias = self.observe(by_name)
            cached = self.observe(ab)
        self.assertEqual(normalized.call_count, 1)
        self.assertNotEqual(alias['binding']['scene_fingerprint'], cached['binding']['scene_fingerprint'])
        self.assertEqual(alias['facts'], cached['facts'])

    def test_global_revision_epoch_and_instance_each_clear_all_selections(self):
        for dimension in ('capture_revision', 'capture_epoch', 'capture_instance'):
            with self.subTest(dimension=dimension):
                self.observe(self.query(('b',)))
                self.observe(self.query(('d',)))
                self.assertEqual(len(self.service._read_context._selections), 2)
                value = getattr(self.host, dimension)
                setattr(self.host, dimension, value + 1 if isinstance(value, int) else value + ':next')
                with patch.object(service_module, '_validated_scene', wraps=service_module._validated_scene) as normalized:
                    self.observe(self.query(('b',)))
                    self.assertEqual(len(self.service._read_context._selections), 1)
                    self.observe(self.query(('d',)))
                self.assertEqual(normalized.call_count, 2)

    def test_revision_edit_updates_returned_geometry_and_ties(self):
        old = self.observe(self.query(('b', 'd')))
        self.assertEqual(old['summary']['nearest_separated_ids'], ['b', 'd'])
        self.observe(self.query(('c',)))
        self.host.translate('b', (1, 0, 0))
        changed = self.observe(self.query(('b', 'd')))
        self.assertEqual(changed['summary']['nearest_separated_ids'], ['d'])
        self.assertEqual(changed['pairs'][0]['separation_gap']['value'], 3.)
        self.assertEqual(old['pairs'][0]['separation_gap']['value'], 2.)
        self.assertEqual(len(self.service._read_context._selections), 1)

    def test_without_token_switching_back_always_normalizes_and_builds_result(self):
        self.host.emit_token = False
        q = self.query(('b',))
        with patch.object(service_module, '_validated_scene', wraps=service_module._validated_scene) as normalized, \
                patch.object(task, 'task_result', wraps=task.task_result) as result:
            first = self.observe(q)
            self.observe(self.query(('d',)))
            again = self.observe(q)
        self.assertEqual((normalized.call_count, result.call_count), (3, 3))
        self.assertEqual(first['pairs'], again['pairs'])
        self.assertLessEqual(len(self.service._read_context._selections), 1)

    def test_mutating_cold_result_does_not_poison_switched_back_selection(self):
        query = self.query(('b',))
        cold = self.observe(query)
        expected = copy.deepcopy(without_trace(cold))
        cold['binding']['objects'][0]['name'] = 'caller-edited'
        cold['pairs'][0]['separation_gap']['value'] = -1.
        cold['summary']['nearest_separated_ids'].append('wrong')
        self.observe(self.query(('d',)))
        with patch.object(service_module, '_validated_scene', side_effect=forbidden), \
                patch.object(task, 'task_result', side_effect=forbidden):
            restored = self.observe(query)
        self.assertEqual(without_trace(restored), expected)

    def test_host_and_source_generation_changes_clear_every_selection(self):
        for boundary in ('host', 'source'):
            with self.subTest(boundary=boundary):
                self.observe(self.query(('b',)))
                self.observe(self.query(('d',)))
                context = self.service._read_context
                self.assertEqual(len(context._selections), 2)
                old_cache = context.scene_cache
                if boundary == 'host':
                    self.host = TokenSelectedHost()  # Deliberately the same token values.
                    self.service.host = self.host
                else:
                    # Simulates the service being rebound to a newly loaded
                    # source descriptor, not an on-disk edit during a request.
                    self.service._identity = {**self.service._identity,
                        'source_sha256': 'f' * 64 if self.service._identity['source_sha256'] != 'f' * 64 else 'e' * 64}
                with patch.object(service_module, '_validated_scene', wraps=service_module._validated_scene) as normalized:
                    self.observe(self.query(('b',)))
                    self.assertEqual(len(context._selections), 1)
                    self.observe(self.query(('d',)))
                self.assertEqual(normalized.call_count, 2)
                self.assertIsNot(context.scene_cache, old_cache)

    def test_selection_lru_capacity_eight_keeps_recent_and_rebuilds_evicted(self):
        choices = [pair_query(left, right, ('aabb',)) for left, right in
                   [('a', 'b'), ('a', 'c'), ('a', 'd'), ('b', 'a'),
                    ('b', 'c'), ('b', 'd'), ('c', 'a'), ('c', 'b'), ('d', 'a')]]
        with patch.object(service_module, '_validated_scene', wraps=service_module._validated_scene) as normalized, \
                patch.object(task, 'task_result', wraps=task.task_result) as result:
            for query in choices[:8]: self.observe(query)
            self.assertEqual((normalized.call_count, result.call_count), (8, 8))
            self.observe(choices[0])  # Refresh the eldest; choices[1] becomes LRU.
            self.assertEqual((normalized.call_count, result.call_count), (8, 8))
            self.observe(choices[8])
            self.assertEqual((normalized.call_count, result.call_count), (9, 9))
            self.assertEqual(len(self.service._read_context._selections), 8)
            self.observe(choices[0])
            self.assertEqual((normalized.call_count, result.call_count), (9, 9))
            self.observe(choices[1])
            self.assertEqual((normalized.call_count, result.call_count), (10, 10))
        self.assertEqual(len(self.service._read_context._selections), 8)

    def test_result_lru_sixteen_per_selection_and_global_bound_128(self):
        selections = [('a', 'b'), ('a', 'c'), ('a', 'd'), ('b', 'a'),
                      ('b', 'c'), ('b', 'd'), ('c', 'a'), ('d', 'a')]
        optional = ('center_delta', 'axis_gap', 'surface_proximity',
                    'closed_solid_relation', 'surface_clearance')
        variants = [('aabb',) + tuple(fact for bit, fact in enumerate(optional) if mask & (1 << bit))
                    for mask in range(17)]
        for left, right in selections:
            for facts in variants: self.observe(pair_query(left, right, facts))
            self.assertEqual(len(self.service._read_context._results), 16)
        context = self.service._read_context
        self.assertEqual(len(context._selections), 8)
        self.assertEqual(sum(len(state['results']) for state in context._selections.values()), 128)
        with patch.object(task, 'task_result', wraps=task.task_result) as result:
            self.observe(pair_query('d', 'a', variants[0]))
        self.assertEqual(result.call_count, 1, 'The first result was evicted within the current selection')
        with patch.object(task, 'task_result', side_effect=forbidden):
            self.observe(pair_query('d', 'a', variants[-1]))
        self.assertEqual(sum(len(state['results']) for state in context._selections.values()), 128)

    def test_switched_back_new_question_rebinds_private_mesh_cache(self):
        ab = pair_query('a', 'b', ('surface_proximity',))
        ad = pair_query('a', 'd', ('surface_proximity',))
        original = self.observe(ab)
        self.observe(ad)
        context = self.service._read_context
        with patch.object(service_module, '_validated_scene', side_effect=forbidden), \
                patch.object(task, 'measure_surface_proximity', side_effect=forbidden):
            expanded = self.observe(pair_query('a', 'b', ('surface_proximity', 'closed_solid_relation')))
        self.assertEqual(expanded['facts']['surface_proximity'], original['facts']['surface_proximity'])
        self.assertEqual(expanded['facts']['closed_solid_relation']['value'], 'separated')
        bound = {entry[0].object_id for entry in context.scene_cache._read_meshes.values()}
        self.assertEqual(bound, {'a', 'b'})


if __name__ == '__main__':
    with patch.object(socket, 'socket', side_effect=forbidden), \
            patch.object(socket, 'create_connection', side_effect=forbidden), \
            patch.object(subprocess, 'Popen', side_effect=forbidden):
        unittest.main(verbosity=2)
