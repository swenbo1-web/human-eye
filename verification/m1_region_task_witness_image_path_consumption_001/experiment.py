"""Freeze the paired experiment and spend each authorized slot at most once."""

import argparse
import ast
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys
import time


NS=Path(__file__).resolve().parent
V=NS.parent
sys.path[:0]=[str(NS/'harness'),str(NS/'qualification'),str(NS)]
import admission
from admission import require
from common import (ASSET, BLENDER, EXTERNAL, FORMAL_LABELS, GENERIC_WORKER, ORDER, PRODUCT_SCHEMA, ROOT,
                    SEAL, SLOTS, append, binding_for, catalogue_for, read, save, sha)


PLAN='6fd280680d203df92b993e40260333d30174b8e2:docs/M1_REGION_TASK_WITNESS_IMAGE_PATH_CONSUMPTION_001_PLAN.md'
BASE='4279bcc430c07980ecbade5c7298e758f2adfe2f'


def argv(entry,*args):
    return [sys.executable,'-IB','-X','utf8',str(NS/entry),*args]


def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT)


def freeze():
    freeze_path=NS/'FROZEN.json'
    require(not freeze_path.exists() and not (EXTERNAL/'slots').exists(),'one_frozen_consumption_matrix_required')
    prefix=NS.relative_to(ROOT).as_posix()+'/'
    require(git('merge-base',BASE,'HEAD').decode().strip()==BASE
            and all(file.startswith(prefix) for file in git('diff','--name-only',BASE).decode().splitlines())
            and (NS/'PLAN.md').read_bytes()==git('show',PLAN),'zero_product_delta_and_fixed_plan_required')
    truth=read(NS/'fixture/TRUTH.json')
    require(sha(ASSET)==admission.ASSET_SHA and set(truth['eligible'])=={'M02','M06','M09'},
            'fixed_whole_scene_geometric_reference_changed')
    reports=[NS/'harness/HOST_PREFLIGHT.json',NS/'harness/RUNTIME_PREFLIGHT.json',NS/'checks/SCORER_PREFLIGHT.json']
    require(all(read(file)['passed'] is True for file in reports),'real_entry_or_scorer_preflight_failed')
    replay=read(reports[1])
    require(set(replay['cells'])=={'QA','QB'} and replay['actual_model_starts']==replay['actual_Blender_starts']==0
            and all(row['actual_process_closed'] and row['actual_stdout_EOF'] and row['product_calls']==1
                    and row['consumer_calls']==(2 if label=='QA' else 1)
                    for label,row in replay['cells'].items()),'paired_real_transport_preflight_differed')
    prepared={}
    for label in ORDER:
        row=json.loads(subprocess.check_output(argv('harness/run_slot.py',label,'--dispatch-smoke'),cwd=ROOT,timeout=40))
        require(row['slot']==label and row['schema']==admission.SCHEMA and row['group']==SLOTS[label][0]
                and row['product']==admission.registered_product(label) and Path(row['asset'])==ASSET.resolve()
                and Path(row['run_root'])==EXTERNAL.resolve() and Path(row['actual_product_schema'])==PRODUCT_SCHEMA.resolve()
                and Path(row['actual_product_binding'])==binding_for(label).resolve()
                and Path(row['actual_catalogue_path'])==catalogue_for(label).resolve()
                and row['endpoint_flag']=='--region-task-evidence','real_frozen_launch_dispatch_changed/'+label)
        prepared[label]=row
    require(all(row['tools']==prepared['QA']['tools'] and len(row['tools'])==6 for row in prepared.values()),
            'equal_public_tool_directory_changed')
    pins={}

    def pin(path,expected=None):
        source=Path(path).resolve(strict=True)
        row={'path':str(source),'bytes':source.stat().st_size,'sha256':sha(source)}
        require(expected is None or all(expected[key]==row[key] for key in ('bytes','sha256')),
                'actual_retained_input_changed/'+str(source))
        pins[source]=row

    for label in FORMAL_LABELS:
        source=binding_for(label)
        bind=read(source)
        pin(source)
        require(sha(bind['wheel_path'])==bind['wheel_sha256'],'fixed_existing_wheel_changed/'+label)
        pin(bind['wheel_path'])
        for member in bind['source_manifest']:
            installed=Path(bind['install_root'])/member['path']
            require(sha(installed)==member['sha256'],'fixed_install_source_changed/'+member['path'])
            pin(installed)
    for path in (ASSET,BLENDER,sys.executable,GENERIC_WORKER,SEAL/'SHARED_DEPENDENCY.json',
                 V/'m4_target_task_consumption_001/native_consumer_audit.py',
                 V/'m4_source_region_display_001/harness/reused/process_proof.py',
                 V/'m4_source_region_display_001/harness/reused/stdio_checks.py',
                 V/'m4_live_source_region_task_003/harness/mcp_entry.py',
                 V/'m4_live_source_region_task_003/harness/reused/verified_bootstrap.py',
                 V/'m4_cross_scale_live_task_formal_001/scoring/formal.py',
                 V/'m4_cross_scale_discovery_001/oracle/check_saved.py',
                 V/'m4_dense_region_brief_001/checks/brief_schema.py',
                 V/'perf050_dense_micro_surface_holdout_recovery_001/qualification/verify.py',
                 V/'m1_region_task_witness_image_path_001/RAW_INDEX.json'):
        pin(path)
    for report in reports:
        for row in read(report).get('source_pins',[]):
            pin(row['path'],row)
    for cell in prepared.values():
        for path in cell['workspace_sources']:
            pin(path)
    for folder in (NS,EXTERNAL):
        for file in folder.rglob('*'):
            if file.is_file():
                require(file.suffix!='.pyc','no_bytecode_in_fixed_inputs')
                if file.suffix=='.py':
                    ast.parse(file.read_bytes(),filename=str(file))
                pin(file)
    save(freeze_path,{'schema':admission.SCHEMA,'plan':PLAN,'slots':list(ORDER),'registered_dispatch':prepared,
         'formal_slots':list(FORMAL_LABELS),'qualification_slots':list(admission.QUALIFICATION),
         'passed_offline_preflight':True,'products':{label:admission.registered_product(label) for label in ORDER},
         'asset_path':str(ASSET),'asset_sha256':admission.ASSET_SHA,'prompt_sha256':sha(NS/'inputs/PROMPT.txt'),
         'task_s':450,'owned_s':600,'max_rasters_per_slot':12,'max_business_per_slot':12,
         'max_qualification_starts':2,'max_formal_starts':2,'max_model_starts':2,'argument_rewrites':0,
         'asset_builds':0,'product_builds':0,'product_installs':0,'replacements':0,
         'direct_inputs':[pins[file] for file in sorted(pins)]})
    print('Frozen',admission.verify_freeze(freeze_path),len(pins),'pins',flush=True)
    return 0


