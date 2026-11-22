"""Freeze and run the two qualification slots and one paired formal sequence."""

import argparse
import ast
from hashlib import file_digest, sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import time


NS = Path(__file__).resolve().parent
V = NS.parent
REPO = V.parent
EXTERNAL = Path('D:/he_m4_yanyite_dual_curved_region_native_001').resolve()
SLOTS = ('QN', 'QP', 'N1', 'P1')
PLAN_GIT = '9eb4d8f8563961b7fea44eb0a004d26c7832b207'
PLAN_SOURCE = PLAN_GIT+':docs/M4_YANYITE_DUAL_CURVED_REGION_NATIVE_001_PLAN.md'
ASSET = Path('D:/codex data/2026-10-02/fps-blender-models/Yanyite/outputs/Yanyite_Appearance.blend')
ASSET_DIGEST = '614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d'
PRODUCT = {
    'commit':'7e096daf3bb24596905f76abefa5e07a96a9f5d1',
    'source_sha256':'3941eaaa911256a5b8876cf5e9fc9926a15cba3583bd3d38f2e960f41626b5d8',
    'wheel_sha256':'fe8080d14f82964f5af3cdb49da7779e71498cc1280f5a0c3514b86ef0792994',
}
BINDING = V/'m4_region_task_global_first_frame_001/install/PRODUCT_RUN_BINDING.json'
DISPLAY = V/'m4_source_region_display_001'
HISTORICAL = 'aa45f033ce662b7453dda77084b36da34640f558'
HIST_REFS = {
    'inputs/evaluated_selected.json':'493ba8fe76d9e3034a1c7393056170e44c84ed1a13209b8d1625f65567d40066',
    'runtime_archive/f000240_ORACLE_initial.json':'470c83108128eae1572f0ad96a902d407c9f8a94bdcd03a63948978086430ff7',
}
PROMPT = NS/'inputs/PROMPT.txt'
FROZEN = NS/'FROZEN.json'
BLENDER = Path('D:/Tools/blender5.2/blender.exe')
CLI = Path('C:/Users/Administrator/.codex/packages/standalone/releases/0.152.1-x86_64-pc-windows-msvc/bin/codex.exe')
RUNNER = NS/'runtime/run_slot.py'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_bytes())


def pin(path):
    path = Path(path).resolve(strict=True)
    with path.open('rb') as handle:
        return {'path':str(path), 'bytes':path.stat().st_size, 'sha256':file_digest(handle,'sha256').hexdigest()}


def write(path, result):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(result,stream,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)
        stream.write('\n')


def append(journal, entry):
    with journal.open('a',encoding='utf8',newline='\n') as io:
        io.write(json.dumps(entry,ensure_ascii=False,sort_keys=True,allow_nan=False)+'\n')
        io.flush()
        os.fsync(io.fileno())


def git(*args):
    return subprocess.check_output(['git','-C',str(REPO),*args])


def freeze(reports):
    require(not FROZEN.exists() and not (EXTERNAL/'slots').exists(),'one_freeze_before_new_owned_slots')
    require(RUNNER.is_file(),'actual_new_slot_entry_missing')
    require((NS/'PLAN.md').read_bytes()==git('show',PLAN_SOURCE),'planning_commit_bytes_changed')
    inputs = {}

    def bind(path, expected=None):
        got = pin(path)
        if expected is not None:
            require(all(got[key]==expected[key] for key in ('bytes','sha256')),'immutable_input_changed/'+got['path'])
        inputs[got['path']] = got
        return got

    asset = bind(ASSET)
    require((asset['bytes'],asset['sha256'])==(3415766,ASSET_DIGEST),'original_yanyite_asset_bytes_changed')
    prompt = bind(PROMPT)
    require(PROMPT.read_bytes().decode('utf8').count('至少 0.40 m')==1,'unexpected_natural_prompt')
    build = read(BINDING)
    require((build['preparation_git'],build['source_sha256'],build['wheel_sha256'])==
            (PRODUCT['commit'],PRODUCT['source_sha256'],PRODUCT['wheel_sha256'])
            and len(build['source_manifest'])==143,'fixed_product_install_identity_changed')
    require(bind(build['wheel_path'])['sha256']==PRODUCT['wheel_sha256'],'installed_wheel_origin_changed')
    for source in build['source_manifest']:
        require(bind(Path(build['install_root'])/source['path'])['sha256']==source['sha256'],
                'installed_python_source_changed/'+source['path'])
    require(subprocess.check_output([str(CLI),'--version'],timeout=15).decode().strip()=='codex-cli 0.152.1',
            'fixed_cli_version_changed')
    for name,expected in HIST_REFS.items():
        data = DISPLAY/name
        original = git('show',HISTORICAL+':'+data.relative_to(REPO).as_posix())
        require(bind(data)['sha256']==sha256(original).hexdigest()==expected,'historical_truth_input_changed/'+name)
    for path in (BINDING,BLENDER,CLI,Path(sys.executable)):
        bind(path)
    require(bool(reports),'actual_preflight_and_independent_geometry_required')
    for report_path in reports:
        proof = read(report_path)
        require(proof['passed'] is True,'offline_preparation_failed/'+str(report_path))
        bind(report_path)
        for item in proof.get('source_pins',[]):
            bind(item['path'],item)
    for path in NS.rglob('*'):
        if path.is_file():
            require(path.suffix!='.pyc','unintended_binary_cache_in_frozen_evidence')
            if path.suffix=='.py':
                ast.parse(path.read_bytes(),filename=str(path))
            bind(path)
    specification = {
        'plan':PLAN_GIT, 'plan_reference':PLAN_SOURCE, 'passed_offline_preflight':True,
        'slots':list(SLOTS), 'asset_path':asset['path'],'asset_sha256':asset['sha256'],
        'prompt_sha256':prompt['sha256'], 'product':PRODUCT,'product_binding':str(BINDING),
        'cli_version':'0.152.1','cli_path':str(CLI),'request_model':['gpt-6.1-sol','medium','default'],
        'limits':{'Blender_starts':4,'model_consumers':2,'tools_per_slot':12,
                  'rasters_per_slot':12,'task_seconds':450,'owned_seconds':600,'replacements':0},
        'direct_inputs':[inputs[path] for path in sorted(inputs)],
    }
    write(FROZEN,specification)
    print('Frozen',pin(FROZEN)['sha256'],len(inputs),'inputs',flush=True)


