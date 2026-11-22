"""Freeze the qualified dispatch and run the single registered holdout sequence."""

import argparse
import ast
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys
import time


NS = Path(__file__).resolve().parent
sys.path[:0] = [str(NS/'harness'), str(NS/'qualification'), str(NS)]
import admission
from admission import require
from common import (ASSET, ASSET_BINDING, BLENDER, EXTERNAL, FORMAL_LABELS, GENERIC_WORKER, ORDER,
                    PRODUCT_BINDING, PRODUCT_SCHEMA, ROOT, SEAL, SLOTS, append, catalogue_for, read, save, sha)


PLAN = '1e8d52aec55f29e9dbfbdaedb72780b787a639db:docs/M1_REGION_TASK_FIRST_PACKET_CONSUMPTION_HOLDOUT_001_PLAN.md'
BASE = '020159ca02607c059a3acf797ed2a3394930f290'


def argv(name, *args):
    return [sys.executable, '-IB', '-X', 'utf8', str(NS/name), *args]


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def freeze():
    destination = NS/'FROZEN.json'
    require(not destination.exists() and not (EXTERNAL/'slots').exists(), 'one_fresh_holdout_freeze_required')
    prefix = NS.relative_to(ROOT).as_posix() + '/'
    require(git('merge-base',BASE,'HEAD').decode().strip() == BASE
            and all(path.startswith(prefix) for path in git('diff','--name-only',BASE).decode().splitlines()),
            'isolated_candidate_must_have_zero_product_delta')
    require((NS/'PLAN.md').read_bytes() == git('show',PLAN), 'fixed_plan_changed')
    fixture = read(ASSET_BINDING)
    require(fixture['one_build']['save_count'] == 1 and fixture['reopen']['save_count'] == 0
            and fixture['original_sources_unchanged'] is True and sha(ASSET) == fixture['asset']['sha256']
            and all(fixture['closed_processes'][key]['exit_observed']
                    and fixture['closed_processes'][key]['exit_code'] == 0 for key in ('build','reopen')),
            'one_qualified_fixture_build_and_independent_reopen_required')
    ports = {}
    for label in ORDER:
        row = json.loads(subprocess.check_output(argv('harness/run_slot.py',label,'--dispatch-smoke'), cwd=ROOT, timeout=30))
        require(row['slot'] == label and row['group'] == SLOTS[label][0] and row['schema'] == admission.SCHEMA
                and row['product'] == admission.registered_product() and Path(row['asset']) == ASSET.resolve()
                and Path(row['run_root']) == EXTERNAL.resolve() and Path(row['actual_product_schema']) == PRODUCT_SCHEMA.resolve()
                and Path(row['actual_catalogue_path']) == catalogue_for(label).resolve()
                and row['endpoint_flag'] == ('--region-task-evidence' if label in ('QB','B1') else None),
                'actual_registered_entry_wrong/' + label)
        ports[label] = row
    require(all(row['tools'] == ports['QA']['tools'] and len(row['tools']) == 6 for row in ports.values()),
            'actual_model_facing_tools_differ_between_arms')
    preflight = read(NS/'qualification/PREFLIGHT.json')
    host = read(NS/'harness/HOST_PREFLIGHT.json')
    require(preflight['passed'] is True and host['passed'] is True and len(preflight['cells']) == 2
            and all(row['actual_process_closed'] and row['product_calls'] == 3 and row['consumer_calls'] == 5
                    for row in preflight['cells'].values())
            and preflight['provider_model_starts'] == preflight['Blender_starts'] == 0,
            'complete_actual_zero_model_preflight_required')
    pins = {}

    def pin(path, expected=None):
        source = Path(path).resolve(strict=True)
        row = {'path':str(source),'bytes':source.stat().st_size,'sha256':sha(source)}
        require(expected is None or all(row[k] == expected[k] for k in ('bytes','sha256')),
                'frozen_input_differs_from_original/' + str(source))
        pins[source] = row

    install = read(PRODUCT_BINDING)
    for row in install['source_manifest']:
        path = Path(install['install_root'])/row['path']
        require(sha(path) == row['sha256'], 'fixed_existing_install_byte_changed/' + row['path'])
        pin(path)
    require(sha(install['wheel_path']) == install['wheel_sha256'], 'fixed_existing_wheel_changed')
    for path in (PRODUCT_BINDING, install['wheel_path'], BLENDER, sys.executable, GENERIC_WORKER,
                 SEAL/'SHARED_DEPENDENCY.json', NS.parent/'m1_region_task_first_packet_projection_001/RAW_INDEX.json',
                 NS.parent/'m4_source_region_display_001/harness/reused/process_proof.py',
                 NS.parent/'m4_source_region_display_001/harness/reused/stdio_checks.py',
                 NS.parent/'m4_target_task_consumption_001/native_consumer_audit.py',
                 NS.parent/'m4_live_source_region_task_003/harness/mcp_entry.py',
                 NS.parent/'m4_live_source_region_task_003/harness/reused/verified_bootstrap.py',
                 NS.parent/'perf050_dense_micro_surface_holdout_recovery_001/qualification/verify.py'):
        pin(path)
    for row in preflight['source_pins']:
        pin(row['path'], row)
    for cell in ports.values():
        for path in cell['workspace_sources']:
            pin(path)
    for folder in ('fixture','offline_preflight','offline_preflight_01'):
        for path in (EXTERNAL/folder).rglob('*'):
            if path.is_file():
                pin(path)
    for name in ('asset','reopened_source','truth','original_asset','original_geometry'):
        pin(fixture[name]['path'],fixture[name])
    for path in NS.rglob('*'):
        if path.is_file():
            require(path.suffix != '.pyc', 'bytecode_cache_must_not_enter_freeze')
            if path.suffix == '.py':
                ast.parse(path.read_bytes(), filename=str(path))
            pin(path)
    save(destination, {'schema':admission.SCHEMA,'plan':PLAN,'slots':list(ORDER),'registered_dispatch':ports,
                       'formal_slots':list(FORMAL_LABELS),'qualification_slots':list(admission.QUALIFICATION),
                       'passed_offline_preflight':True,'product':admission.registered_product(),'asset_path':str(ASSET),
                       'asset_sha256':fixture['asset']['sha256'],'prompt_sha256':sha(NS/'inputs/PROMPT.txt'),
                       'task_s':450,'owned_s':600,'max_rasters_per_slot':12,'max_business_per_slot':12,
                       'asset_builds':1,'product_builds':0,'product_installs':0,'max_qualification_starts':2,
                       'max_formal_starts':2,'max_model_starts':2,'replacements':0,'argument_rewrites':0,
                       'direct_inputs':[pins[path] for path in sorted(pins)]})
    print('Frozen',admission.verify_freeze(),len(pins),'pins',flush=True)
    return 0


