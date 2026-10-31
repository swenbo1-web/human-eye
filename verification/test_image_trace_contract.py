"""Request intent, stage payloads and transport artifacts are distinct facts."""
from concurrent.futures import ThreadPoolExecutor
import copy
import threading
import unittest
from unittest.mock import patch

from human_eye_plugin.auto_router import HumanEyeAutoRouter, _trace_stage
from human_eye_plugin.host_runtime import GuardedHostRuntime
from human_eye_plugin.telemetry import (RequestTrace, annotate, best_effort_trace,
    current_trace, record_image_artifact, record_image_event, set_image_request, summarize_traces)
from verification.test_host_runtime import MutableHost


class ImageTraceContractTests(unittest.TestCase):
    def test_absent_trace_metadata_calls_are_inert(self):
        self.assertFalse(set_image_request(False, source_name='host_hook'))
        self.assertFalse(record_image_event('before_model', False, False))
        self.assertFalse(record_image_artifact('service_result', image_present=False))
        self.assertIsNone(current_trace())

    def test_explicit_request_owner_is_not_a_first_stage_default(self):
        with RequestTrace('request') as trace:
            self.assertTrue(record_image_event('before_model', True, True))
            self.assertNotIn('include_image', trace.record['annotations'])
            self.assertTrue(set_image_request(False, source_name='host_hook'))
            self.assertTrue(record_image_event('before_action', True, False))
        row = trace.record
        self.assertIs(row['annotations']['include_image'], False)
        self.assertEqual(row['annotations']['image_request_source'], 'host_hook')
        self.assertEqual([item['event_include_image'] for item in row['image_events']], [True, True])

    def test_prepare_false_then_readback_true_keeps_outer_true(self):
        with RequestTrace('request') as trace:
            set_image_request(True, source_name='mcp_transport')
            record_image_event('before_model', False, False)
            record_image_event('before_action', True, False)
            record_image_event('after_action', True, True)
        row = trace.record
        self.assertIs(row['annotations']['include_image'], True)
        self.assertEqual([item['event_include_image'] for item in row['image_events']], [False, True, True])
        self.assertNotIn('service_image_present', row['annotations'])
        self.assertNotIn('mcp_native_image_block_count', row['annotations'])

    def test_explicit_unknown_is_not_overwritten_by_nested_defaults(self):
        with RequestTrace('request') as trace:
            self.assertTrue(set_image_request(None, source_name='mcp_transport'))
            record_image_event('before_action', True, False)
            self.assertFalse(set_image_request(True, source_name='service'))
            self.assertFalse(annotate(include_image=True))
        self.assertIsNone(trace.record['annotations']['include_image'])
        self.assertEqual(trace.record['annotations']['image_request_source'], 'mcp_transport')
        self.assertIn('image_request_conflict', trace.record['telemetry_issues'])

    def test_same_request_mode_reentry_retains_outer_owner(self):
        with RequestTrace('request') as trace:
            self.assertTrue(set_image_request(False, source_name='host_hook'))
            self.assertTrue(set_image_request(False, source_name='service'))
            self.assertTrue(annotate(include_image=False, status='preview'))
        self.assertEqual(trace.record['annotations']['image_request_source'], 'host_hook')
        self.assertEqual(trace.record['telemetry_issues'], [])

    def test_legacy_annotations_remain_compatible_until_explicit_owner(self):
        with RequestTrace('legacy') as trace:
            self.assertTrue(annotate(include_image=True))
            self.assertTrue(annotate(include_image=False))
            self.assertNotIn('image_request_source', trace.record['annotations'])
            self.assertTrue(set_image_request(True, source_name='service'))
            self.assertFalse(annotate(include_image=False, status='must_not_partially_apply'))
        self.assertIs(trace.record['annotations']['include_image'], True)
        self.assertNotIn('status', trace.record['annotations'])

    def test_final_artifacts_and_request_intent_are_independent(self):
        with RequestTrace('request') as trace:
            set_image_request(True, source_name='service')
            record_image_artifact('service_result', image_present=False)
            record_image_artifact('mcp_content', native_block_count=0)
        annotations = trace.record['annotations']
        self.assertIs(annotations['include_image'], True)
        self.assertIs(annotations['service_image_present'], False)
        self.assertEqual(annotations['mcp_native_image_block_count'], 0)
        self.assertNotIn('model_consumed_image', annotations)

    def test_unknown_artifact_is_not_known_zero_or_false(self):
        with RequestTrace('request') as trace:
            record_image_artifact('service_result')
            record_image_artifact('mcp_content')
        self.assertIsNone(trace.record['annotations']['service_image_present'])
        self.assertIsNone(trace.record['annotations']['mcp_native_image_block_count'])

    def test_invalid_metadata_never_promotes_private_payload(self):
        with RequestTrace('request') as trace:
            for bad in (0, 1, 'True', {}, []):
                self.assertFalse(set_image_request(bad, source_name='service'))
            self.assertFalse(set_image_request(True, source_name='prompt/private'))
            self.assertFalse(record_image_event('private\ntext', True, False))
            self.assertFalse(record_image_event('before_model', {'private': 'mesh'}, False))
            self.assertFalse(record_image_artifact('service_result', image_present=1))
            for bad in (True, -1, 1.5, {}):
                self.assertFalse(record_image_artifact('mcp_content', native_block_count=bad))
            self.assertFalse(record_image_artifact('unknown_scope', image_present=True))
        self.assertEqual(trace.record['annotations'], {})
        self.assertEqual(trace.record['image_events'], [])
        self.assertNotIn('private', str(trace.record))

    def test_stage_history_is_bounded_with_explicit_truncation(self):
        with RequestTrace('request') as trace:
            set_image_request(False, source_name='host_hook')
            for _ in range(32):
                self.assertTrue(record_image_event('before_model', False, False))
            self.assertFalse(record_image_event('after_action', True, True))
        self.assertEqual(len(trace.record['image_events']), 32)
        self.assertTrue(trace.record['image_events_truncated'])
        self.assertIn('image_events_truncated', trace.record['telemetry_issues'])
        self.assertIs(trace.record['annotations']['event_image_present'], True)
        self.assertIs(trace.record['annotations']['include_image'], False)

    def test_failed_request_has_no_invented_final_artifact(self):
        with self.assertRaisesRegex(RuntimeError, 'business failure'):
            with RequestTrace('request') as trace:
                set_image_request(True, source_name='service')
                record_image_event('before_model', False, False)
                raise RuntimeError('business failure')
        self.assertNotIn('service_image_present', trace.record['annotations'])
        self.assertNotIn('mcp_native_image_block_count', trace.record['annotations'])
        self.assertIsNone(current_trace())

    def test_nested_and_concurrent_requests_keep_ownership_isolated(self):
        with RequestTrace('outer') as outer:
            set_image_request(False, source_name='host_hook')
            with RequestTrace('inner') as inner:
                set_image_request(True, source_name='service')
            self.assertIs(current_trace(), outer)
            self.assertIs(outer.record['annotations']['include_image'], False)
            self.assertIs(inner.record['annotations']['include_image'], True)
        barrier = threading.Barrier(2)
        def worker(mode):
            with RequestTrace('parallel') as trace:
                set_image_request(mode, source_name='service')
                barrier.wait(timeout=5)
                record_image_event('before_action', not mode, False)
            return trace.record
        with ThreadPoolExecutor(max_workers=2) as executor:
            records = list(executor.map(worker, (False, True)))
        self.assertEqual([row['annotations']['include_image'] for row in records], [False, True])

    def test_metadata_implementation_failure_is_best_effort(self):
        with RequestTrace('request'):
            with patch.object(RequestTrace, 'set_image_request', side_effect=OSError('metadata unavailable')):
                self.assertFalse(set_image_request(True, source_name='service'))
            with patch.object(RequestTrace, 'record_image_event', side_effect=OSError('metadata unavailable')):
                self.assertFalse(record_image_event('before_model', True, True))
            with patch.object(RequestTrace, 'record_image_artifact', side_effect=OSError('metadata unavailable')):
                self.assertFalse(record_image_artifact('service_result', image_present=True))

    def test_metadata_envelope_inspection_failure_cannot_prevent_business(self):
        class UnreadableMetadata(dict):
            def get(self, *args, **kwargs):
                raise OSError('metadata inspection unavailable')
        calls = []
        class Pipeline:
            @_trace_stage('router.test', image_event=True)
            def operation(self, event):
                calls.append(event)
                return {'image': None, 'success': True}
        with RequestTrace('request') as trace:
            self.assertTrue(Pipeline().operation(UnreadableMetadata())['success'])
        self.assertEqual(len(calls), 1)
        self.assertIsNone(trace.record['image_events'][0]['event_include_image'])

    def test_malformed_stage_result_is_unknown_not_known_absence(self):
        class Pipeline:
            @_trace_stage('router.test', image_event=True)
            def operation(self, event, result):
                return result
        with RequestTrace('request') as trace:
            for malformed in (None, {'image': 'invalid-image-payload'}):
                Pipeline().operation({'event': 'before_model'}, malformed)
        self.assertEqual([item['image_present'] for item in trace.record['image_events']], [None, None])

    @staticmethod
    def event(scene, **changes):
        value = {'event': 'before_model', 'session_id': 's', 'scene': scene,
                 'focal_id': 'part', 'reference_id': 'base', 'task_kind': 'spatial_3d',
                 'task_instruction': 'Measure the clearance.'}
        value.update(changes)
        return value

    def test_real_router_before_action_default_cannot_change_text_request(self):
        router = HumanEyeAutoRouter(quad_size=64)
        scene = MutableHost().scene
        with RequestTrace('hook.preview') as trace:
            set_image_request(False, source_name='host_hook')
            prepared = router.handle_event(self.event(scene, include_image=False))
            checked = router.handle_event({'event': 'before_action', 'session_id': 's',
                'focal_id': 'part', 'reference_id': 'base',
                'observation_id': prepared['observation_id'], 'action': {'translation': [0, 0, .01]}})
        self.assertTrue(checked['allow_action'], checked)
        self.assertEqual([row['event_include_image'] for row in trace.record['image_events']], [False, True])
        self.assertIs(trace.record['annotations']['include_image'], False)
        self.assertFalse(any(row['name'].startswith('render.') for row in trace.record['spans']))

    def test_real_runtime_false_preparation_then_true_readback_is_one_request(self):
        host = MutableHost()
        runtime = GuardedHostRuntime(host, quad_size=64)
        with RequestTrace('transform') as trace:
            set_image_request(True, source_name='service')
            runtime.before_model(session_id='s', task_instruction='Measure the clearance.',
                focal_id='part', reference_id='base', messages=[], format='mcp',
                include_image=False, supports_images=False, final_include_image=True)
            result = runtime.execute_action(session_id='s', action={'translation': [0, 0, .01]})
        self.assertEqual(result['status'], 'verified', result)
        self.assertEqual(host.calls, 1)
        self.assertEqual([row['event_include_image'] for row in trace.record['image_events']], [False, True, True])
        self.assertEqual([row['image_present'] for row in trace.record['image_events']], [False, False, True])
        self.assertIs(trace.record['annotations']['include_image'], True)
        self.assertNotIn('service_image_present', trace.record['annotations'])

    def test_router_alone_does_not_guess_request_mode(self):
        router = HumanEyeAutoRouter(quad_size=64)
        with RequestTrace('sdk') as trace:
            result = router.handle_event(self.event(MutableHost().scene, include_image=False))
        self.assertEqual(result['route'], 'engine')
        self.assertNotIn('include_image', trace.record['annotations'])
        self.assertIs(trace.record['annotations']['event_include_image'], False)

    def test_cache_payload_presence_is_not_new_rendering(self):
        router = HumanEyeAutoRouter(quad_size=64, clock=lambda: 5.0)
        event = self.event(MutableHost().scene, include_image=True)
        router.handle_event(event)
        with RequestTrace('observe') as trace:
            set_image_request(True, source_name='direct_router')
            result = router.handle_event(event)
        self.assertTrue(result['cache_hit'], result)
        self.assertIsInstance(result['image'], dict)
        self.assertIs(trace.record['image_events'][0]['image_present'], True)
        names = [row['name'] for row in trace.record['spans']]
        self.assertNotIn('encoding.png', names)
        self.assertNotIn('render.scene_canvas', names)

    def test_render_failure_returns_measured_result_with_no_image(self):
        router = HumanEyeAutoRouter(quad_size=64)
        with RequestTrace('observe') as trace:
            set_image_request(True, source_name='direct_router')
            with patch('human_eye_plugin.auto_router._render_scene_canvas_prepared', side_effect=ValueError('render unavailable')):
                result = router.handle_event(self.event(MutableHost().scene, include_image=True))
        self.assertEqual(result['route'], 'engine', result)
        self.assertTrue(result['measurement_valid'])
        self.assertIsNone(result['image'])
        self.assertIs(trace.record['image_events'][0]['image_present'], False)
        self.assertIs(trace.record['annotations']['include_image'], True)

    def test_invalid_router_call_records_unknown_not_fabricated_absence(self):
        router = HumanEyeAutoRouter(quad_size=64)
        with RequestTrace('observe') as trace:
            set_image_request(None, source_name='service')
            with self.assertRaises(ValueError):
                router.handle_event(self.event(MutableHost().scene, include_image=None))
        self.assertIsNone(trace.record['image_events'][0]['event_include_image'])
        self.assertIsNone(trace.record['image_events'][0]['image_present'])

    def test_router_metadata_and_trace_writer_failure_do_not_change_mutation(self):
        host = MutableHost()
        runtime = GuardedHostRuntime(host, quad_size=64)
        with best_effort_trace('transform', writer=lambda row: (_ for _ in ()).throw(OSError('writer unavailable'))):
            set_image_request(False, source_name='service')
            with patch('human_eye_plugin.auto_router._image_event', side_effect=OSError('image tracing unavailable')):
                runtime.before_model(session_id='s', task_instruction='Measure the clearance.',
                    focal_id='part', reference_id='base', messages=[], format='mcp',
                    include_image=False, supports_images=False, final_include_image=False)
                result = runtime.execute_action(session_id='s', action={'translation': [0, 0, .01]})
        self.assertEqual(result['status'], 'verified', result)
        self.assertEqual(host.calls, 1)
        self.assertIsNone(current_trace())

    def test_analyzer_separates_builds_owners_and_legacy_without_rewriting(self):
        with RequestTrace('observe', aggregation_key='same', implementation_revision='v1') as trace:
            set_image_request(False, source_name='service')
            annotate(build_id='sha256:build-a')
        original = trace.record
        records = [copy.deepcopy(original) for _ in range(5)]
        for index, row in enumerate(records):
            row['trace_id'] = str(index)
        records[1]['annotations']['build_id'] = 'sha256:build-b'
        records[2]['annotations']['image_request_source'] = 'host_hook'
        for key in ('image_request_source', 'image_request_scope'):
            records[3]['annotations'].pop(key)
            records[4]['annotations'].pop(key)
        records[4]['annotations'].pop('include_image')
        unchanged = copy.deepcopy(records)
        groups = summarize_traces(records)['groups']
        self.assertEqual(len(groups), 5)
        self.assertEqual(records, unchanged)
        identities = [group['identity'] for group in groups]
        self.assertEqual(identities[3]['image_request_source'], 'legacy_annotation_unowned')
        self.assertIs(identities[3]['include_image'], False)
        self.assertEqual(identities[4]['image_request_source'], 'unknown')
        self.assertIsNone(identities[4]['include_image'])


if __name__ == '__main__':
    unittest.main()
