"""One owned Blender slot for reference-only focus, using the frozen production MCP."""
import argparse
import importlib.util
from pathlib import Path
import subprocess
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
EARLIER = HERE.parent / 'm4_task_region_focus_feedback_001'
SOURCE_RUNNER = EARLIER / 'runner.py'
spec = importlib.util.spec_from_file_location('reference_only_prior_focus_runner', SOURCE_RUNNER)
pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)
prior = pipeline.prior
need, read, save, pin, confirm, digest = (pipeline.need, pipeline.read, pipeline.save, pipeline.pin,
                                         pipeline.confirm, pipeline.digest)
BATCH = 'M4-REFERENCE-ONLY-INTENT-HOLDOUT-001'
ADMIN_SHA = '28668b2018d7abc17bfcdc056797f5589c34f7afc8c571f6d2012b5a77cb0f6a'
PRODUCT = 'b7fe4bb0dc2ce277ff5dd7a6198365253b716c09'
CUSTODY_SHA = '004211486086650514d2c586cbf617bea3bd5a017fd2ede8384c81a420768e11'
HELPER_PINS = (
    (SOURCE_RUNNER, 'a764199d0c08312bea8c66c6f75748ba11dd4407a8a3af6e571f5ee833550118'),
    (EARLIER / 'worker_wire.py', '7c28595dfeb1b48e317cc40aa404efe5de91bf6e182184bf6b16d69377cb3dc0'),
    (pipeline.PRIOR, '3fd1a0ffa770c043c8d1d29083bedcf6901c6a000545b50014d4f0889a89ba5f'),
)
SLOT = 'DIAGNOSTIC'
CASE_NAMES = (('K', 'Fixture K'), ('T', 'Fixture T'))
TARGET_NAME = 'Part M'


def prepare(root):
    admin = root / 'preflight/ADMIN_PLAN.md'
    need(root.name == BATCH and digest(admin) == ADMIN_SHA
         and sys.flags.isolated and sys.dont_write_bytecode, 'wrong_batch_or_interpreter')
    support = [pin(path) for path, expected in HELPER_PINS]
    need([value['sha256'] for value in support] == [expected for _, expected in HELPER_PINS],
         'previous_actual_dispatcher_changed')
    earlier_root = root.parent / 'M4-TASK-REGION-FOCUS-FEEDBACK-001'
    receipt = earlier_root / 'preflight/CANDIDATE_INSTALL_CUSTODY.json'
    need(digest(receipt) == CUSTODY_SHA, 'installed_product_receipt_changed')
    product = read(receipt)
    need(product['passed'] is True and product['candidate_commit'] == PRODUCT
         and product['runtime_sources'] == 146 and product['python']['sha256'] == pipeline.PYTHON
         and product['blender']['sha256'] == pipeline.BLENDER
         and Path(sys.executable).resolve() == Path(product['python']['path']), 'wrong_owned_installed_runtime')
    for field in ('blender', 'python', 'build', 'wheel'):
        confirm(product[field])
    for value in product['dependencies'].values():
        confirm(value['module'])
    site = Path(product['installation']['path']).resolve(strict=True)
    fixture = root / 'preflight/fixture/main.blend'
    rows = []
    for index, (key, reference) in enumerate(CASE_NAMES, 3):
        focus = {'task_region': {'reference': {'name': reference}}}
        query = {'mode': 'active_observation', 'objects': [{'name': TARGET_NAME}], 'focus': focus}
        rows.append({'id': index, 'label': key, 'arguments': {'query': query, 'include_image': True,
                                                             'response_detail': 'full'}})
    job = {'asset': 'synthetic_reference_only', 'arm': 'task', 'fixture': pin(fixture),
           'candidate_site': str(site), 'candidate_source_sha256': product['source_sha256'],
           'runtime_sources': product['source_manifest'], 'candidate_commit': PRODUCT, 'requests': rows}
    return {'batch': BATCH, 'order': [SLOT], 'jobs': {SLOT: job},
            'inputs': [pin(admin), pin(receipt), pin(Path(__file__)), *support],
            'blender': product['blender'], 'python': product['python'],
            'budget': {'formal_blender': 1, 'business_requests': 2, 'max_rasters_per_request': 2,
                       'whole_slot_window_ns': prior.LIMIT_NS, 'models': 0, 'substitutes': 0}}


def frozen(root):
    plan = read(root / 'preflight/DIAGNOSTIC_PLAN.json')
    need(plan == prepare(root), 'diagnostic_plan_drift')
    return plan


def require_authorized_freeze(root):
    final_path = root / 'preflight/FROZEN_EXECUTION.json'
    final = read(final_path)
    cold_path = root / 'preflight/DIAGNOSTIC_COLD.json'
    plan_path = root / 'preflight/DIAGNOSTIC_PLAN.json'
    need(final['batch'] == BATCH and final['diagnostic_plan'] == pin(plan_path)
         and final['diagnostic_cold'] == pin(cold_path), 'diagnostic_missing_from_unified_freeze')
    gate = read(cold_path)
    need(gate['passed'] is True and gate['launches'] == 0 and gate['plan'] == pin(plan_path)
         and gate['slot'] == SLOT and gate['exit'] == 0, 'diagnostic_cold_gate_wrong')
    for item in gate['receipts']:
        confirm(item)
    return pin(final_path)


