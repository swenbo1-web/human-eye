"""Bind this batch's real thread records without exposing cost or chat bodies."""

import hashlib
import json
from pathlib import Path
from uuid import UUID


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent.parent
ROOT = BATCH.parents[1]


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    whitelist_path = BATCH / 'private/THREAD_WHITELIST.json'
    run_path = BATCH / 'RUN_RESULT.json'
    whitelist = read(whitelist_path)
    run = read(run_path)
    assert whitelist['schema'] == 'continuous_actual_thread_whitelist_v1'
    assert whitelist['source_sha256'] == sha(run_path), 'formal_source_binding'
    records = whitelist['records']
    expected = []
    for episode in run['records']:
        for turn in episode.get('coordinator', {}).get('turns', []):
            consumer = turn.get('consumer')
            if consumer is not None and consumer.get('thread_id') is not None:
                expected.append((consumer['thread_id'], turn['turn_index']))
    assert sorted(expected) == sorted((row['thread_id'], row['turn_index']) for row in records), 'complete_actual_UUID_whitelist'
    bindings = []
    for entry in records:
        assert str(UUID(entry['thread_id'])) == entry['thread_id'], 'canonical_actual_UUID'
        path = Path(entry['consumer_record']).resolve()
        assert path.is_relative_to((ROOT / '.m4cc1').resolve()), 'owned_runtime_source'
        consumer = read(path)
        assert consumer['thread_id'] == entry['thread_id'], 'actual_UUID_source_binding'
        assert consumer['turn_index'] == entry['turn_index'], 'actual_turn_source_binding'
        assert consumer['expected_thread_id'] == entry['expected_thread_id'], 'expected_UUID_source_binding'
        bindings.append({
            'thread_id': entry['thread_id'], 'turn_index': entry['turn_index'],
            'expected_thread_id': entry['expected_thread_id'],
            'explicit_resume_requested': 'resume' in consumer['frozen_cli_argv'],
            'consumer_record': str(path), 'consumer_sha256': sha(path),
        })
    resume_rows = [row for row in bindings if row['turn_index'] > 1
                   or row['expected_thread_id'] is not None or row['explicit_resume_requested']]
    assert not resume_rows, 'new_resume_evidence_requires_a_separate_scoped_analysis'
    result = {
        'schema': 'continuous_actual_usage_scope_v1',
        'whitelist_sha256': sha(whitelist_path), 'run_result_sha256': sha(run_path),
        'analyzer_sha256': sha(Path(__file__)), 'actual_consumer_turns': len(bindings),
        'actual_distinct_threads': len({row['thread_id'] for row in bindings}),
        'actual_resume_turns': len(resume_rows), 'bindings': bindings,
        'usage_scope': 'unknown', 'usage_aggregation': None,
        'reason': 'All actual turns are first turns. No same-thread resumed turn exists to distinguish per-turn from session scope.',
        'session_logs_opened': 0, 'other_chats_opened': 0,
        'cost_unsealed': False, 'group_totals_computed': False,
        'scope': 'Only this batch whitelist, formal result and exact listed consumer metadata were used. No token numbers or message bodies are exported.',
    }
    destination = HERE / 'BINDING.json'
    destination.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2) + '\n',
                           encoding='utf8', newline='\n')
    print(json.dumps({key: result[key] for key in (
        'actual_consumer_turns', 'actual_distinct_threads', 'actual_resume_turns',
        'usage_scope', 'usage_aggregation', 'session_logs_opened', 'cost_unsealed',
    )}))


if __name__ == '__main__':
    main()
