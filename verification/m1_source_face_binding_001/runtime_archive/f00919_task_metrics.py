"""Pure, bounded reconciliation of request evidence for one declared task run.

Task IDs correlate caller-supplied evidence; they do not identify a trusted
human or confer execution authority. Whole-task wall time must come from an
independent elapsed timer, never request, segment or nested-span addition.
"""
from __future__ import annotations

import hashlib
import json

from .telemetry import SCHEMA_VERSION, _bounded_metric_counter, _identifier, _segment_usage_summary
from .request_context import validate_task_context


MAX_TASK_TRACES = 256
MAX_TASK_USAGE_RECORDS = 256
MAX_TASK_SPANS = 4096
MAX_TASK_TRACE_BYTES = 8 * 1024 * 1024
_CAPTURE_SPANS = frozenset({'host.capture', 'host.capture_before_action',
    'host.readback_capture', 'host.capture_preview', 'host.segment_capture'})


def _record_list(value, field, limit):
    if not isinstance(value, (list, tuple)) or len(value) > limit:
        raise ValueError(field + ' must be a bounded list or tuple')
    return value


def _fingerprint(record):
    try:
        encoded = json.dumps(record, ensure_ascii=True, sort_keys=True,
                             separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, RecursionError) as exc:
        raise ValueError('Trace evidence must be finite JSON data') from exc
    if len(encoded) > MAX_TASK_TRACE_BYTES:
        raise ValueError('Task trace evidence exceeds the byte budget')
    return hashlib.sha256(encoded).hexdigest(), len(encoded)


