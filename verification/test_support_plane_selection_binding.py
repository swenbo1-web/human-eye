"""Snapshot-bound face selection is a freshness check, never a write grant."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from human_eye_plugin.auto_router import _validated_scene
from human_eye_plugin.goal_execution import validate_segment_ledger
from human_eye_plugin.goal_segment import (
    CLEARANCE_SEGMENT_REQUEST_SCHEMA, selection_binding_rejection,
    solve_segment_candidate, validate_clearance_segment_request,
)
from human_eye_plugin.live_service import LiveSpatialService
from verification.test_auto_router import box
from verification.test_support_plane_candidate import host_frame
from verification.test_support_plane_segment import PlaneSegmentHost, support_request


def snapshot_binding(scene):
    normalized, _, fingerprint = _validated_scene(scene)
    return {'scene_revision': normalized['revision'], 'scene_fingerprint': fingerprint,
            'focal_id': 'part', 'reference_id': 'base'}


class SelectionBindingRequestTests(unittest.TestCase):
    def test_support_only_optional_schema_and_legacy_manual_request(self):
        old, support = CLEARANCE_SEGMENT_REQUEST_SCHEMA['oneOf']
        self.assertNotIn('selection_binding', old['properties'])
        self.assertNotIn('selection_binding', support['required'])
        schema = support['properties']['selection_binding']
        self.assertFalse(schema['additionalProperties'])
        self.assertEqual(set(schema['required']),
            {'scene_revision', 'scene_fingerprint', 'focal_id', 'reference_id'})
        self.assertNotIn('selection_binding', validate_clearance_segment_request(support_request()))
        raw = {'focal_id': 'part', 'reference_id': 'base', 'axis': '+z',
               'target_clearance_m': .001, 'clearance_tolerance_m': 1e-6,
               'selection_binding': snapshot_binding(PlaneSegmentHost().scene)}
        with self.assertRaises(ValueError):validate_clearance_segment_request(raw)

    def test_binding_normalization_is_detached_and_persistently_idempotent(self):
        raw = support_request(direction_world=[.1, .2, .3],
            selection_binding=snapshot_binding(PlaneSegmentHost().scene))
        normalized = validate_clearance_segment_request(raw)
        self.assertIsNot(normalized['selection_binding'], raw['selection_binding'])
        expected = json.dumps(normalized, sort_keys=True, separators=(',', ':'))
        for _ in range(30):
            normalized = validate_clearance_segment_request(json.loads(json.dumps(normalized)))
            self.assertEqual(json.dumps(normalized, sort_keys=True, separators=(',', ':')), expected)
        raw['selection_binding']['scene_revision'] = 'changed'
        self.assertNotEqual(normalized['selection_binding']['scene_revision'], 'changed')

    def test_malformed_binding_never_silently_becomes_unbound(self):
        valid = snapshot_binding(PlaneSegmentHost().scene)
        invalid = [None, True, [], 'token', {}, {**valid, 'force': True}]
        invalid += [{key: value for key, value in valid.items() if key != missing} for missing in valid]
        invalid += [{**valid, 'scene_fingerprint': value} for value in
                    (True, '', 'A'*64, 'g'*64, '0'*63, '0'*65)]
        for key in ('scene_revision', 'focal_id', 'reference_id'):
            invalid += [{**valid, key: value} for value in (True, None, '', ' ', 'x'*257)]
        for binding in invalid:
            with self.subTest(binding=binding), self.assertRaises(ValueError):
                validate_clearance_segment_request(support_request(selection_binding=binding))

    def test_binding_helper_is_pure_and_matching_is_not_action_authority(self):
        scene = PlaneSegmentHost().scene;before = copy.deepcopy(scene)
        request = support_request(selection_binding=snapshot_binding(scene))
        self.assertIsNone(selection_binding_rejection(scene, request))
        result = solve_segment_candidate(scene, request)
        self.assertEqual(result['status'], 'candidate')
        self.assertFalse(result['execution_authority'])
        self.assertFalse(result['whole_scene_collision_certified'])
        self.assertEqual(scene, before)


class SelectionBindingServiceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name);self.state = self.folder/'state.json'
        self.config = self.folder/'config.json'
        self.config.write_text(json.dumps({'schema_version': '1.0',
            'project_root': str(Path(__file__).resolve().parents[1]),
            'state_file': 'state.json', 'audit_file': 'audit.jsonl',
            'quad_size': 64, 'max_sessions': 4, 'enabled': True}), encoding='utf-8')
        self.host = PlaneSegmentHost();self.service = self.new_service()

    def new_service(self):return LiveSpatialService(self.config, host=self.host)

    def request(self, **changes):
        return support_request(selection_binding=snapshot_binding(self.host.scene), **changes)

    def run_segment(self, request, identity='bound-1', execute=True, service=None):
        return (service or self.service).run_clearance_segment('bound-segment', identity,
            request, execute=execute, include_image=False)

    def assert_stale_rejected(self, request, reason, *, execute=True):
        before = self.state.read_bytes() if self.state.exists() else None
        calls = self.host.calls;scene = copy.deepcopy(self.host.scene)
        with patch('human_eye_plugin.goal_execution.solve_segment_candidate') as planner:
            result = self.run_segment(request, execute=execute)
        self.assertEqual(result['status'], 'blocked', result)
        self.assertEqual(result['reason_codes'], [reason])
        self.assertIs(result['executed'], False)
        self.assertFalse(result['retry_authorized'])
        self.assertTrue(result['requires_reobserve'])
        planner.assert_not_called();self.assertEqual(self.host.calls, calls)
        self.assertEqual(self.host.scene, scene)
        self.assertEqual(self.state.read_bytes() if self.state.exists() else None, before)

    def test_valid_binding_preview_reads_fresh_but_never_writes(self):
        request = self.request();before = copy.deepcopy(self.host.scene)
        result = self.run_segment(request, execute=False)
        self.assertEqual(result['status'], 'preview', result)
        self.assertEqual(result['candidate']['status'], 'candidate')
        self.assertGreater(self.host.captures, 0);self.assertEqual(self.host.calls, 0)
        self.assertEqual(self.host.scene, before);self.assertFalse(self.state.exists())

    def test_stale_revision_refused_before_preview_and_new_ledger(self):
        request = self.request();self.host.scene['revision'] = 'r-new'
        for execute in (False, True):
            with self.subTest(execute=execute):
                self.assert_stale_rejected(request, 'support_plane_selection_stale_revision', execute=execute)

    def test_forged_fingerprint_refused_even_same_revision(self):
        request = self.request();request['selection_binding']['scene_fingerprint'] = '0'*64
        self.assert_stale_rejected(request, 'support_plane_selection_stale_fingerprint')

    def test_changed_geometry_keeps_same_triangle_index_but_binding_is_stale(self):
        request = self.request();old_faces = copy.deepcopy(self.host.scene['meshes'][0]['faces'])
        # A current plane would still support the object, but it is no longer
        # the captured geometry the caller selected.
        for vertex in self.host.scene['meshes'][0]['vertices']:vertex[2] += .0001
        self.host.scene['meshes'][0]['pivot_world'][2] += .0001
        self.assertEqual(self.host.scene['revision'], request['selection_binding']['scene_revision'])
        self.assertEqual(self.host.scene['meshes'][0]['faces'], old_faces)
        self.assert_stale_rejected(request, 'support_plane_selection_stale_fingerprint')

    def test_rename_same_name_rebuild_and_document_change_invalidate(self):
        initial = copy.deepcopy(self.host.scene)
        for mutation in ('rename', 'same_name_rebuild', 'document'):
            self.host.scene = copy.deepcopy(initial);request = self.request()
            if mutation == 'rename':self.host.scene['meshes'][1]['name'] = 'renamed-part'
            elif mutation == 'same_name_rebuild':self.host.scene['host_identity']['object_instances']['part'] = 'new-instance'
            else:self.host.scene['host_identity']['document_epoch'] = 'new-document'
            with self.subTest(mutation=mutation):
                self.assert_stale_rejected(request, 'support_plane_selection_stale_fingerprint')

    def test_reordered_faces_invalidate_even_when_index_is_in_range(self):
        request = self.request();ref = self.host.scene['meshes'][0]
        ref['faces'][2], ref['faces'][3] = ref['faces'][3], ref['faces'][2]
        self.assertEqual(request['reference_triangle_index'], 2)
        self.assert_stale_rejected(request, 'support_plane_selection_stale_fingerprint')

    def test_pair_scope_mismatch_cannot_mix_two_discovered_selectors(self):
        for field in ('focal_id', 'reference_id'):
            request = self.request();request['selection_binding'][field] = 'other-object'
            with self.subTest(field=field):
                self.assert_stale_rejected(request, 'support_plane_selection_pair_mismatch')

    def test_stale_binding_preserves_existing_observation_and_id_remains_reusable(self):
        request = self.request();request['selection_binding']['scene_revision'] = 'old'
        self.service.observe('old-observation', focal_id='part', reference_id='base', include_image=False)
        before = self.state.read_bytes()
        self.assert_stale_rejected(request, 'support_plane_selection_stale_revision')
        self.assertEqual(self.state.read_bytes(), before)
        result = self.run_segment(self.request())
        self.assertEqual(result['status'], 'satisfied', result)
        self.assertAlmostEqual(self.host.actual_gap(), .001, places=10)

    def test_initial_binding_does_not_block_own_subsequent_steps(self):
        request = self.request(max_step_translation_m=.0008)
        original_revision = request['selection_binding']['scene_revision']
        result = self.run_segment(request)
        self.assertEqual(result['status'], 'satisfied', result)
        self.assertGreater(self.host.calls, 1)
        self.assertNotEqual(self.host.scene['revision'], original_revision)
        self.assertTrue(all(s['result']['execution_verified'] for s in result['steps']))
        self.assertAlmostEqual(self.host.actual_gap(), .001, places=10)
        state = json.loads(self.state.read_text(encoding='utf-8'));validate_segment_ledger(state)
        self.assertEqual(state['goal_segments']['records']['bound-1']['request']['selection_binding'], request['selection_binding'])

    def test_historical_receipt_precedes_stale_binding_and_host_capture(self):
        request = self.request();result = self.run_segment(request)
        self.assertEqual(result['status'], 'satisfied', result)
        for vertex in self.host.scene['meshes'][1]['vertices']:vertex[2] += .02
        self.host.scene['revision'] = 'external-r90'
        calls = self.host.calls;before = self.state.read_bytes()
        for service in (self.service, self.new_service()):
            with patch.object(self.host, 'capture_scene', side_effect=AssertionError('historical receipt captured')):
                replay = self.run_segment(request, service=service)
            self.assertTrue(replay['historical_receipt']);self.assertTrue(replay['replayed'])
            self.assertFalse(replay['current_scene_revalidated'])
            self.assertEqual(self.host.calls, calls);self.assertEqual(self.state.read_bytes(), before)

    def test_changed_binding_with_same_request_id_is_conflict_before_capture(self):
        request = self.request();self.assertEqual(self.run_segment(request)['status'], 'satisfied')
        for field, value in (('scene_revision','other-r'),('scene_fingerprint','0'*64),('focal_id','other')):
            changed = copy.deepcopy(request);changed['selection_binding'][field] = value
            with patch.object(self.host, 'capture_scene', side_effect=AssertionError('conflict captured')):
                result = self.run_segment(changed)
            self.assertEqual(result['status'], 'request_conflict', result)

    def test_unbound_v18_and_old_axis_receipts_still_load(self):
        # An older caller can keep explicitly choosing its original triangle.
        request = support_request();self.assertNotIn('selection_binding', request)
        self.assertEqual(self.run_segment(request, identity='v18-manual')['status'], 'satisfied')
        old = {'axis': '+z', 'focal_id':'part','reference_id':'base',
               'target_clearance_m': .001, 'clearance_tolerance_m':1e-6}
        normalized = validate_clearance_segment_request(old)
        self.assertNotIn('selection_binding', normalized)
        # Same legacy shape remains ledger-valid after a separate axis request
        # in a genuinely axis-aligned host fixture.
        from verification.test_support_plane_candidate import flat_scene
        self.host.install(flat_scene());service=self.new_service()
        self.assertEqual(self.run_segment(old, identity='old-axis', service=service)['status'], 'satisfied')
        validate_segment_ledger(json.loads(self.state.read_text(encoding='utf-8')))

    def test_matching_binding_cannot_override_whole_scene_obstacle_check(self):
        obstacle = host_frame(box('obstacle',[.04,0,.1015],[.01,.02,.001]))
        self.host.scene['meshes'].append(obstacle)
        self.host.scene['host_identity']['object_instances']['obstacle'] = 'obstacle-instance'
        result = self.run_segment(self.request())
        self.assertEqual(result['status'], 'blocked', result);self.assertEqual(self.host.calls,0)
        self.assertFalse(result['task_succeeded'])

    def test_external_edit_between_own_steps_is_still_detected(self):
        request=self.request(max_step_translation_m=.0008)
        def change(host):
            host.scene['meshes'][0]['color_rgb']=[255,0,0]
            host.scene['revision']='external-revision'
        self.host.change_between_steps=change
        result=self.run_segment(request)
        self.assertEqual(result['status'],'review_required',result)
        self.assertEqual(self.host.calls,1)

    def test_discovered_selector_json_roundtrip_executes_without_manual_face_index(self):
        from human_eye_plugin.support_plane_discovery import discover_support_planes
        discovery = discover_support_planes(self.host.scene, 'part', 'base',
            {'direction_world': [0., 0., 3.]})
        self.assertEqual(discovery['status'], 'complete', discovery)
        self.assertEqual(len(discovery['candidates']), 1)
        before = copy.deepcopy(discovery)
        selector = json.loads(json.dumps(discovery['candidates'][0]['selector']))
        request = support_request(**selector, direction_world=[0., 0., 3.],
            max_step_translation_m=.0008)
        result = self.run_segment(request)
        self.assertEqual(result['status'], 'satisfied', result)
        self.assertGreater(self.host.calls, 1)
        self.assertAlmostEqual(self.host.actual_gap(), .001, places=10)
        self.assertEqual(discovery, before)

    def test_discovered_selector_after_new_capture_requires_reobservation(self):
        from human_eye_plugin.support_plane_discovery import discover_support_planes
        discovery = discover_support_planes(self.host.scene, 'part', 'base', {})
        selector = copy.deepcopy(discovery['candidates'][0]['selector'])
        self.host.scene['revision'] = 'different-capture'
        self.assert_stale_rejected(support_request(**selector),
            'support_plane_selection_stale_revision')

    def test_corrupt_persisted_binding_is_refused_without_new_host_access(self):
        request = self.request();self.assertEqual(self.run_segment(request)['status'], 'satisfied')
        initial = json.loads(self.state.read_text(encoding='utf-8'))
        counts = self.host.calls, self.host.captures
        for binding in (None, {'force': True}, {**request['selection_binding'], 'scene_fingerprint': 'bad'}):
            state = copy.deepcopy(initial)
            state['goal_segments']['records']['bound-1']['request']['selection_binding'] = binding
            self.state.write_text(json.dumps(state), encoding='utf-8')
            with self.subTest(binding=binding), self.assertRaises(ValueError):
                self.run_segment(request, service=self.new_service())
            self.assertEqual((self.host.calls, self.host.captures), counts)


if __name__ == '__main__':unittest.main()
