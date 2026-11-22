"""Freeze the real entries and spend each registered real slot at most once."""

import argparse
import ast
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys
import time
from zipfile import ZipFile


NS = Path(__file__).resolve().parent
V = NS.parent
sys.path[:0] = [str(NS / 'harness'), str(NS / 'qualification'), str(NS)]
import admission
from admission import require
from common import (ASSET, BLENDER, EXTERNAL, FORMAL_LABELS, GENERIC_WORKER, ORDER,
                    PRODUCT_BINDING, PRODUCT_SCHEMA, ROOT, SEAL, SLOTS, append, read, save, sha)


BASE = '3ccea33b8ed50d50dceab8729c4aef1530827b1e'
PLAN = '684db7f225d9b4d8e59b9da21a9fd7aada63fada:docs/M4_DENSE_SWEEP_INTEGRATED_NATIVE_PILOT_001_PLAN.md'
PRIOR = '19c4333ccf0e135db24edc593edd8a10d78908eb:verification/m1_region_task_first_packet_consumption_holdout_recovery_001/inputs/PROMPT.txt'
PROMPT_SHA = '254f79b43eaf77a305a2372a77f26454a3aac75882591b845533ca6c805ce771'
REOPEN_SHA = '0ced1d8185dfbeb3ef3540f8a568c0f055d791196f56431ec611db25dcd21072'
TRUTH_SHA = 'b44d0a75376667b7abf8c12d023dd67180086b5fba77653e3972edd84f7ee5f8'
ASSET_SHA = '219541e921666ddf6c406507afb5e59168415a14b8ea7b3d8eca28c6dacbe12f'
QUALIFICATION = ('QN', 'QP')
ORDINARY = {'execute_blender_code', 'execute_python', 'read_images', 'render_local', 'render_views'}


