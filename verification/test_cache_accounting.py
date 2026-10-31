"""Incremental cache accounting agrees with payload inventory under mixed work."""
import copy
import json
import random
import sys
import unittest
from unittest.mock import patch

from human_eye_plugin import scene_cache as module
from human_eye_plugin.scene_cache import SpatialSceneCache
from verification.test_auto_router import box, scene


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def inventory(cache):
    """Independent published budget formula; do not call production _charge."""
    return {
        'blob': sum(sys.getsizeof(value) + sys.getsizeof(key) + 256
                    for key, value in cache._blobs.items()),
        'frame': sum(sys.getsizeof(value) + 256 for value in cache._frames),
        'measurement': sum(sys.getsizeof(value[0]) + sys.getsizeof(key) + 256 + 64
                           for key, value in cache._measurements.items()),
        'support': sum(sys.getsizeof(value) + sys.getsizeof(key) + 256
                       for key, value in cache._solid_support.items()),
        'payload': (sys.getsizeof(cache._latest_scene_payload) + 256
                    if cache._latest_scene_payload is not None else 0),
    }


class SlowAccountingReference(SpatialSceneCache):
    """Retain old full-inventory admission decisions, independent of counters."""
    def _bytes(self):
        return sum(inventory(self).values())


def retained(cache):
    return {'history': cache.export_state(),
        'pair': [(key, value[0]) for key, value in cache._measurements.items()],
        'support': list(cache._solid_support.items()),
        'current_payload': cache._latest_scene_payload, 'current_frame': cache._latest_frame}


def record(cache, value, prepared=False):
    if prepared:
        return cache._record_validated_scene(value, canonical_scene_payload=canonical(value))
    return cache.record_scene(value)


def pair(cache, tag, payload_size=0, compute=None):
    a, b = scene()['meshes']
    return cache.pair_measurement(a, b, compute or (lambda: {
        'measurement_valid': True, 'distance': tag, 'payload': 'x' * payload_size}),
        parameters={'tag': tag}, algorithm_version='accounting-contract-test')


