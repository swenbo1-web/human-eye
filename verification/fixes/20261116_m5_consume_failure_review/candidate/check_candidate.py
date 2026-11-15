"""Independent pure/mock/replay validation of the archive-correlation candidate."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import time

OUT = Path(__file__).resolve().parent
AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe')
NAMESPACE = AUTHOR / 'verification/m5_task_consumption_001'
SOURCE = NAMESPACE / 'recovery_candidate/owned_runtime.py'
BASE = NAMESPACE / 'harness/owned_runtime.py'
RUN = Path('D:/he_m5_task_consume_001')
EXPECTED_SHA = '371049158c7370a0e29e30992e5b1fe2cd6d6ba726688e77017ca44c27f94318'
checks = []


def check(name, condition, detail=None):
    row = {'name': name, 'pass': bool(condition)}
    if detail is not None:
        row['detail'] = detail
    checks.append(row)
    if not condition:
        raise AssertionError(name)


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(value, sort_keys=True, ensure_ascii=True).encode() + b'\n')


def encode(rows):
    return b''.join(json.dumps(row, sort_keys=True).encode() + b'\n' for row in rows)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def expected_error(name, action, prefix):
    try:
        action()
    except (ValueError, KeyError, TypeError, FileNotFoundError) as error:
        check(name, prefix is None or str(error).startswith(prefix),
              {'error_type': type(error).__name__, 'message': str(error)})
    else:
        check(name, False)


raw = SOURCE.read_bytes()
check('fixed candidate source', hashlib.sha256(raw).hexdigest() == EXPECTED_SHA)
tree = ast.parse(raw)
functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
             and node.name in ('digest', 'read', 'append', 'correlate_archive')]
runtime_class = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                     and node.name == 'RootRuntime')
public_method = next(node for node in runtime_class.body if isinstance(node, ast.FunctionDef)
                     and node.name == 'public_request')
isolated_class = ast.ClassDef(name='Runtime', bases=[], keywords=[],
                             body=[public_method], decorator_list=[])
selected_tree = ast.fix_missing_locations(ast.Module(body=functions + [isolated_class], type_ignores=[]))
namespace = {'Path': Path, 'hashlib': hashlib, 'json': json, 'copy': copy,
             'time': time, 'save': save}
exec(compile(selected_tree, str(SOURCE), 'exec'), namespace)
correlate = namespace['correlate_archive']
Runtime = namespace['Runtime']
fixtures = OUT / 'pure_fixtures_final'
root = fixtures / 'one_slot/product_full'
root.mkdir(parents=True, exist_ok=True)


def record(index, begin=110, end=190, folder=root, status='observed'):
    path = folder / ('call_' + str(index).zfill(3)) / 'SERVICE_RESULT.json'
    save(path, {'result_kind': 'task_query', 'status': status, 'facts': {'value': index}})
    return {'index': index, 'started_ns': begin, 'producer_returned_ns': end,
            'path': str(path), 'sha256': digest(path)}


first = record(1)
second = record(2, status='partial')
third = record(3)
check('one append exact record', correlate(b'', encode([first]), 100, 200, False, root) == first)
check('error without producer at empty prefix', correlate(b'', b'', 100, 200, True, root) is None)
check('repeated error without producer after valid prefix',
      all(correlate(encode([first]), encode([first]), 200, 300, True, root) is None for _ in range(3)))
check('partial reply single append',
      correlate(encode([first]), encode([first, second]), 100, 200, False, root) == second)
check('service failure can consume counter without append',
      correlate(encode([first]), encode([first, third]), 100, 200, False, root) == third)
check('error with produced result can retain original producer entry',
      correlate(encode([first]), encode([first, second]), 100, 200, True, root) == second)
check('exact inclusive time markers',
      correlate(b'', encode([dict(first, started_ns=100, producer_returned_ns=200)]),
                100, 200, False, root)['index'] == 1)

cases = [
    ('successful response no archive', b'', b'', False, 'same_producer_archive_missing'),
    ('successful response only old archive', encode([first]), encode([first]), False,
     'same_producer_archive_missing'),
    ('changed byte prefix', encode([first]), encode([dict(first, started_ns=111), second]), False,
     'same_producer_archive_prefix_changed'),
    ('incomplete new line', b'', encode([first]).rstrip(b'\n'), False,
     'same_producer_archive_incomplete_index'),
    ('incomplete previous line', encode([first]).rstrip(b'\n'), encode([first]), True,
     'same_producer_archive_incomplete_index'),
    ('duplicate archive index', encode([first]), encode([first, first]), False,
     'same_producer_archive_duplicate_or_unordered_index'),
    ('backwards archive index', encode([second]), encode([second, first]), False,
     'same_producer_archive_duplicate_or_unordered_index'),
    ('boolean archive index', b'', encode([dict(first, index=True)]), False,
     'same_producer_archive_duplicate_or_unordered_index'),
    ('zero archive index', b'', encode([dict(first, index=0)]), False,
     'same_producer_archive_duplicate_or_unordered_index'),
    ('string archive index', b'', encode([dict(first, index='1')]), False,
     'same_producer_archive_duplicate_or_unordered_index'),
    ('array archive row', b'', encode([[first]]), False, 'same_producer_archive_invalid_entry'),
    ('multiple appended producers', b'', encode([first, second]), False,
     'same_producer_archive_multiple_new_entries'),
    ('producer before current request', b'', encode([dict(first, started_ns=99)]), False,
     'same_producer_archive_cross_request_window'),
    ('producer after response', b'', encode([dict(first, producer_returned_ns=201)]), False,
     'same_producer_archive_cross_request_window'),
    ('producer inverted times', b'', encode([dict(first, started_ns=190, producer_returned_ns=110)]), False,
     'same_producer_archive_cross_request_window'),
    ('producer missing time', b'', encode([{key: value for key, value in first.items() if key != 'started_ns'}]), False,
     'same_producer_archive_cross_request_window'),
    ('different slot path', b'', encode([record(1, folder=fixtures / 'other_slot/product_full')]), False,
     'same_producer_archive_cross_slot_path'),
    ('wrong independent counter path', b'', encode([dict(second, index=3)]), False,
     'same_producer_archive_cross_slot_path'),
    ('changed content hash', b'', encode([dict(first, sha256='0' * 64)]), False,
     'same_producer_archive_content_changed'),
]
for name, before, after, is_error, expected in cases:
    expected_error(name, lambda b=before, a=after, e=is_error: correlate(b, a, 100, 200, e, root), expected)

# Replay exact final-INDEX byte prefixes selected by actual synchronous windows.
# No final record is edited and no caller-count assertion defines expected producer IDs.
replays = []
for label in ('A1', 'B1', 'B2', 'A2', 'A3'):
    slot = RUN / 'formal' / label
    requests = [json.loads(line) for line in (slot / 'PUBLIC_REQUESTS.jsonl').read_bytes().splitlines()]
    lines = (slot / 'product_full/INDEX.jsonl').read_bytes().splitlines(keepends=True)
    rows = [json.loads(line) for line in lines]
    mapping = []
    check(label + ' original record order', [row['index'] for row in rows] == sorted({row['index'] for row in rows}))
    for request in requests:
        before_count = sum(row['saved_ns'] <= request['started_ns'] for row in rows)
        after_count = sum(row['saved_ns'] <= request['closed_ns'] for row in rows)
        before = b''.join(lines[:before_count])
        after = b''.join(lines[:after_count])
        response = request['response']
        is_error = 'error' in response or response.get('result', {}).get('isError') is True
        correlated = correlate(before, after, request['started_ns'], request['closed_ns'], is_error,
                               slot / 'product_full')
        expected_matches = [row for row in rows
                            if request['started_ns'] <= row['started_ns'] <= row['producer_returned_ns']
                            <= row['saved_ns'] <= request['closed_ns']]
        check(label + '/' + request['id'] + ' unique actual window', len(expected_matches) <= 1)
        check(label + '/' + request['id'] + ' independent window match',
              correlated == (expected_matches[0] if expected_matches else None))
        mapping.append(None if correlated is None else correlated['index'])
        check(label + '/' + request['id'] + ' original response saved hash',
              digest(request['response_path']) == request['response_sha256'])
    replays.append({'slot': label, 'actual_public_requests': len(requests), 'producer_mapping': mapping})
check('A1 required independent sequence', replays[0]['producer_mapping'] == [1, None, 2, 3])


class MockClient:
    def __init__(self, folder, outcomes):
        self.folder, self.outcomes = folder, list(outcomes)
        self.records, self.replies = [], []
        self.producer_counter = 0

    def call(self, message):
        current = len(self.records)
        outcome = self.outcomes[current]
        began = time.perf_counter_ns()
        is_error = outcome in ('prevalidation_error', 'service_error_no_append', 'formatter_error')
        if outcome != 'prevalidation_error':
            self.producer_counter += 1
        if outcome not in ('prevalidation_error', 'service_error_no_append', 'no_archive_success'):
            result_path = self.folder / 'product_full' / ('call_' + str(self.producer_counter).zfill(3)) / 'SERVICE_RESULT.json'
            save(result_path, {'result_kind': 'task_query', 'status': outcome, 'facts': {'distance_m': 0.996}})
            row = {'index': self.producer_counter, 'started_ns': began,
                   'producer_returned_ns': time.perf_counter_ns(), 'path': str(result_path),
                   'sha256': digest(result_path)}
            with (self.folder / 'product_full/INDEX.jsonl').open('ab') as stream:
                stream.write(encode([row]))
        response = {'jsonrpc': '2.0', 'id': message['id'], 'result': {
            'isError': is_error, 'content': [{'type': 'text', 'text': outcome}]}}
        rpc = self.folder / 'mcp' / ('rpc_' + str(current + 1).zfill(2))
        rpc.mkdir(parents=True, exist_ok=False)
        (rpc / 'TX.bin').write_bytes(json.dumps(message).encode() + b'\n')
        (rpc / 'RX.bin').write_bytes(json.dumps(response).encode() + b'\n')
        ended = time.perf_counter_ns()
        self.records.append({'index': current + 1, 'started_ns': began, 'closed_ns': ended,
                             'stdin_flushed_ns': began, 'received_complete_ns': ended})
        self.replies.append(response)
        return response


def mock_runtime(label, outcomes, expected_mapping):
    runtime = Runtime()
    runtime.runroot = fixtures / label
    (runtime.runroot / 'product_full').mkdir(parents=True, exist_ok=False)
    runtime._product_calls = 0
    runtime.public_requests = []
    runtime.check = lambda: None
    runtime._save_evidence = lambda: None
    runtime.client = MockClient(runtime.runroot, outcomes)
    replies = [runtime.public_request({'query': {'mode': 'task'}, 'include_image': False}) for _ in outcomes]
    check(label + ' responses preserve exact objects', all(a is b for a, b in zip(replies, runtime.client.replies)))
    check(label + ' independent actual producer counter',
          [row['producer_archive_index'] for row in runtime.public_requests] == expected_mapping)
    journal = [json.loads(line) for line in (runtime.runroot / 'PUBLIC_REQUESTS.jsonl').read_bytes().splitlines()]
    check(label + ' all replies journaled', len(journal) == len(outcomes))
    check(label + ' original errors and successes remain', [row['response'] for row in journal] == replies)
    check(label + ' exact snapshots retained',
          all(digest(Path(row['request_path']).parent / 'ARCHIVE_BEFORE.bin') == row['archive_before_sha256']
              and digest(Path(row['request_path']).parent / 'ARCHIVE_AFTER.bin') == row['archive_after_sha256']
              for row in journal))
    check(label + ' no correlation errors', all('post_reply_binding_error' not in row for row in journal))


mock_runtime('multiple_rejection_recovery',
             ['prevalidation_error', 'prevalidation_error', 'observed', 'partial', 'prevalidation_error', 'observed'],
             [None, None, 1, 2, None, 3])
mock_runtime('service_counter_gap_and_formatter_error',
             ['observed', 'service_error_no_append', 'observed', 'formatter_error', 'partial'],
             [1, None, 3, 4, 5])

# A correlation fault must preserve the original successful reply in its journal.
runtime = Runtime()
runtime.runroot = fixtures / 'missing_archive_journal'
(runtime.runroot / 'product_full').mkdir(parents=True, exist_ok=False)
runtime._product_calls = 0
runtime.public_requests = []
runtime.check = lambda: None
runtime._save_evidence = lambda: None
runtime.client = MockClient(runtime.runroot, ['no_archive_success'])
expected_error('runtime refuses success lacking receipt',
               lambda: runtime.public_request({'query': {'mode': 'task'}, 'include_image': False}),
               'same_producer_archive_missing')
journal = [json.loads(line) for line in (runtime.runroot / 'PUBLIC_REQUESTS.jsonl').read_bytes().splitlines()]
check('correlation fault original successful response remains',
      len(journal) == 1 and journal[0]['response'] == runtime.client.replies[0]
      and journal[0]['response']['result']['isError'] is False)
check('correlation fault actual independent index remains null', journal[0]['producer_archive_index'] is None)
check('correlation fault explicit post-reply record',
      journal[0]['post_reply_binding_error'] == {'type': 'ValueError', 'message': 'same_producer_archive_missing'})

check('candidate retains old EXTERNAL and import context',
      b'EXTERNAL = Path("D:/he_m5_task_consume_001")' in raw
      and b"HERE = NAMESPACE / 'harness'" in raw)
save(OUT / 'RESULT.json', {'status': 'pass', 'checks': len(checks), 'source_sha256': digest(SOURCE),
                         'original_sha256': digest(BASE), 'replays': replays, 'checks_detail': checks,
                         'new_Blender': 0, 'new_raster': 0, 'new_models': 0,
                         'scope': 'Independent AST-extracted candidate helpers, mocked method, and original byte-prefix replay.'})
print(json.dumps({'status': 'pass', 'checks': len(checks), 'replays': replays}))
