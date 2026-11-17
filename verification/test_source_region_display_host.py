"""Current viewport snapshots through mock capture and resource-delta paths."""
import copy
import hashlib
import json
import time
from types import SimpleNamespace as NS
import unittest

from human_eye_plugin.scene_residency import SceneDeltaDecoder
from human_eye_plugin.auto_router import _validated_scene
from verification.test_blender_host_contracts import FakeRNAWrapper
from verification.test_m4_capture_001 import fixture, m


def display_fixture(*, resident=False):
    host, objects = fixture((0., 2.))
    host.view_layer.name = '当前显示层'
    host.view_layer.as_pointer = lambda: 5001
    for obj in objects:
        obj.effective_visible = True
        obj.layer_hidden = False
        obj.display_calls = []

        def visible_get(*, view_layer, obj=obj):
            obj.display_calls.append(('visible_get', view_layer))
            return obj.effective_visible

        def hide_get(*, view_layer, obj=obj):
            obj.display_calls.append(('hide_get', view_layer))
            return obj.layer_hidden

        obj.visible_get = visible_get
        obj.hide_get = hide_get
    if resident:
        host.bpy.app.handlers = NS(depsgraph_update_post=[], undo_post=[], redo_post=[], load_post=[],
                                   persistent=lambda callback: callback)
    return host, objects


def row(snapshot, host, obj):
    return next(item for item in snapshot['objects'] if item['host_id'] == host.object_id(obj))