class CacheAccountingTests(unittest.TestCase):
    def assert_accounted(self, cache):
        with cache._lock:
            sizes = inventory(cache)
            for name, size in sizes.items():
                self.assertEqual(getattr(cache, '_' + name + '_bytes'), size, name)
                self.assertGreaterEqual(size, 0)
            expected = sum(sizes.values())
            self.assertEqual(cache._bytes(), expected)
            self.assertEqual(cache.stats()['accounted_bytes'], expected)
            self.assertEqual(cache._slow_recount_bytes(), expected)
            self.assertLessEqual(expected, cache.max_bytes)
            self.assertLessEqual(len(cache._frames), cache.max_frames)
            self.assertLessEqual(len(cache._solid_support), cache.max_measurements)
            self.assertLessEqual(len(cache._measurements), cache.max_measurements)

    def test_empty_and_all_five_payload_categories_match_independent_inventory(self):
        cache = SpatialSceneCache()
        self.assert_accounted(cache)
        record(cache, scene(), prepared=True)
        pair(cache, 1)
        cache._observation_solid_support(scene()['meshes'][0])
        self.assertTrue(all(value > 0 for value in inventory(cache).values()))
        self.assert_accounted(cache)
        before = retained(cache)
        self.assertEqual(cache._slow_recount_bytes(), cache._bytes())
        self.assertEqual(retained(cache), before)

    def test_random_mixed_operations_match_slow_accounting_retention(self):
        for budget, frames, entries, seed in ((12_288, 1, 2, 7), (32_768, 3, 5, 17),
                                              (131_072, 7, 17, 29)):
            with self.subTest(budget=budget):
                rng = random.Random(seed)
                limits = dict(max_bytes=budget, max_frames=frames, max_measurements=entries)
                cache, reference = SpatialSceneCache(**limits), SlowAccountingReference(**limits)
                archives = []
                for index in range(100):
                    operation = rng.randrange(8)
                    if operation in (0, 1, 2):
                        value = scene(str(rng.randrange(8)))
                        value['source'] = {'capture': rng.randrange(3), 'padding': 'm' * rng.randrange(300)}
                        if operation == 1:
                            value['meshes'].append(box('extra', [10 + index, 0, 0], [1, 1, 1]))
                        if operation == 2 and index % 3 == 0:
                            value['meshes'] = []
                        prepared = bool(rng.randrange(2))
                        for item in (cache, reference):
                            record(item, copy.deepcopy(value), prepared=prepared)
                    elif operation == 3:
                        tag, length = rng.randrange(8), rng.randrange(3000)
                        self.assertEqual(pair(cache, tag, length), pair(reference, tag, length))
                    elif operation == 4:
                        mesh = box(str(rng.randrange(12)), [rng.randrange(8), 0, 0], [1, 1, 1])
                        self.assertEqual(cache._observation_solid_support(mesh), reference._observation_solid_support(mesh))
                    elif operation == 5:
                        archives.append(cache.export_state())
                    elif operation == 6 and archives:
                        selected, preserve = rng.choice(archives), bool(rng.randrange(2))
                        for item in (cache, reference):
                            item.import_state(copy.deepcopy(selected), preserve_measurements=preserve)
                    else:
                        value = scene('oversized')
                        value['source'] = 'q' * (budget * 2)
                        for item in (cache, reference):
                            self.assertFalse(item.record_scene(value)['retained'])
                    self.assert_accounted(cache)
                    self.assertEqual(retained(cache), retained(reference), (seed, index, operation))
                    if cache.stats()['frames']:
                        self.assertEqual(cache.snapshot(), reference.snapshot())

    def test_duplicate_current_bytes_and_public_record_do_not_double_charge(self):
        cache = SpatialSceneCache()
        value = scene()
        record(cache, value, prepared=True)
        initial = cache._bytes()
        for _ in range(10):
            self.assertTrue(record(cache, copy.deepcopy(value), prepared=True)['duplicate_frame'])
            self.assertEqual(cache._bytes(), initial)
            self.assert_accounted(cache)
        cache.record_scene(value)
        self.assertEqual(inventory(cache)['payload'], 0)
        self.assert_accounted(cache)
        record(cache, value, prepared=True)
        self.assertEqual(cache._bytes(), initial)

    def test_frame_and_blob_collection_releases_only_unreferenced_payloads(self):
        cache = SpatialSceneCache(max_frames=2)
        expected = []
        for index in range(8):
            value = scene(str(index))
            value['meshes'][1]['vertices'][0][0] += index * 1e-5
            record(cache, value, prepared=True)
            expected.append(copy.deepcopy(value))
            self.assert_accounted(cache)
        self.assertEqual(cache.snapshot(0), expected[-2])
        self.assertEqual(cache.snapshot(1), expected[-1])
        self.assertEqual(len(cache._blobs), 6)  # Shared base plus two unique parts.

    def test_shared_budget_eviction_order_stays_frames_then_support_then_pairs(self):
        values = [scene('first'), scene('second')]
        meshes = [box('support' + str(i), [i, 0, 0], [1, 1, 1]) for i in range(2)]
        def populate(cache, history):
            for value in values[-history:]:
                cache.record_scene(value)
            pair(cache, 2, 3000)
            for mesh in meshes:
                cache._observation_solid_support(mesh)
        calibration = SpatialSceneCache()
        populate(calibration, 2)
        sizes = inventory(calibration)
        frame_first = SpatialSceneCache(max_bytes=sum(sizes.values()) - 1)
        populate(frame_first, 2)
        self.assertEqual(frame_first.stats()['frames'], 1)
        self.assertEqual(frame_first.snapshot()['revision'], 'second')
        self.assertEqual(frame_first.stats()['solid_support_entries'], 2)
        self.assertEqual(frame_first.stats()['measurement_entries'], 1)
        self.assert_accounted(frame_first)
        one = SpatialSceneCache()
        populate(one, 1)
        sizes = inventory(one)
        support_first = SpatialSceneCache(max_bytes=sum(sizes.values()) - 1)
        populate(support_first, 1)
        self.assertEqual(support_first.stats()['frames'], 1)
        self.assertEqual(support_first.stats()['solid_support_entries'], 1)
        self.assertEqual(support_first.stats()['measurement_entries'], 1)
        self.assert_accounted(support_first)
        pair_last = SpatialSceneCache(max_bytes=sum(sizes.values()) - sizes['support'] - 1)
        populate(pair_last, 1)
        self.assertEqual(pair_last.stats()['measurement_entries'], 0)
        self.assertEqual(pair_last.stats()['frames'], 1)
        self.assert_accounted(pair_last)

    def test_lru_hits_do_not_charge_again_and_remove_the_actual_oldest_entry(self):
        cache = SpatialSceneCache(max_measurements=2)
        for tag in (1, 2):
            pair(cache, tag)
        original = cache._bytes()
        self.assertTrue(pair(cache, 1)[1])
        self.assertEqual(cache._bytes(), original)
        pair(cache, 3)
        self.assertFalse(pair(cache, 2)[1])
        self.assert_accounted(cache)
        meshes = [box(str(i), [i, 0, 0], [1, 1, 1]) for i in range(3)]
        for mesh in meshes[:2]:
            cache._observation_solid_support(mesh)
        hit_bytes = cache._bytes()
        cache._observation_solid_support(meshes[0])
        self.assertEqual(cache._bytes(), hit_bytes)
        cache._observation_solid_support(meshes[2])
        misses = cache.stats()['solid_support_misses']
        cache._observation_solid_support(meshes[1])
        self.assertEqual(cache.stats()['solid_support_misses'], misses + 1)
        self.assert_accounted(cache)

    def test_import_replaces_history_and_preserves_only_local_memo_when_requested(self):
        source = SpatialSceneCache()
        source.record_scene(scene('imported'))
        for preserve in (True, False):
            cache = SpatialSceneCache()
            record(cache, scene('old'), prepared=True)
            pair(cache, 1)
            cache._observation_solid_support(scene()['meshes'][0])
            cache.import_state(source.export_state(), preserve_measurements=preserve)
            self.assertEqual(cache.snapshot()['revision'], 'imported')
            self.assertEqual(cache.stats()['measurement_entries'], int(preserve))
            self.assertEqual(cache.stats()['solid_support_entries'], int(preserve))
            self.assertEqual(inventory(cache)['payload'], 0)
            self.assert_accounted(cache)

    def test_late_invalid_import_and_encoding_failures_leave_retained_state_atomic(self):
        cache = SpatialSceneCache()
        record(cache, scene('retained'), prepared=True)
        pair(cache, 1)
        cache._observation_solid_support(scene()['meshes'][0])
        source = SpatialSceneCache()
        source.record_scene(scene('valid-first'))
        source.record_scene(scene('valid-second'))
        invalid = source.export_state()
        invalid['frames'][-1] = '{"metadata":{},"objects":[["bad","missing"]]}'
        before, accounted = retained(cache), cache._bytes()
        with self.assertRaises(ValueError):
            cache.import_state(invalid, preserve_measurements=True)
        self.assertEqual(retained(cache), before)
        self.assertEqual(cache._bytes(), accounted)
        malformed = scene('invalid-source')
        malformed['source'] = float('nan')
        with self.assertRaises(ValueError):
            cache.record_scene(malformed)
        self.assertEqual(retained(cache), before)
        with self.assertRaises(ValueError):
            pair(cache, 99, compute=lambda: {'measurement_valid': True, 'value': float('nan')})
        self.assertEqual(retained(cache), before)
        self.assert_accounted(cache)

    def test_unknown_oversize_and_compute_exception_do_not_charge_a_result(self):
        cache = SpatialSceneCache(max_bytes=8192)
        cache.record_scene(scene())
        original = retained(cache)
        for callback in (lambda: {'measurement_valid': False},
                         lambda: {'measurement_valid': True, 'huge': 'x' * 20_000}):
            result, hit = pair(cache, 99, compute=callback)
            self.assertFalse(hit)
            self.assertEqual(retained(cache), original)
        def fail():
            raise RuntimeError('evaluation failed')
        with self.assertRaises(RuntimeError):
            pair(cache, 99, compute=fail)
        open_mesh = scene()['meshes'][0]
        open_mesh['faces'].pop()
        self.assertFalse(cache._observation_solid_support(open_mesh)['supported'])
        self.assertEqual(retained(cache), original)
        self.assert_accounted(cache)

    def test_reentrant_pair_replacement_charges_only_the_retained_final_payload(self):
        cache = SpatialSceneCache()
        def outer():
            pair(cache, 1, payload_size=100)
            return {'measurement_valid': True, 'outer': 'y' * 200}
        value, hit = pair(cache, 1, compute=outer)
        self.assertFalse(hit)
        self.assertEqual(value['outer'], 'y' * 200)
        self.assertEqual(cache.stats()['measurement_entries'], 1)
        self.assert_accounted(cache)

    def test_reentrant_support_replacement_charges_only_one_immutable_result(self):
        from human_eye_plugin.geometry_safety import solid_support_status
        cache, mesh, nested = SpatialSceneCache(), scene()['meshes'][0], []
        def evaluate(value):
            if not nested:
                nested.append(True)
                cache._observation_solid_support(value)
            return solid_support_status(value)
        with patch('human_eye_plugin.geometry_safety.solid_support_status', side_effect=evaluate):
            self.assertTrue(cache._observation_solid_support(mesh)['supported'])
        self.assertEqual(cache.stats()['solid_support_entries'], 1)
        self.assert_accounted(cache)

    def test_defensive_single_frame_clear_releases_each_history_charge(self):
        cache = SpatialSceneCache(max_bytes=32 * 1024)
        record(cache, scene(), prepared=True)
        pair(cache, 1)
        cache._observation_solid_support(scene()['meshes'][0])
        # Trusted limit reduction exercises the existing last-resort trim path.
        cache.max_bytes = 1024
        with cache._lock:
            cache._trim()
        self.assertEqual(cache.export_state()['frames'], [])
        self.assertEqual(cache._bytes(), 0)
        self.assert_accounted(cache)

    def test_import_with_local_memo_pressure_matches_original_eviction_admission(self):
        source = SpatialSceneCache(max_bytes=8192)
        value = scene('incoming')
        value['source'] = 'incoming metadata' * 100
        self.assertTrue(source.record_scene(value)['retained'])
        cache, reference = SpatialSceneCache(max_bytes=8192), SlowAccountingReference(max_bytes=8192)
        for item in (cache, reference):
            pair(item, 1, payload_size=3000)
            item._observation_solid_support(scene()['meshes'][0])
            item.import_state(source.export_state(), preserve_measurements=True)
        self.assertEqual(retained(cache), retained(reference))
        self.assertEqual(cache.snapshot()['revision'], 'incoming')
        self.assertLess(cache.stats()['solid_support_entries'] + cache.stats()['measurement_entries'], 2)
        self.assert_accounted(cache)

    def test_slow_recount_detects_drift_without_silently_repairing_counters(self):
        cache = SpatialSceneCache()
        cache.record_scene(scene())
        expected = cache._bytes()
        cache._blob_bytes += 1  # Deliberate internal corruption, never an import field.
        self.assertEqual(cache._slow_recount_bytes(), expected)
        self.assertEqual(cache._bytes(), expected + 1)
        cache._blob_bytes -= 1
        self.assert_accounted(cache)

    def test_snapshot_export_and_return_mutation_never_changes_charges_or_contents(self):
        cache = SpatialSceneCache()
        value = scene()
        record(cache, value, prepared=True)
        measured, _ = pair(cache, 1)
        support = cache._observation_solid_support(value['meshes'][0])
        before, accounted = retained(cache), cache._bytes()
        cache.snapshot()['meshes'][0]['vertices'][0][0] = 1000
        cache.export_state()['blobs'].clear()
        value['meshes'][1]['name'] = 'caller mutation'
        measured['distance'] = -1000
        support['supported'] = False
        self.assertEqual(retained(cache), before)
        self.assertEqual(cache._bytes(), accounted)
        self.assert_accounted(cache)

    def test_stats_and_support_admission_never_call_the_slow_full_inventory(self):
        cache = SpatialSceneCache(max_bytes=2 * 1024 * 1024)
        cache.record_scene(scene())
        with patch.object(cache, '_slow_recount_bytes', side_effect=AssertionError('hot recount')):
            for i in range(100):
                cache._observation_solid_support(box(str(i), [10 + i, 0, 0], [1, 1, 1]))
            with patch.object(module, '_charge', side_effect=AssertionError('stats must be constant work')):
                for _ in range(10):
                    self.assertGreater(cache.stats()['accounted_bytes'], 0)
        self.assertEqual(cache.stats()['solid_support_entries'], 100)
        self.assert_accounted(cache)


if __name__ == '__main__':
    unittest.main()
