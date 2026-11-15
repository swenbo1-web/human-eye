"""Root-only fixed six formal slots and two task-only controls, once."""
import argparse
import json
from pathlib import Path
import time
import traceback

from run_case import EXTERNAL, NAMESPACE, Budget, load, run, save, sha, verify_install

MAIN_ORDER = ['A1', 'B1', 'B2', 'A2', 'A3', 'B3']
CONTROLS = ['A_task_only', 'B_task_only']


def validate_pins(pins):
    if not isinstance(pins, list) or not pins:
        raise ValueError('formal_source_evidence_pins_required')
    for row in pins:
        path = Path(row['path'])
        if path.stat().st_size != row['bytes'] or sha(path) != row['sha256']:
            raise ValueError('formal_source_or_qualification_pin_changed:' + str(path))


def validate_gate(gate):
    if (gate.get('formal_allowed') is not True or gate['formal_order'] != MAIN_ORDER
            or gate['task_only_controls'] != CONTROLS):
        raise ValueError('root_formal_gate_or_fixed_order_rejected')
    for field, name in [('plan_sha256', 'PLAN.json'), ('requests_sha256', 'REQUESTS.json'),
                        ('STATE_REQUESTS_sha256', 'STATE_REQUESTS.json')]:
        if sha(NAMESPACE / name) != gate[field]:
            raise ValueError('formal_registered_contract_changed:' + name)
    validate_pins(gate['harness_pins'])
    validate_pins(gate['qualification_pins'])
    bindings = {}
    for arm in ('A', 'B'):
        row = gate[arm + '_binding']
        if sha(row['path']) != row['sha256']:
            raise ValueError('formal_binding_changed:' + arm)
        binding = load(row['path'])
        if binding['source_sha256'] != row['source_sha256']:
            raise ValueError('formal_binding_source_changed:' + arm)
        verify_install(binding)
        bindings[arm] = row['path']
    return bindings


def summarize(folder):
    result = load(folder / 'RESULT.json')
    publication = load(folder / 'PUBLICATION.json')
    if publication['result_sha256'] != sha(folder / 'RESULT.json'):
        raise ValueError('actual_publication_result_hash_changed')
    if publication['complete_session_ns'] != publication['result_published_ns'] - result['started_ns']:
        raise ValueError('actual_complete_session_clock_mismatch')
    window = result['business_windows'][0]
    return dict(passed_transport_scope=publication['passed_transport_scope'], errors=result['errors'],
        source_sha256=result['source_sha256'], complete_session_ns=publication['complete_session_ns'],
        business_ns=window['continuous_business_ns'], owned_lifecycle_ns=result['owned_lifecycle_ns'],
        started_ns=result['started_ns'], result_published_ns=publication['result_published_ns'],
        requests=[dict(id=row['id'], complete_client_call_ns=row['complete_client_call_ns'],
            client_flush_to_received_ns=row['client_flush_to_received_ns'],
            client_internal_pre_receipt_ns=row['client_internal_pre_receipt_ns'],
            server_request_to_reply_ns=row['server']['request_to_reply_ns'],
            actual_stdio_TX_bytes=row['receipt']['TX_bytes'], actual_stdio_RX_bytes=row['receipt']['RX_bytes'],
            server_LF_text_bytes=row['server']['RX_text_UTF8_LF_bytes'],
            public_text_UTF8_bytes=row['public_text_UTF8_bytes'], image_blocks=row['image_blocks'])
            for row in result['requests']])


def execute(gate_path, output, ledger):
    gate_path, output = Path(gate_path).resolve(), Path(output).resolve()
    if not output.is_relative_to(EXTERNAL.resolve()):
        raise ValueError('formal_output_outside_M5_runtime')
    gate = load(gate_path)
    bindings = validate_gate(gate)
    budget = Budget(ledger)
    before = budget.snapshot()
    counts = before['counts']
    if counts != gate['budget_before']['counts']:
        raise ValueError('formal_gate_budget_state_changed')
    if (counts['Blender_start_attempts'] + 8 > 12 or counts['Blender_spawned_unknown']
            or counts['pending_raster_reservations'] or counts['formal_raster_upper']
            or counts['all_raster_upper'] + 36 > 72):
        raise ValueError('formal_remaining_or_unknown_budget_rejected')
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter_ns()
    intent = dict(schema='m5-formal-once-v1', started_ns=started, gate_path=str(gate_path),
        gate_sha256=sha(gate_path), main_order=MAIN_ORDER, task_only_controls=CONTROLS,
        A_binding=gate['A_binding'], B_binding=gate['B_binding'], budget_before=before,
        formal_samples=6, task_only_samples=2, retries=0, replacement_samples=0,
        model_consumers=0, paid_API_calls=0)
    save(EXTERNAL / 'FORMAL_ONCE.json', intent)
    save(output / 'INTENT.json', intent)
    records = []
    blocker = None
    schedule = [(label, label[0] + '_main') for label in MAIN_ORDER]
    schedule += [(label, 'task_only') for label in CONTROLS]
    for label, request_key in schedule:
        folder = output / label
        dispatch = dict(label=label, arm=label[0], request_key=request_key, output=str(folder),
                        dispatched_ns=time.perf_counter_ns(), attempt=1)
        try:
            validate_pins(gate['harness_pins'])
            validate_pins(gate['qualification_pins'])
            save(output / ('DISPATCH_' + label + '.json'), dispatch)
            run(bindings[label[0]], folder, ledger, 'formal', label, request_key)
            record = dict(dispatch, result=summarize(folder))
            records.append(record)
            save(output / ('SLOT_' + label + '.json'), record)
            if not record['result']['passed_transport_scope']:
                blocker = dict(label=label, stage='actual_transport_or_cleanup_failure')
                break
        except BaseException as error:
            blocker = dict(label=label, stage='dispatch_or_saved_publication_failure',
                           type=type(error).__name__, message=str(error), traceback=traceback.format_exc())
            save(output / ('FAILURE_' + label + '.json'), blocker)
            break
    result = dict(schema='m5-formal-dispatch-result-v1', started_ns=started,
        closed_ns=time.perf_counter_ns(), gate_sha256=sha(gate_path), records=records,
        dispatched=len(list(output.glob('DISPATCH_*.json'))), completed_records=len(records),
        not_run=[label for label, _ in schedule if not (output / ('DISPATCH_' + label + '.json')).exists()],
        blocker=blocker, retries=0, replacement_samples=0,
        all_eight_transport_closed=blocker is None and len(records) == 8,
        budget_after=budget.snapshot(),
        quality_and_timing_gate='Independent saved review computes paired main gates after all fixed slots. Task-only controls are one diagnostic pair.')
    save(output / 'RUN_RESULT.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gate', type=Path, default=NAMESPACE / 'FORMAL_GATE.json')
    parser.add_argument('--output', type=Path, default=EXTERNAL / 'formal')
    parser.add_argument('--ledger', type=Path, default=EXTERNAL / 'budget')
    args = parser.parse_args()
    result = execute(args.gate, args.output, args.ledger)
    print(json.dumps(dict(passed=result['all_eight_transport_closed'], dispatched=result['dispatched'],
                          completed_records=result['completed_records'], blocker=result['blocker'])))
    if not result['all_eight_transport_closed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
