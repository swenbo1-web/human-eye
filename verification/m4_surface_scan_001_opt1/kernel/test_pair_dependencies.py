"""Decoded surface dependency cache invalidation and bounded-store regressions."""
import copy
import hashlib
import json
import unittest
from unittest.mock import patch

from human_eye_plugin.auto_router import _validated_scene
from human_eye_plugin.read_context import ReadContext
from human_eye_plugin.runtime_identity import runtime_identity
from human_eye_plugin.scene_cache import SpatialSceneCache
from human_eye_plugin.scene_residency import SceneDeltaDecoder, encode_capture
from human_eye_plugin.surface_scan import surface_scan_result
from human_eye_plugin.task_query import _surface_pair_measurement
from verification.m4_surface_scan_001.tests.test_surface_scan import packet_for, triangle


NOOP = lambda stage: None


def capture(decoder, positions=None, *, revision=1, resource_revisions=None,
            incarnations=None, document='analytic-document', epoch=1, instance='host',
            scale=1., threshold=10., local_change=0., names=None, unsupported=(), issues=()):
    positions = {'a': 0., 'b': 1., 'c': 2.} if positions is None else positions
    meshes = [triangle(oid, offset*scale) for oid, offset in positions.items()]
    for mesh in meshes:
        mesh.vertices[:, 1:] *= scale
        if mesh.object_id == 'a':
            mesh.vertices[0, 0] += local_change*scale
        if names and mesh.object_id in names:
            mesh.name = names[mesh.object_id]
    packet = packet_for(meshes, threshold, unsupported=unsupported, issues=issues)
    scene = packet['capture']
    state = scene['capture_state']
    state.update(instance_id=instance, epoch=epoch, revision=revision)
    for identity in (scene['host_identity'], packet['binding']['host_identity']):
        identity['document_epoch'] = document
        identity['object_instances'] = {oid: (incarnations or {}).get(oid, 'instance-'+oid)
                                        for oid in identity['object_instances']}
    packet['binding']['scale_length'] = scale
    resources = {}
    for mesh in scene['meshes']:
        oid = mesh['object_id']
        local = [[0.,0.,0.], [0.,1.,0.], [0.,0.,1.]]
        if oid == 'a':
            local[0][0] += local_change
        resource = dict(resource_id=hashlib.sha256(oid.encode()).hexdigest(),
            revision=(resource_revisions or {}).get(oid, 1), vertices_local=local,
            faces=[[0,1,2]], edges=[[0,1],[1,2],[2,0]])
        matrix = [[1.,0.,0.,positions[oid]], [0.,1.,0.,0.], [0.,0.,1.,0.], [0.,0.,0.,1.]]
        resources[oid] = (resource, matrix, scale)
    if decoder is None:
        return packet, None
    wire = encode_capture(packet, decoder.baseline(), resources)
    # Geometry edits publish a new resource version, so baseline transmission
    # necessarily includes the new current arrays.
    decoded = decoder.apply(wire)
    return decoded, decoder.surface_scan_dependencies(decoded)


