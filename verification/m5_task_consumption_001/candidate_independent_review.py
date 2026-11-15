"""Independent read-only recovery-candidate review, without candidate deployment."""

import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
CANDIDATE = HERE / 'recovery_candidate'
RUNTIME = Path('D:/he_m5_task_consume_001')


def pin(path):
    raw = Path(path).read_bytes()
    return {'path': str(Path(path).resolve()), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def read(path):
    return json.loads(Path(path).read_bytes())


def encoded(rows):
    return b''.join(json.dumps(row, sort_keys=True).encode() + b'\n' for row in rows)


def functions(tree):
    found = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            found[node.name] = ast.dump(node, include_attributes=False)
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, ast.FunctionDef):
                    found[node.name + '.' + child.name] = ast.dump(child, include_attributes=False)
    return found


def main():
    checks = []
    inputs = {}

    def check(name, value, detail=None):
        checks.append({'name': name, 'passed': bool(value), 'detail': detail})

    def verify(rows):
        for row in rows:
            actual = pin(row['path'])
            inputs[actual['path']] = actual
            check('pin_' + str(len(inputs)), actual['sha256'] == row['sha256']
                and ('bytes' not in row or actual['bytes'] == row['bytes']), actual['path'])

    manifest = read(CANDIDATE / 'CANDIDATE.json')
    verify(manifest['input_pins'])
    baseline = read(CANDIDATE / 'BASELINE.json')
    verify([{'path': baseline['source'], 'sha256': baseline['sha256'], 'bytes': baseline['bytes']}])
    result = read(CANDIDATE / 'PURE_01/RESULT.json')
    verify(result['input_pins'])
    check('saved_nineteen_checks_are_complete_and_all_passed', result['passed'] is True
        and len(result['checks']) == 19 and all(row['passed'] is True for row in result['checks'])
        and len({row['name'] for row in result['checks']}) == 19)
    original_tree = ast.parse(Path(baseline['source']).read_bytes())
    source_path = CANDIDATE / 'owned_runtime.py'
    source_pin = pin(source_path)
    candidate_tree = ast.parse(source_path.read_bytes())
    original_functions, candidate_functions = functions(original_tree), functions(candidate_tree)
    changed = {name for name in original_functions if original_functions[name] != candidate_functions.get(name)}
    added = set(candidate_functions) - set(original_functions)
    check('only_public_request_method_changed_and_one_pure_helper_added',
        changed == {'RootRuntime.public_request'} and added == {'correlate_archive'},
        {'changed': sorted(changed), 'added': sorted(added)})
    spec = importlib.util.spec_from_file_location('_independent_m5_recovery_helper', source_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    public = [json.loads(line) for line in (RUNTIME / 'formal/A1/PUBLIC_REQUESTS.jsonl').read_bytes().splitlines()]
    index_path = RUNTIME / 'formal/A1/product_full/INDEX.jsonl'
    raw_index = index_path.read_bytes()
    raw_lines = raw_index.splitlines(keepends=True)
    entries = [json.loads(line) for line in raw_lines]
    associations = []
    for entry in entries:
        requests = [row['id'] for row in public if row['started_ns'] <= entry['started_ns']
                    <= entry['producer_returned_ns'] <= row['closed_ns']]
        associations.append({'service_index': entry['index'], 'matching_public_ids': requests})
    check('independent_actual_window_assignment_is_unique', associations == [
        {'service_index': 1, 'matching_public_ids': ['observe-1']},
        {'service_index': 2, 'matching_public_ids': ['observe-3']},
        {'service_index': 3, 'matching_public_ids': ['observe-4']}])
    mapping = []
    for request in public:
        before = b''.join(line for line, row in zip(raw_lines, entries)
            if row['producer_returned_ns'] <= request['started_ns'])
        after = b''.join(line for line, row in zip(raw_lines, entries)
            if row['producer_returned_ns'] <= request['closed_ns'])
        linked = module.correlate_archive(before, after, request['started_ns'], request['closed_ns'],
            request['response']['result']['isError'] is True, index_path.parent)
        mapping.append(None if linked is None else linked['index'])
    check('readonly_actual_replay_handles_pre_service_rejection', mapping == [1, None, 2, 3])
    synthetic = CANDIDATE / 'PURE_01/synthetic_product_full'
    one_path = synthetic / 'call_001/SERVICE_RESULT.json'
    two_path = synthetic / 'call_002/SERVICE_RESULT.json'
    one = {'index': 1, 'started_ns': 120, 'producer_returned_ns': 160,
           'path': str(one_path.resolve()), 'sha256': pin(one_path)['sha256']}
    two = {'index': 2, 'started_ns': 120, 'producer_returned_ns': 160,
           'path': str(two_path.resolve()), 'sha256': pin(two_path)['sha256']}
    for name, before, after, error_flag, expected in (
        ('unchanged_error', b'', b'', True, None),
        ('valid_after_prior_entry', encoded([one]), encoded([one, two]), False, 2),
    ):
        linked = module.correlate_archive(before, after, 100, 200, error_flag, synthetic)
        check(name, (None if linked is None else linked['index']) == expected)
    cases = [
        ('missing', b'', b'', 'same_producer_archive_missing'),
        ('duplicate', encoded([one]), encoded([one, one]), 'same_producer_archive_duplicate_or_unordered_index'),
        ('multiple', b'', encoded([one, two]), 'same_producer_archive_multiple_new_entries'),
        ('earlier_request', b'', encoded([dict(one, started_ns=99)]), 'same_producer_archive_cross_request_window'),
        ('late_producer', b'', encoded([dict(one, producer_returned_ns=201)]), 'same_producer_archive_cross_request_window'),
        ('cross_slot', b'', encoded([dict(one, path=str((CANDIDATE / 'PURE_01/other_slot/call_001/SERVICE_RESULT.json').resolve()))]), 'same_producer_archive_cross_slot_path'),
        ('hash', b'', encoded([dict(one, sha256='0' * 64)]), 'same_producer_archive_content_changed'),
        ('prefix', encoded([one]), encoded([dict(one, started_ns=121)]), 'same_producer_archive_prefix_changed'),
        ('incomplete', b'', encoded([one]).rstrip(b'\n'), 'same_producer_archive_incomplete_index'),
    ]
    for name, before, after, reason in cases:
        try:
            module.correlate_archive(before, after, 100, 200, False, synthetic)
        except ValueError as error:
            check('reject_' + name, str(error) == reason)
        else:
            check('reject_' + name, False)
    mock = CANDIDATE / 'PURE_01/runtime_mock'
    journal = [json.loads(line) for line in (mock / 'PUBLIC_REQUESTS.jsonl').read_bytes().splitlines()]
    check('public_count_and_service_index_independent_in_saved_mock',
        [row['internal_public_call_index'] for row in journal] == [1, 2, 3]
        and [row['producer_archive_index'] for row in journal] == [None, 1, 2])
    for number, row in enumerate(journal, 1):
        raw_response = read(mock / 'mcp' / ('rpc_' + str(number).zfill(2)) / 'RX.bin')
        response_copy = read(row['response_path'])
        check('saved_mock_original_response_preserved_' + str(number),
            raw_response == response_copy == row['response'] and 'post_reply_binding_error' not in row)
        before = (mock / 'product_calls' / ('call_' + str(number).zfill(3)) / 'ARCHIVE_BEFORE.bin').read_bytes()
        after = (mock / 'product_calls' / ('call_' + str(number).zfill(3)) / 'ARCHIVE_AFTER.bin').read_bytes()
        check('saved_before_after_original_hashes_' + str(number),
            hashlib.sha256(before).hexdigest() == row['archive_before_sha256']
            and hashlib.sha256(after).hexdigest() == row['archive_after_sha256'])
    runtime_method = next(node for node in candidate_tree.body if isinstance(node, ast.ClassDef) and node.name == 'RootRuntime')
    runtime_method = next(node for node in runtime_method.body if isinstance(node, ast.FunctionDef) and node.name == 'public_request')
    returns = [node.value for node in ast.walk(runtime_method) if isinstance(node, ast.Return)]
    check('runtime_returns_exact_response_variable_without_reconstructing_reply',
        len(returns) == 1 and isinstance(returns[0], ast.Name) and returns[0].id == 'response')
    check('uninstalled_candidate_and_old_batch_untouched_flags_are_explicit',
        manifest['candidate_deployed'] is False and manifest['current_batch_rerun'] is False
        and manifest['actual_Blender_MCP_models_rasters'] == 0)
    check('candidate_source_stable_during_review', pin(source_path) == source_pin)
    report = {'schema': 'm5-candidate-independent-review-v1',
        'passed_checked_scope': all(row['passed'] for row in checks), 'reviewed_source': source_pin,
        'checks': checks, 'check_count': len(checks), 'passed_count': sum(row['passed'] for row in checks),
        'input_pins': list(inputs.values()) + [pin(CANDIDATE / 'CANDIDATE.json'), pin(__file__)],
        'actual_A1_associations': associations, 'saved_replay_mapping': mapping,
        'author_association': 'This reviewer authored the common bridge, not the candidate or frozen owned-runtime harness. Another agent authored the candidate, its nineteen checks and the original harness. Root executed the actual cohort and imposed the stop. This is an independent review of that minimal correction, with bridge-author association disclosed.',
        'limitations': ['Replayed A1 prefixes are reconstructed exact byte prefixes of its final original INDEX using original request windows. They are not historical captured before/after snapshots.',
            'Original A1 observe-3 and observe-4 remain internally received successful replies replaced before consumer delivery. This review does not relabel them as consumed or adopted.',
            'The nineteen saved checks combine helper counterexamples, a full runtime mock and original-data replay. They establish saved/mock scope, not deployment or a new live recovery qualification.',
            'The existing synchronous single-owner call boundary is a dependency of window correlation. No concurrent or asynchronous producer domain is added.',
            'No new performance, task-quality or model-benefit claim follows from this repair candidate.'],
        'recommendation': 'Retain this as the sole minimal external-harness repair candidate for a future authorized recovery qualification. Preserve this stopped cohort and its negative comparability decision.',
        'new_actual_operations': {'Blender_starts': 0, 'MCP_processes': 0, 'raster_attempts': 0,
            'model_consumers': 0, 'product_edits': 0, 'current_batch_retries': 0,
            'candidate_or_frozen_source_edits': 0}}
    with (HERE / 'CANDIDATE_INDEPENDENT_REVIEW.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed': report['passed_checked_scope'], 'checks': len(checks),
        'failed': [row['name'] for row in checks if not row['passed']], 'source_sha256': source_pin['sha256']}))
    if not report['passed_checked_scope']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
