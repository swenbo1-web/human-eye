"""Freeze the startup correction, then admit at most one new genuine formal pair."""

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
sys.path[:0] = [str(NS/'harness'),str(NS)]
import admission
from admission import require
from common import (ASSET, BLENDER, EXTERNAL, GENERIC_WORKER, ORDER, PRODUCT_BINDING,
                    ROOT, SEAL, append, read, save, sha)


PLAN = 'b6261a04e5299f7a78c410838176a614395bfe7d:docs/M4_DENSE_SWEEP_INTEGRATED_NATIVE_STARTUP_001_PLAN.md'
PRIOR_COMMIT = '62a631344922ddcea57d78b051a37d33629ad3a2'
PRIOR_ROOT = Path('D:/he_m4_dense_sweep_integrated_native_pilot_recovery_001')
PRIOR_FREEZE = 'ea4c90e1567ac61d823f97a6d58244ce73e7e85d862a376041730e52f61b4bca'
PRIOR_ARCHIVE = 'aef290d67a13869ffb643298d10592adb7c48611e22ec19ebc969561741f78c2'
DERIVED_SHA = '7d37be07327a090741b4ba6bfbfa5229007d8404a14e90938966e8906dd93a56'
ASSET_SHA = '219541e921666ddf6c406507afb5e59168415a14b8ea7b3d8eca28c6dacbe12f'
COLD = EXTERNAL/'preflight/COLD_ENTRY.json'


def command(entry,*args):
    return [sys.executable,'-IB','-X','utf8',str(NS/entry),*args]


def git(*args):
    return subprocess.check_output(['git','-C',str(ROOT),*args])


def checked_prior():
    prior = admission.PRIOR
    freeze, index, archive = (prior/name for name in ('FROZEN.json','RAW_INDEX.json','ORIGINAL_RUNTIME.zip'))
    for path in (freeze,index,archive):
        require(path.read_bytes() == git('show',PRIOR_COMMIT+':'+path.relative_to(ROOT).as_posix()),
                'previous_frozen_Git_artifact_changed/'+path.name)
    idx = read(index)
    require(sha(freeze)==idx['freeze_sha256']==PRIOR_FREEZE and sha(archive)==idx['archive']['sha256']==PRIOR_ARCHIVE
            and idx['member_count']==9 and idx['slots']['N1']['owned']=='failed' and idx['slots']['P1']['owned']=='unrun'
            and set(idx['new_formal_totals'].values())=={0}
            and idx['original_qualification_totals']=={'blender':2,'rasters':5,'business':10,'models':0},
            'previous_real_failure_or_historical_denominator_changed')
    require(not any((PRIOR_ROOT/'slots'/label).exists() for label in ('P1','QN','QP')),
            'old_frozen_slot_roster_changed')
    disk = {'runtime/'+path.relative_to(PRIOR_ROOT).as_posix():path
            for path in PRIOR_ROOT.rglob('*') if path.is_file()}
    require(disk.keys()==idx['members'].keys(),'old_recovery_file_roster_changed')
    with ZipFile(archive) as pack:
        require(len(pack.namelist())==9 and set(pack.namelist())==disk.keys(),'old_recovery_archive_roster_changed')
        for key,path in disk.items():
            require(path.read_bytes()==pack.read(key) and sha(path)==idx['members'][key]['sha256']
                    and path.stat().st_size==idx['members'][key]['bytes'],'old_recovery_live_bytes_changed/'+key)
    return freeze,index,archive