class DependencyCacheTests(unittest.TestCase):
    def setUp(self):
        self.decoder = SceneDeltaDecoder()
        self.context = ReadContext()

    def run_scan(self, packet, binding, *, new_pairs=512, cache=None, progress=None, identity=None):
        cache = self.context.scene_cache if cache is None else cache
        self.context.activate(packet['capture'], 'surface_scan',
            dict(binding=packet['binding'], threshold=packet['threshold_m'], issues=packet['scope_issues']))
        work = {}
        result = surface_scan_result(packet, cache, NOOP, diagnostics=work,
            _dependencies=binding, max_new_pairs=new_pairs,
            _progress=progress, _identity=identity)
        self.assertEqual(result['coverage']['total_pairs'], sum(result['coverage'][k] for k in
            ('bound_excluded','measured_match','measured_nonmatch','unknown','deferred')))
        return result, work

    def test_local_move_reuses_only_the_unaffected_pair(self):
        initial = capture(self.decoder)
        first, cold = self.run_scan(*initial)
        self.assertEqual(cold['kernel_calls'], 3)
        repeated = capture(self.decoder)
        _, warm = self.run_scan(*repeated)
        self.assertEqual((warm['kernel_calls'], warm['cache_hits']), (0, 3))
        edited = capture(self.decoder, {'a':.25,'b':1.,'c':2.}, revision=2)
        actual, work = self.run_scan(*edited)
        self.assertEqual((work['kernel_calls'], work['cache_hits']), (2,1))
        key = json.dumps(['b','c'], separators=(',',':'))
        self.assertEqual(work['pairs'][key]['surface_dependency_key'], cold['pairs'][key]['surface_dependency_key'])
        self.assertTrue(work['pairs'][key]['surface_dependency_cache_hit'])
        for ids in (['a','b'],['a','c']):
            key = json.dumps(ids, separators=(',',':'))
            self.assertFalse(work['pairs'][key]['surface_dependency_cache_hit'])
            self.assertNotEqual(work['pairs'][key]['surface_dependency_key'], cold['pairs'][key]['surface_dependency_key'])
        self.assertEqual(actual['status'], first['status'])
        self.assertEqual(actual['matches'][0]['distance_m'], .75)

    def test_same_face_count_resource_change_and_same_name_replacement_miss(self):
        for changed in (dict(resource_revisions={'a':2}, local_change=.125),
                        dict(incarnations={'a':'replacement-a'})):
            with self.subTest(changed=changed):
                self.decoder = SceneDeltaDecoder()
                self.context = ReadContext()
                self.run_scan(*capture(self.decoder))
                result, work = self.run_scan(*capture(self.decoder, revision=2, **changed))
                self.assertEqual((work['kernel_calls'],work['cache_hits']), (2,1))
                self.assertEqual(result['status'], 'complete')

    def test_rename_is_only_a_current_output_label(self):
        self.run_scan(*capture(self.decoder))
        result, work = self.run_scan(*capture(self.decoder, revision=2, names={'a':'New A'}))
        self.assertEqual((work['kernel_calls'],work['cache_hits']), (0,3))
        self.assertTrue(any(obj['name']=='New A' for row in result['matches'] for obj in row['objects']))

    def test_unit_epoch_document_host_and_runtime_changes_invalidate(self):
        for changed in (dict(scale=.01), dict(epoch=2), dict(document='new-document'), dict(instance='new-host')):
            with self.subTest(changed=changed):
                self.decoder = SceneDeltaDecoder()
                self.context = ReadContext()
                self.run_scan(*capture(self.decoder))
                _, work = self.run_scan(*capture(self.decoder, revision=2, **changed))
                self.assertEqual((work['kernel_calls'],work['cache_hits']), (3,0))
        self.decoder = SceneDeltaDecoder()
        self.context = ReadContext()
        self.run_scan(*capture(self.decoder))
        identity = runtime_identity()
        identity['source_sha256'] = 'f'*64
        _, work = self.run_scan(*capture(self.decoder, revision=2), identity=identity)
        self.assertEqual((work['kernel_calls'],work['cache_hits']), (3,0))

    def test_deleted_then_reintroduced_resource_does_not_inherit_old_admission(self):
        self.run_scan(*capture(self.decoder))
        self.run_scan(*capture(self.decoder, {'b':1.,'c':2.}, revision=2))
        _, work = self.run_scan(*capture(self.decoder, revision=3))
        self.assertEqual((work['kernel_calls'],work['cache_hits']), (2,1))

    def test_threshold_a_b_a_reclassifies_cached_exact_distances(self):
        matches = []
        for index, threshold in enumerate((1., 1.5, 1.)):
            result, work = self.run_scan(*capture(self.decoder, threshold=threshold, revision=index+1))
            matches.append(result['coverage']['measured_match'])
            if index:
                self.assertEqual(work['kernel_calls'], 0)
        self.assertEqual(matches, [2,2,2])

    def test_ordered_pair_keeps_original_witness_direction(self):
        packet, binding = capture(self.decoder, {'a':0.,'b':1.})
        self.run_scan(packet, binding)
        _, meshes, _ = _validated_scene(packet['capture'], _surface_scan_capture=True)
        cache = self.context.scene_cache
        cache._bind_surface_scan_meshes(meshes, binding, runtime_identity()['source_sha256'], capture=packet)
        forward_work = {}
        forward = _surface_pair_measurement(meshes[0], meshes[1], cache, NOOP,
            source='blender', diagnostics=forward_work, retain_exact_rank=True, _surface_scan=True)
        reverse_work = {}
        reverse = _surface_pair_measurement(meshes[1], meshes[0], cache, NOOP,
            source='blender', diagnostics=reverse_work, retain_exact_rank=True, _surface_scan=True)
        self.assertTrue(forward_work['surface_pair_cache_hit'])
        self.assertFalse(reverse_work['surface_pair_cache_hit'])
        self.assertEqual(forward['point_a_world'], reverse['point_b_world'])
        self.assertEqual(forward['point_b_world'], reverse['point_a_world'])
        self.assertNotEqual(forward_work['surface_dependency_key'], reverse_work['surface_dependency_key'])

    def test_unknown_source_recovers_without_reusing_unsupported_facts(self):
        self.run_scan(*capture(self.decoder))
        result, work = self.run_scan(*capture(self.decoder, revision=2, unsupported=('a',)))
        self.assertEqual(result['coverage']['unknown'], 2)
        self.assertEqual(work['kernel_calls'], 0)
        recovered, work = self.run_scan(*capture(self.decoder, revision=3))
        self.assertEqual(recovered['status'], 'complete')
        self.assertEqual(work['kernel_calls'], 2)
        self.assertEqual(work['cache_hits'], 1)

    def test_scope_change_keeps_current_unknown_even_with_cached_pair_measurements(self):
        self.run_scan(*capture(self.decoder))
        result, work = self.run_scan(*capture(self.decoder, revision=2, issues=['unsupported_instance']))
        self.assertEqual(work['kernel_calls'], 0)
        self.assertEqual(work['cache_hits'], 3)
        self.assertEqual(result['status'], 'unknown')

    def test_low_cap_continues_and_hits_are_free(self):
        first = capture(self.decoder)
        progress = {}
        result, work = self.run_scan(*first, new_pairs=1, progress=progress)
        self.assertEqual(result['coverage']['deferred'], 2)
        self.assertEqual(work['kernel_calls'], 1)
        result, work = self.run_scan(*first, new_pairs=1, progress=progress)
        self.assertEqual(result['coverage']['deferred'], 1)
        result, work = self.run_scan(*first, new_pairs=1, progress=progress)
        self.assertEqual(result['status'], 'complete')
        other = capture(self.decoder, revision=2)
        result, work = self.run_scan(*other, new_pairs=0)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual((work['kernel_calls'],work['cache_hits']), (0,3))

    def test_plain_missing_stale_and_forged_bindings_fall_back(self):
        initial = capture(self.decoder)
        self.run_scan(*initial)
        for binding in (None, {}, dict(objects={'a':'invented'}), initial[1]):
            with self.subTest(binding=type(binding).__name__):
                packet, _ = capture(self.decoder, revision=3)
                result, work = self.run_scan(packet, binding)
                self.assertEqual(result['status'], 'complete')
                self.assertEqual(work['kernel_calls'], 3)
                self.assertTrue(all(not row['surface_dependency_used'] for row in work['pairs'].values()))
                # Plain legacy content may legitimately memoize exact content.
                self.context = ReadContext()
        plain, _ = capture(None)
        result, work = self.run_scan(plain, None)
        self.assertEqual(result['status'],'complete')
        self.assertTrue(all(not row['surface_dependency_used'] for row in work['pairs'].values()))

    def test_copied_or_rebound_packet_does_not_authorize_dependency_key(self):
        packet, binding = capture(self.decoder)
        self.run_scan(packet, binding)
        copied = copy.deepcopy(packet)
        _, work = self.run_scan(copied, binding)
        self.assertTrue(all(not row['surface_dependency_used'] for row in work['pairs'].values()))
        changed, current_binding = capture(self.decoder, revision=3)
        changed['capture']['capture_state']['revision'] += 1
        _, work = self.run_scan(changed, current_binding)
        self.assertTrue(all(not row['surface_dependency_used'] for row in work['pairs'].values()))

    def test_unknown_measurement_does_not_poison_dependency_memo(self):
        packet = capture(self.decoder, {'a':0., 'b':1.})
        with patch('human_eye_plugin.task_query.measure_surface_proximity',
                   return_value=dict(measurement_valid=False, reason='temporary_numeric_unknown')):
            result, work = self.run_scan(*packet)
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['coverage']['unknown'],1)
        self.assertEqual(len(self.context.scene_cache._measurements),0)
        result, work = self.run_scan(*capture(self.decoder, {'a':0.,'b':1.}, revision=2))
        self.assertEqual(result['status'],'complete')
        self.assertEqual((work['kernel_calls'],work['cache_hits']),(1,0))
        _, work = self.run_scan(*capture(self.decoder, {'a':0.,'b':1.}, revision=3))
        self.assertEqual((work['kernel_calls'],work['cache_hits']),(0,1))

    def test_decoder_owner_is_part_of_surface_dependency_namespace(self):
        self.run_scan(*capture(self.decoder))
        _, work = self.run_scan(*capture(SceneDeltaDecoder(), revision=2))
        self.assertEqual((work['kernel_calls'],work['cache_hits']),(3,0))

    def test_general_surface_and_solid_metadata_keys_stay_separate(self):
        packet, binding = capture(self.decoder, {'a':0.,'b':1.})
        self.run_scan(packet, binding)
        _, meshes, _ = _validated_scene(packet['capture'], _surface_scan_capture=True)
        cache = self.context.scene_cache
        cache._bind_surface_scan_meshes(meshes, binding, runtime_identity()['source_sha256'], capture=packet)
        work = {}
        _surface_pair_measurement(*meshes, cache, NOOP, source='blender', diagnostics=work,
                                  retain_exact_rank=True)
        self.assertFalse(work['surface_pair_cache_hit'])
        meshes[0].pivot_world[0] += 1.
        other = {}
        _surface_pair_measurement(*meshes, cache, NOOP, source='blender', diagnostics=other,
                                  retain_exact_rank=True)
        self.assertFalse(other['surface_pair_cache_hit'])
        self.assertNotIn('surface_dependency_key', other)

    def test_shared_measurement_capacity_and_actual_lru_eviction(self):
        cache = SpatialSceneCache(max_bytes=2*1024*1024, max_measurements=2)
        initial = capture(self.decoder)
        self.run_scan(*initial, cache=cache)
        self.assertEqual(len(cache._measurements),2)
        repeated = capture(self.decoder, revision=2)
        _, work = self.run_scan(*repeated, cache=cache)
        self.assertGreater(work['kernel_calls'],0)
        self.assertEqual(len(cache._measurements),2)
        self.assertEqual(cache.max_bytes,2*1024*1024)
        self.assertEqual(cache._bytes(),cache._slow_recount_bytes())
        self.assertLessEqual(cache._bytes(),cache.max_bytes)
        self.assertEqual(ReadContext().scene_cache.max_measurements,256)

    def test_tiny_shared_byte_budget_does_not_increase_for_dependency_cache(self):
        cache = SpatialSceneCache(max_bytes=1024)
        self.run_scan(*capture(self.decoder), cache=cache)
        self.assertLessEqual(cache._bytes(),1024)
        self.assertEqual(cache._bytes(),cache._slow_recount_bytes())
        self.assertEqual(len(cache._measurements),0)

    def test_default_256_slot_store_really_evicts_dependency_results(self):
        packet, binding = capture(self.decoder, {'a':0.,'b':1.})
        _, meshes, _ = _validated_scene(packet['capture'], _surface_scan_capture=True)
        cache = self.context.scene_cache
        cache._bind_surface_scan_meshes(meshes, binding, runtime_identity()['source_sha256'], capture=packet)
        calls = []
        def compute():
            calls.append(1)
            return dict(measurement_valid=True, distance_m=1.)
        for index in range(257):
            value, hit = cache.pair_measurement(*meshes, compute,
                parameters={'case':index}, algorithm_version='bounded-dependency-regression', _surface_scan=True)
            self.assertFalse(hit)
        self.assertEqual(len(cache._measurements),256)
        _, hit = cache.pair_measurement(*meshes, compute,
            parameters={'case':0}, algorithm_version='bounded-dependency-regression', _surface_scan=True)
        self.assertFalse(hit)
        self.assertEqual(len(calls),258)
        self.assertEqual(cache.max_bytes,2*1024*1024)
        self.assertEqual(cache._bytes(),cache._slow_recount_bytes())
        self.assertLessEqual(cache._bytes(),cache.max_bytes)


if __name__ == '__main__':
    unittest.main()
