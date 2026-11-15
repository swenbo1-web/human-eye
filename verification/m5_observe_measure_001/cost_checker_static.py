"""Independent saved-source review using only small in-memory synthetic inputs."""

import ast
import copy
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'cost_decision.py'
CHECKS = []


def pin(path):
    blob = Path(path).read_bytes()
    return {'path': str(Path(path).resolve()), 'sha256': hashlib.sha256(blob).hexdigest(), 'bytes': len(blob)}


def check(name, condition, detail=None):
    CHECKS.append({'name': name, 'passed': bool(condition), 'detail': detail})


def fixture(module, label):
    folder = module.RUNTIME / 'formal' / label
    control = label.endswith('task_only')
    arm = label[0]
    count = 1 if control or arm == 'B' else 2
    key = 'task_only' if control else arm + '_main'
    task = {'result_kind': 'task_query', 'facts': {'surface_proximity': {'status': 'measured'}}}
    task_work = {'surface_pair_count': 1, 'supplemental_capture_calls': 0, 'additional_raster_attempts': 0}
    values = [copy.deepcopy(task)] if control else [
        {'result_kind': 'active_observation', **({'task_result': task} if arm == 'B' else {})}]
    if count == 2:
        values.append(task)
    documents, requests, contract = {}, [], []
    for index, value in enumerate(values):
        request = {'id': 'synthetic-' + str(index), 'method': 'tools/call', 'params': {'synthetic': index}}
        contract.append(request)
        public = folder / ('PUBLIC_' + str(index) + '.json')
        producer = folder / ('PRODUCER_' + str(index) + '.json')
        text = json.dumps(value)
        row = {'id': request['id'], 'request': request,
            'response': {'id': request['id'], 'result': {'isError': False, 'content': [{'type': 'text', 'text': text}]}},
            'public_path': str(public), 'producer': {'path': str(producer), 'sha256': 'a' * 64},
            'public_text_UTF8_bytes': len(text.encode()), 'image_blocks': int(not control and index == 0),
            'complete_client_call_ns': 100, 'client_flush_to_received_ns': 90,
            'server': {'request_to_reply_ns': 80}, 'receipt': {'TX_bytes': 10, 'RX_bytes': 20}}
        requests.append(row)
        documents[str(public)] = value
        work = {'raster_attempts': int(not control and index == 0)}
        if arm == 'B' and not control:
            work['task_query'] = task_work
        documents[str(producer)] = {'work': work, 'frames': [] if control or index else [{}]}
    result = {'label': label, 'phase': 'formal', 'source_sha256': 'source-' + arm,
        'started_ns': 100, 'original_owned_deadline_ns': 600_000_000_100,
        'business_windows': [{'label': 'main', 'continuous_business_ns': 600, 'started_ns': 200,
            'completed_ns': 800, 'public_business_calls': count}],
        'requests': requests, 'owned_lifecycle_ns': 850}
    publication = {'result_sha256': 'a' * 64, 'result_published_ns': 1000,
        'complete_session_ns': 900, 'passed_transport_scope': True}
    documents[str(folder / 'RESULT.json')] = result
    documents[str(folder / 'PUBLICATION.json')] = publication
    documents[str(folder / 'SAVED_WIRE.json')] = {'steps': [{'command': {'command': 'synthetic-capture'},
        'actual_TCP_TX_bytes': 30, 'actual_TCP_RX_bytes': 40, 'resources_forwarded': 0,
        'resource_vertices_forwarded': 0, 'resource_faces_forwarded': 0}]}
    audit = [{'event': 'observe', 'task_work': task_work}]
    record = {'output': str(folder), 'label': label, 'arm': arm, 'request_key': key}
    gate = {arm + '_binding': {'source_sha256': 'source-' + arm}}
    return documents, audit, result, record, gate, {key: contract}


def collect(module, label, mutation=None):
    documents, audit, result, record, gate, contracts = fixture(module, label)
    if mutation is not None:
        mutation(documents, audit, result, record, gate, contracts)
    with patch.object(module, 'read', side_effect=lambda path: copy.deepcopy(documents[str(Path(path))])), \
         patch.object(module, 'sha', return_value='a' * 64), \
         patch.object(module, 'raw', return_value=b'\n'.join(json.dumps(row).encode() for row in audit)):
        return module.collect(label, record, {'passed_checked_scope': True}, gate, contracts)