def summarize_task_run(traces, *, task_id, task_run_id, duration_ns=None,
                       expected_request_ids=None, provider_usage_records=()):
    """Reconcile one task run without inferring completion, authority or fees.

    ``expected_request_ids`` optionally lists all outer request-attempt IDs.
    Child traces do not count as additional outer requests. Missing parents
    remain orphans, not apparent roots. Request retries require distinct
    attempt IDs. Duplicate trace/provider IDs and repeated spans within the
    same trace are counted once only when their contents agree. A span ID has
    exactly one owning trace; contradictory ownership or cyclic parentage is
    rejected. Missing parent evidence is reported as incomplete coverage.

    The explicit external usage list must contain ordinary RequestTrace usage
    records selected by the caller for this run. Unknown or unidentified usage
    is never treated as zero. Coverage describes supplied records, not proof
    that every model call or physical host operation has been captured.
    """
    context = validate_task_context({'task_id': task_id, 'task_run_id': task_run_id})
    task_id, task_run_id = context['task_id'], context['task_run_id']
    duration_ns = _bounded_metric_counter(duration_ns, 'duration_ns')
    _record_list(traces, 'traces', MAX_TASK_TRACES)
    _record_list(provider_usage_records, 'provider_usage_records', MAX_TASK_USAGE_RECORDS)
    expected = None
    if expected_request_ids is not None:
        _record_list(expected_request_ids, 'expected_request_ids', MAX_TASK_TRACES)
        expected = [_identifier(value, 'expected_request_id', optional=False)
                    for value in expected_request_ids]
        if len(set(expected)) != len(expected):
            raise ValueError('Expected outer request IDs must be unique')
        expected = set(expected)

    unique, digests, request_owners, spans = {}, {}, {}, {}
    usage, duplicate_traces, duplicate_spans, total_bytes = [], 0, 0, 0
    issue_traces = []
    for record in traces:
        required = {'schema_version', 'trace_id', 'request_id', 'parent_trace_id', 'parent_span_id', 'scope',
            'operation', 'duration_ns', 'duration_scope', 'clock', 'outcome', 'correlation',
            'annotations', 'usage', 'spans'}
        if (not isinstance(record, dict) or not required.issubset(record)
                or record.get('schema_version') != SCHEMA_VERSION):
            raise ValueError('Unsupported request trace schema')
        trace_id = _identifier(record.get('trace_id'), 'trace_id', optional=False)
        request_id = _identifier(record.get('request_id'), 'request_id', optional=False)
        correlation = record.get('correlation')
        annotations = record.get('annotations')
        if not isinstance(correlation, dict) or not isinstance(annotations, dict):
            raise ValueError('Request trace correlation and annotations must be objects')
        if correlation.get('task_id') != task_id or correlation.get('task_run_id') != task_run_id:
            raise ValueError('Request trace is not bound to this exact task run')
        if (record.get('scope') not in ('engine_request', 'provider_request', 'benchmark_request')
                or record.get('duration_scope') != 'one_request_attempt_wall_clock'
                or record.get('clock') != 'perf_counter_ns'):
            raise ValueError('Unsupported trace timing scope')
        _identifier(record.get('operation'), 'operation', optional=False)
        _identifier(record.get('outcome'), 'outcome', optional=False)
        parent = _identifier(record.get('parent_trace_id'), 'parent_trace_id')
        parent_span = _identifier(record.get('parent_span_id'), 'parent_span_id')
        if parent == trace_id:
            raise ValueError('Trace cannot parent itself')
        if parent is None and parent_span is not None:
            raise ValueError('An outer trace cannot reference a parent span')
        _bounded_metric_counter(record.get('duration_ns'), 'trace duration_ns')
        for key in ('receipt_replayed', 'historical_receipt'):
            if key in annotations and type(annotations[key]) is not bool:
                raise ValueError(key + ' must be a boolean when reported')
        raw_usage = _record_list(record.get('usage'), 'trace usage', MAX_TASK_USAGE_RECORDS)
        raw_spans = _record_list(record.get('spans'), 'trace spans', MAX_TASK_SPANS)
        issues = _record_list(record.get('telemetry_issues', []), 'telemetry_issues', 32)
        if any(not isinstance(issue, str) for issue in issues):
            raise ValueError('Telemetry issues must be strings')
        digest, size = _fingerprint(record)
        total_bytes += size
        if total_bytes > MAX_TASK_TRACE_BYTES:
            raise ValueError('Task trace evidence exceeds the byte budget')
        if trace_id in unique:
            if digests[trace_id] != digest:
                raise ValueError('Conflicting duplicate trace identity')
            duplicate_traces += 1
            continue
        if request_id in request_owners:
            raise ValueError('One request-attempt ID cannot identify two traces')
        request_owners[request_id] = trace_id
        unique[trace_id], digests[trace_id] = record, digest
        if issues:
            issue_traces.append(trace_id)
        usage.extend(raw_usage)
        if len(usage) + len(provider_usage_records) > MAX_TASK_USAGE_RECORDS:
            raise ValueError('Task usage records exceed the bounded reconciliation limit')
        for item in raw_spans:
            span_fields = {'span_id', 'parent_span_id', 'name', 'kind', 'outcome',
                           'timing_semantics', 'start_offset_ns', 'duration_ns'}
            if not isinstance(item, dict) or not span_fields.issubset(item):
                raise ValueError('Span evidence must be an object')
            span_id = _identifier(item.get('span_id'), 'span_id', optional=False)
            _identifier(item.get('parent_span_id'), 'parent_span_id')
            _identifier(item.get('name'), 'span name', optional=False)
            _identifier(item.get('kind'), 'span kind', optional=False)
            _identifier(item.get('outcome'), 'span outcome', optional=False)
            if item.get('timing_semantics') != 'inclusive_wall_clock':
                raise ValueError('Unsupported span timing semantics')
            _bounded_metric_counter(item.get('start_offset_ns'), 'span start_offset_ns', optional=False)
            _bounded_metric_counter(item.get('duration_ns'), 'span duration_ns')
            span_digest, _ = _fingerprint(item)
            if span_id in spans:
                if spans[span_id][2] != trace_id:
                    raise ValueError('One span ID cannot belong to two traces')
                if spans[span_id][1] != span_digest:
                    raise ValueError('Conflicting duplicate span identity')
                duplicate_spans += 1
                continue
            spans[span_id] = (item, span_digest, trace_id)
            if len(spans) > MAX_TASK_SPANS:
                raise ValueError('Task spans exceed the bounded reconciliation limit')

    # Validate the complete supplied parent graph before classifying roots.
    for trace_id in unique:
        trail, current = set(), trace_id
        while current in unique:
            if current in trail:
                raise ValueError('Cyclic trace parent graph')
            trail.add(current)
            current = unique[current].get('parent_trace_id')
    roots = [row for row in unique.values() if row.get('parent_trace_id') is None]
    children = [row for row in unique.values() if row.get('parent_trace_id') is not None]
    orphans = [row['trace_id'] for row in children if row['parent_trace_id'] not in unique]
    # A nested span belongs to its enclosing trace. Crossing a request boundary
    # is represented by the child trace's parent_span_id, never by copying a
    # parent's span or attaching a child's local span to another trace's span.
    orphan_spans = []
    for span_id, (item, _, owner) in spans.items():
        parent_span = item['parent_span_id']
        if parent_span is None:
            continue
        if parent_span not in spans:
            orphan_spans.append(span_id)
        elif spans[parent_span][2] != owner:
            raise ValueError('A span parent must belong to the same owning trace')
    resolved_spans = set()
    for span_id in spans:
        trail, current = set(), span_id
        while current in spans and current not in resolved_spans:
            if current in trail:
                raise ValueError('Cyclic span parent graph')
            trail.add(current)
            current = spans[current][0]['parent_span_id']
        resolved_spans.update(trail)
    missing_trace_parent_spans = []
    for row in children:
        parent_span = row['parent_span_id']
        if parent_span is None:
            continue
        if parent_span not in spans:
            missing_trace_parent_spans.append(row['trace_id'])
        elif spans[parent_span][2] != row['parent_trace_id']:
            raise ValueError('A child trace parent span must belong to its actual parent trace')
    actual_root_ids = {row['request_id'] for row in roots}
    nested_ids = {row['request_id'] for row in children}
    if expected is not None and expected & nested_ids:
        raise ValueError('Expected request manifest must identify outer requests only')
    missing = None if expected is None else sorted(expected - actual_root_ids)
    unexpected = None if expected is None else sorted(actual_root_ids - expected)
    unfinished = sorted(row['trace_id'] for row in unique.values() if row['duration_ns'] is None)
    unfinished_spans = sorted(key for key, (item, _, _) in spans.items() if item['duration_ns'] is None)
    counts_by_operation, counts_by_outcome = {}, {}
    root_rows = []
    for row in roots:
        operation, outcome = row['operation'], row['outcome']
        counts_by_operation[operation] = counts_by_operation.get(operation, 0) + 1
        counts_by_outcome[outcome] = counts_by_outcome.get(outcome, 0) + 1
        annotations = row['annotations']
        root_rows.append({'trace_id': row['trace_id'], 'request_id': row['request_id'],
            'operation': operation, 'outcome': outcome, 'duration_ns': row['duration_ns'],
            'receipt_replayed': annotations.get('receipt_replayed'),
            'historical_receipt': annotations.get('historical_receipt')})

    def span_counts(names):
        matching = [item for item, _, _ in spans.values() if item['name'] in names and item['kind'] == 'host']
        return {'observed_call_spans': len(matching),
            'completed_spans': sum(item['outcome'] == 'completed' and item['duration_ns'] is not None
                                   for item in matching),
            'error_spans': sum(item['outcome'] == 'error' for item in matching),
            'unfinished_spans': sum(item['duration_ns'] is None for item in matching)}

    complete = (expected is not None and not missing and not unexpected and not orphans
                and not orphan_spans and not missing_trace_parent_spans
                and not unfinished and not unfinished_spans and not issue_traces)
    return {'schema_version': SCHEMA_VERSION, 'task_id': task_id, 'task_run_id': task_run_id,
        'execution_authority': False, 'identity_scope': 'caller_correlation_not_host_authority',
        'duration_ns': duration_ns, 'duration_scope': 'whole_task_run_caller_boundary',
        'duration_source': 'caller_monotonic_elapsed' if duration_ns is not None else 'unknown',
        'timing_policy': 'never_sum_request_segment_or_nested_span_durations',
        'unique_traces': len(unique), 'duplicate_trace_records': duplicate_traces,
        'outer_request_attempts': len(roots), 'nested_traces': len(children),
        'root_requests': sorted(root_rows, key=lambda row: row['request_id']),
        'outer_request_counts_by_operation': counts_by_operation,
        'outer_request_counts_by_outcome': counts_by_outcome,
        'receipt_replayed_outer_requests': sum(row['annotations'].get('receipt_replayed') is True for row in roots),
        'historical_receipt_outer_requests': sum(row['annotations'].get('historical_receipt') is True for row in roots),
        'goal_completion_count': None,
        'goal_completion_policy': 'request_outcomes_and_receipt_replays_are_not_task_completion',
        'coverage': {'expected_outer_request_ids': None if expected is None else sorted(expected),
            'missing_request_ids': missing, 'unexpected_request_ids': unexpected,
            'orphan_trace_ids': sorted(orphans), 'unfinished_trace_ids': unfinished,
            'orphan_span_ids': sorted(orphan_spans),
            'trace_ids_with_missing_parent_spans': sorted(missing_trace_parent_spans),
            'unfinished_span_ids': unfinished_spans, 'trace_ids_with_telemetry_issues': sorted(issue_traces),
            'complete_against_declared_requests': bool(complete),
            'scope': 'declared_request_manifest_not_proof_of_all_host_or_model_work'},
        'span_evidence': {'unique_spans': len(spans), 'duplicate_span_records': duplicate_spans,
            'ownership_policy': 'one_trace_per_span_id_same_trace_span_parents',
            'host_capture_call_spans': span_counts(_CAPTURE_SPANS),
            'host_apply_call_spans': span_counts({'host.mutation'}),
            'scope': 'explicit_instrumented_calls_excludes_uninstrumented_host_internal_work',
            'apply_semantics': 'call_attempts_not_confirmed_mutations_or_goal_success'},
        'model_usage': _segment_usage_summary([*usage, *provider_usage_records]),
        'provider_usage_binding': 'trace_association_and_caller_selected_external_records'}