def command(entry, *args):
    return [sys.executable, '-IB', '-X', 'utf8', str(NS / entry), *args]


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def freeze(reports):
    spec = NS / 'FROZEN.json'
    require(not spec.exists() and not (EXTERNAL / 'slots').exists(), 'one_fresh_dense_sweep_freeze_required')
    namespace = NS.relative_to(ROOT).as_posix() + '/'
    require(git('merge-base', BASE, 'HEAD').decode().strip() == BASE
            and all(path.startswith(namespace) for path in git('diff', '--name-only', BASE).decode().splitlines()),
            'zero_product_delta_required')
    prompt = NS / 'inputs/PROMPT.txt'
    require((NS / 'PLAN.md').read_bytes() == git('show', PLAN)
            and prompt.read_bytes() == git('show', PRIOR) and sha(prompt) == PROMPT_SHA
            and prompt.stat().st_size == 1072, 'fixed_plan_or_original_question_changed')
    reopened, truth = (ASSET.with_name(name) for name in ('REOPEN.json', 'TRUTH.json'))
    require(sha(ASSET) == ASSET_SHA and ASSET.stat().st_size == 102540
            and sha(reopened) == REOPEN_SHA and sha(truth) == TRUTH_SHA, 'sealed_asset_or_source_changed')
    require(read(truth)['counts'] == {'objects':20, 'vertices':3502, 'triangles':6160},
            'sealed_dense_asset_roster_changed')

    pins = {}

    def pin(path, expected=None):
        path = Path(path).resolve(strict=True)
        if path not in pins:
            pins[path] = {'path':str(path), 'bytes':path.stat().st_size, 'sha256':sha(path)}
        require(expected is None or all(pins[path][field] == expected[field] for field in ('bytes', 'sha256')),
                f'freeze_input_mismatch/{path}')

    for report in reports:
        report = report.resolve(strict=True)
        proof = read(report)
        require(proof['passed'] is True, f'actual_preflight_failed/{report}')
        pin(report)
        for row in proof.get('source_pins', []):
            pin(row['path'], row)
    runtime = read(NS / 'harness/RUNTIME_PREFLIGHT.json')
    cells = runtime['cells']
    require(runtime['passed'] is True and runtime['actual_Blender_starts'] == runtime['actual_model_starts'] == 0
            and set(cells) == set(QUALIFICATION)
            and all(row['passed'] and row['actual_consumer_process_closed'] and row['business_calls'] == 5
                    for row in cells.values())
            and cells['QN']['product_calls'] == 0 and cells['QN']['ordinary_PNGs'] == 1
            and cells['QP']['product_calls'] == 1 and cells['QP']['ordinary_PNGs'] == 2
            and cells['QP']['actual_product_process_closed'] and cells['QP']['actual_product_stdout_EOF'],
            'actual_installed_replay_or_ordinary_transport_not_ready')
    consumer = read(NS / 'consumer/CONSUMER_PREFLIGHT.json')
    require(consumer['actual_model_requests'] == 0 and consumer['ambient_ChatGPT_login_confirmed']
            and consumer['requested'] == ['gpt-6.1-sol','medium','default']
            and consumer['actual_version'] == 'codex-cli 0.152.1', 'configured_consumer_preflight_changed')

    product = admission.registered_product()
    dispatch = {}
    for label in ORDER:
        result = json.loads(subprocess.check_output(command('harness/run_slot.py', label, '--dispatch-smoke'),
                                                    cwd=ROOT, timeout=40))
        group = SLOTS[label][0]
        names = ORDINARY | ({'human_eye_scene_observe'} if group == 'P' else set())
        schema = str(PRODUCT_SCHEMA.resolve()) if group == 'P' else None
        binding_path = str(PRODUCT_BINDING.resolve()) if group == 'P' else None
        require(result['slot'] == label and result['group'] == group and result['schema'] == admission.SCHEMA
                and Path(result['asset']) == ASSET.resolve() and Path(result['run_root']) == EXTERNAL.resolve()
                and result['product'] == product and result['actual_product_schema'] == schema
                and result['actual_product_binding'] == binding_path
                and result['tools'] == sorted(names)
                and result['endpoint_flag'] == ('--region-task-evidence' if group == 'P' else None),
                f'dispatch_roster_or_installed_mode_changed/{label}')
        for path in result['workspace_sources']:
            pin(path)
        dispatch[label] = result

    binding = read(PRODUCT_BINDING)
    wheel_path = Path(binding['wheel_path'])
    require(sha(wheel_path) == binding['wheel_sha256'], 'existing_wheel_changed')
    pin(wheel_path)
    git_blob_script = V / 'm4_cross_scale_local_first_view_001/install/build_install.py'
    pin(git_blob_script)
    names = [row['path'] for row in binding['source_manifest']]
    blobs = run_path(str(git_blob_script))['git_blobs'](product['commit'], names)
    with ZipFile(wheel_path) as package:
        for row in binding['source_manifest']:
            name = row['path']
            path = Path(binding['install_root']) / name
            require(sha(path) == row['sha256'] and path.read_bytes() == package.read(name) == blobs[name],
                    f'installed_Git_wheel_source_changed/{name}')
            pin(path)
    for path in (ASSET, reopened, truth, ASSET.with_name('ASSET_BINDING.json'),
                 ROOT / 'verification/m4_source_region_display_001/harness/reused/stdio_checks.py',
                 ROOT / 'verification/m4_source_region_display_001/harness/reused/process_proof.py',
                 ROOT / 'verification/m4_cross_scale_live_task_formal_001/scoring/formal.py',
                 ROOT / 'verification/m4_cross_scale_discovery_001/oracle/check_saved.py',
                 BLENDER, sys.executable, GENERIC_WORKER, PRODUCT_BINDING, SEAL / 'SHARED_DEPENDENCY.json'):
        pin(path)
    for folder in (NS, EXTERNAL):
        for path in folder.rglob('*'):
            if path.is_file():
                require(path.suffix != '.pyc', 'unexpected_bytecode_in_frozen_inputs')
                if path.suffix == '.py':
                    ast.parse(path.read_bytes(), filename=str(path))
                pin(path)
    save(spec, {
        'schema':admission.SCHEMA, 'plan':PLAN, 'slots':list(ORDER), 'product':product,
        'formal_slots':list(FORMAL_LABELS), 'qualification_slots':list(QUALIFICATION),
        'passed_offline_preflight':True, 'registered_dispatch':dispatch,
        'asset_path':str(ASSET), 'asset_sha256':ASSET_SHA, 'reopened_sha256':REOPEN_SHA,
        'truth_sha256':TRUTH_SHA, 'prompt_sha256':PROMPT_SHA, 'prompt_bytes':1072,
        'CLI_version':'0.152.1', 'model_request':['gpt-6.1-sol','medium','default'],
        'task_s':450, 'owned_s':600, 'max_rasters_per_slot':12, 'max_business_per_slot':12,
        'max_qualification_starts':2, 'max_formal_starts':2, 'max_model_starts':2,
        'product_builds':0, 'product_installs':0, 'asset_builds':0, 'replacements':0, 'argument_rewrites':0,
        'direct_inputs':[pins[path] for path in sorted(pins)],
    })
    print('Frozen', admission.verify_freeze(), len(pins), 'pins', flush=True)


