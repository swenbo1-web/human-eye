"""Saved operator-stop and synthetic failure-policy review; never run a seal."""

import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'final_seal.py'


def pin(path):
    data = Path(path).read_bytes()
    return {'path': str(Path(path).resolve()), 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}


def main():
    source_pin = pin(SOURCE)
    spec = importlib.util.spec_from_file_location('_m5_task_saved_seal_review', SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    run = module.read(module.RUNTIME / 'RUN_RESULT.json')
    checks = []

    def check(name, passed, detail=None):
        checks.append({'name': name, 'passed': bool(passed), 'detail': detail})

    saved = module.verify_operator_stop(run, {'passed_frozen_gates': False})
    check('actual_operator_stop_and_raw_harness_loss_source_verified', saved['operator_stop_present']
        and saved['stopped_unstarted_slot'] == 'B3' and saved['workflow_positive_signal_permitted'] is False)
    for name, changed_run, decision in (
        ('positive_signal', run, {'passed_frozen_gates': True}),
        ('fabricated_sixth_consumer', dict(run, actual_consumers=6), {'passed_frozen_gates': False}),
    ):
        try:
            module.verify_operator_stop(changed_run, decision)
        except AssertionError:
            check('reject_' + name, True)
        else:
            check('reject_' + name, False)
    wrong = copy.deepcopy(run)
    wrong['records'][-1].update(status='completed', result_path='fabricated')
    try:
        module.verify_operator_stop(wrong, {'passed_frozen_gates': False})
    except AssertionError:
        check('reject_fabricated_B3_result', True)
    else:
        check('reject_fabricated_B3_result', False)
    original_exists = Path.exists

    def fabricated_public(path):
        if path == module.RUNTIME / 'formal/B3/consumer/PUBLIC_FINAL.txt':
            return True
        return original_exists(path)

    with patch.object(Path, 'exists', fabricated_public):
        try:
            module.verify_operator_stop(run, {'passed_frozen_gates': False})
        except AssertionError:
            check('reject_fabricated_B3_answer', True)
        else:
            check('reject_fabricated_B3_answer', False)
    absent, state = module.optional_json(module.RUNTIME / 'formal/B3/consumer/CONSUMER.json')
    check('unstarted_B3_consumer_remains_missing', absent is None and state == 'missing')
    tree = ast.parse(SOURCE.read_bytes(), filename=str(SOURCE))
    checks_by_label = {}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'require'
                and len(node.args) == 2 and isinstance(node.args[1], ast.Constant)):
            checks_by_label[node.args[1].value] = node.args[0]

    def evaluate(label, **values):
        return eval(compile(ast.Expression(checks_by_label[label]), str(SOURCE), 'eval'), values)

    check('failed_runtime_audit_acceptance_is_rejected', evaluate('failed runtime audit cannot accept candidate',
        review={'passed_checked_scope': False}, decision={'passed_frozen_gates': True}) is False)
    check('failed_runtime_audit_can_be_honestly_sealed', evaluate('failed runtime audit cannot accept candidate',
        review={'passed_checked_scope': False}, decision={'passed_frozen_gates': False}) is True)
    check('unknown_attempts_reject_positive_candidate', evaluate('unknown original attempts cannot pass candidate gates',
        checks={'unconfirmed_original_attempts': [{}], 'passed_frozen_business_gates': True}) is False)
    check('unknown_attempts_preserved_with_negative_gate', evaluate('unknown original attempts cannot pass candidate gates',
        checks={'unconfirmed_original_attempts': [{}], 'passed_frozen_business_gates': False}) is True)
    check('incomplete_denominator_rejects_positive_gate', evaluate('incomplete consumer denominator cannot pass candidate gates',
        run={'actual_consumers': 5}, decision={'passed_frozen_gates': True}) is False)
    check('source_stable_during_saved_review', pin(SOURCE) == source_pin)
    report = {'schema': 'm5-task-seal-preparation-review-v1',
        'passed_checked_scope': all(row['passed'] for row in checks), 'reviewed_source': source_pin,
        'checks': checks, 'check_count': len(checks), 'passed_count': sum(row['passed'] for row in checks),
        'saved_operator_stop_result': saved, 'reviewer_source': pin(__file__),
        'input_pins': [pin(path) for path in (module.RUNTIME / 'RUN_RESULT.json',
            module.RUNTIME / 'ROOT_OPERATOR_STOP.json', module.RUNTIME / 'formal/B3/ROOT_OPERATOR_STOP.json',
            HERE / 'A1_ARCHIVE_CORRELATION_DIAGNOSIS.json')],
        'author_association': 'Reviewer authored this sealer and the common bridge. Root authored the operator stop and independently accepted the runtime-author diagnosis. This review verifies saved source/error-delivery evidence and explicit failure policy.',
        'scope': 'The only sealer helper run on originals is verify_operator_stop. Original successful MCP replies and outer harness errors are checked without grading answers or ranking formal costs.',
        'pending': ['All-five answer quality and quality seal, full runtime audit, negative DECISION and root REPORT must be present before archive or whole seal.',
            'Full protected-manifest/source/archive verification remains deferred to the root-approved final seal.'],
        'new_actual_operations': {'Blender_starts': 0, 'MCP_processes': 0, 'rasters': 0,
            'model_consumers': 0, 'archive_copies': 0, 'whole_seal': 0}}
    with (HERE / 'SEAL_PREPARATION_REVIEW.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed': report['passed_checked_scope'], 'checks': len(checks),
        'source_sha256': source_pin['sha256'], 'report_sha256': pin(HERE / 'SEAL_PREPARATION_REVIEW.json')['sha256']}))
    if not report['passed_checked_scope']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