def freeze(reports):
    at = NS/'FROZEN.json'
    require(not at.exists() and not (EXTERNAL/'slots').exists() and not COLD.exists(),
            'freeze_before_new_cold_or_live_entry')
    prefix = NS.relative_to(ROOT).as_posix()+'/'
    require(git('merge-base',PRIOR_COMMIT,'HEAD').decode().strip()==PRIOR_COMMIT
            and all(path.startswith(prefix) for path in git('diff','--name-only',PRIOR_COMMIT).decode().splitlines())
            and (NS/'PLAN.md').read_bytes()==git('show',PLAN),'startup_plan_or_zero_product_delta_changed')
    prior_freeze, prior_index, prior_archive = checked_prior()
    for name in ('PROMPT.txt','PRODUCT_SCHEMA.json','EVIDENCE_TOOLS_SCHEMA.json','CATALOGUE_ORIGIN.json'):
        left,right = NS/'inputs'/name,admission.PRIOR/'inputs'/name
        require(left.read_bytes()==git('show',PRIOR_COMMIT+':'+right.relative_to(ROOT).as_posix()),
                'prior_question_or_common_tools_changed/'+name)
    require(sha(ASSET)==ASSET_SHA and ASSET.stat().st_size==102540
            and sha(NS/'inputs/PROMPT.txt')==admission.PROMPT_SHA and (NS/'inputs/PROMPT.txt').stat().st_size==1072,
            'fixed_startup_fixture_or_prompt_changed')
    original_path = sys.path[:]
    require(admission.verify_derived()==DERIVED_SHA and sys.path==original_path,
            'retained_derived_proof_or_loader_scope_changed')

    pins = {}
    def pin(path,expected=None):
        target = Path(path).resolve(strict=True)
        row = {'path':str(target),'bytes':target.stat().st_size,'sha256':sha(target)}
        require(expected is None or all(expected[key]==row[key] for key in ('bytes','sha256')),
                'immutable_startup_input_changed/'+str(target))
        pins[target] = row

    for row in read(prior_freeze)['direct_inputs']:
        pin(row['path'],row)
    required = (NS/'harness/RUNTIME_PREFLIGHT.json',NS/'analysis/ANALYSIS_PREFLIGHT.json')
    for path in (*required,*reports):
        proof = read(path)
        require(proof['passed'] is True,'required_frozen_contract_preflight_failed/'+str(path))
        pin(path)
        for row in proof.get('source_pins',[]):
            pin(row['path'],row)

    product = admission.registered_product()
    installed = read(PRODUCT_BINDING)
    wheel = Path(installed['wheel_path'])
    require(sha(wheel)==product['wheel_sha256'],'existing_startup_wheel_changed')
    helper = V/'m4_cross_scale_local_first_view_001/install/build_install.py'
    blobs = run_path(str(helper))['git_blobs'](product['commit'],[row['path'] for row in installed['source_manifest']])
    with ZipFile(wheel) as package:
        for row in installed['source_manifest']:
            name = row['path']
            source = Path(installed['install_root'])/name
            require(source.read_bytes()==blobs[name]==package.read(name) and sha(source)==row['sha256'],
                    'fixed_Git_wheel_installed_source_changed/'+name)
            pin(source)
    for path in (prior_freeze,prior_index,prior_archive,ASSET,BLENDER,GENERIC_WORKER,sys.executable,
                 PRODUCT_BINDING,wheel,helper,admission.DERIVED,admission.PREFLIGHT,SEAL/'SHARED_DEPENDENCY.json',
                 NS/'harness/cold_entry.py'):
        pin(path)
    for path in NS.rglob('*'):
        if path.is_file():
            require(path.suffix!='.pyc','unexpected_bytecode_in_frozen_inputs')
            if path.suffix=='.py':
                ast.parse(path.read_bytes(),filename=str(path))
            pin(path)
    save(at,{
        'schema':admission.SCHEMA,'plan':PLAN,'previous_recovery_commit':PRIOR_COMMIT,
        'previous_recovery_freeze_sha256':PRIOR_FREEZE,'derived_admission_sha256':DERIVED_SHA,
        'slots':list(ORDER),'formal_slots':list(ORDER),'qualification_slots':[],
        'product':product,'asset_path':str(ASSET),'asset_sha256':ASSET_SHA,'prompt_sha256':admission.PROMPT_SHA,
        'prompt_bytes':1072,'passed_offline_preflight':True,'formal_requires_independent_post_freeze_COLD_ENTRY':True,
        'CLI_version':'0.152.1','model_request':['gpt-6.1-sol','medium','default'],
        'task_s':450,'owned_s':600,'max_business_per_slot':12,'max_rasters_per_slot':12,
        'max_qualification_starts':0,'max_formal_starts':2,'max_model_starts':2,
        'asset_builds':0,'product_builds':0,'product_installs':0,'replacements':0,'argument_rewrites':0,
        'direct_inputs':[pins[path] for path in sorted(pins)],
    })
    print('Frozen',admission.verify_freeze(),len(pins),'pins',flush=True)


