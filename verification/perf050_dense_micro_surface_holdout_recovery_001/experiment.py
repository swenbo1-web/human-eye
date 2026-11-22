"""Run the sole closed-evidence recovery and the original-order formal slots."""

import argparse
import ast
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys
import time

NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
import admission
from common import (ASSET, ASSET_BINDING, ASSET_SHA256, EXTERNAL, FORMAL_LABELS, ORDER,
                    ORIGINAL, PRODUCT, PRODUCT_BINDING, PRODUCT_SCHEMA, ROOT, SLOTS, append, read, save, sha)
from derive_qn import BASE, require


PLAN = '0b1aec4d7a3a8b6ba12017a7e4b337f2662be186:docs/PERF050_DENSE_MICRO_SURFACE_HOLDOUT_RECOVERY_001_PLAN.md'


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def dispatch(entry, *args):
    return json.loads(subprocess.check_output([sys.executable, '-IB', str(NS/entry), *args],cwd=ROOT,timeout=45))


def freeze():
    namespace = NS.relative_to(ROOT).as_posix() + '/'
    require(not EXTERNAL.exists() and not (NS/'FROZEN.json').exists(), 'one_fresh_recovery_freeze_required')
    require(git('merge-base',BASE,'HEAD').decode().strip()==BASE and all(path.startswith(namespace)
            for path in git('diff','--name-only',BASE).decode().splitlines()),'zero_product_delta_required')
    require((NS/'PLAN.md').read_bytes()==git('show',PLAN),'fixed_plan_changed')
    previous = read(ORIGINAL/'FROZEN.json')
    require(previous['asset_sha256']==ASSET_SHA256==sha(ASSET) and previous['product']==PRODUCT
            and previous['prompt_sha256']==sha(NS/'inputs/PROMPT.txt')
            and (NS/'inputs/PROMPT.txt').read_bytes()==(ORIGINAL/'inputs/PROMPT.txt').read_bytes(),
            'fixed_original_asset_product_or_prompt_changed')
    pins = {}

    def pin(path, digest=None, size=None):
        path = Path(path).resolve(strict=True)
        if path not in pins:
            pins[path] = {'path':str(path),'sha256':sha(path),'bytes':path.stat().st_size}
        row = pins[path]
        require((digest is None or row['sha256']==digest) and (size is None or row['bytes']==size), f'freeze_input_mismatch/{path}')

    for row in previous['direct_inputs']:
        pin(row['path'],row['sha256'],row['bytes'])
    pin(ORIGINAL/'PLAN.md')
    for name in ('qualification/QN_DERIVED_ADMISSION.json','qualification/PREFLIGHT.json','consumer/PREFLIGHT.json','checks/SCORER_PREFLIGHT.json'):
        proof = read(NS/name)
        require(proof['passed'] is True, f'required_zero_live_preflight_failed/{name}')
        for row in proof.get('source_pins',[]):
            pin(row['path'],row['sha256'],row['bytes'])

    qn_tools = sorted(row['name'] for row in read(admission.QN_DERIVED)['tools'])
    launch, recorders = {}, {}
    prior_dispatch = read(ORIGINAL/'harness/HOST_PREFLIGHT.json')['fresh_dispatch']
    for label in ORDER:
        entry = dispatch('harness/run_slot.py',label,'--dispatch-smoke')
        group, phase = SLOTS[label]
        require(entry['slot']==label and entry['group']==group and entry['schema']==admission.SCHEMA
                and entry['product']==PRODUCT and Path(entry['asset'])==ASSET and Path(entry['run_root'])==EXTERNAL
                and Path(entry['actual_product_schema'])==PRODUCT_SCHEMA and entry['tools']==prior_dispatch[label]['tools']
                == sorted(set(qn_tools)|({'human_eye_scene_observe'} if group=='P' else set())),f'dispatch_not_current/{label}')
        for source in entry['workspace_sources']:
            pin(source)
        launch[label]=entry
        if group=='P':
            recorder = dispatch('harness/mcp_entry.py','--dispatch-smoke',label)
            require(recorder['label']==label and Path(recorder['current_binding'])==PRODUCT_BINDING
                    and Path(recorder['absolute_state_file'])==EXTERNAL/'slots'/label/'product_state.json', f'actual_recorder_not_current/{label}')
            recorders[label] = recorder
    save(NS/'harness/HOST_PREFLIGHT.json',{'passed':True,'fresh_dispatch':launch,'fresh_recorder':recorders})
    for path in NS.rglob('*'):
        if path.is_file():
            require(path.suffix!='.pyc','preflight_cache_must_not_enter_freeze')
            if path.suffix=='.py':
                ast.parse(path.read_bytes(),filename=str(path))
            pin(path)
    save(NS/'FROZEN.json',{'schema':admission.SCHEMA,'passed_offline_preflight':True,'slots':list(ORDER),
        'formal_slots':list(FORMAL_LABELS),'qualification_slots':['QP'],'prior_QN_reused':True,'original_batch':BASE,
        'original_freeze_sha256':sha(ORIGINAL/'FROZEN.json'),'asset_path':str(ASSET),'asset_sha256':ASSET_SHA256,
        'product':PRODUCT,'prompt_sha256':previous['prompt_sha256'],'prompt_bytes':previous['prompt_bytes'],
        'max_Blender_starts':7,'max_models':6,'max_business_per_slot':12,'max_qualification_rasters_per_slot':6,
        'max_formal_rasters_per_slot':12,'max_all_rasters':78,'task_s':450,'owned_s':600,'product_diff_files':0,
        'product_builds':0,'product_installs':0,'asset_builds':0,'replacements':0,'argument_rewrites':0,
        'direct_inputs':[pins[p] for p in sorted(pins)]})
    print('Frozen',admission.verify_freeze(),len(pins),flush=True)


