"""Scoped numeric checks for the six closed UUIDs in the final 002 whitelist."""

import importlib.util
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent.parent
ROOT = BATCH.parents[1]
WHITELIST = BATCH / 'private/THREAD_WHITELIST.json'
spec = importlib.util.spec_from_file_location('_002_usage_first_proof_helpers', HERE / 'check_episode_01.py')
first = importlib.util.module_from_spec(spec)
spec.loader.exec_module(first)
read, sha, usage, FIELDS = first.read, first.sha, first.usage, first.FIELDS


def session_numeric_events(path, thread_id):
    initial_sha = sha(path)
    metadata, selected, turns = [], [], []
    active = None
    with path.open('rb') as stream:
        for number, raw in enumerate(stream, 1):
            row = json.loads(raw)
            payload = row.get('payload', {})
            event = None
            if row.get('type') == 'session_meta':
                event = {'type': 'session_meta', 'thread_id': payload.get('id'), 'cli_version': payload.get('cli_version')}
                metadata.append(event)
            if row.get('type') == 'event_msg':
                kind = payload.get('type')
                if kind == 'task_started':
                    assert active is None, 'overlapping_turn_boundaries'
                    active = {'turn_id': payload['turn_id'], 'states': []}
                    turns.append(active)
                    event = {'type': kind, 'turn_id': payload['turn_id']}
                elif kind == 'task_complete':
                    assert active is not None and active['turn_id'] == payload['turn_id'], 'turn_end_binding'
                    active['complete'] = True
                    active = None
                    event = {'type': kind, 'turn_id': payload['turn_id']}
                elif kind == 'token_count':
                    info = payload.get('info')
                    event = {'type': kind, 'info_present': info is not None}
                    if info is not None:
                        assert active is not None, 'numeric_state_outside_actual_turn'
                        state = {'total_token_usage': usage(info['total_token_usage']),
                                 'last_token_usage': usage(info['last_token_usage'])}
                        active['states'].append(state)
                        event.update(turn_id=active['turn_id'], **state)
            if event is not None:
                event.update(source_line=number, source_line_sha256=hashlib.sha256(raw).hexdigest(),
                             timestamp=row.get('timestamp'))
                selected.append(event)
    assert active is None and all(turn.get('complete') for turn in turns)
    assert metadata and all(row['thread_id'] == thread_id and row['cli_version'] == '0.152.1' for row in metadata)
    assert sha(path) == initial_sha, 'closed_log_changed'
    return selected, turns, initial_sha


