"""Segment evidence preserves unknowns, bounded identity and real elapsed time."""
import copy
import json
import unittest

from human_eye_plugin.telemetry import (
    MAX_GOAL_SEGMENT_RECORDS, MAX_GOAL_SEGMENT_STEPS, RequestTrace,
    build_goal_step_metrics, summarize_goal_segment_metrics, summarize_traces,
)


class ExistingDiagnosticAnnotationTests(unittest.TestCase):
    def test_current_budget_and_prewrite_annotations_are_retained(self):
        with RequestTrace('transform') as trace:
            self.assertTrue(trace.annotate(request_budget_s=2.5,
                request_budget_scope='service_entry_to_precommit_checkpoints_not_hard_realtime'))
            self.assertTrue(trace.annotate(request_budget_status='expired',
                request_budget_stage='before_atomic_state_write'))
            self.assertTrue(trace.annotate(
                request_budget_enforcement='stopped_after_durable_inflight_commit'))
            self.assertTrue(trace.annotate(mutation_started=False, host_prewrite_refused=True))
        result = trace.record
        self.assertEqual(result['annotations']['request_budget_s'], 2.5)
        self.assertEqual(result['annotations']['request_budget_status'], 'expired')
        self.assertTrue(result['annotations']['host_prewrite_refused'])
        self.assertFalse(result['annotations']['mutation_started'])
        self.assertNotIn('invalid_annotation', result['telemetry_issues'])

    def test_unknown_field_still_rejects_whole_batch_without_payload_leak(self):
        with RequestTrace('transform') as trace:
            self.assertFalse(trace.annotate(host_prewrite_refused=True, prompt='private payload'))
            self.assertFalse(trace.annotate(request_budget_future='private payload'))
        self.assertEqual(trace.record['annotations'], {})
        self.assertNotIn('private payload', json.dumps(trace.record))
        self.assertIn('invalid_annotation', trace.record['telemetry_issues'])

    def test_new_annotation_types_fail_without_raising_or_partial_write(self):
        invalid = [dict(request_budget_s=value) for value in
                   (True, 0, -1, float('nan'), float('inf'), 10 ** 1000, '1')]
        invalid += [dict(host_prewrite_refused=1), dict(request_budget_status='success'),
                    dict(request_budget_stage='\nprivate'), dict(request_budget_scope={}),
                    dict(goal_revision=True), dict(step_index=-1)]
        with RequestTrace('transform') as trace:
            for values in invalid:
                with self.subTest(values=tuple(values)):
                    self.assertFalse(trace.annotate(status='not_written', **values))
        self.assertEqual(trace.record['annotations'], {})

    def test_segment_correlation_does_not_change_request_scope_or_summary(self):
        with RequestTrace('transform', aggregation_key='same-input') as trace:
            self.assertTrue(trace.annotate(segment_id='segment', step_id='step',
                goal_id='goal', goal_revision=0, step_index=0))
        row = trace.record
        self.assertEqual(row['correlation']['segment_id'], 'segment')
        self.assertEqual(row['annotations']['goal_revision'], 0)
        self.assertEqual(row['duration_scope'], 'one_request_attempt_wall_clock')
        self.assertEqual(summarize_traces([row])['groups'][0]['requests']['count'], 1)


