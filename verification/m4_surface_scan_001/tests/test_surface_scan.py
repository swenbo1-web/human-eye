"""Exact threshold/coverage and request-local continuation regressions."""
import copy
from fractions import Fraction
from itertools import combinations
import json
import math
import random
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin import auto_router, task_query
from human_eye_plugin.blender_host import _acquisition_lower, _digest
from human_eye_plugin.read_context import ReadContext
from human_eye_plugin.runtime_identity import runtime_identity
from human_eye_plugin.scene_cache import SpatialSceneCache
from human_eye_plugin.surface_scan import _packet, surface_scan_result, validate_surface_scan_query


NOOP = lambda stage: None


def triangle(identity, x):
    return MeshEntity3D(identity, '#'+identity, identity,
        np.asarray([(x, 0, 0), (x, 1, 0), (x, 0, 1)], dtype=float),
        np.asarray([[0, 1, 2]]), None, (100, 140, 180), False,
        local_axes=np.eye(3), pivot_world=np.zeros(3), axes_source='host',
        axes_confidence='explicit', axes_reason='analytic_parallel_planes')


def packet_for(meshes, threshold=1., *, unknown_bounds=(), unsupported=(), issues=()):
    identity = runtime_identity()
    rows = []
    for mesh in meshes:
        invalid = mesh.object_id in unknown_bounds
        unsupported_source = mesh.object_id in unsupported
        rows.append(dict(object_id=mesh.object_id, name=mesh.name,
            bounds_world_m=None if invalid else [mesh.vertices.min(axis=0).tolist(),
                                                   mesh.vertices.max(axis=0).tolist()],
            bounds_status='unknown' if invalid else 'enclosed',
            source_status='unsupported' if unsupported_source else 'supported',
            source_mode=None if unsupported_source else 'evaluated_static',
            reason='unsupported_fixture' if unsupported_source else None))
    directory = {row['object_id']: row for row in rows}
    pairs, retained = [], set()
    for a, b in combinations(sorted(directory), 2):
        left, right = directory[a], directory[b]
        lower = _acquisition_lower(left['bounds_world_m'], right['bounds_world_m'])
        disposition = ('unknown_source' if a in unsupported or b in unsupported else
                       'excluded_strict_bound' if lower > threshold else 'retained')
        pairs.append(dict(object_ids=[a, b], lower_bound_m=lower, disposition=disposition))
        if disposition == 'retained':
            retained.update((a, b))
    full_identity = dict(schema_version='1.0', document_epoch='analytic-document',
        capture_scope='complete_scene_meshes',
        object_instances={oid: 'instance-'+oid for oid in directory})
    union_identity = dict(full_identity, capture_scope='surface_scan_candidates',
        object_instances={oid: value for oid, value in full_identity['object_instances'].items()
                          if oid in retained})
    capture = dict(revision='analytic-r1', unit='m', coordinate_frame='world', source='blender',
        capture_scope='surface_scan_candidates', host_identity=union_identity,
        meshes=[mesh.to_dict() for mesh in meshes if mesh.object_id in retained],
        capture_state=dict(instance_id='analytic-runtime', epoch=1, revision=1,
                           selection_key='surface-scan-'+str(threshold)))
    host_sha = next(row['sha256'] for row in identity['source_files']
                    if row['path'] == 'human_eye_plugin/blender_host.py')
    return dict(protocol='single-read-surface-scan-v1',
        result_kind='acquisition_only_not_surface_scan_result',
        scope='independent_static_triangle_meshes_current_evaluated_surfaces',
        M3_qualification_performed=False, execution_authority=False, threshold_m=threshold,
        coverage=rows, pairs=pairs, scope_issues=list(issues), capture=capture,
        binding=dict(host_source_sha256=host_sha, host_identity=full_identity,
            frame=1, scale_length=1., unit='m', coordinate_frame='world',
            same_main_thread_read=True, directory_sha256=_digest(rows)))