def close_qualifier(label, token, result, receipt):
    require(result['model_consumers'] == 0, 'actual_qualification_used_model')
    verify = run_path(str(NS / 'qualification/closed.py'))['verify']
    proof = verify(EXTERNAL / 'slots' / label, result)
    at = EXTERNAL / 'preflight' / f'{label}_CLOSED_PROOF.json'
    save(at, proof)
    now = time.perf_counter_ns()
    require(proof['passed'] is True and now < result['owned_deadline_ns'],
            f'actual_qualification_failed_or_outside_original_window/{label}')
    save(at.with_name(f'{label}_CLOSED_GATE.json'), {
        'passed':True, 'freeze_sha256':token, 'result_sha256':receipt['result_sha256'],
        'proof_sha256':sha(at), 'verified_ns':now,
    })
    return admission.qualified(label, token)


def sequence():
    token = admission.verify_freeze()
    require(not (EXTERNAL / 'slots').exists(), 'one_fresh_sequence_only')
    sys.path[:0] = [read(PRODUCT_BINDING)['dependency_root'], read(SEAL / 'SHARED_DEPENDENCY.json')['dependency_root']]
    journal = EXTERNAL / 'preflight/SEQUENCE.jsonl'
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.touch(exist_ok=False)
    for index, label in enumerate(ORDER):
        append(journal, {'event':'start', 'label':label, 'stamp_ns':time.perf_counter_ns(), 'freeze_sha256':token})
        process = subprocess.run(command('harness/run_slot.py', label), cwd=ROOT)
        try:
            result, receipt = admission.publication(label, token)
            safe = admission.safe_to_continue(result, receipt)
            append(journal, {'event':'publication', 'label':label, 'exit_code':process.returncode,
                            'status':receipt['status'], 'model_consumers':result['model_consumers'],
                            'safe_to_continue':safe, 'result_sha256':receipt['result_sha256']})
            require(process.returncode == 0 and safe and receipt['status'] == 'completed',
                    'actual_owned_slot_failed_or_unconfirmed')
            if label in QUALIFICATION:
                gate = close_qualifier(label, token, result, receipt)
                append(journal, {'event':'qualification_passed', 'label':label, 'proof_sha256':gate['proof_sha256']})
                print(label, 'closed qualification passed', flush=True)
            else:
                require(result['model_consumers'] == 1, 'one_formal_consumer_required')
        except Exception as error:
            append(journal, {'event':'blocked', 'label':label, 'exit_code':process.returncode,
                            'error_type':type(error).__name__, 'reason':str(error),
                            'remaining':list(ORDER[index + 1:])})
            print(label, 'blocked', type(error).__name__, str(error), flush=True)
            return 1
    return 0


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'pinned_interpreter_I_B_required')
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('stage', choices=('freeze', 'sequence'))
    cli.add_argument('--reports', type=Path, nargs='+')
    args = cli.parse_args()
    if args.stage == 'freeze':
        require(args.reports, 'actual_preflight_records_required')
        freeze(args.reports)
    else:
        raise SystemExit(sequence())
