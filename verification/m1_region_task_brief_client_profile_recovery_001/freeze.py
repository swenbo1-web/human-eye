"""Bind the historical failure, recovered assembly preflight and sole trial."""

import hashlib
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile

NS=Path(__file__).resolve().parent
sys.path.insert(0,str(NS/'harness'))
from common import EXTERNAL, PREVIOUS, PREVIOUS_RUN, PRODUCT, ROOT, read, save


BASE='6778775f3fb0717c3c5315d87a6fdd50e50e02b3'
PLAN='17c6236e8bf8c9782ffb40a9fd736c86431bc54e:docs/M1_REGION_TASK_BRIEF_CLIENT_PROFILE_RECOVERY_001_PLAN.md'
OLD_FREEZE='5a2a91b24b6415d520c75a35e4f24fd5bba95595c0c919bd62b87013326802ff'
OLD_ARCHIVE='de931a43c01c4272ffd3cd65d1304b460c4a0c8f4b90990f3b7b3b606875ffc9'


def digest(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source,'sha256').hexdigest()


def git(*args):
    return subprocess.check_output(['git','-C',str(ROOT),*args])


def require(ok,reason):
    if not ok:
        raise ValueError(reason)


def freeze():
    prefix=NS.relative_to(ROOT).as_posix()+'/'
    require(not (EXTERNAL/'integrated').exists() and not (NS/'FROZEN.json').exists(), 'sole_fresh_integrated_recovery_required')
    require(git('merge-base',BASE,'HEAD').decode().strip()==BASE and all(path.startswith(prefix)
            for path in git('diff','--name-only',BASE).decode().splitlines()),'evidence_namespace_only')
    require(git('show',PLAN)==(NS/'PLAN.md').read_bytes(),'fixed_recovery_plan_changed')
    previous=read(PREVIOUS/'FROZEN.json')
    require(previous['product']==PRODUCT and digest(PREVIOUS/'FROZEN.json')==OLD_FREEZE
            and digest(PREVIOUS/'ORIGINAL_RUNTIME.zip')==OLD_ARCHIVE,'prior_profile_evidence_changed')
    previous_status=read(PREVIOUS/'evidence/STARTUP_AND_REGISTRY_REVIEW.json')
    count=previous_status['integrated']
    require(not previous_status['passed_integrated_qualification'] and count['attempts']==1 and count['business_calls']==0
            and count['stock_A_normal_exit'] and count['B_stock_started']==0,'prior_failure_and_denominators_not_retained')
    with ZipFile(PREVIOUS/'ORIGINAL_RUNTIME.zip') as archive:
        for name in ('TRIAL.json','stock_QA/STOCK_CLOSE.json','stock_QA/worker/EOF.json'):
            require(archive.read('integrated/'+name)==(PREVIOUS_RUN/'integrated'/name).read_bytes(), 'original_failed_run_changed/'+name)
    preflight = EXTERNAL/'preflight/PREFLIGHT.json'
    proof=read(preflight)
    require(proof['passed'] and proof['old_import_failed_at_expected_symbol'] and proof['same_formal_stock_assembly']
            and proof['same_formal_owner_and_real_thin'] and proof['thin_budget_rejected_before_owner']
            and proof['owner_budget']['passed'] and proof['owner_budget']['zero_product_dispatch']
            and all(proof[key]==0 for key in ('new_Blender_starts','new_rasters','new_model_starts','extra_API_calls')),
            'actual_recovered_assembly_preflight_not_passed')
    inputs={}

    def pin(path, receipt=None):
        path=Path(path).resolve(strict=True)
        row=inputs.get(path)
        if row is None:
            row={'path':str(path),'sha256':digest(path),'bytes':path.stat().st_size}
            inputs[path]=row
        if receipt is not None:
            require(row['sha256']==receipt['sha256'] and row['bytes']==receipt['bytes'],'prior_input_changed/'+str(path))

    for row in previous['direct_inputs']:
        pin(row['path'],row)
    for file in ('FROZEN.json','REPORT.md','RAW_INDEX.json','ORIGINAL_RUNTIME.zip','evidence/STARTUP_AND_REGISTRY_REVIEW.json',
                 'evidence/CLI_REGISTRY_PROOF.json','evidence/TRIAL_FAILURE.json'):
        path=PREVIOUS/file
        require(hashlib.sha256(git('show',BASE+':'+path.relative_to(ROOT).as_posix())).hexdigest()==digest(path),
                'prior_seal_differs_from_Git/'+file)
        pin(path)
    for folder in (NS,preflight.parent):
        for path in folder.rglob('*'):
            if path.is_file():
                require(path.suffix!='.pyc','bytecode_must_not_enter_freeze')
                pin(path)
    save(NS/'FROZEN.json',{'schema':'m1-region-task-brief-client-profile-recovery-001-v1',
         'prior_result_commit':BASE,'prior_freeze_sha256':OLD_FREEZE,'prior_archive_sha256':OLD_ARCHIVE,
         'private_root':str(EXTERNAL),'formal_run_root':str(EXTERNAL/'integrated'),
         'preflight_sha256':digest(preflight),'product':PRODUCT,'source_count':143,'CLI':'0.152.1',
         'fixture_slots':['P2','P3'],'arms':['QA','QB'],'qualification_attempts':1,'replacement_attempts':0,
         'new_Blender_starts':0,'new_model_starts':0,'new_rasters':0,'extra_API_calls':0,'product_diff':0,
         'max_outer_business':12,'direct_inputs':[inputs[key] for key in sorted(inputs)]})
    print('Frozen',len(inputs),digest(NS/'FROZEN.json'),flush=True)


def verify():
    path=NS/'FROZEN.json'
    fixed=read(path)
    require(fixed['product']==PRODUCT and fixed['prior_result_commit']==BASE and Path(fixed['private_root'])==EXTERNAL
            and digest(EXTERNAL/'preflight/PREFLIGHT.json')==fixed['preflight_sha256'],'profile_frozen_identity_changed')
    for row in fixed['direct_inputs']:
        source=Path(row['path'])
        require(source.stat().st_size==row['bytes'] and digest(source)==row['sha256'],'profile_frozen_input_changed/'+str(source))
    return digest(path)


if __name__=='__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'fixed_interpreter_required')
    freeze()