class SourceRegionDisplayHostTests(unittest.TestCase):
    def assert_display_digest(self, snapshot):
        content = {key: value for key, value in snapshot.items() if key != 'sha256'}
        encoded = json.dumps(content, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=False, allow_nan=False).encode('utf8')
        self.assertEqual(snapshot['sha256'], hashlib.sha256(encoded).hexdigest())

    def test_effective_host_result_is_preserved_when_flags_disagree(self):
        host, objects = display_fixture()
        visible, collection_hidden = objects
        visible.hide_render = visible.hide_viewport = visible.layer_hidden = True
        collection_hidden.effective_visible = False
        captured = host.capture_scene()
        display = captured['display_snapshot']
        self.assertEqual(display['schema'], 'blender-viewport-display-v1')
        self.assertEqual(display['scope'], 'active_view_layer')
        self.assertEqual(display['status'], 'captured')
        self.assertEqual(display['view_layer'], dict(name='当前显示层', instance_id='rna:5001'))
        shown = row(display, host, visible)
        hidden = row(display, host, collection_hidden)
        self.assertTrue(shown['visible_get'])
        self.assertTrue(all(shown[key] for key in ('hide_get', 'hide_viewport', 'hide_render')))
        self.assertFalse(hidden['visible_get'])
        self.assertFalse(any(hidden[key] for key in ('hide_get', 'hide_viewport', 'hide_render')))
        self.assertEqual({item['host_id']: item['instance_id'] for item in display['objects']},
                         captured['host_identity']['object_instances'])
        self.assertEqual(len(captured['meshes']), 2)
        self.assertEqual(sum(len(mesh['faces']) for mesh in captured['meshes']), 2)
        for obj in objects:
            self.assertEqual(obj.display_calls, [('visible_get', host.view_layer), ('hide_get', host.view_layer)])
            self.assertEqual(obj.mesh_calls, 1)
        self.assert_display_digest(display)

    def test_nonresident_display_changes_and_restores_without_geometry_revision_change(self):
        host, objects = display_fixture()
        before = host.capture_scene()
        objects[0].effective_visible = False
        objects[0].layer_hidden = True
        hidden = host.capture_scene()
        objects[0].effective_visible = True
        objects[0].layer_hidden = False
        restored = host.capture_scene()
        self.assertEqual(before['revision'], hidden['revision'])
        self.assertEqual(before['meshes'], hidden['meshes'])
        self.assertNotEqual(before['display_snapshot']['sha256'], hidden['display_snapshot']['sha256'])
        self.assertEqual(before, restored)
        self.assertEqual(host.residency_work()['display_snapshots'], 3)
        self.assertEqual(host.residency_work()['display_objects'], 6)
        self.assertGreater(host.residency_work()['display_read_ns'], 0)

    def test_resident_hit_refreshes_current_snapshot_and_reuses_all_geometry(self):
        host, objects = display_fixture(resident=True)
        self.addCleanup(host.close_residency)
        before = host.capture_scene()
        work = host.residency_work()
        objects[0].effective_visible = False
        objects[0].layer_hidden = True
        hidden = host.capture_scene()
        after_work = host.residency_work()
        self.assertEqual(before['revision'], hidden['revision'])
        self.assertEqual(before['capture_state'], hidden['capture_state'])
        self.assertEqual(before['meshes'], hidden['meshes'])
        self.assertFalse(row(hidden['display_snapshot'], host, objects[0])['visible_get'])
        self.assertTrue(row(before['display_snapshot'], host, objects[0])['visible_get'])
        self.assertEqual(after_work['capture_cache_hits'] - work['capture_cache_hits'], 1)
        for field in ('to_mesh', 'resource_builds', 'triangulations', 'resource_vertices_read',
                      'resource_faces_read', 'world_transforms', 'world_vertices_transformed'):
            self.assertEqual(after_work[field], work[field], field)
        self.assertEqual([obj.mesh_calls for obj in objects], [1, 1])
        objects[0].effective_visible = True
        objects[0].layer_hidden = False
        restored = host.capture_scene()
        self.assertEqual(before, restored)
        for obj in objects:
            self.assertEqual(len(obj.display_calls), 6)

    def test_existing_viewport_and_render_signature_invalidation_is_preserved(self):
        host, objects = display_fixture(resident=True)
        self.addCleanup(host.close_residency)
        before = host.capture_scene()
        objects[0].hide_render = True
        changed = host.capture_scene()
        self.assertGreater(changed['capture_state']['revision'], before['capture_state']['revision'])
        self.assertTrue(row(changed['display_snapshot'], host, objects[0])['visible_get'])
        self.assertEqual(before['revision'], changed['revision'])
        self.assertEqual(host.residency_work()['resource_builds'], 2)
        objects[0].hide_viewport = True
        changed_again = host.capture_scene()
        self.assertGreater(changed_again['capture_state']['revision'], changed['capture_state']['revision'])
        self.assertEqual(host.residency_work()['resource_builds'], 2)

    def test_delta_round_trip_refreshes_display_with_no_resource_or_world_work(self):
        host, objects = display_fixture(resident=True)
        self.addCleanup(host.close_residency)
        decoder = SceneDeltaDecoder()
        before = host.capture_scene()
        self.assertEqual(decoder.apply(host.capture_delta(before)), before)
        work = decoder.work_totals()
        objects[0].effective_visible = False
        hidden = host.capture_scene()
        wire = host.capture_delta(hidden, decoder.baseline())
        self.assertEqual(wire['resources'], [])
        decoded = decoder.apply(wire)
        self.assertEqual(decoded, hidden)
        self.assertEqual(decoder.work_totals(), work)
        decoded['display_snapshot']['objects'][0]['visible_get'] = 'mutated'
        self.assertEqual(decoder.apply(wire), hidden)
        self.assert_display_digest(hidden['display_snapshot'])

    def test_unavailable_host_visibility_stays_unknown_and_keeps_geometry(self):
        for failure in ('missing', 'raises', 'non_boolean', 'missing_instance'):
            with self.subTest(failure=failure):
                host, objects = display_fixture()
                if failure == 'missing':
                    del objects[0].visible_get
                elif failure == 'raises':
                    def unavailable(**kwargs):
                        raise RuntimeError('view layer unavailable')
                    objects[0].visible_get = unavailable
                elif failure == 'non_boolean':
                    objects[0].effective_visible = 1
                else:
                    objects[0].session_uid = None
                captured = host.capture_scene()
                display = captured['display_snapshot']
                self.assertEqual(display['status'], 'unknown')
                self.assertEqual(display['reason'], 'current_viewport_display_source_unavailable')
                self.assertEqual(len(captured['meshes']), 2)
                key = 'instance_id' if failure == 'missing_instance' else 'visible_get'
                self.assertIsNone(row(display, host, objects[0])[key])
                self.assert_display_digest(display)

    def test_selected_capture_has_matching_display_membership(self):
        host, objects = display_fixture(resident=True)
        self.addCleanup(host.close_residency)
        captured = host.capture_task_scene([dict(name=objects[1].name)])
        self.assertEqual([item['host_id'] for item in captured['display_snapshot']['objects']],
                         [mesh['object_id'] for mesh in captured['meshes']])
        self.assertEqual(objects[0].display_calls, [])
        self.assertEqual(len(objects[1].display_calls), 2)

    def test_view_layer_identity_is_stable_across_rna_wrappers(self):
        host, _ = display_fixture()
        host.scene.as_pointer = lambda: 5000
        before = host.capture_scene()
        wrapped = type(host)(host.bpy, scene=FakeRNAWrapper(host.scene, 5000),
                             view_layer=FakeRNAWrapper(host.view_layer, 5001), identity_metadata=True)
        self.assertEqual(wrapped.capture_scene(), before)

    def test_active_view_layer_switch_has_fresh_layer_scoped_reads(self):
        host, objects = display_fixture(resident=True)
        self.addCleanup(host.close_residency)
        before = host.capture_scene()
        first_layer = host.view_layer
        next_layer = NS(name='另一显示层', as_pointer=lambda: 5002, update=lambda: None,
                        depsgraph=first_layer.depsgraph, objects=first_layer.objects)
        host.scene.view_layers.append(next_layer)
        host.bpy.context.view_layer = next_layer
        objects[0].effective_visible = False
        changed = host.capture_scene()
        self.assertEqual(changed['display_snapshot']['view_layer'], dict(name='另一显示层', instance_id='rna:5002'))
        self.assertNotEqual(before['display_snapshot']['sha256'], changed['display_snapshot']['sha256'])
        for obj in objects:
            self.assertIs(obj.display_calls[-2][1], next_layer)
            self.assertIs(obj.display_calls[-1][1], next_layer)

    def test_delta_without_display_does_not_inherit_old_snapshot(self):
        host, _ = display_fixture(resident=True)
        self.addCleanup(host.close_residency)
        decoder = SceneDeltaDecoder()
        captured = host.capture_scene()
        decoder.apply(host.capture_delta(captured))
        missing = copy.deepcopy(captured)
        missing.pop('display_snapshot')
        wire = host.capture_delta(missing, decoder.baseline())
        self.assertEqual(wire['resources'], [])
        self.assertNotIn('display_snapshot', decoder.apply(wire))
        legacy = copy.deepcopy(missing)
        legacy.pop('capture_state')
        self.assertEqual(decoder.apply(legacy), legacy)

    def test_cached_acquisition_refreshes_display_and_checks_current_wire_budget(self):
        host, objects = display_fixture(resident=True)
        self.addCleanup(host.close_residency)

        def acquire(limit=1_000_000):
            return host.capture_nearest_candidates(host.object_id(objects[0]),
                time.perf_counter_ns() + 10_000_000_000, limit)

        before = acquire()
        wire_bytes = len(json.dumps(before, ensure_ascii=True, allow_nan=False,
                                    separators=(',', ':')).encode('utf8'))
        objects[0].effective_visible = False
        with self.assertRaisesRegex(ValueError, 'acquisition_document_budget_exceeded'):
            acquire(wire_bytes)
        hidden = acquire()
        self.assertEqual(before['capture']['revision'], hidden['capture']['revision'])
        self.assertFalse(row(hidden['capture']['display_snapshot'], host, objects[0])['visible_get'])
        self.assertEqual([obj.mesh_calls for obj in objects], [1, 1])

    def test_cached_scan_refreshes_display_without_expanding_geometry(self):
        host, objects = display_fixture(resident=True)
        self.addCleanup(host.close_residency)

        def acquire():
            return host.capture_surface_scan(3., time.perf_counter_ns() + 10_000_000_000, 1_000_000)

        before = acquire()
        objects[0].effective_visible = False
        hidden = acquire()
        self.assertTrue(hidden['work']['cache_hit'])
        self.assertEqual(before['capture']['capture_state'], hidden['capture']['capture_state'])
        self.assertFalse(row(hidden['capture']['display_snapshot'], host, objects[0])['visible_get'])
        self.assertEqual(hidden['work']['residency_delta']['resource_vertices_read'], 0)
        self.assertEqual(hidden['work']['residency_delta']['world_vertices_transformed'], 0)

    def test_current_display_preserves_router_fingerprint_and_execution_prewrite(self):
        host, objects = display_fixture()
        captured = host.capture_scene()
        normalized, _, fingerprint = _validated_scene(captured)
        self.assertNotIn('display_snapshot', normalized)
        self.assertEqual(m._digest(captured), fingerprint)
        objects[0].effective_visible = False
        changed = host.capture_scene()
        self.assertEqual(m._digest(changed), fingerprint)
        applied = host.apply_transform(dict(focal_id=host.object_id(objects[0]), translation=[0, 0, 0]),
                                       captured['revision'], fingerprint)
        self.assertEqual(applied['scene']['revision'], captured['revision'])

    def test_source_region_accepts_actual_host_snapshot_contract(self):
        from human_eye_plugin.source_region import display_state

        host, objects = display_fixture(resident=True)
        self.addCleanup(host.close_residency)
        objects[0].effective_visible = False
        captured = host.capture_scene()
        display = display_state(captured)
        self.assertEqual(display['status'], 'captured')
        self.assertEqual(display['identity'], captured['display_snapshot']['sha256'])
        expected = {host.object_id(obj): obj.effective_visible for obj in objects}
        self.assertEqual({item['host_id']: item['participates'] for item in display['objects']}, expected)

    def test_native_evidence_keeps_existing_geometry_schema_and_coherence(self):
        host, _ = display_fixture()
        host.execution_metadata = True
        captured = host.capture_scene()
        evidence = host.capture_evidence()
        normalized, _, fingerprint = _validated_scene(captured)
        self.assertNotIn('display_snapshot', evidence['capture'])
        self.assertEqual(evidence['capture'], normalized)
        self.assertEqual(evidence['coherence']['capture_fingerprint'], fingerprint)


if __name__ == '__main__':
    unittest.main()
