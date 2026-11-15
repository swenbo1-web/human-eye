"""One root-invoked fixed translation control in an owned unsaved copy."""
import argparse
import copy
import json
from pathlib import Path
import traceback

from run_case import EXTERNAL, HERE, NAMESPACE, Session, load, save, sha

STATE_SHA256 = 'e3c5e4fb9b21611fdb513e840a05aef4601dd82fad48c3679de4dead3d766a31'


def requests():
    path = NAMESPACE / 'STATE_REQUESTS.json'
    if sha(path) != STATE_SHA256:
        raise ValueError('frozen_state_requests_changed')
    value = load(path)
    return [(label, dict(copy.deepcopy(value['requests'][label]), id='m5_' + label))
            for label in value['order']]


def run(binding, output, ledger, label='B_state', session_class=Session):
    session = session_class(binding, output, ledger, 'qualification', label,
                            helper_path=HERE / 'state_owned_native.py')
    registered = []
    moved = restored = False
    completed = []
    receipts = []
    try:
        registered = requests()
        session.start()
        for stage, request in registered:
            if stage == 'matrix_changed_main_brief':
                receipts.append(session.native.m5_matrix_step('qa_m5_matrix_move'))
                moved = True
            if stage == 'restored_main_brief':
                receipts.append(session.native.m5_matrix_step('qa_m5_matrix_restore'))
                restored = True
            session.business([request], label=stage)
            completed.append(stage)
    except BaseException as error:
        session.errors.append(dict(stage='state_control', type=type(error).__name__,
                                   message=str(error), traceback=traceback.format_exc()))
    finally:
        if moved and not restored and session.native is not None:
            poisoned = session.output / 'native/POISONED.json'
            attempted = session.output / 'native/M5_MATRIX_RESTORE_ATTEMPT.json'
            if not poisoned.exists() and not attempted.exists():
                try:
                    receipts.append(session.native.m5_matrix_step('qa_m5_matrix_restore'))
                    restored = True
                except BaseException as error:
                    session.errors.append(dict(stage='planned_restore_during_failure_cleanup',
                                               type=type(error).__name__, message=str(error),
                                               traceback=traceback.format_exc()))
        control = dict(schema='m5-fixed-owned-matrix-control-v1', registered_request_sha256=STATE_SHA256,
            registered_order=[stage for stage, _ in registered], completed_order=completed,
            transport_sequence_complete=completed == [stage for stage, _ in registered],
            moved_confirmed=moved, restored_confirmed=restored, fixture_receipts=receipts,
            fixture_scope='fixed M4_Far_00 matrix +X .25 and restore in independent unsaved copy',
            product_setters=0, actual_fixture_matrix_setters=sum(
                row['response']['result']['test_matrix_setters'] for row in receipts),
            unknown_fixture_attempts_preserved=True, source_asset_saved=False,
            quality_scope='source, measurement, visibility and full/brief semantics require independent saved review')
        try:
            save(session.output / 'STATE_CONTROL.json', control)
        finally:
            result = session.close()
    return dict(result, state_control=control)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binding', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ledger', type=Path, default=EXTERNAL / 'budget')
    parser.add_argument('--label', default='B_state')
    args = parser.parse_args()
    result = run(args.binding, args.output, args.ledger, args.label)
    passed = result['passed_transport_scope'] and result['state_control']['transport_sequence_complete']
    print(json.dumps(dict(passed=passed, output=str(args.output), errors=result['errors'])))
    if not passed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