def main():
    source_pin = pin(SOURCE)
    tree = ast.parse(SOURCE.read_bytes(), filename=str(SOURCE))
    spec = importlib.util.spec_from_file_location('_m5_cost_review_only', SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.RUNTIME = Path('D:/__M5_IN_MEMORY_SYNTHETIC_ONLY__')
    check('exact_registered_six_main_plus_two_controls', module.MAIN + module.CONTROLS ==
        ['A1', 'B1', 'B2', 'A2', 'A3', 'B3', 'A_task_only', 'B_task_only'])
    main_node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
    assignments = {node.targets[0].id: node.value for node in main_node.body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)}
    gate_nodes = {row.arg: row.value for row in assignments['gates'].keywords}
    plan = {'gates': {'minimum_B_faster_business_pairs': 2, 'median_business_B_over_A_max': 1.05,
        'median_complete_session_B_over_A_max': 1.05, 'engineering_time_benefit_separate_ratio_max': .9}}

    def evaluate(node, **values):
        return eval(compile(ast.Expression(node), str(SOURCE), 'eval'),
            {'statistics': statistics, 'all': all, 'sum': sum, **values})

    a = collect(module, 'A1')
    b = collect(module, 'B1')
    control = collect(module, 'A_task_only')
    for name, row, expected in [('A', a, 2), ('B', b, 1), ('task_only', control, 1)]:
        check('synthetic_' + name + '_actual_call_count', row['public_business_calls'] == expected)
        check('synthetic_' + name + '_separate_clocks', row['business_ns'] == 600
            and row['complete_session_ns'] == 900 and row['complete_client_calls_ns'] == expected * 100
            and row['server_request_windows_ns'] == expected * 80
            and row['client_flush_to_received_ns'] == expected * 90)
        check('synthetic_' + name + '_bytes_and_zero_forwarded_resources', row['actual_stdio_TX_bytes'] == expected * 10
            and row['actual_stdio_RX_bytes'] == expected * 20 and row['forwarded_resources'] == 0)
    for name, mutation, gate_name in (
        ('numeric_unknown', lambda docs, audit, result, record, gate, contracts:
            docs[result['requests'][0]['public_path']]['task_result']['facts']['surface_proximity'].update(status='unknown'),
            'requested_measurement'),
        ('missing_image', lambda docs, audit, result, record, gate, contracts: result['requests'][0].update(image_blocks=0),
            'actual_image_path'),
        ('zero_solver', lambda docs, audit, result, record, gate, contracts:
            docs[result['requests'][0]['producer']['path']]['work']['task_query'].update(surface_pair_count=0),
            'one_M3_pair'),
    ):
        def synchronized(docs, audit, result, record, gate, contracts):
            mutation(docs, audit, result, record, gate, contracts)
            # Preserve byte-consistent public text after the synthetic mutation.
            for request in result['requests']:
                text = json.dumps(docs[request['public_path']])
                request['response']['result']['content'] = [{'type': 'text', 'text': text}]
                request['public_text_UTF8_bytes'] = len(text.encode())
        row = collect(module, 'B1', synchronized)
        check(name + '_becomes_false_business_gate_without_collection_abort',
            evaluate(gate_nodes[gate_name], rows=[row], main=[row]) is False)
    failures = [
        ('wrong_source', lambda docs, audit, result, record, gate, contracts: result.update(source_sha256='wrong')),
        ('wrong_publication', lambda docs, audit, result, record, gate, contracts:
            docs[str(module.RUNTIME / 'formal/B1/PUBLICATION.json')].update(result_sha256='wrong')),
        ('wrong_query', lambda docs, audit, result, record, gate, contracts: contracts['B_main'].append({'extra': True})),
        ('wrong_deadline', lambda docs, audit, result, record, gate, contracts: result.update(original_owned_deadline_ns=999)),
    ]
    for name, mutation in failures:
        try:
            collect(module, 'B1', mutation)
        except ValueError:
            check(name + '_remains_hard_source_rejection', True)
        else:
            check(name + '_remains_hard_source_rejection', False)
    # Evaluate the actual source guard expressions without running main or reading runtime data.
    guard_calls = [node for node in ast.walk(main_node) if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name) and node.func.id == 'need']
    quality_guard = next(node.args[0] for node in guard_calls if isinstance(node.args[-1], ast.Constant)
        and node.args[-1].value == 'all_eight_unique_quality_rows')
    run_guard = next(node.args[0] for node in guard_calls if isinstance(node.args[-1], ast.Constant)
        and node.args[-1].value == 'original_eight_closed_slots')
    order = module.MAIN + module.CONTROLS
    for name, labels in [('empty', []), ('missing_tail', order[:-1]), ('extra_tail', order + ['B4']),
                         ('duplicate', order[:-1] + [order[0]]), ('reordered', order[::-1])]:
        quality = {'registered_order': order, 'slots': [{'label': label} for label in labels]}
        run = {'records': quality['slots'], 'retries': 0, 'replacement_samples': 0, 'not_run': [], 'blocker': None}
        check('quality_and_run_reject_' + name + '_before_zip',
            not evaluate(quality_guard, MAIN=module.MAIN, CONTROLS=module.CONTROLS, quality=quality)
            and not evaluate(run_guard, MAIN=module.MAIN, CONTROLS=module.CONTROLS, run=run))
    for name, b_values in [('two_faster', [90, 110, 90]), ('only_one_faster', [90, 110, 110]),
                            ('ties_not_faster', [100, 100, 100])]:
        pairs = [{'B_business_faster': value < 100} for value in b_values]
        check(name + '_uses_two_strict_faster_pairs',
            evaluate(gate_nodes['minimum_faster_pairs'], pairs=pairs, plan=plan) == (sum(value < 100 for value in b_values) >= 2))
    for denominator in (20, 1_000_000_000, 599_999_999_980):
        exact_boundary = denominator * 21 // 20
        for offset in (-1, 0, 1):
            numerator = exact_boundary + offset
            ratio = numerator / denominator
            expected = Fraction(numerator, denominator) <= Fraction(21, 20)
            check('1_05_boundary_' + str(denominator) + '_' + str(offset),
                evaluate(gate_nodes['business_median'], business_ratio=ratio, plan=plan) == expected
                and evaluate(gate_nodes['complete_session_median'], session_ratio=ratio, plan=plan) == expected)
    source = SOURCE.read_text(encoding='utf-8')
    check('fixed205_and_runtime_input_pins_revalidated', "pins(frozen['files'])" in source
        and "pins(runtime['input_pins'])" in source and "pins(quality['input_pins'])" in source)
    check('ten_percent_is_separate_from_acceptance_gates', 'engineering_business_10percent_benefit' not in gate_nodes
        and 'engineering_complete_10percent_benefit' not in gate_nodes
        and "business_ratio <= plan['gates']['engineering_time_benefit_separate_ratio_max']" in source)
    check('source_unchanged_during_review', pin(SOURCE) == source_pin)
    report = {'schema': 'm5-independent-cost-checker-review-v1',
        'passed_checked_scope': all(row['passed'] for row in CHECKS), 'reviewed_source': source_pin,
        'checks': CHECKS, 'check_count': len(CHECKS), 'passed_count': sum(row['passed'] for row in CHECKS),
        'reviewer_source': pin(__file__), 'initial_source_retained': pin(HERE / 'cost_decision_initial.py'),
        'correction_record': pin(HERE / 'COST_CHECKER_CORRECTION_01.json'),
        'author_association': 'Root authored reviewed cost_decision.py. This reviewer authored the independent checker, M5 product wiring, its unique optimization and final sealer. This is source review and synthetic verification, without a blind or independent-product-author claim.',
        'scope': 'Read only the cost source and fixed source metadata. In-memory collect fixtures and actual AST guard/formula expressions. Runtime four-clock and receipt authenticity are delegated to the passed, re-pinned RUNTIME_REVIEW dependency. No formal runtime numeric ranking was read or recomputed.',
        'new_operations': {'cost_main_executions': 0, 'formal_retries': 0, 'Blender_starts': 0,
            'MCP_processes': 0, 'rasters': 0, 'models': 0}}
    with (HERE / 'COST_CHECKER_REVIEW.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed': report['passed_checked_scope'], 'checks': len(CHECKS),
        'failed': [row['name'] for row in CHECKS if not row['passed']], 'source_sha256': source_pin['sha256']}))
    if not report['passed_checked_scope']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