def child_args(root, slot, mode):
    return [sys.executable, '-IB', '-X', 'utf8', str(Path(__file__).resolve()), str(root), 'worker', slot, mode]


observed_registry = pipeline.observed_registry


def preflight_registry(folder, service, run_stdio, job):
    for request in job['requests']:
        case = folder / ('case_' + request['label'])
        case.mkdir()
        observed_registry(case, service, run_stdio, {**job, 'requests': [request]})


def run_cold(root):
    plan = frozen(root)
    folder = root / 'preflight/cold' / SLOT
    folder.mkdir(parents=True)
    failure = None
    try:
        result = subprocess.run(child_args(root, SLOT, 'cold'), cwd=folder, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=prior.process_env(),
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), timeout=40)
        exit_code, output, errors = result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as error:
        exit_code, output, errors = None, error.stdout or b'', error.stderr or b''
        failure = 'cold_process_timeout'
    stdout = folder / 'stdout.bin'
    stderr = folder / 'stderr.bin'
    stdout.write_bytes(output)
    stderr.write_bytes(errors)
    appointment = folder / 'AT_APPOINTMENT.json'
    actual_launches = int((folder / 'Blender_SPAWN.json').exists())
    passed = exit_code == 0 and not output and not actual_launches and appointment.is_file()
    if passed:
        mark = read(appointment)
        passed = (mark['attempt'] is False and mark['geometry_preflight_reads'] == 0
                  and mark['fixture']['sha256'] == plan['jobs'][SLOT]['fixture']['sha256'])
    receipts = [stdout, stderr]
    receipts.extend(path for path in [appointment, *(folder / ('case_' + label) / name
                    for label, _ in CASE_NAMES for name in
                    ('REGISTRY.tx', 'REGISTRY.rx', 'REGISTRY_SERVICE.json'))] if path.is_file())
    passed = passed and len(receipts) == 9
    save(root / 'preflight/DIAGNOSTIC_COLD.json',
         {'passed': passed, 'launches': actual_launches, 'slot': SLOT,
          'exit': exit_code, 'failure': failure, 'plan': pin(root / 'preflight/DIAGNOSTIC_PLAN.json'),
          'receipts': [pin(path) for path in receipts]})
    return int(not passed)


def run_formal(root):
    settings = frozen(root)
    freeze = require_authorized_freeze(root)
    began = time.perf_counter_ns()
    receipt = {'order': [SLOT], 'freeze': freeze, 'started_ns': began,
               'max_Blender': 1, 'max_business': 2, 'max_rasters_per_request': 2}
    save(root / 'FORMAL_START.json', receipt)
    (root / 'slots').mkdir(exist_ok=True)
    ledger = {}
    failure = None
    try:
        ledger = pipeline.run_slot(root, SLOT, settings)
    except BaseException as error:
        failure = {'type': type(error).__name__, 'reason': str(error), 'traceback': traceback.format_exc()}
    finally:
        folder = root / 'slots' / SLOT
        pass_evidence = ledger.get('status') == 'closed'
        files = ('ledger.json', 'ready.json', 'closed.json', 'post_capture.json', 'WORKER_ADMISSION.json',
                 'Blender_RESERVATION.json', 'Blender_SPAWN.json', 'REGISTERED.json',
                 'producer_03.json', 'producer_04.json', 'construction_03.json', 'construction_04.json',
                 'worker_wire/INDEX.json', 'worker_wire/TX.bin', 'worker_wire/RX.bin',
                 '01-init.tx', '01-init.rx', '02-tools.tx', '02-tools.rx',
                 '03-K.tx', '03-K.rx', '04-T.tx', '04-T.rx')
        raw_pins = {name: pin(folder / name) for name in files if (folder / name).is_file()}
        save(root / 'DIAGNOSTIC_EXECUTION.json', {'batch': BATCH, 'freeze': freeze, 'slot': SLOT,
             'status': 'closed' if pass_evidence else 'failed', 'ledger': ledger, 'failure': failure,
             'first_dispatch_ns': began, 'closed_ns': time.perf_counter_ns(), 'raw': raw_pins,
             'Blender_launches': int((folder / 'Blender_SPAWN.json').is_file()), 'model_calls': 0, 'substitutes': 0})
    return int(not pass_evidence)


pipeline.frozen = frozen
pipeline.observed_registry = preflight_registry
prior.child_args = child_args

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=lambda x: Path(x).resolve(strict=True))
    parser.add_argument('action', choices=('plan', 'cold', 'formal', 'worker'))
    parser.add_argument('slot', nargs='?', choices=(SLOT,))
    parser.add_argument('mode', nargs='?', choices=('formal', 'cold'))
    options = parser.parse_args()
    if options.action == 'plan':
        save(options.root / 'preflight/DIAGNOSTIC_PLAN.json', prepare(options.root))
    elif options.action == 'cold':
        raise SystemExit(run_cold(options.root))
    elif options.action == 'formal':
        raise SystemExit(run_formal(options.root))
    else:
        need(options.slot == SLOT and options.mode is not None, 'slot_required_for_worker')
        if options.mode == 'formal':
            require_authorized_freeze(options.root)
        raise SystemExit(pipeline.worker(options.root, SLOT, options.mode))