class GoalSegmentMetricsTests(unittest.TestCase):
    @staticmethod
    def step(index=0, **changes):
        fields = dict(segment_id='segment', step_id='step-' + str(index), step_index=index,
            operation_id='op-' + str(index), outcome='verified', executed=True,
            execution_verified=True, request_ids=['req-' + str(index)],
            counters={'host_captures': 3, 'host_commits': 1, 'local_corrections': int(index > 0),
                      'rendered_images': 0}, duration_ns=90)
        fields.update(changes)
        return build_goal_step_metrics(**fields)

    def test_replay_is_not_counted_twice_and_wall_time_is_not_sum_of_steps(self):
        first, second = self.step(), self.step(1)
        before = copy.deepcopy([first, second, first])
        result = summarize_goal_segment_metrics([first, second, first], segment_id='segment',
            duration_ns=100, outcome='completed')
        self.assertEqual(result['duration_ns'], 100)
        self.assertEqual(result['unique_steps'], 2)
        self.assertEqual(result['duplicate_step_records'], 1)
        self.assertEqual(result['execution_counts']['confirmed_execution'], 2)
        self.assertEqual(result['counters']['host_captures']['known_value_sum'], 6)
        self.assertEqual(result['counters']['local_corrections']['known_value_sum'], 1)
        self.assertFalse(result['execution_authority'])
        self.assertNotIn('task_succeeded', result)
        self.assertEqual([first, second, first], before)
        json.dumps(result, allow_nan=False)

    def test_unknown_and_known_zero_are_distinct(self):
        uncertain = self.step(executed=None, execution_verified=None, operation_id=None,
            outcome='host_execution_uncertain', counters={'rendered_images': 0})
        result = summarize_goal_segment_metrics([uncertain], segment_id='segment')
        self.assertEqual(result['execution_counts']['execution_unknown'], 1)
        self.assertIsNone(result['counters']['host_commits']['known_value_sum'])
        self.assertFalse(result['counters']['host_commits']['complete_for_recorded_steps'])
        self.assertEqual(result['counters']['rendered_images']['known_value_sum'], 0)
        self.assertTrue(result['counters']['rendered_images']['complete_for_recorded_steps'])
        self.assertIsNone(result['duration_ns'])
        self.assertEqual(result['model_usage']['availability'], 'unknown')

    def test_empty_segment_does_not_infer_capture_or_model_usage_zero(self):
        result = summarize_goal_segment_metrics([], segment_id='segment', duration_ns=0,
            outcome='already_satisfied')
        self.assertEqual(result['unique_steps'], 0)
        self.assertEqual(result['duration_ns'], 0)
        self.assertIsNone(result['counters']['host_captures']['known_value_sum'])
        self.assertFalse(result['counters']['host_captures']['complete_for_recorded_steps'])
        self.assertEqual(result['model_usage']['groups'], [])
        self.assertEqual(result['model_usage']['availability'], 'unknown')

    def test_not_executed_and_executed_unverified_do_not_become_confirmed(self):
        rows = [self.step(executed=False, execution_verified=False, outcome='blocked'),
                self.step(1, execution_verified=False, outcome='readback_failed')]
        counts = summarize_goal_segment_metrics(rows, segment_id='segment')['execution_counts']
        self.assertEqual(counts, {'confirmed_execution': 0, 'not_executed': 1,
            'executed_unverified': 1, 'execution_unknown': 0})

    def test_identity_conflicts_cannot_silently_remove_real_work(self):
        first = self.step()
        conflicts = [self.step(counters={'host_captures': 9}),
            self.step(1, step_index=0), self.step(1, operation_id='op-0'),
            self.step(1, segment_id='other')]
        for conflicting in conflicts:
            with self.subTest(conflicting=conflicting['step_id']), self.assertRaises(ValueError):
                summarize_goal_segment_metrics([first, conflicting], segment_id='segment')

    def test_one_transport_request_can_contain_multiple_local_steps(self):
        rows = [self.step(request_ids=['outer']), self.step(1, request_ids=['outer'])]
        result = summarize_goal_segment_metrics(rows, segment_id='segment')
        self.assertEqual(result['unique_steps'], 2)
        self.assertEqual(result['unique_step_request_ids'], 1)
        self.assertEqual(result['counters']['host_commits']['known_value_sum'], 2)

    def test_bounded_contract_rejects_overflow_and_malformed_inputs(self):
        invalid_steps = [dict(step_index=True), dict(step_index=MAX_GOAL_SEGMENT_STEPS),
            dict(executed=1), dict(executed=None, execution_verified=True),
            dict(counters={'host_commits': -1}), dict(counters={'host_commits': True}),
            dict(counters={'host_commits': 1 << 63}), dict(counters={'mesh': 2}),
            dict(request_ids=['r'] * 33), dict(duration_ns=float('inf'))]
        for values in invalid_steps:
            with self.subTest(values=tuple(values)), self.assertRaises(ValueError):
                self.step(**values)
        for kwargs in (dict(max_steps=0), dict(max_steps=True),
                       dict(max_steps=MAX_GOAL_SEGMENT_STEPS + 1), dict(duration_ns=-1)):
            with self.assertRaises(ValueError):
                summarize_goal_segment_metrics([], segment_id='segment', **kwargs)
        with self.assertRaises(ValueError):
            summarize_goal_segment_metrics([self.step()] * (MAX_GOAL_SEGMENT_RECORDS + 1),
                                           segment_id='segment')
        with self.assertRaises(ValueError):
            summarize_goal_segment_metrics([self.step(1)], segment_id='segment', max_steps=1)

    def test_only_known_step_counters_are_aggregated(self):
        first, second = self.step(), self.step(1, counters={})
        result = summarize_goal_segment_metrics([first, second], segment_id='segment')
        self.assertEqual(result['counters']['host_captures'], {
            'known_value_sum': 3, 'known_steps': 1, 'unknown_steps': 1,
            'complete_for_recorded_steps': False})
        self.assertIn('excludes_unassigned_segment_work', result['counter_scope'])

    @staticmethod
    def usage(**changes):
        value = dict(scope='single_provider_response', provider='provider', model='model',
            source='provider_response', provider_request_id='response', input_tokens=10,
            output_tokens=2, total_tokens=12, total_includes_reasoning=True)
        value.update(changes)
        return value

    def test_usage_deduplicates_provider_identity_without_reconstructing_totals(self):
        usage = self.usage(total_tokens=None)
        result = summarize_goal_segment_metrics([], segment_id='segment',
            model_usage_records=[usage, copy.deepcopy(usage)])['model_usage']
        self.assertEqual(result['identified_responses'], 1)
        self.assertEqual(result['duplicate_records'], 1)
        fields = result['groups'][0]['fields']
        self.assertEqual(fields['input_tokens']['known_value_sum'], 10)
        self.assertIsNone(fields['total_tokens']['known_value_sum'])
        self.assertIsNone(fields['reasoning_tokens']['known_value_sum'])
        self.assertEqual(result['availability'], 'reported')

    def test_unidentified_usage_is_not_double_counted_or_reported_as_zero(self):
        unidentifiable = self.usage(provider_request_id=None)
        result = summarize_goal_segment_metrics([], segment_id='segment',
            model_usage_records=[unidentifiable, unidentifiable])['model_usage']
        self.assertEqual(result['identified_responses'], 0)
        self.assertEqual(result['unidentified_records_not_summed'], 2)
        self.assertEqual(result['groups'], [])
        self.assertEqual(result['availability'], 'unknown')

    def test_same_provider_response_with_conflicting_counts_is_rejected(self):
        with self.assertRaises(ValueError):
            summarize_goal_segment_metrics([], segment_id='segment',
                model_usage_records=[self.usage(), self.usage(input_tokens=11, total_tokens=13)])

    def test_unknown_or_invalid_provider_records_cannot_manufacture_usage(self):
        unknown = self.usage(input_tokens=None, output_tokens=None, total_tokens=None,
                             total_includes_reasoning=None, source='unavailable')
        summary = summarize_goal_segment_metrics([], segment_id='segment',
            model_usage_records=[unknown])['model_usage']
        self.assertEqual(summary['availability'], 'unknown')
        invalid = [self.usage(input_tokens=True), self.usage(source='unavailable'),
            self.usage(total_tokens=999), self.usage(cached_input_tokens=11),
            self.usage(scope='cumulative_session'), self.usage(usage_available=False),
            self.usage(reasoning_semantics='extra_tokens'), self.usage(prompt='private')]
        for row in invalid:
            with self.subTest(row=tuple(row)), self.assertRaises(ValueError):
                summarize_goal_segment_metrics([], segment_id='segment', model_usage_records=[row])


if __name__ == '__main__':
    unittest.main()
