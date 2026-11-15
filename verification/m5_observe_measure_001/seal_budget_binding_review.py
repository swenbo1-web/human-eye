"""Review the corrected sealer using synthetic guards and saved byte archives."""

import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'final_seal.py'


def pin(path):
    blob = Path(path).read_bytes()
    return {'path': str(Path(path).resolve()), 'sha256': hashlib.sha256(blob).hexdigest(), 'bytes': len(blob)}


def main():
    source_pin = pin(SOURCE)
    spec = importlib.util.spec_from_file_location('_m5_seal_budget_review', SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    tree = ast.parse(SOURCE.read_bytes(), filename=str(SOURCE))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == 'verify_budget_archive')
    loop = next(node for node in function.body if isinstance(node, ast.For))
    first = next(index for index, node in enumerate(loop.body) if isinstance(node, ast.Assign)
                 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == 'evidence')
    last = next(index for index, node in enumerate(loop.body) if isinstance(node, ast.Assign)
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id == 'original')
    guard = compile(ast.Module(body=loop.body[first:last], type_ignores=[]), str(SOURCE), 'exec')
    runtime = Path('D:/__M5_BUDGET_SYNTHETIC_ONLY__').resolve()
    checks = []

    def check(name, passed, detail=None):
        checks.append({'name': name, 'passed': bool(passed), 'detail': detail})

    def synthetic(label='B1', mutation=None):
        phase = 'formal' if label in module.ORDER else 'qualification'
        folder = runtime / ('control' if label == 'B_state' else phase) / label
        claim = {'token': 'synthetic-reservation', 'label': 'synthetic-rpc-id', 'phase': phase}
        settled = {'evidence': {'audit_path': str(folder / 'audit.jsonl')}}
        request = {'id': claim['label'], 'server': {'raster_reservation': claim['token']},
            'request': {'id': claim['label'], 'method': 'tools/call', 'params': {
                'name': 'human_eye_scene_observe', 'arguments': {'include_image': True,
                    'query': {'mode': 'active_observation'}}}}}
        documents = {str(folder / 'RESULT.json'): {'requests': [request]}}
        if mutation is not None:
            mutation(claim, settled, request, documents, folder)

        def read(path):
            if str(path) not in documents:
                raise AssertionError('unexpected synthetic source lookup')
            return copy.deepcopy(documents[str(path)])

        scope = {'Path': Path, 'RUNTIME': runtime, 'QUALIFICATIONS': module.QUALIFICATIONS,
            'ORDER': module.ORDER, 'claim': claim, 'settled': settled,
            'read': read, 'require': module.require}
        exec(guard, scope)
        return scope

    for label in ('A_qual', 'B_initial_qual', 'B_qual', 'B_state', 'A1', 'B1'):
        scope = synthetic(label)
        check('valid_phase_and_original_slot_' + label, scope['label'] == label)
    scope = synthetic(mutation=lambda claim, settled, request, docs, folder:
        request['request']['params']['arguments'].pop('include_image'))
    check('existing_default_true_image_contract_preserved', scope['arguments'].get('include_image', True) is True)

    def wrong_other_registered_slot(claim, settled, request, docs, folder):
        other = runtime / 'formal/B2'
        settled['evidence']['audit_path'] = str(other / 'audit.jsonl')
        different = copy.deepcopy(request)
        different['server']['raster_reservation'] = 'another-slot-token'
        docs[str(other / 'RESULT.json')] = {'requests': [different]}

    negative = [
        ('outside_runtime_audit', lambda c, s, q, d, f:
            s['evidence'].update(audit_path='D:/outside_m5/formal/B1/audit.jsonl')),
        ('unregistered_slot', lambda c, s, q, d, f:
            s['evidence'].update(audit_path=str(runtime / 'formal/B99/audit.jsonl'))),
        ('wrong_registered_slot_token', wrong_other_registered_slot),
        ('wrong_audit_filename', lambda c, s, q, d, f:
            s['evidence'].update(audit_path=str(f / 'other.jsonl'))),
        ('wrong_phase', lambda c, s, q, d, f: c.update(phase='qualification')),
        ('wrong_token', lambda c, s, q, d, f: q['server'].update(raster_reservation='wrong-token')),
        ('wrong_rpc_id', lambda c, s, q, d, f: q.update(id='wrong-id')),
        ('duplicate_token_match', lambda c, s, q, d, f:
            d[str(f / 'RESULT.json')]['requests'].append(copy.deepcopy(q))),
        ('no_token_match', lambda c, s, q, d, f: d[str(f / 'RESULT.json')].update(requests=[])),
        ('image_false', lambda c, s, q, d, f: q['request']['params']['arguments'].update(include_image=False)),
        ('wrong_mode', lambda c, s, q, d, f: q['request']['params']['arguments']['query'].update(mode='task')),
        ('wrong_tool', lambda c, s, q, d, f: q['request']['params'].update(name='other-tool')),
        ('wrong_method', lambda c, s, q, d, f: q['request'].update(method='other-method')),
    ]
    for name, mutation in negative:
        try:
            synthetic(mutation=mutation)
        except AssertionError as error:
            check('reject_' + name, True, str(error))
        else:
            check('reject_' + name, False)
    check('original_string_token_comparison_without_protocol_change',
        "row['server'].get('raster_reservation') == claim['token']" in SOURCE.read_text(encoding='utf-8'))
    actual = module.verify_budget_archive()
    check('saved_originals_and_archive_remain_byte_exact', actual['runtime_archive_files'] == 1288
        and actual['runtime_archive_bytes'] == 30355846 and actual['original_runtime_retained'] is True)
    check('saved_budget_twelve_owned_thirteen_actual_rasters', actual['owned_starts'] == 12
        and actual['qualification_and_state_rasters'] == 7 and actual['formal_rasters'] == 6
        and actual['total_rasters'] == 13 and actual['pending_attempt_reservations'] == 0)
    check('reviewed_source_stable', pin(SOURCE) == source_pin)
    report = {'schema': 'm5-seal-budget-binding-review-v1',
        'passed_checked_scope': all(row['passed'] for row in checks), 'reviewed_source': source_pin,
        'checks': checks, 'check_count': len(checks), 'passed_count': sum(row['passed'] for row in checks),
        'saved_budget_archive_result': actual, 'reviewer_source': pin(__file__),
        'input_pins': [pin(HERE / name) for name in (
            'RUNTIME_ARCHIVE.json', 'final_seal_initial.py', 'FINAL_SEAL_CORRECTION_01.json')],
        'author_association': 'This reviewer authored the initial sealer and M5 product wiring. Root authored the corrected budget-binding block. This review independently checks that correction using source-extracted synthetic guards and saved archive verification.',
        'actual_field_contract': 'Blender_start labels are owned slot labels. Raster_request labels are stringified JSON-RPC IDs. server.raster_reservation contains the token string, not a token object. The actual audit path identifies the owned slot, and its original RESULT provides a unique current request-token match.',
        'first_readonly_probe_correction': 'The first diagnostic probe assumed a token object and raised AttributeError on the actual string. A second read-only probe established the existing string contract. No original bytes were changed.',
        'limitations': ['Source-extracted guard tests cover budget path/phase/token/RPC metadata and active-image arguments. Whole-seal verify_sources/verify_results and the passed runtime audit separately bind complete RESULT/publication/request bytes.',
            'The only sealer function executed here is verify_budget_archive. No whole seal, archive copy, source edit or actual runtime operation is performed.'],
        'new_operations': {'whole_seal': 0, 'archive_copies': 0, 'Blender_starts': 0, 'MCP_processes': 0,
            'rasters': 0, 'models': 0, 'product_changes': 0}}
    with (HERE / 'SEAL_BUDGET_BINDING_REVIEW.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed_checked_scope': report['passed_checked_scope'], 'checks': len(checks),
        'source_sha256': source_pin['sha256'], 'report_sha256': pin(HERE / 'SEAL_BUDGET_BINDING_REVIEW.json')['sha256']}))
    if not report['passed_checked_scope']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