def qualification(label,token,result,receipt):
    require(result['model_consumers']==0,'actual_qualifier_used_model')
    check=run_path(str(NS/'qualification/closed.py'))['verify']
    proof=check(EXTERNAL/'slots'/label,result)
    now=time.perf_counter_ns()
    require(proof['passed'] is True and now<result['owned_deadline_ns'],'actual_QA_or_QB_evidence_not_in_owned_window')
    folder=EXTERNAL/'preflight'
    at=folder/f'{label}_CLOSED_PROOF.json'
    save(at,proof)
    save(folder/f'{label}_CLOSED_GATE.json',{'passed':True,'freeze_sha256':token,'result_sha256':receipt['result_sha256'],
         'proof_sha256':sha(at),'verified_ns':now,'original_images':proof['original_images']})
    return admission.qualified(label,token)


def sequence():
    token=admission.verify_freeze()
    require(not (EXTERNAL/'slots').exists(),'one_consumption_sequence_only')
    baseline=read(binding_for('A1'))
    sys.path[:0]=[baseline['dependency_root'],read(SEAL/'SHARED_DEPENDENCY.json')['dependency_root']]
    journal=EXTERNAL/'preflight/SEQUENCE.jsonl'
    journal.parent.mkdir(parents=True,exist_ok=False)
    journal.touch(exist_ok=False)
    for i,label in enumerate(ORDER):
        append(journal,{'event':'start','label':label,'stamp_ns':time.perf_counter_ns(),'freeze_sha256':token})
        process=subprocess.run(argv('harness/run_slot.py',label),cwd=ROOT)
        try:
            result,receipt=admission.publication(label,token)
            safe=admission.safe_to_continue(result,receipt)
            append(journal,{'event':'publication','label':label,'exit_code':process.returncode,'status':receipt['status'],
                            'model_consumers':result['model_consumers'],'safe_to_continue':safe,
                            'result_sha256':receipt['result_sha256']})
            require(process.returncode==0 and safe,'actual_owned_slot_failed_or_unconfirmed')
            if label in admission.QUALIFICATION:
                gate=qualification(label,token,result,receipt)
                append(journal,{'event':'qualification_passed','label':label,'proof_sha256':gate['proof_sha256']})
                print(label,'closed qualification passed',flush=True)
        except Exception as error:
            append(journal,{'event':'blocked','label':label,'exit_code':process.returncode,'type':type(error).__name__,
                            'reason':str(error),'remaining':list(ORDER[i+1:])})
            print(label,'blocked',type(error).__name__,str(error),flush=True)
            return 1
    return 0


if __name__=='__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'pinned_interpreter_I_B_required')
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('stage',choices=('freeze','sequence'))
    raise SystemExit(globals()[cli.parse_args().stage]())