def close_qp(root, frozen, result, receipt):
    require(admission.can_continue(result,receipt) and result['status']=='completed'
            and result['model_consumers']==0 and result['closure_verification']['status']=='ready_closed',
            'QP_owned_runtime_or_calls_incomplete')
    verifier = run_path(str(NS/'qualification/verify.py'))['verify_closed']
    proof = verifier(root/'slots/QP', result)
    now = time.perf_counter_ns()
    require(proof['passed'] is True and now < result['owned_deadline_ns'], 'QP_closed_qualification_or_deadline_failed')
    path = root/'preflight/QP_CLOSED_PROOF.json'
    save(path,proof)
    save(root/'preflight/QP_CLOSED_GATE.json',{'passed':True,'freeze_sha256':frozen,'result_sha256':receipt['result_sha256'],
             'proof_sha256':sha(path),'qn_derived_sha256':sha(admission.QN_DERIVED),'verified_ns':now})
    return admission.verify_qp_gate(root,frozen,result,receipt)


def sequence():
    frozen = admission.verify_freeze()
    require(not EXTERNAL.exists(),'one_fresh_owned_sequence_only')
    sys.path.insert(0,read(PRODUCT_BINDING)['dependency_root'])
    journal = EXTERNAL/'preflight/FORMAL_SEQUENCE.jsonl'
    journal.parent.mkdir(parents=True)
    journal.touch(exist_ok=False)
    complete_batch = True
    for label in ORDER:
        append(journal,{'event':'start','label':label,'started_ns':time.perf_counter_ns(),'freeze_sha256':frozen})
        process = subprocess.run([sys.executable,'-IB',str(NS/'harness/run_slot.py'),label],cwd=ROOT)
        try:
            result, receipt = admission.publication(label,frozen)
            safe = admission.can_continue(result,receipt)
            complete = safe and process.returncode==0 and receipt['status']=='completed'
            append(journal,{'event':'publication','label':label,'exit_code':process.returncode,'status':receipt['status'],
                'result_sha256':receipt['result_sha256'],'safe_to_continue':safe,'model_consumers':result['model_consumers']})
            if label=='QP':
                require(complete,'QP_live_calls_did_not_complete')
                passed = close_qp(EXTERNAL,frozen,result,receipt)
                append(journal,{'event':'QP_CLOSED_GATE','passed':True,'result_sha256':passed['result_sha256'],
                                'proof_sha256':passed['proof_sha256']})
        except Exception as error:
            append(journal,{'event':'qualification_blocked' if label=='QP' else 'unconfirmed',
                  'label':label,'exit_code':process.returncode,'type':type(error).__name__, 'error':str(error),
                  'remaining':list(ORDER[ORDER.index(label)+1:])})
            print(label,'closed gate failed:',type(error).__name__,str(error),flush=True)
            return 1
        complete_batch &= complete
        if not safe:
            append(journal,{'event':'unsafe_to_continue','label':label,'remaining':list(ORDER[ORDER.index(label)+1:])})
            return 1
    return 0 if complete_batch else 1


if __name__=='__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'pinned_interpreter_I_B_required')
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('action',choices=('freeze','sequence'))
    raise SystemExit(globals()[cli.parse_args().action]())