def verify_cold_entry(token):
    proof = read(COLD)
    require(proof['passed'] is True and proof['freeze_sha256']==token and set(proof['arms'])==set(ORDER)
            and proof['formal_slots_created'] is False and not proof['unrun']
            and proof['program']['sha256']==sha(NS/'harness/cold_entry.py')
            and proof['actual_Blender_starts']==proof['actual_model_starts']==proof['actual_rasters']==0,
            'both_registered_true_cold_entries_required')
    root = (EXTERNAL/'preflight/cold_entry').resolve()
    for label in ORDER:
        arm = proof['arms'][label]
        receipt = arm['receipt']
        path = Path(receipt['path']).resolve(strict=True)
        require(arm['passed'] is True and path==(root/label/'RECEIPT.json').resolve()
                and sha(path)==receipt['sha256'] and path.stat().st_size==receipt['bytes'],
                'cold_constructor_or_boundary_receipt_detached/'+label)
        recorded = read(path)
        child = recorded['proof']
        checks = child['checks']
        require(recorded['passed'] is True and recorded['returncode']==0 and recorded['removed_temporary_root']
                and child['freeze_sha256']==recorded['freeze_sha256']==token and child['label']==label
                and checks['actual_admission']['restored'] and checks['first_import_after_derived_admission']
                and checks['runtime_constructed'] and checks['reserve_call_before_body']
                == {'kind':'Blender_start','label':label,'phase':'formal','upper':1}
                and all(value==0 for value in checks['budget']['counts_before_reserve'].values()),
                'true_reservation_boundary_or_control_missing/'+label)
        for item in (recorded['stdout'],recorded['stderr'],*recorded['held_files']):
            raw = Path(item['path']).resolve(strict=True)
            require(raw.is_relative_to(path.parent) and sha(raw)==item['sha256']
                    and raw.stat().st_size==item['bytes'],'sealed_cold_child_bytes_changed/'+label)
        if label=='N1':
            require(child['rejecting_path_restoration']['restored']
                    and child['rejecting_path_restoration']['after_full_audit'],'rejection_path_not_scope_isolated')
        else:
            require(child['predecessor']['simulated'] and child['predecessor']['old_failed_predecessor_rejected'],
                    'P1_predecessor_not_controlled')
    return sha(COLD)


def sequence():
    require(not (EXTERNAL/'slots').exists(),'one_fresh_formal_startup_sequence')
    token = admission.verify_freeze()
    cold_sha = verify_cold_entry(token)
    journal = EXTERNAL/'preflight/SEQUENCE.jsonl'
    journal.touch(exist_ok=False)
    for index,label in enumerate(ORDER):
        append(journal,{'event':'start','label':label,'started_ns':time.perf_counter_ns(),'freeze_sha256':token,
                        'cold_entry_sha256':cold_sha})
        process = subprocess.run(command('harness/run_slot.py',label),cwd=ROOT)
        try:
            result,receipt = admission.publication(label,token)
            safe = admission.safe_to_continue(result,receipt)
            append(journal,{'event':'publication','label':label,'status':receipt['status'],
                            'result_sha256':receipt['result_sha256'],'exit_code':process.returncode,
                            'safe_to_continue':safe,'model_consumers':result['model_consumers']})
            require(process.returncode==0 and safe,'actual_formal_slot_failed_or_unconfirmed')
        except Exception as error:
            append(journal,{'event':'blocked','label':label,'exit_code':process.returncode,
                            'error_type':type(error).__name__,'reason':str(error),'remaining':list(ORDER[index+1:])})
            print(label,'blocked',type(error).__name__,str(error),flush=True)
            return 1
    return 0


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'pinned_interpreter_I_B_required')
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('stage',choices=('freeze','sequence'))
    cli.add_argument('--reports',type=Path,nargs='*',default=[])
    config = cli.parse_args()
    if config.stage=='freeze':
        freeze(config.reports)
    else:
        raise SystemExit(sequence())
