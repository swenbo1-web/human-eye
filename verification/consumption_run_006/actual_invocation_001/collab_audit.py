"""Audit only RUN006's already projected public collaboration metadata.

This is evidence bookkeeping: it neither imports nor runs the experiment,
opens final answers, or recovers original/private collaboration events.
"""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time


HERE = Path(__file__).resolve().parent
RUN = HERE.parent
ACTUAL = RUN / 'actual_01'
EXPECTED_RUNNER = '7d7815d475a531b263bd51e74a676b6d4f11eacca994427f6723de9f02228afc'
PHASES = {'item.started', 'item.updated', 'item.completed'}
TOOLS = {'spawn_agent', 'send_input', 'wait', 'close_agent'}
STATUSES = {'in_progress', 'completed', 'failed'}
AGENT_STATUSES = {'pending_init', 'running', 'interrupted', 'completed',
                  'errored', 'shutdown', 'not_found'}
SCOPE = 'public metadata in this consume; observed IDs include senders, not created-agent counts'
INCOMPLETE = 'collaboration usage/total participant coverage not exposed; no main-usage addition'
COVERAGE = 'not exposed by verified public collab schema'
CALL_KEY = 'item.id within this consume only'
STATE_KEYS = {'events', 'calls', 'event_count', 'identifiable_call_count',
              'unattributed_event_count', 'observed_thread_ids',
              'observed_thread_id_count', 'extra_participant_count',
              'extra_usage', 'accounting_complete', 'scope', 'incompleteness'}
EVENT_KEYS = {'phase', 'item_id', 'call_key_source', 'tool', 'status',
              'sender_thread_id', 'receiver_thread_ids', 'receiver_ids_complete',
              'agents_states', 'agent_states_complete', 'extra_usage',
              'usage_coverage', 'received_ns'}
CALL_KEYS = {'phases', 'tools', 'statuses', 'terminal_statuses',
             'observed_thread_ids', 'terminal_observed',
             'terminal_status_conflict', 'tool_conflict'}


def load(path):
    return json.loads(path.read_bytes())


def file_identity(path):
    raw = path.read_bytes()
    return {'path': path.relative_to(RUN).as_posix(), 'bytes': len(raw),
            'sha256': hashlib.sha256(raw).hexdigest()}


def check_identity(value, nullable=False):
    if value is None and nullable:
        return
    assert type(value) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', value)


def check_ids(values, nullable=False):
    if values is None and nullable:
        return
    assert type(values) is list
    for value in values:
        check_identity(value)
    assert values == sorted(set(values))


def check_enum(value, allowed, nullable=False):
    assert (value is None and nullable) or (type(value) is str and value in allowed)


def validate_projection(state):
    """Allowlist before copying; unexpected fields are an audit failure."""
    assert type(state) is dict and set(state) == STATE_KEYS
    for key in ['event_count', 'identifiable_call_count', 'unattributed_event_count',
                'observed_thread_id_count']:
        assert type(state[key]) is int and state[key] >= 0
    assert state['extra_usage'] is None and state['extra_participant_count'] is None
    assert state['accounting_complete'] is False
    assert state['scope'] == SCOPE and state['incompleteness'] == INCOMPLETE
    check_ids(state['observed_thread_ids'])
    assert type(state['events']) is list and type(state['calls']) is dict
    for event in state['events']:
        assert type(event) is dict and set(event) == EVENT_KEYS
        check_enum(event['phase'], PHASES)
        check_enum(event['tool'], TOOLS, True)
        check_enum(event['status'], STATUSES, True)
        check_identity(event['item_id'], True)
        check_identity(event['sender_thread_id'], True)
        check_ids(event['receiver_thread_ids'], True)
        assert type(event['receiver_ids_complete']) is bool
        assert type(event['agent_states_complete']) is bool
        assert event['call_key_source'] == CALL_KEY
        assert event['extra_usage'] is None and event['usage_coverage'] == COVERAGE
        assert event['received_ns'] is None or (type(event['received_ns']) is int and event['received_ns'] >= 0)
        states = event['agents_states']
        assert states is None or type(states) is dict
        for identity, value in (states or {}).items():
            check_identity(identity)
            assert type(value) is dict and set(value) == {'status'}
            check_enum(value['status'], AGENT_STATUSES, True)
    for identity, call in state['calls'].items():
        check_identity(identity)
        assert type(call) is dict and set(call) == CALL_KEYS
        for field, enum in [('phases', PHASES), ('tools', TOOLS),
                            ('statuses', STATUSES), ('terminal_statuses', {'completed', 'failed'})]:
            assert type(call[field]) is list and len(call[field]) == len(set(call[field]))
            for value in call[field]:
                check_enum(value, enum)
        check_ids(call['observed_thread_ids'])
        for field in ['terminal_observed', 'terminal_status_conflict', 'tool_conflict']:
            assert type(call[field]) is bool