def verified_freeze():
    frozen = read(FROZEN)
    require(frozen['plan']==PLAN_GIT and frozen['slots']==list(SLOTS)
            and all(pin(item['path'])==item for item in frozen['direct_inputs']),'fixed_frozen_inputs_changed')
    return pin(FROZEN)['sha256']


def launch(label,journal,freeze_digest):
    root = EXTERNAL/'slots'/label
    require(not root.exists(),'fresh_owned_slot_already_exists/'+label)
    start = time.perf_counter_ns()
    append(journal,{'event':'start','label':label,'perf_ns':start,'freeze_sha256':freeze_digest})
    argv = [sys.executable,'-IB','-X','utf8',str(RUNNER),label]
    proc = subprocess.run(argv,cwd=REPO)
    closed = time.perf_counter_ns()
    pub_path, result_path = root/'SLOT_PUBLICATION.json', root/'SLOT_RESULT.json'
    item = {'event':'slot_exit','label':label,'perf_ns':closed,'controller_wall_ns':closed-start,
            'exit_code':proc.returncode}
    if pub_path.is_file() and result_path.is_file():
        pub, result = read(pub_path), read(result_path)
        status = pub['status']
        require(result['status']==status and pub['result_sha256']==pin(result_path)['sha256'],
                'slot_publication_not_its_own_result/'+label)
        item.update(status=status, publication=pin(pub_path), result=pin(result_path))
    append(journal,item)
    return item


def qualify():
    digest = verified_freeze()
    journal = EXTERNAL/'QUALIFICATION_SEQUENCE.jsonl'
    journal.open('x').close()
    # One slot is available to each arm even if the other arm logs a real quality failure.
    for label in SLOTS[:2]:
        launch(label,journal,digest)


def formal(qualification_scores):
    digest = verified_freeze()
    require(len(qualification_scores)==2,'exactly_two_current_raw_qualification_scores')
    arms = {}
    for label,score_path in zip(SLOTS[:2],qualification_scores,strict=True):
        root = EXTERNAL/'slots'/label
        result, publication = pin(root/'SLOT_RESULT.json'),pin(root/'SLOT_PUBLICATION.json')
        live = read(publication['path'])
        proof = read(score_path)
        require(live['status']=='completed' and live['result_sha256']==result['sha256']
                and proof['passed'] is True and proof['label']==label
                and proof['slot_result']==result and proof['slot_publication']==publication
                and Path(score_path).resolve().is_relative_to(EXTERNAL/'score'),
                'both_same_batch_live_qualifications_required/'+label)
        arms[label] = {'result_sha256':result['sha256'],'publication_sha256':publication['sha256'],'score':pin(score_path)}
    write(EXTERNAL/'QUALIFICATION_GATE.json',{'passed':True,'freeze_sha256':digest,'arms':arms})
    journal = EXTERNAL/'FORMAL_SEQUENCE.jsonl'
    journal.open('x').close()
    for label in SLOTS[2:]:
        item = launch(label,journal,digest)
        if item['exit_code']!=0 or item.get('status')!='completed':
            append(journal,{'event':'blocked','label':label,'unrun':list(SLOTS[SLOTS.index(label)+1:])})
            return 1
    return 0


if __name__=='__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'fixed_isolated_interpreter_flags_required')
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument('phase',choices=('freeze','qualification','formal'))
    command.add_argument('--reports',type=Path,nargs='*',default=[])
    args = command.parse_args()
    if args.phase=='freeze':
        freeze(args.reports)
    elif args.phase=='qualification':
        qualify()
    else:
        raise SystemExit(formal(args.reports))
