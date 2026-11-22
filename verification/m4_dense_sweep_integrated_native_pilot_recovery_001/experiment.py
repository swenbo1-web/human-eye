"""Derive historical qualification and run the two outstanding formal slots once."""

import argparse
import ast
from datetime import datetime, timezone
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys
import time
from zipfile import ZipFile


NS = Path(__file__).resolve().parent
V = NS.parent
sys.path[:0] = [str(NS/'harness'),str(NS/'qualification'),str(NS)]
import admission
from admission import require
from common import (ASSET, BLENDER, EXTERNAL, GENERIC_WORKER, ORDER, PRODUCT_BINDING,
                    PRODUCT_SCHEMA, ROOT, SEAL, SLOTS, append, read, save, sha)
import origin
import recovery


PLAN = '67b4e561ba387d04d905b9d51e1ca23e3738571d:docs/M4_DENSE_SWEEP_INTEGRATED_NATIVE_PILOT_RECOVERY_001_PLAN.md'
ORDINARY = {'execute_blender_code','execute_python','read_images','render_local','render_views'}


def git(*args):
    return subprocess.check_output(['git','-C',str(ROOT),*args])


def command(entry,*args):
    return [sys.executable,'-IB','-X','utf8',str(NS/entry),*args]


def derive():
    require(not (NS/'FROZEN.json').exists() and not (EXTERNAL/'slots').exists()
            and not admission.DERIVED.exists() and not admission.PREFLIGHT.exists(),
            'derive_once_before_formal_freeze')
    started = time.perf_counter_ns()
    utc = datetime.now(timezone.utc).isoformat()
    evidence = recovery.audit()
    controls = recovery.negative_publication_controls()
    scope = recovery.scope_control()
    finished = time.perf_counter_ns()
    token = {
        'schema':admission.SCHEMA+'-derived-qualification','purpose':'from-original-closed-evidence-only',
        'offline_started_utc':utc,'offline_started_ns':started,'offline_finished_ns':finished,
        'new_Blender_starts':0,'new_model_starts':0,'evidence':evidence,
    }
    admission.DERIVED.parent.mkdir(parents=True,exist_ok=True)
    save(admission.DERIVED,token)
    match = admission.verify_derived()
    save(admission.PREFLIGHT,{
        'passed':True,'same_live_admission_function':'harness.admission.verify_derived',
        'derived_admission_sha256':match,'checked_original_order':list(origin.LABELS),
        'publication_rejects':controls,'equal_length_local_SCENE_reject':scope,
        'source_pins':[origin.pin(path) for path in (Path(__file__),Path(admission.__file__),Path(origin.__file__),
            Path(recovery.__file__),NS/'qualification/budget.py',origin.OLD_NS/'qualification/closed.py',recovery.CONTROLS)],
    })
    print('Derived',match,'old qualifiers',list(origin.LABELS),'new qualifiers 0',flush=True)