def independently_recount(state):
    calls = {}
    observed = set()
    phase_counts = Counter()
    event_tool_counts = Counter()
    unattributed = 0
    incomplete_receiver_events = 0
    incomplete_agent_state_events = 0
    for event in state['events']:
        ids = set(event['receiver_thread_ids'] or []) | set(event['agents_states'] or {})
        if event['sender_thread_id'] is not None:
            ids.add(event['sender_thread_id'])
        observed.update(ids)
        phase_counts[event['phase']] += 1
        event_tool_counts[event['tool'] if event['tool'] is not None else 'unrecognized_or_absent'] += 1
        incomplete_receiver_events += not event['receiver_ids_complete']
        incomplete_agent_state_events += not event['agent_states_complete']
        identity = event['item_id']
        if identity is None:
            unattributed += 1
            continue
        call = calls.setdefault(identity, {'phases': [], 'tools': [], 'statuses': [],
            'terminal_statuses': [], 'observed_thread_ids': [], 'terminal_observed': False,
            'terminal_status_conflict': False, 'tool_conflict': False})
        for field, value in [('phases', event['phase']), ('tools', event['tool']),
                             ('statuses', event['status'])]:
            if value is not None and value not in call[field]:
                call[field].append(value)
        if event['phase'] == 'item.completed' and event['status'] in {'completed', 'failed'}:
            call['terminal_observed'] = True
            if event['status'] not in call['terminal_statuses']:
                call['terminal_statuses'].append(event['status'])
        call['observed_thread_ids'] = sorted(set(call['observed_thread_ids']) | ids)
        call['terminal_status_conflict'] = len(call['terminal_statuses']) > 1
        call['tool_conflict'] = len(call['tools']) > 1
    assert state['event_count'] == len(state['events'])
    assert state['identifiable_call_count'] == len(calls)
    assert state['unattributed_event_count'] == unattributed
    assert state['observed_thread_ids'] == sorted(observed)
    assert state['observed_thread_id_count'] == len(observed)
    assert state['calls'] == calls
    per_tool = Counter(call['tools'][0] if len(call['tools']) == 1 else
                       'conflicting_or_unrecognized' for call in calls.values())
    return {'event_count': len(state['events']), 'identifiable_call_count': len(calls),
        'unattributed_event_count': unattributed, 'observed_thread_ids': sorted(observed),
        'observed_thread_id_count': len(observed), 'event_phase_counts': dict(phase_counts),
        'event_tool_counts': dict(event_tool_counts),
        'identifiable_calls_by_single_tool': dict(per_tool),
        'calls_without_terminal_event': [identity for identity, call in calls.items() if not call['terminal_observed']],
        'terminal_status_conflict_ids': [identity for identity, call in calls.items() if call['terminal_status_conflict']],
        'tool_conflict_ids': [identity for identity, call in calls.items() if call['tool_conflict']],
        'events_with_incomplete_receiver_metadata': incomplete_receiver_events,
        'events_with_incomplete_agent_state_metadata': incomplete_agent_state_events,
        'projected_state_matches_recount': True}