class SurfaceScanTests(unittest.TestCase):
    def scan(self, packet, **options):
        diagnostics = options.pop('diagnostics', {})
        result = surface_scan_result(packet, options.pop('cache', SpatialSceneCache()),
            options.pop('checkpoint', NOOP), diagnostics=diagnostics, **options)
        coverage = result['coverage']
        self.assertEqual(coverage['total_pairs'], sum(coverage[key] for key in (
            'bound_excluded', 'measured_match', 'measured_nonmatch', 'unknown', 'deferred')))
        self.assertFalse(result['execution_authority'])
        return result

    def test_query_contract_and_binary64_normalization(self):
        self.assertEqual(validate_surface_scan_query(dict(mode='surface_scan', threshold_m=-0.)),
                         dict(mode='surface_scan', threshold_m=0.))
        for value in (True, -1, math.inf, -math.inf, math.nan, '1', None, 10**1000):
            with self.subTest(value=repr(value)[:30]), self.assertRaises(ValueError):
                validate_surface_scan_query(dict(mode='surface_scan', threshold_m=value))
        for query in ({}, dict(mode='surface_scan', threshold_m=1., objects=[]),
                      dict(mode='surface_scan', threshold_m=1., requested_facts=[])):
            with self.assertRaises(ValueError):
                validate_surface_scan_query(query)

    def test_equal_and_adjacent_thresholds_use_exact_distance_key(self):
        meshes = [triangle('a', 0), triangle('b', 1)]
        for threshold, matches in ((math.nextafter(1., 0.), 0), (1., 1),
                                   (math.nextafter(1., math.inf), 1)):
            work = {}
            result = self.scan(packet_for(meshes, threshold), diagnostics=work)
            self.assertEqual(result['status'], 'complete')
            self.assertEqual(result['coverage']['measured_match'], matches)
            self.assertEqual(work['kernel_calls'], 1)
            self.assertEqual(result['coverage']['bound_excluded'], 0)
            self.assertNotIn('_exact_distance_sq', json.dumps(result))

    def test_tiny_distance_and_huge_threshold_avoid_float_square(self):
        gap = 2.**-500
        meshes = [triangle('a', 0), triangle('b', gap)]
        for threshold, expected in ((gap/2, 0), (gap, 1), (1e308, 1)):
            result = self.scan(packet_for(meshes, threshold, unknown_bounds=('a',)))
            self.assertEqual(result['status'], 'complete')
            self.assertEqual(result['coverage']['measured_match'], expected)

    def test_zero_touching_and_strict_bound_exclusion(self):
        result = self.scan(packet_for([triangle('a', 0), triangle('b', 0)], 0.))
        self.assertEqual(result['coverage']['measured_match'], 1)
        work = {}
        result = self.scan(packet_for([triangle('a', 0), triangle('b', 2)], 1.), diagnostics=work)
        self.assertEqual(result['coverage']['bound_excluded'], 1)
        self.assertEqual(work['kernel_calls'], 0)
        self.assertEqual(work['endpoint_union'], 0)
        self.assertEqual(result['matches'], [])

    def test_cross_object_bounds_are_below_independent_exact_box_distance(self):
        rng = random.Random(184620)
        boxes = []
        for _ in range(96):
            origin = [rng.uniform(-1e100, 1e100) for _ in range(3)]
            width = [rng.uniform(0, 1e99) for _ in range(3)]
            boxes.append([[x-w for x, w in zip(origin, width)],
                          [x+w for x, w in zip(origin, width)]])
        maximum = float.fromhex('0x1.fffffffffffffp+1023')
        boxes.extend([[[-maximum]*3, [-maximum]*3], [[maximum]*3, [maximum]*3]])
        for left, right in zip(boxes, boxes[1:]):
            lower = _acquisition_lower(left, right)
            gaps = [max(Fraction(0), Fraction(left[0][axis])-Fraction(right[1][axis]),
                        Fraction(right[0][axis])-Fraction(left[1][axis])) for axis in range(3)]
            self.assertLessEqual(Fraction(lower)**2, sum(gap*gap for gap in gaps))
        self.assertEqual(_acquisition_lower(None, boxes[0]), 0.)

    def test_diagonal_box_candidate_is_measured_before_nonmatch(self):
        left = triangle('a', 0)
        right = triangle('b', 1)
        right.vertices += np.asarray([0., 2., 0.])
        work = {}
        result = self.scan(packet_for([left, right], 1.1), diagnostics=work)
        self.assertEqual(result['coverage']['bound_excluded'], 0)
        self.assertEqual(result['coverage']['measured_nonmatch'], 1)
        self.assertEqual(work['kernel_calls'], 1)

    def test_zero_and_one_objects_have_true_empty_complete_result(self):
        for meshes in ([], [triangle('a', 0)]):
            result = self.scan(packet_for(meshes))
            self.assertEqual(result['status'], 'complete')
            self.assertEqual(result['coverage']['total_pairs'], 0)
            self.assertEqual(result['matches'], [])

    def test_256_object_envelope_covers_all_pairs_and_257_rejects(self):
        meshes = [triangle(str(i), 10.*i) for i in range(256)]
        work = {}
        result = self.scan(packet_for(meshes, 0.), diagnostics=work)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['source_envelope']['max_objects'], 256)
        self.assertEqual(result['coverage']['total_pairs'], 32640)
        self.assertEqual(result['coverage']['bound_excluded'], 32640)
        self.assertEqual(work['kernel_calls'], 0)
        with self.assertRaisesRegex(ValueError, 'directory binding'):
            self.scan(packet_for(meshes+[triangle('overflow', 9999.)], 0.))

    def test_source_mode_and_invalid_enclosure_reject_before_measurement(self):
        original = packet_for([triangle('a', 0), triangle('b', .5)])
        for field, value in (('source_mode', None), ('bounds_world_m', [[1, 0, 0], [0, 1, 1]]),
                             ('bounds_world_m', [[0, 0, 0], [10**1000, 1, 1]])):
            packet = copy.deepcopy(original)
            packet['coverage'][0][field] = value
            packet['binding']['directory_sha256'] = _digest(packet['coverage'])
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.scan(packet)

    def test_unknown_bound_retains_and_unsupported_source_overrides_far_bound(self):
        meshes = [triangle('a', 0), triangle('b', 100)]
        work = {}
        result = self.scan(packet_for(meshes, unknown_bounds=('a',)), diagnostics=work)
        self.assertEqual(result['coverage']['measured_nonmatch'], 1)
        self.assertEqual(work['kernel_calls'], 1)
        result = self.scan(packet_for(meshes, unsupported=('a',)))
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['coverage']['unknown'], 1)
        self.assertEqual(result['coverage']['bound_excluded'], 0)
        self.assertEqual(result['unsupported_objects'][0]['reason'], 'unsupported_fixture')

    def test_global_scope_issue_never_becomes_complete(self):
        result = self.scan(packet_for([], issues=[dict(reason='unsupported_evaluated_instance')]))
        self.assertEqual(result['status'], 'unknown')
        self.assertFalse(result['coverage']['catalog_scope_confirmed'])

    def test_all_pairs_once_one_normalization_no_spatial_or_closed_calls(self):
        packet = packet_for([triangle(str(i), i/10) for i in range(4)])
        calls = []
        def normalize():
            calls.append(1)
            return auto_router._validated_scene(packet['capture'], _surface_scan_capture=True)
        with patch.object(task_query, '_spatial_pair_measurement', side_effect=AssertionError('spatial')), \
             patch.object(task_query, '_closed_solid_pair_measurement', side_effect=AssertionError('closed')):
            work = {}
            result = self.scan(packet, _normalize=normalize, diagnostics=work)
        self.assertEqual(len(calls), 1)
        self.assertEqual(work['pair_calls'], 6)
        self.assertEqual(work['kernel_calls'], 6)
        self.assertEqual(result['coverage']['measured_match'], 6)
        self.assertEqual(len(work['dispositions']), 6)
        self.assertNotIn('dispositions', result)

    def test_current_request_validated_packet_reuses_validation_once(self):
        packet = packet_for([triangle('a', 0), triangle('b', .5)])
        identity = runtime_identity()
        validated = _packet(packet, NOOP, identity)
        with patch('human_eye_plugin.surface_scan._packet', side_effect=AssertionError('duplicate validation')):
            result = self.scan(packet, _identity=identity, _validated_packet=validated)
        self.assertEqual(result['status'], 'complete')

    def test_low_work_budget_continues_without_terminal_partial_cache(self):
        packet = packet_for([triangle(str(i), i/10) for i in range(4)])
        progress, cache = {}, SpatialSceneCache(max_measurements=1)
        for count in range(1, 7):
            work = {}
            result = self.scan(packet, cache=cache, max_new_pairs=1, _progress=progress,
                               diagnostics=work)
            self.assertEqual(work['kernel_calls'], 1)
            self.assertEqual(result['coverage']['measured_match'], count)
            self.assertEqual(result['coverage']['deferred'], 6-count)
            self.assertEqual(result['status'], 'complete' if count == 6 else 'partial')
        result = self.scan(packet, cache=cache, max_new_pairs=0, _progress=progress)
        self.assertEqual(result['status'], 'complete')

    def test_cache_hit_is_free_under_zero_new_work_cap(self):
        packet = packet_for([triangle('a', 0), triangle('b', .5)])
        cache = SpatialSceneCache()
        self.scan(packet, cache=cache)
        work = {}
        result = self.scan(packet, cache=cache, max_new_pairs=0, diagnostics=work)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(work['kernel_calls'], 0)
        self.assertEqual(work['cache_hits'], 1)

    def test_private_dispositions_remain_complete_for_result_cache_hit(self):
        packet = packet_for([triangle('a', 0), triangle('b', .5), triangle('c', 100)])
        context = ReadContext()
        context.activate(packet['capture'], 'surface_scan', dict(threshold_m=1.))
        progress = context.surface_scan_progress('query')
        def compute():
            return self.scan(packet, cache=context.scene_cache, _progress=progress)
        context.result('query', compute, cache_partial=False)
        result, hit = context.result('query', lambda: self.fail('result cache miss'), cache_partial=False)
        self.assertTrue(hit)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(len(progress['last_dispositions']), 3)
        self.assertEqual({row['status'] for row in progress['last_dispositions']},
                         {'bound_excluded', 'measured_match'})

    def test_unknown_retry_does_not_starve_unattempted_pairs(self):
        packet = packet_for([triangle(str(i), i/10) for i in range(3)])
        progress, cache = {}, SpatialSceneCache()
        original = task_query.measure_surface_proximity
        def measured(left, right, *args, **kwargs):
            if (left.object_id, right.object_id) == ('0', '1'):
                return dict(measurement_valid=False, reason='deliberate_unknown')
            return original(left, right, *args, **kwargs)
        with patch.object(task_query, 'measure_surface_proximity', side_effect=measured):
            for _ in range(3):
                result = self.scan(packet, cache=cache, max_new_pairs=1, _progress=progress)
        self.assertEqual(result['coverage']['unknown'], 1)
        self.assertEqual(result['coverage']['measured_match'], 2)
        self.assertEqual(result['coverage']['deferred'], 0)
        self.assertEqual(result['status'], 'partial')

    def test_delivery_budget_reports_all_measurements_and_actual_delivery(self):
        packet = packet_for([triangle(str(i), i/10) for i in range(8)])
        progress, cache = {}, SpatialSceneCache()
        full = self.scan(packet, cache=cache, _progress=progress)
        budget = len(json.dumps(full, sort_keys=True, separators=(',', ':'),
                                ensure_ascii=False).encode()) - 300
        work = {}
        partial = self.scan(packet, cache=cache, _progress=progress,
                            max_delivery_bytes=budget, diagnostics=work)
        self.assertEqual(partial['status'], 'partial')
        self.assertEqual(partial['coverage']['measured_match'], 28)
        self.assertEqual(partial['delivery']['matches_total'], 28)
        self.assertLess(partial['delivery']['delivered_matches'], 28)
        self.assertFalse(partial['delivery']['complete'])
        self.assertEqual(work['kernel_calls'], 0)
        self.assertLessEqual(len(json.dumps(partial, sort_keys=True,
            separators=(',', ':'), ensure_ascii=False).encode()), budget)

    def test_same_named_objects_do_not_collapse_identity(self):
        meshes = [triangle('a', 0), triangle('b', .5), triangle('c', .75)]
        packet = packet_for(meshes)
        for row in packet['coverage']:
            row['name'] = 'same'
        for row in packet['capture']['meshes']:
            row['name'] = 'same'
        packet['binding']['directory_sha256'] = _digest(packet['coverage'])
        result = self.scan(packet)
        self.assertEqual(len(result['matches']), 3)
        self.assertEqual({tuple(obj['id'] for obj in row['objects']) for row in result['matches']},
                         {('a', 'b'), ('a', 'c'), ('b', 'c')})

    def test_directory_and_active_object_order_cannot_change_pair_predicate(self):
        meshes = [triangle('a', 0), triangle('b', .5), triangle('c', .75)]
        original = self.scan(packet_for(meshes))
        meshes[0].is_focal = True
        reversed_result = self.scan(packet_for(list(reversed(meshes))))
        self.assertEqual(original['matches'], reversed_result['matches'])
        self.assertEqual(original['coverage'], reversed_result['coverage'])

    def test_unknown_witness_preserves_exact_match_without_inventing_points(self):
        packet = packet_for([triangle('a', 0), triangle('b', .5)])
        original = task_query.measure_surface_proximity
        def without_witness(*args, **kwargs):
            measured = original(*args, **kwargs)
            measured.pop('point_a_world', None)
            measured.pop('point_b_world', None)
            measured.update(witness_status='unknown', witness_reason='deliberate_publication_limit')
            return measured
        with patch.object(task_query, 'measure_surface_proximity', side_effect=without_witness):
            result = self.scan(packet)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['coverage']['measured_match'], 1)
        self.assertEqual(result['matches'][0]['witness_status'], 'unknown')
        self.assertNotIn('point_a_world', result['matches'][0])

    def test_malformed_pair_coverage_bound_digest_and_union_reject(self):
        original = packet_for([triangle('a', 0), triangle('b', .5), triangle('c', .75)])
        def missing(packet):
            packet['pairs'].pop()
        def duplicate(packet):
            packet['pairs'][1] = copy.deepcopy(packet['pairs'][0])
        def false_lower(packet):
            packet['pairs'][0]['lower_bound_m'] = False
        def wrong_bound(packet):
            packet['pairs'][0]['lower_bound_m'] = 100.
            packet['pairs'][0]['disposition'] = 'excluded_strict_bound'
        def digest(packet):
            packet['coverage'][0]['name'] = 'tampered'
        def union(packet):
            packet['capture']['meshes'].pop()
        def current_name(packet):
            packet['capture']['meshes'][0]['name'] = 'different_current_name'
        for mutate in (missing, duplicate, false_lower, wrong_bound, digest, union, current_name):
            packet = copy.deepcopy(original)
            mutate(packet)
            with self.subTest(mutation=mutate.__name__), self.assertRaises(ValueError):
                self.scan(packet)

    def test_request_checkpoint_propagates_at_final_publication(self):
        packet = packet_for([triangle('a', 0), triangle('b', .5)])
        stages = []
        def checkpoint(stage):
            stages.append(stage)
            if stage == 'surface_scan_result':
                raise RuntimeError('request_deadline')
        with self.assertRaisesRegex(RuntimeError, 'request_deadline'):
            self.scan(packet, checkpoint=checkpoint)
        self.assertIn('surface_scan_before_new_pair', stages)

    def test_progress_clears_when_source_or_threshold_changes(self):
        packet = packet_for([triangle('a', 0), triangle('b', .5)])
        progress, cache = {}, SpatialSceneCache()
        self.scan(packet, _progress=progress, cache=cache)
        changed = packet_for([triangle('a', 0), triangle('b', 2.)])
        result = self.scan(changed, _progress=progress, cache=cache)
        self.assertEqual(result['matches'], [])
        self.assertEqual(progress['measured'], {})
        result = self.scan(packet_for([triangle('a', 0), triangle('b', .5)], .25),
                           _progress=progress, cache=cache)
        self.assertEqual(result['matches'], [])

    def test_document_reload_clears_private_progress_and_old_union_is_rejected(self):
        packet = packet_for([triangle('a', 0), triangle('b', .5)])
        progress = {}
        self.scan(packet, _progress=progress)
        changed = copy.deepcopy(packet)
        changed['binding']['host_identity']['document_epoch'] = 'new-document'
        with self.assertRaisesRegex(ValueError, 'endpoint union identity'):
            self.scan(changed, _progress=progress)
        changed['capture']['host_identity']['document_epoch'] = 'new-document'
        work = {}
        result = self.scan(changed, _progress=progress, diagnostics=work)
        self.assertEqual(result['binding']['document_epoch'], 'new-document')
        self.assertEqual(work['continuation_hits'], 0)