def freeze(reports):
    target = NS/'FROZEN.json'
    require(not target.exists() and not (EXTERNAL/'slots').exists(), 'one_recovery_freeze_before_new_formal')
    prefix = NS.relative_to(ROOT).as_posix()+'/'
    require(git('merge-base',origin.OLD_COMMIT,'HEAD').decode().strip() == origin.OLD_COMMIT
            and all(path.startswith(prefix) for path in git('diff','--name-only',origin.OLD_COMMIT).decode().splitlines())
            and (NS/'PLAN.md').read_bytes() == git('show',PLAN),'recovery_plan_or_zero_product_delta_changed')
    for name in ('PROMPT.txt','PRODUCT_SCHEMA.json','EVIDENCE_TOOLS_SCHEMA.json','CATALOGUE_ORIGIN.json'):
        left,right = NS/'inputs'/name,origin.OLD_NS/'inputs'/name
        require(left.read_bytes() == git('show',origin.OLD_COMMIT+':'+right.relative_to(ROOT).as_posix()),
                'old_prompt_or_tool_schema_changed/'+name)
    require(ASSET.stat().st_size == 102540 and sha(ASSET) == origin.ASSET
            and (NS/'inputs/PROMPT.txt').stat().st_size == 1072
            and sha(NS/'inputs/PROMPT.txt') == admission.PROMPT_SHA,'fixed_asset_or_common_prompt_changed')
    derived = admission.verify_derived()
    require(read(admission.PREFLIGHT)['passed'] and read(admission.PREFLIGHT)['derived_admission_sha256']==derived,
            'actual_recovery_entry_preflight_changed')
    pins = {}

    def pin(path,expected=None):
        row = origin.pin(path)
        require(expected is None or all(expected[key]==row[key] for key in ('bytes','sha256')),
                'recovery_frozen_source_pin_changed/'+row['path'])
        pins[Path(row['path'])] = row

    old_spec = origin.OLD_NS/'FROZEN.json'
    for item in read(old_spec)['direct_inputs']:
        pin(item['path'],item)
    for path in (old_spec,origin.OLD_NS/'RAW_INDEX.json',origin.OLD_NS/'ORIGINAL_RUNTIME.zip'):
        pin(path)
    required = (admission.PREFLIGHT,NS/'harness/RUNTIME_PREFLIGHT.json',NS/'analysis/ANALYSIS_PREFLIGHT.json')
    for path in (*required,*reports):
        proof = read(path)
        require(proof['passed'] is True,'required_recovery_preflight_failed/'+str(path))
        pin(path)
        for item in proof.get('source_pins',[]):
            pin(item['path'],item)
    product = admission.registered_product()
    installed = read(PRODUCT_BINDING)
    pin(PRODUCT_BINDING)
    wheel = Path(installed['wheel_path'])
    require(sha(wheel) == product['wheel_sha256'],'existing_recovery_wheel_changed')
    pin(wheel)
    git_blobs = run_path(str(V/'m4_cross_scale_local_first_view_001/install/build_install.py'))['git_blobs']
    blobs = git_blobs(product['commit'],[row['path'] for row in installed['source_manifest']])
    with ZipFile(wheel) as package:
        for item in installed['source_manifest']:
            name = item['path']
            path = Path(installed['install_root'])/name
            require(path.read_bytes() == blobs[name] == package.read(name) and sha(path)==item['sha256'],
                    'fixed_Git_wheel_install_changed/'+name)
            pin(path)

    dispatch = {}
    for label in ORDER:
        data = json.loads(subprocess.check_output(command('harness/run_slot.py',label,'--dispatch-smoke'),
                                                 cwd=ROOT,timeout=45))
        group = SLOTS[label][0]
        names = ORDINARY | ({'human_eye_scene_observe'} if group=='P' else set())
        require(data['slot']==label and data['schema']==admission.SCHEMA and data['group']==group
                and Path(data['asset']).resolve()==ASSET.resolve() and Path(data['run_root']).resolve()==EXTERNAL.resolve()
                and data['product']==product and data['tools']==sorted(names)
                and data['endpoint_flag']==('--region-task-evidence' if group=='P' else None)
                and data['actual_product_schema']==(str(PRODUCT_SCHEMA.resolve()) if group=='P' else None),
                'actual_recovery_dispatch_changed/'+label)
        dispatch[label] = data
        for path in data['workspace_sources']:
            pin(path)
    for path in (ASSET,BLENDER,GENERIC_WORKER,sys.executable,SEAL/'SHARED_DEPENDENCY.json',admission.DERIVED):
        pin(path)
    for path in NS.rglob('*'):
        if path.is_file():
            require(path.suffix!='.pyc','unexpected_bytecode_in_new_freeze')
            if path.suffix == '.py':
                ast.parse(path.read_bytes(),filename=str(path))
            pin(path)
    save(target,{
        'schema':admission.SCHEMA,'plan':PLAN,'prior_qualification_commit':origin.OLD_COMMIT,
        'prior_freeze_sha256':origin.OLD_FREEZE,'derived_admission_sha256':derived,'slots':list(ORDER),
        'formal_slots':list(ORDER),'qualification_slots':[],'product':product,'asset_path':str(ASSET),
        'asset_sha256':origin.ASSET,'prompt_sha256':admission.PROMPT_SHA,'prompt_bytes':1072,
        'passed_offline_preflight':True,'registered_dispatch':dispatch,'CLI_version':'0.152.1',
        'model_request':['gpt-6.1-sol','medium','default'],'task_s':450,'owned_s':600,
        'max_business_per_slot':12,'max_rasters_per_slot':12,'max_qualification_starts':0,
        'max_formal_starts':2,'max_model_starts':2,'asset_builds':0,'product_builds':0,'product_installs':0,
        'replacements':0,'argument_rewrites':0,'direct_inputs':[pins[path] for path in sorted(pins)],
    })
    print('Frozen',admission.verify_freeze(),len(pins),'pins',flush=True)


def sequence():
    require(not (EXTERNAL/'slots').exists(),'one_fresh_formal_only_sequence')
    token = admission.validate_admission('N1',NS/'FROZEN.json')['freeze_sha256']
    journal = EXTERNAL/'preflight/SEQUENCE.jsonl'
    journal.touch(exist_ok=False)
    for index,label in enumerate(ORDER):
        append(journal,{'event':'start','label':label,'started_ns':time.perf_counter_ns(),'freeze_sha256':token})
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
    cli.add_argument('stage',choices=('derive','freeze','sequence'))
    cli.add_argument('--reports',type=Path,nargs='*',default=[])
    config = cli.parse_args()
    if config.stage == 'derive':
        derive()
    elif config.stage == 'freeze':
        freeze(config.reports)
    else:
        raise SystemExit(sequence())