def qualification(label, token, result, receipt):
    require(admission.can_continue(result,receipt) and result['status'] == 'completed'
            and result['model_consumers'] == 0, 'actual_owned_qualification_incomplete')
    verify = run_path(str(NS/'qualification/closed.py'))['verify']
    proof = verify(EXTERNAL/'slots'/label,result)
    now = time.perf_counter_ns()
    require(proof['passed'] is True and now < result['owned_deadline_ns'], 'closed_evidence_or_owned_deadline_failed')
    folder = EXTERNAL/'preflight'
    saved = folder/f'{label}_CLOSED_PROOF.json'
    save(saved,proof)
    originals = [{'ref':key,**row['PNG']} for key,row in proof['readback'].items()]
    save(folder/f'{label}_CLOSED_GATE.json', {'passed':True,'freeze_sha256':token,'result_sha256':receipt['result_sha256'],
                                           'proof_sha256':sha(saved),'verified_ns':now,'original_images':originals})
    return admission.qualified(label,token)


def sequence():
    token = admission.verify_freeze()
    require(not (EXTERNAL/'slots').exists(), 'one_frozen_holdout_sequence_required')
    journal = EXTERNAL/'preflight/SEQUENCE.jsonl'
    journal.parent.mkdir(exist_ok=False)
    journal.touch(exist_ok=False)
    install = read(PRODUCT_BINDING)
    sys.path[:0] = [install['dependency_root'], read(SEAL/'SHARED_DEPENDENCY.json')['dependency_root']]
    successful = True
    for index,label in enumerate(ORDER):
        append(journal,{'event':'start','label':label,'stamp_ns':time.perf_counter_ns(),'freeze_sha256':token})
        process = subprocess.run(argv('harness/run_slot.py',label),cwd=ROOT)
        try:
            result, receipt = admission.publication(label,token)
            safe = admission.can_continue(result,receipt)
            complete = safe and process.returncode == 0 and receipt['status'] == 'completed'
            append(journal,{'event':'publication','label':label,'exit_code':process.returncode,'status':receipt['status'],
                            'result_sha256':receipt['result_sha256'],'safe_to_continue':safe,
                            'model_consumers':result['model_consumers']})
            if label in admission.QUALIFICATION:
                require(complete, 'qualification_slot_failed_before_independent_gates')
                gate = qualification(label,token,result,receipt)
                append(journal,{'event':'closed_qualification_passed','label':label,'proof_sha256':gate['proof_sha256']})
                print(label,'closed qualification passed',flush=True)
            require(safe,'unconfirmed_closed_slot_blocks_following_work')
            successful &= complete
        except Exception as error:
            append(journal,{'event':'blocked','label':label,'exit_code':process.returncode,'type':type(error).__name__,
                            'reason':str(error),'remaining':list(ORDER[index+1:])})
            print(label, 'blocked', type(error).__name__, str(error),flush=True)
            return 1
    return 0 if successful else 1


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'pinned_interpreter_I_B_required')
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('stage',choices=('freeze','sequence'))
    raise SystemExit(globals()[cli.parse_args().stage]())
