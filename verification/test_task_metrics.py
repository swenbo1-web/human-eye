"""Task-run evidence cannot turn overlapping traces or receipts into gains."""
import copy
import json
import unittest

from human_eye_plugin.task_metrics import (
    MAX_TASK_SPANS, MAX_TASK_TRACES, MAX_TASK_USAGE_RECORDS, summarize_task_run,
)
from human_eye_plugin.telemetry import RequestTrace, span as trace_span


class TaskRunMetricsTests(unittest.TestCase):
    @staticmethod
    def trace(name='one', **changes):
        # Use the actual trace constructor's data shape, without timing or
        # executing a model/host operation. Fixtures declare their own run IDs.
        row = RequestTrace('mcp.observe', request_id='request-' + name).record
        row.update(trace_id='trace-' + name, duration_ns=100, outcome='observed')
        row['correlation'].update(task_id='task', task_run_id='run')
        row.update(changes)
        return row

    @staticmethod
    def span(name='host.capture', identity='span-one', **changes):
        value = {'span_id': identity, 'parent_span_id': None, 'name': name, 'kind': 'host',
            'source_name': 'host_blender', 'start_offset_ns': 0, 'duration_ns': 50,
            'outcome': 'completed', 'error_type': None, 'thread_id': 1,
            'timing_semantics': 'inclusive_wall_clock'}
        value.update(changes)
        return value

    @staticmethod
    def usage(identity='provider-reply', **changes):
        value = {'scope': 'single_provider_response', 'provider': 'provider', 'model': 'model',
            'source': 'provider_response', 'provider_request_id': identity,
            'input_tokens': 10, 'output_tokens': 2, 'total_tokens': 12,
            'total_includes_reasoning': True}
        value.update(changes)
        return value

    def summary(self, rows, **changes):
        return summarize_task_run(rows, task_id='task', task_run_id='run', **changes)

    def test_repeated_logs_count_once_and_whole_task_clock_is_independent(self):
        first, second = self.trace(), self.trace('two', duration_ns=200)
        original = copy.deepcopy([first, second, first])
        result = self.summary([first, second, first], duration_ns=900,
                              expected_request_ids=['request-one', 'request-two'])
        self.assertEqual(result['duration_ns'], 900)
        self.assertEqual(result['unique_traces'], 2)
        self.assertEqual(result['duplicate_trace_records'], 1)
        self.assertEqual(result['outer_request_attempts'], 2)
        self.assertTrue(result['coverage']['complete_against_declared_requests'])
        self.assertEqual([first, second, first], original)
        self.assertFalse(result['execution_authority'])
        self.assertIsNone(result['goal_completion_count'])
        json.dumps(result, allow_nan=False)

    def test_missing_task_clock_is_not_reconstructed_from_requests_or_segments(self):
        rows = [self.trace(operation='mcp.clearance_segment', duration_ns=700),
                self.trace('two', operation='mcp.clearance_segment', duration_ns=900)]
        result = self.summary(rows)
        self.assertIsNone(result['duration_ns'])
        self.assertEqual(result['duration_source'], 'unknown')
        self.assertEqual(result['timing_policy'], 'never_sum_request_segment_or_nested_span_durations')
        self.assertIsNone(result['coverage']['expected_outer_request_ids'])
        self.assertFalse(result['coverage']['complete_against_declared_requests'])

    def test_child_trace_is_diagnostic_not_an_extra_outer_request(self):
        outer = self.trace(spans=[self.span()])
        child = self.trace('child', parent_trace_id=outer['trace_id'], parent_span_id='span-one',
                           duration_ns=40, spans=[self.span('host.mutation', 'span-child')])
        result = self.summary([outer, child], duration_ns=110,
                              expected_request_ids=['request-one'])
        self.assertEqual(result['unique_traces'], 2)
        self.assertEqual(result['outer_request_attempts'], 1)
        self.assertEqual(result['nested_traces'], 1)
        self.assertEqual(len(result['root_requests']), 1)
        self.assertEqual(result['duration_ns'], 110)
        self.assertTrue(result['coverage']['complete_against_declared_requests'])
        self.assertEqual(result['span_evidence']['host_apply_call_spans']['observed_call_spans'], 1)

    def test_orphan_child_does_not_become_an_apparent_root(self):
        row = self.trace('child', parent_trace_id='absent-parent')
        result = self.summary([row], expected_request_ids=[])
        self.assertEqual(result['outer_request_attempts'], 0)
        self.assertEqual(result['coverage']['orphan_trace_ids'], ['trace-child'])
        self.assertFalse(result['coverage']['complete_against_declared_requests'])

    def test_missing_and_unexpected_requests_are_preserved_in_coverage(self):
        result = self.summary([self.trace()], expected_request_ids=['expected-other'])
        self.assertEqual(result['outer_request_attempts'], 1)
        self.assertEqual(result['coverage']['missing_request_ids'], ['expected-other'])
        self.assertEqual(result['coverage']['unexpected_request_ids'], ['request-one'])
        self.assertFalse(result['coverage']['complete_against_declared_requests'])

    def test_unfinished_trace_span_or_instrumentation_issue_prevents_complete_claim(self):
        variants = [self.trace(duration_ns=None),
                    self.trace(spans=[self.span(duration_ns=None, outcome='running')]),
                    self.trace(telemetry_issues=['writer_failed'])]
        for row in variants:
            with self.subTest(trace=row['trace_id']):
                result = self.summary([row], expected_request_ids=['request-one'])
                self.assertFalse(result['coverage']['complete_against_declared_requests'])

    def test_conflicting_trace_or_request_attempt_id_is_rejected(self):
        first = self.trace()
        for second in (self.trace(duration_ns=101), self.trace('two', request_id='request-one')):
            with self.assertRaises(ValueError):
                self.summary([first, second])

    def test_different_run_or_missing_task_binding_is_never_silently_pooled(self):
        for correlation in ({}, {'task_id': 'task', 'task_run_id': 'another'},
                            {'task_id': 'another', 'task_run_id': 'run'}):
            with self.assertRaises(ValueError):
                self.summary([self.trace(correlation=correlation)])

    def test_parent_cycles_and_nested_manifest_ids_are_rejected(self):
        with self.assertRaises(ValueError):
            self.summary([self.trace(parent_trace_id='trace-one')])
        with self.assertRaises(ValueError):
            self.summary([self.trace(parent_trace_id='trace-two'),
                          self.trace('two', parent_trace_id='trace-one')])
        with self.assertRaises(ValueError):
            self.summary([self.trace(), self.trace('child', parent_trace_id='trace-one')],
                         expected_request_ids=['request-one', 'request-child'])

    def test_retries_are_new_attempts_not_identical_successes(self):
        first = self.trace(outcome='error')
        retry = self.trace('retry', attempt_index=1, retry_of_request_id='request-one')
        result = self.summary([first, retry])
        self.assertEqual(result['outer_request_attempts'], 2)
        self.assertEqual(result['outer_request_counts_by_outcome'], {'error': 1, 'observed': 1})
        self.assertIsNone(result['goal_completion_count'])

    def test_receipt_replay_does_not_create_host_calls_or_goal_completion(self):
        row = self.trace(outcome='satisfied', annotations={
            'receipt_replayed': True, 'historical_receipt': True, 'task_succeeded': True})
        result = self.summary([row])
        self.assertEqual(result['receipt_replayed_outer_requests'], 1)
        self.assertEqual(result['historical_receipt_outer_requests'], 1)
        self.assertEqual(result['span_evidence']['host_apply_call_spans']['observed_call_spans'], 0)
        self.assertIsNone(result['goal_completion_count'])

    def test_completed_apply_call_including_prewrite_refusal_is_not_a_commit_count(self):
        row = self.trace(outcome='blocked', annotations={'host_prewrite_refused': True},
                         spans=[self.span('host.mutation')])
        result = self.summary([row])
        apply = result['span_evidence']['host_apply_call_spans']
        self.assertEqual(apply['completed_spans'], 1)
        self.assertNotIn('successful_commits', result)
        self.assertIn('not_confirmed_mutations', result['span_evidence']['apply_semantics'])

    def test_span_identity_deduplicates_and_wrapper_names_are_not_capture_calls(self):
        capture = self.span()
        rows = [self.trace(spans=[capture, copy.deepcopy(capture),
                                self.span('host.before_model', 'wrapper')])]
        result = self.summary(rows)
        self.assertEqual(result['span_evidence']['unique_spans'], 2)
        self.assertEqual(result['span_evidence']['duplicate_span_records'], 1)
        self.assertEqual(result['span_evidence']['host_capture_call_spans']['observed_call_spans'], 1)
        with self.assertRaises(ValueError):
            self.summary([self.trace(spans=[capture, self.span(duration_ns=51)])])

    def test_identical_span_cannot_be_copied_into_a_different_trace(self):
        capture = self.span()
        for parent in (None, 'trace-one'):
            rows = [self.trace(spans=[capture]),
                    self.trace('child', parent_trace_id=parent, spans=[copy.deepcopy(capture)])]
            for order in (rows, list(reversed(rows))):
                with self.subTest(parent=parent, first=order[0]['trace_id']):
                    with self.assertRaisesRegex(ValueError, 'two traces'):
                        self.summary(order)

    def test_span_missing_parent_is_explicitly_incomplete(self):
        row = self.trace(spans=[self.span(parent_span_id='unreported-span')])
        result = self.summary([row], expected_request_ids=['request-one'])
        self.assertEqual(result['coverage']['orphan_span_ids'], ['span-one'])
        self.assertEqual(result['coverage']['orphan_trace_ids'], [])
        self.assertFalse(result['coverage']['complete_against_declared_requests'])
        # The visible call remains observable evidence, but cannot certify
        # that its trace graph is complete.
        self.assertEqual(result['span_evidence']['host_capture_call_spans']['observed_call_spans'], 1)

    def test_span_parent_cannot_cross_trace_boundary(self):
        outer = self.trace(spans=[self.span(identity='outer-span')])
        child = self.trace('child', parent_trace_id='trace-one', parent_span_id='outer-span',
            spans=[self.span(identity='child-span', parent_span_id='outer-span')])
        for rows in ([outer, child], [child, outer]):
            with self.assertRaisesRegex(ValueError, 'same owning trace'):
                self.summary(rows, expected_request_ids=['request-one'])

    def test_self_and_longer_span_parent_cycles_are_rejected(self):
        variants = [
            [self.span(parent_span_id='span-one')],
            [self.span(identity='a', parent_span_id='b'),
             self.span(identity='b', parent_span_id='a')],
            [self.span(identity='c', parent_span_id='a'),
             self.span(identity='a', parent_span_id='b'),
             self.span(identity='b', parent_span_id='c')],
        ]
        for spans in variants:
            with self.subTest(span_count=len(spans)):
                with self.assertRaisesRegex(ValueError, 'Cyclic span'):
                    self.summary([self.trace(spans=spans)], expected_request_ids=['request-one'])

    def test_child_trace_missing_declared_parent_span_is_incomplete(self):
        child = self.trace('child', parent_trace_id='trace-one', parent_span_id='missing-span')
        for rows in ([self.trace(), child], [child]):
            result = self.summary(rows, expected_request_ids=['request-one'])
            self.assertEqual(result['coverage']['trace_ids_with_missing_parent_spans'], ['trace-child'])
            self.assertEqual(result['coverage']['orphan_trace_ids'], [] if len(rows) == 2 else ['trace-child'])
            self.assertFalse(result['coverage']['complete_against_declared_requests'])

    def test_child_trace_parent_span_must_belong_to_immediate_parent(self):
        outer = self.trace(spans=[self.span(identity='outer-span')])
        middle = self.trace('middle', parent_trace_id='trace-one', parent_span_id='outer-span',
                            spans=[self.span(identity='middle-span')])
        for foreign_span in ('outer-span', 'child-span'):
            child = self.trace('child', parent_trace_id='trace-middle', parent_span_id=foreign_span,
                               spans=[self.span(identity='child-span')])
            with self.subTest(parent_span=foreign_span):
                with self.assertRaisesRegex(ValueError, 'actual parent trace'):
                    self.summary([child, middle, outer], expected_request_ids=['request-one'])

    def test_root_trace_cannot_claim_a_parent_span_without_parent_trace(self):
        with self.assertRaisesRegex(ValueError, 'outer trace'):
            self.summary([self.trace(parent_span_id='span-one', spans=[self.span()])],
                         expected_request_ids=['request-one'])

    def test_actual_nested_trace_records_have_valid_ownership_without_double_counting(self):
        rows = []
        with RequestTrace('mcp.observe', request_id='outer', writer=rows.append) as outer:
            outer.annotate(task_id='task', task_run_id='run')
            with trace_span('host.capture', kind='host'):
                with RequestTrace('provider.child', request_id='child', writer=rows.append) as child:
                    child.annotate(task_id='task', task_run_id='run')
                    with trace_span('host.mutation', kind='host'):
                        pass
        # Actual records arrive child-first. Child-local root spans have no
        # local parent; the child trace itself links to the outer capture span.
        result = self.summary(rows, expected_request_ids=['outer'])
        self.assertTrue(result['coverage']['complete_against_declared_requests'])
        self.assertEqual(result['outer_request_attempts'], 1)
        self.assertEqual(result['span_evidence']['unique_spans'], 2)
        self.assertEqual(result['span_evidence']['host_capture_call_spans']['observed_call_spans'], 1)
        self.assertEqual(result['span_evidence']['host_apply_call_spans']['observed_call_spans'], 1)

    def test_long_valid_span_chain_is_order_independent_and_does_not_sum_durations(self):
        spans = [self.span(identity='s-' + str(i),
                           parent_span_id='s-' + str(i - 1) if i else None) for i in range(1100)]
        row = self.trace(spans=list(reversed(spans)))
        original = copy.deepcopy(row)
        result = self.summary([row], duration_ns=123, expected_request_ids=['request-one'])
        self.assertTrue(result['coverage']['complete_against_declared_requests'])
        self.assertEqual(result['span_evidence']['unique_spans'], 1100)
        self.assertEqual(result['duration_ns'], 123)
        self.assertEqual(row, original)

    def test_task_labels_share_service_utf8_and_length_validation(self):
        for field in ('task_id', 'task_run_id'):
            for invalid in ('\ud800', '\udfff', 'x' * 129, '', ' ', '\n', None, 1):
                labels = {'task_id': 'task', 'task_run_id': 'run', field: invalid}
                with self.subTest(field=field, invalid=repr(invalid)):
                    with self.assertRaises(ValueError):
                        summarize_task_run([], **labels)
        result = summarize_task_run([], task_id='任务🧪', task_run_id='轮次一', expected_request_ids=[])
        self.assertEqual(result['task_id'], '任务🧪')
        self.assertEqual(result['task_run_id'], '轮次一')

    def test_provider_receipts_deduplicate_across_trace_and_external_inputs(self):
        usage = self.usage()
        rows = [self.trace(usage=[usage]), self.trace('child', parent_trace_id='trace-one',
                                                    usage=[copy.deepcopy(usage)])]
        result = self.summary(rows, provider_usage_records=[copy.deepcopy(usage)])['model_usage']
        self.assertEqual(result['identified_responses'], 1)
        self.assertEqual(result['duplicate_records'], 2)
        self.assertEqual(result['groups'][0]['fields']['input_tokens']['known_value_sum'], 10)

    def test_conflicting_provider_reply_or_unknown_usage_remains_honest(self):
        with self.assertRaises(ValueError):
            self.summary([self.trace(usage=[self.usage()])],
                         provider_usage_records=[self.usage(input_tokens=11, total_tokens=13)])
        unknown = self.summary([self.trace()])['model_usage']
        self.assertEqual(unknown['availability'], 'unknown')
        self.assertEqual(unknown['groups'], [])
        unidentified = self.summary([self.trace(usage=[self.usage(identity=None)])])['model_usage']
        self.assertEqual(unidentified['availability'], 'unknown')
        self.assertEqual(unidentified['identified_responses'], 0)

    def test_malformed_nonfinite_or_over_budget_inputs_fail_without_mutating_evidence(self):
        row = self.trace()
        original = copy.deepcopy(row)
        invalid_rows = [self.trace(duration_ns=True), self.trace(clock='wall_clock'),
            self.trace(annotations={'receipt_replayed': 'yes'}), self.trace(usage={}),
            self.trace(spans=[self.span(duration_ns=-1)]), self.trace(spans=[{}]),
            self.trace(annotations={'bad': float('nan')}),
            self.trace(spans=[self.span()] * (MAX_TASK_SPANS + 1))]
        missing = self.trace()
        missing.pop('parent_trace_id')
        invalid_rows.append(missing)
        missing = self.trace()
        missing.pop('parent_span_id')
        invalid_rows.append(missing)
        for malformed in invalid_rows:
            with self.assertRaises(ValueError):
                self.summary([malformed])
        with self.assertRaises(ValueError):
            self.summary([row] * (MAX_TASK_TRACES + 1))
        with self.assertRaises(ValueError):
            self.summary([], provider_usage_records=[self.usage()] * (MAX_TASK_USAGE_RECORDS + 1))
        with self.assertRaises(ValueError):
            self.summary([], expected_request_ids=['one', 'one'])
        for invalid in (True, -1, float('inf')):
            with self.assertRaises(ValueError):
                self.summary([], duration_ns=invalid)
        self.assertEqual(row, original)


if __name__ == '__main__':
    unittest.main()