class ReadContextScanTests(unittest.TestCase):
    def setUp(self):
        self.context = ReadContext()
        self.capture = dict(capture_state=dict(instance_id='runtime', epoch=1,
                                              revision=1, selection_key='scan'))
        self.context.activate(self.capture, 'surface_scan', dict(threshold_m=1.))

    def test_default_partial_cache_and_opt_in_recompute(self):
        calls = []
        def compute():
            calls.append(1)
            return dict(status='partial')
        self.context.result('query', compute)
        _, hit = self.context.result('query', compute)
        self.assertTrue(hit)
        self.context.result('query', compute, cache_partial=False)
        self.context.result('query', compute, cache_partial=False)
        self.assertEqual(len(calls), 3)
        self.context.result('query', lambda: dict(status='complete'), cache_partial=False)
        _, hit = self.context.result('query', compute, cache_partial=False)
        self.assertTrue(hit)

    def test_progress_bound_to_selection_generation_and_query(self):
        progress = self.context.surface_scan_progress('one')
        progress['measured'] = {'a': 'summary'}
        self.assertIs(self.context.surface_scan_progress('one'), progress)
        self.assertEqual(self.context.surface_scan_progress('two'), {})
        progress = self.context.surface_scan_progress('two')
        progress['measured'] = {'a': 'summary'}
        self.capture['capture_state']['revision'] += 1
        self.context.activate(self.capture, 'surface_scan', dict(threshold_m=1.))
        self.assertEqual(self.context.surface_scan_progress('two'), {})

    def test_a_b_a_invalidates_complete_result_with_evicted_scan_progress(self):
        calls = []
        def compute(label):
            calls.append(label)
            return dict(status='complete')
        progress = self.context.surface_scan_progress('A')
        progress['last_dispositions'] = [dict(status='measured_nonmatch')]
        self.context.result('A', lambda: compute('A'), cache_partial=False)
        self.context.surface_scan_progress('B')
        self.context.result('B', lambda: compute('B'), cache_partial=False)
        self.assertEqual(self.context.surface_scan_progress('A'), {})
        _, hit = self.context.result('A', lambda: compute('A'), cache_partial=False)
        self.assertFalse(hit)
        self.assertEqual(calls, ['A', 'B', 'A'])


if __name__ == '__main__':
    unittest.main()
