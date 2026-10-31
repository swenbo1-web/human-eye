"""Independent mutable-host checks for explicit support-plane goal segments.

No Blender connection is used. Expected gaps come from elementary original
support-plane formulas, not the new solver or its response metadata.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from human_eye_plugin.goal_execution import validate_segment_ledger
from human_eye_plugin.goal_segment import (
    clearance_segment_goal, validate_clearance_segment_request,
)
from human_eye_plugin.live_service import LiveSpatialService
from verification.test_auto_router import box
from verification.test_clearance_segment_service import SegmentClock, SegmentHost
from verification.test_support_plane_candidate import (
    flat_scene, host_frame, normal_gap, slope_scene, tilted_scene,
)


def support_request(**changes):
    result = {'solver': 'support_plane', 'focal_id': 'part', 'reference_id': 'base',
        'reference_triangle_index': 2, 'direction_world': [0., 0., 1.],
        'target_clearance_m': .001, 'clearance_tolerance_m': 1e-6,
        'max_steps': 8, 'max_step_translation_m': .01,
        'max_total_translation_m': .04, 'max_duration_s': 10.}
    result.update(changes)
    return result


class PlaneSegmentHost(SegmentHost):
    def __init__(self, scene=None, normal=(0., 0., 1.)):
        super().__init__()
        self.install(tilted_scene() if scene is None else scene, normal)

    def install(self, scene, normal=(0., 0., 1.)):
        self.scene = copy.deepcopy(scene)
        self.scene['revision'] = 'r1'
        self.scene['host_identity'] = {'schema_version': '1.0',
            'document_epoch': 'plane-doc-1',
            'object_instances': {m['object_id']: 'instance-' + m['object_id']
                                 for m in self.scene['meshes']},
            'capture_scope': 'complete_scene_meshes'}
        self.normal = normal

    def actual_gap(self):
        return normal_gap(self.scene, self.normal)


class SupportPlaneSegmentRequestTests(unittest.TestCase):
    def test_arbitrary_direction_request_is_persistently_idempotent(self):
        for direction in ([1., 2., 3.], [.1, .2, .3], [0., 0., 3.], [0., 0., -5.]):
            with self.subTest(direction=direction):
                request = validate_clearance_segment_request(support_request(direction_world=direction))
                fingerprint = json.dumps(request, sort_keys=True, separators=(',', ':'))
                for _ in range(25):
                    request = validate_clearance_segment_request(json.loads(json.dumps(request)))
                    self.assertEqual(json.dumps(request, sort_keys=True, separators=(',', ':')), fingerprint)

    def test_original_axis_normalization_keeps_legacy_keys_and_values(self):
        raw = {'focal_id': 'part', 'reference_id': 'base', 'axis': '+z',
               'target_clearance_m': .001, 'clearance_tolerance_m': 1e-6}
        value = validate_clearance_segment_request(raw)
        self.assertEqual(value, {**raw, 'max_steps': 4, 'max_step_translation_m': .01,
            'max_total_translation_m': .04, 'max_duration_s': 5.})
        self.assertNotIn('solver', value)

    def test_explicit_solver_rejects_mixed_or_incomplete_intent(self):
        for changes in ({'solver': 'guess'}, {'solver': True}, {'axis': '+z'},
                        {'direction_world': [0, 0, 0]}, {'reference_triangle_index': True},
                        {'reference_triangle_index': -1}, {'direction_world': [False, 0, 1]},
                        {'direction_world': [0, 0, float('inf')]}, {'force': True}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_clearance_segment_request(support_request(**changes))
        for field in ('solver', 'reference_triangle_index', 'direction_world'):
            raw = support_request();raw.pop(field)
            with self.subTest(missing=field), self.assertRaises(ValueError):
                validate_clearance_segment_request(raw)

    def test_goal_projection_keeps_measurement_criteria_without_solver_authority(self):
        self.assertEqual(clearance_segment_goal(support_request()), {
            'focal_id': 'part', 'reference_id': 'base',
            'target_clearance_m': .001, 'clearance_tolerance_m': 1e-6})


class SupportPlaneSegmentServiceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        self.config_path = self.folder / 'live.json'
        self.state_path = self.folder / 'state.json'
        self.config_path.write_text(json.dumps({'schema_version': '1.0',
            'project_root': str(Path(__file__).resolve().parents[1]),
            'state_file': 'state.json', 'audit_file': 'audit.jsonl',
            'quad_size': 64, 'max_sessions': 4, 'enabled': True}), encoding='utf-8')
        self.host = PlaneSegmentHost()
        self.service = self.new_service()

    def new_service(self):
        return LiveSpatialService(self.config_path, host=self.host)

    def read_state(self):
        return json.loads(self.state_path.read_text(encoding='utf-8'))

    def run_segment(self, *, request=None, request_id='support-1', execute=True, service=None):
        return (service or self.service).run_clearance_segment('plane-segment', request_id,
            support_request() if request is None else request, execute=execute, include_image=False)

    def assert_no_new_host_work(self, counts):
        self.assertEqual((self.host.calls, self.host.captures), counts)

    def assert_satisfied(self, result, target=.001):
        self.assertEqual(result['status'], 'satisfied', result)
        self.assertTrue(result['task_succeeded'])
        self.assertLessEqual(abs(self.host.actual_gap()-target), 1e-6)
        self.assertFalse(result['execution_authority'])
        self.assertFalse(result['swept_path_certified'])
        self.assertFalse(result['retry_authorized'])
        state = self.read_state()
        self.assertIsNone(state['inflight'])
        validate_segment_ledger(state)

    def test_tilted_box_one_step_reaches_independent_gap(self):
        before = copy.deepcopy(self.host.scene)
        initial_gap = self.host.actual_gap()
        result = self.run_segment()
        self.assert_satisfied(result)
        self.assertEqual(self.host.calls, 1)
        self.assertEqual(self.host.scene['meshes'][0], before['meshes'][0])
        self.assertEqual(self.host.scene['meshes'][1]['local_axes'], before['meshes'][1]['local_axes'])
        self.assertAlmostEqual(result['actual_total_translation_m'], initial_gap-.001, places=11)
        self.assertIn('support', result['task_succeeded_scope'])

    def test_closed_slope_reaches_normal_gap_not_vertical_gap(self):
        self.host = PlaneSegmentHost(slope_scene(), normal=(-.5, 0., 1.))
        self.service = self.new_service()
        initial = self.host.actual_gap()
        start_z = self.host.scene['meshes'][1]['pivot_world'][2]
        result = self.run_segment(request=support_request(max_step_translation_m=.02))
        self.assert_satisfied(result)
        self.assertEqual(self.host.calls, 1)
        delta = self.host.scene['meshes'][1]['pivot_world'][2]-start_z
        self.assertAlmostEqual(delta, (.001-initial)*(1.25**.5), places=11)

    def test_arbitrary_nonunit_direction_reaches_same_plane_goal(self):
        result = self.run_segment(request=support_request(direction_world=[1., 2., 3.]))
        self.assert_satisfied(result)
        self.assertEqual(self.host.calls, 1)

    def test_float32_host_readback_still_must_meet_actual_gap_tolerance(self):
        self.host.mode='float32'
        result=self.run_segment()
        self.assert_satisfied(result)
        self.assertEqual(self.host.calls, 1)
        self.assertTrue(result['steps'][0]['result']['execution_verified'])

    def test_multi_step_tilted_box_confirms_each_step(self):
        result = self.run_segment(request=support_request(max_step_translation_m=.0008))
        self.assert_satisfied(result)
        self.assertGreater(self.host.calls, 1)
        self.assertLessEqual(self.host.calls, 8)
        self.assertEqual(len(result['steps']), self.host.calls)
        self.assertTrue(all(s['state']=='complete' and s['result']['execution_verified'] for s in result['steps']))

    def test_multi_step_slope_confirms_each_step(self):
        self.host = PlaneSegmentHost(slope_scene(), normal=(-.5, 0., 1.))
        self.service = self.new_service()
        result = self.run_segment(request=support_request(max_step_translation_m=.005))
        self.assert_satisfied(result)
        self.assertGreaterEqual(self.host.calls, 3)
        self.assertLessEqual(self.host.calls, 4)

    def test_restore_goal_preserves_orientation_and_shape(self):
        before = copy.deepcopy(self.host.scene['meshes'][1])
        initial = self.host.actual_gap()
        self.assert_satisfied(self.run_segment())
        result = self.run_segment(request_id='restore', request=support_request(target_clearance_m=initial))
        self.assert_satisfied(result, initial)
        self.assertEqual(self.host.calls, 2)
        after = self.host.scene['meshes'][1]
        self.assertEqual(after['faces'], before['faces'])
        self.assertEqual(after['local_axes'], before['local_axes'])
        for old, new in zip(before['vertices'], after['vertices']):
            for a, b in zip(old, new):self.assertAlmostEqual(a, b, places=12)

    def test_preview_does_not_write_state_or_change_host(self):
        before = copy.deepcopy(self.host.scene)
        result = self.run_segment(execute=False)
        self.assertEqual(result['status'], 'preview', result)
        self.assertEqual(result['candidate']['status'], 'candidate', result)
        self.assertEqual(self.host.scene, before)
        self.assertEqual(self.host.calls, 0)
        self.assertFalse(self.state_path.exists())

    def test_preview_preserves_existing_state_bytes_and_does_not_reserve_id(self):
        self.service.observe('old', focal_id='part', reference_id='base', include_image=False)
        before = self.state_path.read_bytes()
        self.assertEqual(self.run_segment(execute=False)['status'], 'preview')
        self.assertEqual(self.state_path.read_bytes(), before)
        self.assert_satisfied(self.run_segment())

    def test_goal_already_satisfied_does_not_move(self):
        before = copy.deepcopy(self.host.scene)
        goal = self.host.actual_gap()
        self.assert_satisfied(self.run_segment(request=support_request(target_clearance_m=goal)), goal)
        self.assertEqual(self.host.calls, 0)
        self.assertEqual(self.host.scene, before)

    def test_repeated_request_and_new_service_return_historical_receipt(self):
        request = support_request(direction_world=[1., 2., 3.])
        self.assert_satisfied(self.run_segment(request=request))
        counts = self.host.calls, self.host.captures
        before = self.state_path.read_bytes()
        for service in (self.service, self.new_service()):
            result = self.run_segment(request=request, service=service)
            self.assertEqual(result['status'], 'satisfied', result)
            self.assertTrue(result['historical_receipt'])
            self.assertTrue(result['replayed'])
            self.assertFalse(result['current_scene_revalidated'])
            self.assert_no_new_host_work(counts)
            self.assertEqual(self.state_path.read_bytes(), before)

    def test_historical_receipt_after_external_scene_change_never_moves_back(self):
        self.assert_satisfied(self.run_segment())
        for vertex in self.host.scene['meshes'][1]['vertices']:vertex[2]+=.02
        self.host.scene['meshes'][1]['pivot_world'][2]+=.02
        self.host.scene['revision']='r90'
        counts = self.host.calls, self.host.captures
        result = self.run_segment(service=self.new_service())
        self.assertEqual(result['status'], 'satisfied', result)
        self.assertTrue(result['historical_receipt'])
        self.assertFalse(result['current_scene_revalidated'])
        self.assert_no_new_host_work(counts)
        self.assertAlmostEqual(self.host.actual_gap(), .021, places=11)

    def test_same_request_id_rejects_changed_support_constraint(self):
        self.assert_satisfied(self.run_segment())
        counts = self.host.calls, self.host.captures
        for changes in ({'reference_triangle_index': 3}, {'direction_world': [1., 0., 2.]},
                        {'target_clearance_m': .002}, {'max_steps': 1}):
            result = self.run_segment(request=support_request(**changes))
            self.assertEqual(result['status'], 'request_conflict', result)
            self.assert_no_new_host_work(counts)

    def test_old_and_support_plane_receipts_coexist_after_restart(self):
        self.host = PlaneSegmentHost(flat_scene());self.service=self.new_service()
        old = {'focal_id':'part','reference_id':'base','axis':'+z',
               'target_clearance_m':.001,'clearance_tolerance_m':1e-6}
        self.assert_satisfied(self.run_segment(request=old, request_id='old'))
        self.assert_satisfied(self.run_segment(service=self.new_service(), request_id='new',
            request=support_request(target_clearance_m=.002)), .002)
        state = self.read_state();validate_segment_ledger(state)
        self.assertEqual(set(state['goal_segments']['records']), {'old','new'})
        self.assertNotIn('solver', state['goal_segments']['records']['old']['request'])
        self.assertEqual(state['goal_segments']['records']['new']['request']['solver'], 'support_plane')

    def test_zero_target_and_near_parallel_direction_are_blocked_before_write(self):
        for request in (support_request(target_clearance_m=0),
                        support_request(direction_world=[1.,0.,1e-10])):
            with self.subTest(request=request):
                result = self.run_segment(request=request, request_id='block-'+str(request['target_clearance_m'])+str(request['direction_world'][2]))
                self.assertEqual(result['status'], 'blocked', result)
                self.assertEqual(self.host.calls, 0)

    def test_step_budget_reports_confirmed_partial_progress(self):
        initial = self.host.actual_gap()
        result = self.run_segment(request=support_request(max_step_translation_m=.0008, max_steps=1))
        self.assertEqual(result['status'], 'review_required', result)
        self.assertEqual(self.host.calls, 1)
        self.assertGreater(self.host.actual_gap(), .001+1e-6)
        self.assertLess(self.host.actual_gap(), initial)
        self.assertIsNone(self.read_state()['inflight'])

    def test_total_motion_budget_is_not_replaced_by_net_target_error(self):
        initial = self.host.actual_gap()
        result = self.run_segment(request=support_request(max_total_translation_m=.0008))
        self.assertIn(result['status'], {'blocked','review_required'}, result)
        self.assertLessEqual(initial-self.host.actual_gap(), .0008)
        self.assertGreater(self.host.actual_gap(), .001+1e-6)

    def test_extra_obstacle_is_checked_by_existing_full_scene_gate(self):
        obstacle = host_frame(box('obstacle',[.04,0,.1015],[.01,.02,.001]))
        self.host.scene['meshes'].append(obstacle)
        self.host.scene['host_identity']['object_instances']['obstacle']='instance-obstacle'
        before = self.host.actual_gap()
        result = self.run_segment()
        self.assertEqual(result['status'], 'blocked', result)
        self.assertEqual(self.host.calls, 0)
        self.assertEqual(self.host.actual_gap(), before)
        self.assertFalse(result['task_succeeded'])

    def test_external_geometry_edit_between_confirmed_steps_stops(self):
        def external_edit(host):
            host.scene['meshes'][0]['color_rgb']=[255,0,0]
            host.scene['revision']='r91'
        self.host.change_between_steps=external_edit
        result = self.run_segment(request=support_request(max_step_translation_m=.0008))
        self.assertEqual(result['status'], 'review_required', result)
        self.assertEqual(self.host.calls, 1)

    def test_document_or_object_instance_change_between_steps_stops(self):
        for field in ('document','focal_instance'):
            with self.subTest(field=field):
                self.host=PlaneSegmentHost();self.service=self.new_service()
                # Separate receipt identity keeps previous closed test records.
                def change(host, field=field):
                    if field=='document':host.scene['host_identity']['document_epoch']='different-document'
                    else:host.scene['host_identity']['object_instances']['part']='different-part'
                self.host.change_between_steps=change
                result=self.run_segment(request_id='change-'+field,
                    request=support_request(max_step_translation_m=.0008))
                self.assertEqual(result['status'], 'review_required', result)
                self.assertEqual(self.host.calls, 1)

    def test_partial_submit_or_failed_readback_never_replays_mutation(self):
        for mode in ('partial_failure','readback_failure','incorrect'):
            with self.subTest(mode=mode):
                temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
                self.state_path=Path(temporary.name)/'state.json'
                config=json.loads(self.config_path.read_text(encoding='utf-8'))
                config['state_file']=str(self.state_path)
                self.config_path=Path(temporary.name)/'config.json'
                self.config_path.write_text(json.dumps(config),encoding='utf-8')
                self.host=PlaneSegmentHost();self.host.mode=mode;self.service=self.new_service()
                result=self.run_segment()
                self.assertEqual(result['status'], 'execution_uncertain', result)
                self.assertEqual(self.host.calls, 1)
                self.assertIsNotNone(self.read_state()['inflight'])
                for identity in ('support-1','different-request'):
                    replay=self.run_segment(request_id=identity, service=self.new_service())
                    self.assertIn(replay['status'], {'execution_uncertain','blocked','segment_interrupted'}, replay)
                    self.assertEqual(self.host.calls, 1)

    def test_deadline_expiry_after_capture_prevents_first_commit(self):
        from human_eye_plugin import goal_execution
        clock=SegmentClock();self.host.after_capture=clock.expire
        with patch.object(goal_execution.time,'monotonic',side_effect=clock.monotonic):
            result=self.run_segment()
        self.assertIn(result['status'], {'review_required','blocked'}, result)
        self.assertEqual(self.host.calls, 0)

    def test_deadline_expiring_during_initial_candidate_leaves_no_running_ledger(self):
        from human_eye_plugin import goal_execution
        clock=SegmentClock()
        original=goal_execution.solve_segment_candidate
        def expire_after_solving(*args,**kwargs):
            result=original(*args,**kwargs)
            clock.expire()
            return result
        with patch.object(goal_execution.time,'monotonic',side_effect=clock.monotonic), \
                patch.object(goal_execution,'solve_segment_candidate',side_effect=expire_after_solving):
            result=self.run_segment()
        self.assertEqual(result['status'],'review_required',result)
        self.assertTrue(any(code.startswith('segment_time_budget_exhausted')
                            for code in result['reason_codes']),result)
        self.assertEqual(self.host.calls,0)
        self.assertFalse(self.state_path.exists())

    def test_deadline_after_commit_allows_readback_then_stops_next_step(self):
        from human_eye_plugin import goal_execution
        clock=SegmentClock();self.host.after_mutation=clock.expire
        with patch.object(goal_execution.time,'monotonic',side_effect=clock.monotonic):
            result=self.run_segment(request=support_request(max_step_translation_m=.0008))
        self.assertEqual(result['status'], 'review_required', result)
        self.assertEqual(self.host.calls, 1)
        self.assertGreaterEqual(self.host._first_step_post_captures, 1)
        self.assertIsNone(self.read_state()['inflight'])

    def test_missing_host_identity_does_not_allow_support_plane_commit(self):
        self.host.scene.pop('host_identity')
        result=self.run_segment()
        self.assertEqual(result['status'], 'blocked', result)
        self.assertEqual(self.host.calls, 0)

    def test_support_feature_crossing_is_rejected_without_host_write(self):
        # Increasing the gap along a shallow diagonal exits the explicitly
        # selected finite triangle; a neighboring triangle is not substituted.
        result=self.run_segment(request=support_request(direction_world=[1.,0.,.05],
            target_clearance_m=.006,max_step_translation_m=.2,max_total_translation_m=.2))
        self.assertEqual(result['status'], 'blocked', result)
        self.assertEqual(self.host.calls, 0)

    def test_corrupt_support_request_in_ledger_is_refused_before_host_access(self):
        self.assert_satisfied(self.run_segment())
        baseline=self.read_state();counts=self.host.calls,self.host.captures
        for change in ({'direction_world':[True,0,1]}, {'solver':'unknown'},
                       {'reference_triangle_index':-1}):
            state=copy.deepcopy(baseline)
            state['goal_segments']['records']['support-1']['request'].update(change)
            self.state_path.write_text(json.dumps(state),encoding='utf-8')
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.run_segment(service=self.new_service())
            self.assert_no_new_host_work(counts)

    def test_scene_dependent_invalid_selector_does_not_leave_running_receipt(self):
        for changes in ({'reference_triangle_index':999}, {'focal_id':'missing'},
                        {'reference_id':'missing'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.run_segment(request=support_request(**changes))
            self.assertEqual(self.host.calls, 0)
            self.assertFalse(self.state_path.exists())

    def test_invalid_selector_preserves_existing_state_and_leaves_id_reusable(self):
        self.service.observe('existing',focal_id='part',reference_id='base',include_image=False)
        before=self.state_path.read_bytes()
        with self.assertRaises(ValueError):
            self.run_segment(request=support_request(reference_triangle_index=999))
        self.assertEqual(self.state_path.read_bytes(),before)
        self.assertEqual(self.host.calls,0)
        self.assert_satisfied(self.run_segment())


if __name__=='__main__':unittest.main()
