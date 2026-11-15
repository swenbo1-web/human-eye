"""Fixed dispatch and failure mocks without any product/native startup."""
import ast
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_formal


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True)+'\n', encoding='utf8')


def pin(path):
    return dict(path=str(path.resolve()), sha256=run_formal.sha(path), bytes=path.stat().st_size)


def mock_snapshot():
    return dict(counts=dict(Blender_start_attempts=4, Blender_spawned_unknown=0,
        pending_raster_reservations=0, formal_raster_upper=0, all_raster_upper=6))


class Budget:
    def __init__(self, ledger):
        pass

    def snapshot(self):
        return mock_snapshot()


def main():
    root = HERE.parent / 'FORMAL_STATIC_CHECKS'
    root.mkdir(exist_ok=False)
    checks = []

    def check(name, condition):
        checks.append(dict(name=name, passed=bool(condition)))
        if not condition:
            raise ValueError(name)

    ast.parse((HERE / 'run_formal.py').read_text())
    a, b = root / 'A.json', root / 'B.json'
    write(a, dict(source_sha256='A'))
    write(b, dict(source_sha256='B'))
    gate = dict(formal_allowed=True, formal_order=run_formal.MAIN_ORDER,
        task_only_controls=run_formal.CONTROLS,
        A_binding=dict(path=str(a.resolve()), sha256=run_formal.sha(a), source_sha256='A'),
        B_binding=dict(path=str(b.resolve()), sha256=run_formal.sha(b), source_sha256='B'),
        harness_pins=[pin(HERE / 'run_formal.py')],
        qualification_pins=[pin(HERE.parent / 'STATE_STATIC_CHECKS/RESULT.json')],
        plan_sha256=run_formal.sha(HERE.parent / 'PLAN.json'),
        requests_sha256=run_formal.sha(HERE.parent / 'REQUESTS.json'),
        STATE_REQUESTS_sha256=run_formal.sha(HERE.parent / 'STATE_REQUESTS.json'),
        budget_before=mock_snapshot())
    gate_path = root / 'GATE.json'
    write(gate_path, gate)
    run_formal.verify_install = lambda binding: None
    run_formal.Budget = Budget
    calls = []
    fail = [None]

    def run(binding, folder, ledger, phase, label, request_key):
        calls.append((label, request_key))
        if label == fail[0]:
            raise OSError('mock_slot_failure')
        folder.mkdir()
        request = dict(id='mock', complete_client_call_ns=10, client_flush_to_received_ns=8,
            client_internal_pre_receipt_ns=9, server=dict(request_to_reply_ns=7, RX_text_UTF8_LF_bytes=20),
            receipt=dict(TX_bytes=10, RX_bytes=21), public_text_UTF8_bytes=12, image_blocks=0)
        result = dict(started_ns=100, errors=[], source_sha256=label[0],
            business_windows=[dict(continuous_business_ns=10)], owned_lifecycle_ns=18,
            requests=[request])
        write(folder / 'RESULT.json', result)
        write(folder / 'PUBLICATION.json', dict(result_sha256=run_formal.sha(folder / 'RESULT.json'),
            complete_session_ns=20, result_published_ns=120, passed_transport_scope=True))

    run_formal.run = run
    run_formal.EXTERNAL = root / 'success'
    run_formal.EXTERNAL.mkdir()
    result = run_formal.execute(gate_path, run_formal.EXTERNAL / 'formal', root / 'unused_ledger')
    expected = [(label, label[0] + '_main') for label in run_formal.MAIN_ORDER]
    expected += [(label, 'task_only') for label in run_formal.CONTROLS]
    check('fixed eight-slot order and exact request keys', calls == expected)
    check('once complete dispatch no retry or replacement', result['all_eight_transport_closed']
          and result['dispatched'] == 8 and result['retries'] == 0 and result['replacement_samples'] == 0)
    try:
        run_formal.execute(gate_path, run_formal.EXTERNAL / 'second_formal', root / 'unused_ledger')
    except FileExistsError:
        check('second outer execution rejected before slot dispatch', len(calls) == 8)
    else:
        raise ValueError('outer replay was accepted')
    calls.clear()
    fail[0] = 'B1'
    run_formal.EXTERNAL = root / 'failed'
    run_formal.EXTERNAL.mkdir()
    result = run_formal.execute(gate_path, run_formal.EXTERNAL / 'formal', root / 'unused_ledger')
    check('actual entry failure preserved without redispatch', calls == [('A1', 'A_main'), ('B1', 'B_main')]
          and result['dispatched'] == 2 and result['completed_records'] == 1 and result['blocker']['label'] == 'B1')
    check('remaining six explicitly not run', result['not_run'] == ['B2', 'A2', 'A3', 'B3', 'A_task_only', 'B_task_only'])
    invalid = dict(gate, formal_order=list(reversed(run_formal.MAIN_ORDER)))
    try:
        run_formal.validate_gate(invalid)
    except ValueError as error:
        check('changed registered order precisely rejected', str(error) == 'root_formal_gate_or_fixed_order_rejected')
    else:
        raise ValueError('changed order accepted')
    report = dict(schema='m5-formal-dispatch-static-v1', passed=True, checks=checks,
        input_pins=[pin(Path(__file__)), pin(HERE / 'run_formal.py'), pin(HERE / 'run_case.py')],
        actual_owned_starts=0, actual_MCP_starts=0, actual_rasters=0,
        scope='All slots, budgets, source identities and clocks in these checks are mocks. Actual qualification gate and installed source checks remain root-only prerequisites.')
    path = root / 'RESULT.json'
    write(path, report)
    print(json.dumps(dict(passed=True, checks=len(checks), path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())))


if __name__ == '__main__':
    main()