def main():
    whitelist = read(WHITELIST)
    assert whitelist['schema'] == 'continuous_002_actual_usage_whitelist_v1'
    outer_sources, actual_turns = [], set()
    for source in whitelist['source_outer_results']:
        path = Path(source['path']).resolve()
        assert path.is_relative_to(BATCH.resolve()) and sha(path) == source['sha256']
        outer_sources.append({'path': str(path), 'sha256': sha(path)})
        for turn in read(path)['coordinator']['turns']:
            actual_turns.add((turn['consumer']['thread_id'], turn['turn_index']))
    entries = whitelist['records']
    assert actual_turns == {(row['thread_id'], row['turn_index']) for row in entries}
    assert len(entries) == len(actual_turns) == 18 and len(outer_sources) == 6
    grouped = {}
    for row in entries:
        grouped.setdefault(row['thread_id'], []).append(row)
    assert len(grouped) == 6
    reports = []
    for thread_id, records in grouped.items():
        records = sorted(records, key=lambda row: row['turn_index'])
        assert [row['turn_index'] for row in records] == [1, 2, 3]
        candidates = list(first.SESSION_DAY.glob('*' + thread_id + '.jsonl'))
        assert len(candidates) == 1, 'exact_whitelisted_UUID_file_required'
        path = candidates[0]
        selected, turns, log_sha = session_numeric_events(path, thread_id)
        assert len(turns) == 3
        proofs, bindings = [], []
        previous_terminal = None
        for entry, turn in zip(records, turns):
            consumer_path = Path(entry['consumer_record']).resolve()
            assert consumer_path.is_relative_to((ROOT / '.m4cc2').resolve())
            assert sha(consumer_path) == entry['consumer_sha256']
            consumer = read(consumer_path)
            expected = None if entry['turn_index'] == 1 else thread_id
            assert consumer['thread_id'] == thread_id and consumer['turn_index'] == entry['turn_index']
            assert consumer['expected_thread_id'] == entry['expected_thread_id'] == expected
            assert ('resume' in consumer['frozen_cli_argv']) is (entry['turn_index'] > 1)
            if expected is not None:
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
            observed = cli_usage[0]
            assert type(observed) is dict and {'input_tokens', 'output_tokens'} <= set(observed) <= set(FIELDS)
            assert all(type(value) is int and value >= 0 for value in observed.values())
            states = []
            for state in turn['states']:
                if not states or state != states[-1]:
                    states.append(state)
            assert states, 'numeric_states_required'
            start, end = states[0], states[-1]
            reset = start['total_token_usage'] == start['last_token_usage'] and start['total_token_usage']['input_tokens'] > 0
            additions = [states[index]['total_token_usage'] == {key: states[index - 1]['total_token_usage'][key]
                + states[index]['last_token_usage'][key] for key in FIELDS} for index in range(1, len(states))]
            within_turn_sum = {key: sum(row['last_token_usage'][key] for row in states) for key in FIELDS}
            exact_sum = end['total_token_usage'] == within_turn_sum
            cli_match = all(observed[key] == end['total_token_usage'][key] for key in observed)
            changed_from_previous = previous_terminal is None or start['total_token_usage'] != previous_terminal
            confirmed = reset and all(additions) and exact_sum and cli_match and changed_from_previous
            proofs.append({'turn_index': entry['turn_index'], 'session_turn_id': turn['turn_id'],
                'raw_token_count_events': len(turn['states']), 'distinct_numeric_states': len(states),
                'starts_at_zero_base': reset, 'initial_state_differs_from_previous_terminal': changed_from_previous,
                'subsequent_total_equals_previous_plus_last': additions,
                'terminal_equals_this_turn_last_sum': exact_sum,
                'CLI_equals_terminal_total_on_all_reported_fields': cli_match,
                'raw_CLI_usage': observed, 'confirmed_per_turn_invocation_scope': confirmed})
            previous_terminal = end['total_token_usage']
            bindings.append({'turn_index': entry['turn_index'], 'expected_thread_id': expected,
                'consumer_path': str(consumer_path), 'consumer_sha256': sha(consumer_path),
                'CLI_events_path': str(events_path), 'CLI_events_sha256': sha(events_path)})
        reports.append({'thread_id': thread_id, 'session_path': str(path), 'session_sha256': log_sha,
                        'selected_numeric_events': selected, 'consumer_bindings': bindings, 'per_turn_proof': proofs,
                        'usage_scope': 'per_turn_CLI_invocation_observed' if all(row['confirmed_per_turn_invocation_scope'] for row in proofs) else 'unknown'})
    confirmed_threads = sum(row['usage_scope'] == 'per_turn_CLI_invocation_observed' for row in reports)
    summary = {'actual_threads_checked': len(reports), 'actual_turns_checked': len(entries), 'actual_resume_turns': 12,
               'confirmed_per_turn_scope_threads': confirmed_threads, 'unknown_scope_threads': len(reports) - confirmed_threads}
    output = {'schema': 'continuous_002_all_actual_usage_scope_v1', 'summary': summary,
        'whitelist_path': str(WHITELIST), 'whitelist_sha256': sha(WHITELIST), 'closed_outer_sources': outer_sources,
        'threads': reports, 'cost_unsealed': False, 'usage_aggregation': None,
        'group_totals_computed': False, 'episode_usage_aggregates_computed': False,
        'prior_first_proof_sha256': sha(HERE / 'EPISODE_01_NUMERIC_PROOF.json'),
        'analyzer_sha256': sha(Path(__file__)), 'reused_first_analyzer_sha256': sha(HERE / 'check_episode_01.py'),
        'privacy': 'Only exact authorized UUID filenames were opened. Exported session identifiers/version, boundaries, timestamps and numeric token fields only. No message, reasoning, rate-limit, credential or other chat data was exported.',
        'scope_limit': 'Observed six closed 002 threads only. Within-turn arithmetic is solely a counter-scope proof. No group/episode totals, winner or fee inference.'}
    (HERE / 'ALL_NUMERIC_PROOF.json').write_text(json.dumps(output, ensure_ascii=False, allow_nan=False, indent=2) + '\n',
                                              encoding='utf8', newline='\n')
    (HERE / 'ALL_RESULT.json').write_text(json.dumps({**summary, 'cost_unsealed': False, 'usage_aggregation': None,
        'numeric_proof_sha256': sha(HERE / 'ALL_NUMERIC_PROOF.json')}, indent=2) + '\n', encoding='utf8', newline='\n')
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