def main():
    started = time.perf_counter_ns()
    assert not (HERE / 'COLLAB_AUDIT.json').exists() and not (HERE / 'COLLAB_AUDIT.md').exists(), 'do not replace an earlier final audit'
    assert file_identity(RUN / 'runner.py')['sha256'] == EXPECTED_RUNNER
    outer = load(HERE / 'RESULT.json')
    assert outer.get('process_reaped') is True, 'Wait for parent terminal notification before final audit'
    plan = load(RUN / 'PLAN.json')
    result = load(ACTUAL / 'RESULTS.json')
    assert result['scheduled'] == 8 and len(result['cells']) == 8
    assert len(plan['cells']) == 8
    assert all(cell['status'] not in {'planned', 'running'} for cell in result['cells'])
    records = []
    sources = [file_identity(RUN / 'runner.py'), file_identity(RUN / 'PLAN.json'),
               file_identity(ACTUAL / 'RESULTS.json'), file_identity(HERE / 'RESULT.json'),
               file_identity(HERE / 'COLLAB_METER_REVIEW.snapshot.md')]
    for planned, cell in zip(plan['cells'], result['cells']):
        identity = {key: planned[key] for key in ['ordinal', 'task_id', 'arm']}
        assert all(cell.get(key) == value for key, value in identity.items())
        path = ACTUAL / f"{identity['ordinal']:02d}" / 'CONSUMER.json'
        record = dict(identity, status=cell['status'], consumer_metadata_available=path.exists())
        if not path.exists():
            record.update(collaboration=None, recount=None, discarded_event_types=None,
                          main_context_usage=None, provider_requests=None, fees=None, backend='unexposed',
                          limitation='No consumer artifact: collaboration measurements unavailable, not zero.')
            records.append(record)
            continue
        consumer = load(path)
        state = consumer.get('collaboration')
        validate_projection(state)
        recount = independently_recount(state)
        discarded = consumer.get('discarded_event_types')
        assert type(discarded) is dict and all(type(key) is str and type(value) is int and value >= 0
                                             for key, value in discarded.items())
        usage = consumer.get('usage')
        assert usage is None or (type(usage) is dict and set(usage) <=
            {'input_tokens', 'cached_input_tokens', 'output_tokens', 'total_tokens', 'reasoning_tokens'} and
            all(type(value) is int and value >= 0 for value in usage.values()))
        assert consumer.get('provider_requests') is None and consumer.get('fees') is None
        assert consumer.get('backend') == 'unexposed'
        record.update(collaboration=state, recount=recount, discarded_event_types=discarded,
            main_context_usage=usage, provider_requests=None, fees=None, backend='unexposed')
        sources.append(file_identity(path))
        records.append(record)
    available = [record for record in records if record['consumer_metadata_available']]
    observed = sorted({identity for record in available for identity in record['recount']['observed_thread_ids']})
    phase_counts = Counter()
    tool_calls = Counter()
    discarded_counts = Counter()
    for record in available:
        phase_counts.update(record['recount']['event_phase_counts'])
        tool_calls.update(record['recount']['identifiable_calls_by_single_tool'])
        discarded_counts.update(record['discarded_event_types'])
    totals = {key: sum(record['recount'][key] for record in available)
              for key in ['event_count', 'identifiable_call_count', 'unattributed_event_count']}
    totals.update(consumer_artifacts=len(available), scheduled_slots=8,
        consumer_artifact_coverage_complete=len(available) == 8,
        observed_thread_ids_union=observed, observed_thread_id_union_count=len(observed),
        sum_of_context_observed_thread_id_counts=sum(record['recount']['observed_thread_id_count'] for record in available),
        event_phase_counts=dict(phase_counts), identifiable_calls_by_single_tool=dict(tool_calls),
        original_discarded_event_counts=dict(discarded_counts),
        calls_without_terminal_event=sum(len(record['recount']['calls_without_terminal_event']) for record in available),
        calls_with_terminal_status_conflict=sum(len(record['recount']['terminal_status_conflict_ids']) for record in available),
        calls_with_tool_conflict=sum(len(record['recount']['tool_conflict_ids']) for record in available),
        extra_participant_count=None, extra_usage=None, accounting_complete=False,
        provider_requests=None, fees=None, backend='unexposed')
    # Each main usage is retained once per context above; this audit does not
    # add usage again to the separate counts audit or infer participant usage.
    report = dict(cycle_id='CONSUMPTION-RUN-006', audit='public collaboration metadata only',
        checked_utc=datetime.now(timezone.utc).isoformat(), source_files=sources,
        actual_extra_consumers_Blender_MCP_RPC_API=0, records=records, totals=totals,
        all_available_projected_states_match_recount=True,
        interpretation=[
            'Events, item.id calls within each consume, missing-ID events, and observed thread IDs are different measures.',
            'Observed IDs include senders; they are not new/successful agent counts or a complete participant count.',
            'The collector only sees its verified public projection; zero projected events is not proof of no backend collaboration.',
            'Original discarded counters remain independently retained, including collab_tool_call if present.',
            'Main-context usage is retained once per context for reference and is the same source as the counts audit; do not add the audits together.',
            'Extra participant count and usage, provider requests and fees stay null. Accounting remains incomplete; backend stays unexposed.',
            'No private collaboration prompts/messages/arguments/results/errors, hidden bodies, final answers, truth, auth, or global private logs were used.'
        ], elapsed_ns=time.perf_counter_ns()-started)
    for source in sources:
        assert file_identity(RUN / source['path']) == source, 'Source changed while audit ran'
    (HERE / 'COLLAB_AUDIT.json').write_text(json.dumps(report, indent=2, ensure_ascii=True) + '\n', encoding='utf8')
    lines = ['# RUN006 public collaboration metadata audit', '',
        f"All {len(available)}/8 available consumer projections match an independent recount.", '',
        '| Measure | Observed value |', '|---|---:|',
        f"| Projected events | {totals['event_count']} |",
        f"| Identifiable calls, summed per-consume item.id | {totals['identifiable_call_count']} |",
        f"| Events without usable item.id | {totals['unattributed_event_count']} |",
        f"| Observed thread IDs, union | {totals['observed_thread_id_union_count']} |",
        f"| Calls lacking observed terminal event | {totals['calls_without_terminal_event']} |",
        f"| Calls with conflicting terminal statuses | {totals['calls_with_terminal_status_conflict']} |",
        f"| Calls with conflicting tool values | {totals['calls_with_tool_conflict']} |", '',
        '| Slot | Task/arm | Status | Events | Identifiable calls | No-ID events | Observed IDs |',
        '|---|---|---|---:|---:|---:|---:|']
    for record in records:
        rec = record['recount']
        values = [rec[key] if rec else 'unknown' for key in ['event_count', 'identifiable_call_count',
                  'unattributed_event_count', 'observed_thread_id_count']]
        lines.append(f"| {record['ordinal']:02d} | {record['task_id']}/{record['arm']} | {record['status']} | " +
                     ' | '.join(str(value) for value in values) + ' |')
    lines.extend(['', 'Interpretation and limits:', ''] + ['- ' + text for text in report['interpretation']])
    lines.extend(['', 'The JSON preserves each original projected collaboration object and discarded-event counter unchanged. '
        'It preserves main-context usage once per slot without estimating extra participant usage. '
        'No additional experiment execution was performed.', ''])
    (HERE / 'COLLAB_AUDIT.md').write_text('\n'.join(lines), encoding='utf8')
    print(json.dumps({'totals': totals, 'all_available_projected_states_match_recount': True,
                      'elapsed_ns': report['elapsed_ns']}, indent=2, ensure_ascii=True))


if __name__ == '__main__':
    main()
