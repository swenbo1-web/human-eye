"""Pin the historical inputs and the one isolated local trial."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile

NS = Path(__file__).resolve().parent
sys.path[:0]=[str(NS/'harness'),str(NS)]
from common import CATALOGUE, EXTERNAL, ORIGINAL, PRODUCT, PRODUCT_BINDING, PRODUCT_SCHEMA, ROOT, read, save
from product_replay import archive_scope, fixtures, FORMAL, PREDICTION, TARGET


BASE = 'f56108e537a0664c07a0e9cb2f88186f30ec604c'
PLAN = '3f4ed0ba8aab25a3b7e47f820fdf3cd816687def:docs/M1_REGION_TASK_BRIEF_CLIENT_PROFILE_001_PLAN.md'
ARCHIVE_SHA = 'd260b4854c38cc3e3e23808027442be34903bf88f0f2a4679033254793159c93'


def digest(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source,'sha256').hexdigest()


def git(*args):
    return subprocess.check_output(['git','-C',str(ROOT),*args])


def require(test, error):
    if not test:
        raise ValueError(error)


def freeze():
    prefix = NS.relative_to(ROOT).as_posix()+'/'
    require(not (EXTERNAL/'integrated').exists() and not (NS/'FROZEN.json').exists(),'single_fresh_local_trial_required')
    require(git('merge-base',BASE,'HEAD').decode().strip()==BASE
            and all(path.startswith(prefix) for path in git('diff','--name-only',BASE).decode().splitlines()),
            'evidence_namespace_only')
    require(git('show',PLAN)==(NS/'PLAN.md').read_bytes(),'fixed_plan_changed')
    archive=(ORIGINAL/'ORIGINAL_RUNTIME.zip').resolve()
    require(digest(archive)==ARCHIVE_SHA and read(ORIGINAL/'RAW_INDEX.json')['archive']['sha256']==ARCHIVE_SHA,
            'prior_formal_archive_changed')
    require(len(read(ORIGINAL/'consumer/COSTS.json')['slots'])==6 and
            read(ORIGINAL/'checks/QUALITY.json')['quality_complete_counts']=={'N':2,'P':3},'prior_quality_denominator_changed')
    pins={}

    def pin(path, expected=None, size=None):
        path=Path(path).resolve(strict=True)
        if path not in pins:
            pins[path]={'path':str(path),'sha256':digest(path),'bytes':path.stat().st_size}
        row=pins[path]
        require((expected is None or row['sha256']==expected) and (size is None or row['bytes']==size),
                'fixed_input_changed/'+str(path))

    for row in read(ORIGINAL/'FROZEN.json')['direct_inputs']:
        path=Path(row['path'])
        if path.suffix=='.py' or path.name=='codex.exe':
            pin(path,row['sha256'],row['bytes'])
    for path in (PRODUCT_BINDING,PRODUCT_SCHEMA,CATALOGUE,archive,ORIGINAL/'RAW_INDEX.json',
                 ORIGINAL/'consumer/COSTS.json',ORIGINAL/'checks/QUALITY.json',sys.executable):
        pin(path)
    binding=read(PRODUCT_BINDING)
    require(len(binding['source_manifest'])==143 and binding['preparation_git']==PRODUCT['commit']
            and binding['source_sha256']==PRODUCT['source_sha256'],'wrong_fixed_install')
    wheel=Path(binding['wheel_path'])
    pin(wheel,PRODUCT['wheel_sha256'])
    with ZipFile(wheel) as package:
        for row in binding['source_manifest']:
            name,expected=row['path'],row['sha256']
            pin(Path(binding['install_root'])/name,expected)
            require(hashlib.sha256(package.read(name)).hexdigest()==expected
                    ==hashlib.sha256(git('show',PRODUCT['commit']+':'+name)).hexdigest(), 'Git_wheel_install_changed/'+name)
    for batch in (FORMAL,PREDICTION,TARGET):
        for row in archive_scope(batch)[-1]:
            pin(row['path'],row['sha256'],row['bytes'])
    for label in ('P2','P3'):
        for item in fixtures(label).values():
            for row in item['pins']:
                pin(row['path'],row['sha256'],row['bytes'])
    for path in NS.rglob('*'):
        if path.is_file():
            require(path.suffix!='.pyc','bytecode_must_not_enter_freeze')
            pin(path)
    frozen={'schema':'m1-region-task-brief-client-profile-001-v1','history_Git':BASE,'history_archive_sha256':ARCHIVE_SHA,
            'product':PRODUCT,'source_count':143,'fixture_slots':['P2','P3'],'arms':['QA','QB'],'CLI':'0.152.1',
            'sole_profile_rule':'active_observation with region_task allows absent or brief response_detail',
            'replacements':0,'builds':0,'installs':0,'new_Blender_starts':0,'new_model_starts':0,'new_rasters':0,
            'extra_API_calls':0,'argument_rewrites':0,'max_outer_business':12,
            'direct_inputs':[pins[key] for key in sorted(pins)]}
    save(NS/'FROZEN.json',frozen)
    print('Frozen',len(pins),digest(NS/'FROZEN.json'),flush=True)


def verify():
    path=NS/'FROZEN.json'
    fixed=read(path)
    require(fixed['product']==PRODUCT and fixed['history_Git']==BASE and fixed['history_archive_sha256']==ARCHIVE_SHA,
            'profile_frozen_identity_changed')
    for row in fixed['direct_inputs']:
        source=Path(row['path'])
        require(source.stat().st_size==row['bytes'] and digest(source)==row['sha256'],'profile_frozen_input_changed/'+str(source))
    return digest(path)


if __name__=='__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'fixed_interpreter_required')
    freeze()
