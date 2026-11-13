"""Check only the first explicitly authorized, already-closed 002 UUID.

Only session identifiers, turn boundaries and numeric token fields are exported.
No message/reasoning payload, rate-limit data, other chat or credential is read
as an analysis input. No provider or other subprocess is launched.
"""

import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent.parent
ROOT = BATCH.parents[1]
WHITELIST = BATCH / 'private/USAGE_WHITELIST_EPISODE_01.json'
SESSION_DAY = Path('C:/Users/Administrator/.codex/sessions/2026/11/13')
FIELDS = ('input_tokens', 'cached_input_tokens', 'cache_write_input_tokens',
          'output_tokens', 'reasoning_output_tokens', 'total_tokens')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def usage(value):
    if type(value) is not dict or set(value) != set(FIELDS):
        raise ValueError('unsupported_numeric_usage_fields')
    if any(type(value[key]) is not int or value[key] < 0 for key in FIELDS):
        raise ValueError('invalid_numeric_usage')
    return {key: value[key] for key in FIELDS}


def main():
    whitelist = read(WHITELIST)
    assert whitelist['schema'] == 'continuous_002_actual_usage_whitelist_v1'
    outer = Path(whitelist['source_outer_result'])
    assert outer.resolve().is_relative_to(BATCH.resolve())
    assert sha(outer) == whitelist['source_outer_sha256'], 'closed_outer_binding'
    records = whitelist['records']
    thread_ids = {row['thread_id'] for row in records}
    assert len(thread_ids) == 1 and [row['turn_index'] for row in records] == [1, 2, 3]
    thread_id = next(iter(thread_ids))
    candidates = list(SESSION_DAY.glob('*' + thread_id + '.jsonl'))
    assert len(candidates) == 1, 'exact_authorized_UUID_file_required'
    session = candidates[0]
    session_sha = sha(session)
    selected, turns, metadata = [], [], []
    active = None
    with session.open('rb') as stream:
        for line_number, raw in enumerate(stream, 1):
            value = json.loads(raw)
            payload = value.get('payload', {})
            kind = value.get('type')
            item = None
            if kind == 'session_meta':
                item = {'kind': 'session_meta', 'thread_id': payload.get('id'),
                        'cli_version': payload.get('cli_version')}
                metadata.append(item)
            if kind == 'event_msg':
                event_type = payload.get('type')
                if event_type == 'task_started':
                    assert active is None, 'overlapping_turn_boundaries'
                    active = {'turn_id': payload['turn_id'], 'token_states': []}
                    turns.append(active)
                    item = {'kind': event_type, 'turn_id': payload['turn_id']}
                elif event_type == 'task_complete':
                    assert active is not None and active['turn_id'] == payload['turn_id'], 'turn_completion_binding'
                    item = {'kind': event_type, 'turn_id': payload['turn_id']}
                    active['completed'] = True
                    active = None
                elif event_type == 'token_count':
                    info = payload.get('info')
                    item = {'kind': event_type, 'info_present': info is not None}
                    if info is not None:
                        assert active is not None, 'usage_outside_observed_turn'
                        state = {'total_token_usage': usage(info['total_token_usage']),
                                 'last_token_usage': usage(info['last_token_usage'])}
                        active['token_states'].append(state)
                        item.update(turn_id=active['turn_id'], **state)
            if item is not None:
                item.update(source_line=line_number, source_line_sha256=hashlib.sha256(raw).hexdigest(),
                            timestamp=value.get('timestamp'))
                selected.append(item)
    assert sha(session) == session_sha, 'closed_session_log_changed_during_read'
    assert len(metadata) == 1 and metadata[0]['thread_id'] == thread_id and metadata[0]['cli_version'] == '0.152.1'
    assert active is None and len(turns) == 3 and all(turn.get('completed') for turn in turns)
    bindings, proof = [], []
    for record, turn in zip(records, turns):
        consumer_path = Path(record['consumer_record']).resolve()
        assert consumer_path.is_relative_to((ROOT / '.m4cc2').resolve())
        assert sha(consumer_path) == record['consumer_sha256'], 'authorized_consumer_bytes'
        consumer = read(consumer_path)
        assert consumer['thread_id'] == thread_id and consumer['turn_index'] == record['turn_index']
        assert consumer['expected_thread_id'] == record['expected_thread_id']
        expected = None if record['turn_index'] == 1 else thread_id
        assert consumer['expected_thread_id'] == expected
        assert ('resume' in consumer['frozen_cli_argv']) is (record['turn_index'] > 1)
        if record['turn_index'] > 1:
            assert thread_id in consumer['frozen_cli_argv']
        events_path = consumer_path.parent / 'events.jsonl'
        assert sha(events_path) == consumer['archive']['source_files_sha256']['events.jsonl']
        cli_usage = []
        with events_path.open('rb') as stream:
            for raw in stream:
                event = json.loads(raw).get('event', {})
                if event.get('type') == 'turn.completed':
                    cli_usage.append(event.get('usage'))
        assert len(cli_usage) == 1 and cli_usage == consumer['raw_usage_events']
        raw_usage = cli_usage[0]
        assert type(raw_usage) is dict and set(raw_usage) <= set(FIELDS)
        assert all(type(value) is int and value >= 0 for value in raw_usage.values())
        states = []
        for state in turn['token_states']:
            if not states or state != states[-1]:
                states.append(state)
        assert states, 'numeric_usage_required'
        first = states[0]
        terminal = states[-1]
        reset = first['total_token_usage'] == first['last_token_usage'] and first['total_token_usage']['input_tokens'] > 0
        additions = [states[index]['total_token_usage'] == {
            key: states[index - 1]['total_token_usage'][key] + states[index]['last_token_usage'][key]
            for key in FIELDS} for index in range(1, len(states))]
        within_turn_sum = {key: sum(state['last_token_usage'][key] for state in states) for key in FIELDS}
        exact_sum = terminal['total_token_usage'] == within_turn_sum
        matches_cli = all(raw_usage[key] == terminal['total_token_usage'][key] for key in raw_usage)
        proof.append({'turn_index': record['turn_index'], 'session_turn_id': turn['turn_id'],
                      'raw_token_count_events': len(turn['token_states']), 'distinct_numeric_states': len(states),
                      'starts_at_zero_base': reset, 'subsequent_total_equals_previous_plus_last': additions,
                      'terminal_equals_this_turn_last_sum': exact_sum,
                      'CLI_equals_terminal_total_on_all_reported_fields': matches_cli,
                      'raw_CLI_usage': raw_usage,
                      'confirmed_per_turn_invocation_scope': reset and all(additions) and exact_sum and matches_cli})
        bindings.append({'thread_id': thread_id, 'turn_index': record['turn_index'],
                         'expected_thread_id': expected, 'consumer_path': str(consumer_path),
                         'consumer_sha256': sha(consumer_path), 'CLI_events_path': str(events_path),
                         'CLI_events_sha256': sha(events_path)})
    confirmed = all(row['confirmed_per_turn_invocation_scope'] for row in proof)
    output = {'schema': 'continuous_002_observed_usage_scope_v1',
              'whitelist_path': str(WHITELIST), 'whitelist_sha256': sha(WHITELIST),
              'closed_outer_path': str(outer), 'closed_outer_sha256': sha(outer),
              'authorized_UUID': thread_id, 'session_path': str(session), 'session_sha256': session_sha,
              'session_bytes': session.stat().st_size, 'selected_events': selected,
              'consumer_bindings': bindings, 'per_turn_proof': proof,
              'usage_scope': 'per_turn_CLI_invocation_observed' if confirmed else 'unknown',
              'scope_limit': 'This one authorized already-closed UUID and these three invocations only.',
              'actual_resume_turns': 2, 'usage_aggregation': None, 'cost_unsealed': False,
              'group_totals_computed': False, 'new_provider_calls': 0,
              'analyzer_sha256': sha(Path(__file__)),
              'privacy': 'Exported only session IDs/version, turn boundaries, timestamps and numeric token fields. No message/reasoning or rate-limit body was copied. Only the exact authorized session file was opened.'}
    (HERE / 'EPISODE_01_NUMERIC_PROOF.json').write_text(json.dumps(output, ensure_ascii=False, allow_nan=False, indent=2) + '\n',
                                                     encoding='utf8', newline='\n')
    print(json.dumps({'usage_scope': output['usage_scope'], 'actual_resume_turns': 2,
                      'turns_checked': 3, 'cost_unsealed': False, 'usage_aggregation': None}))


if __name__ == '__main__':
    main()
