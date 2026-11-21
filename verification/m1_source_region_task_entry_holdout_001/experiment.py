"""Freeze and run the single authorized nonplanar holdout comparison."""

import argparse
import ast
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import time
from zipfile import ZipFile


NS = Path(__file__).resolve().parent
sys.path.insert(0,str(NS/'harness'))
import admission
from common import ASSET,ASSET_SHA256,BLENDER,EXTERNAL,NARROW_TOOL,ORDER,ROOT,V,append,product_for,read,save,sha


PRIOR = V/'m1_source_region_task_entry_001'
HISTORY = '33a177873b07076409b3f813db476775583b8ee7'
PLAN = 'd0249e49bcaada70ef6a79130d3a164b7f9f4411:docs/M1_SOURCE_REGION_TASK_ENTRY_HOLDOUT_001_PLAN.md'
PROMPT = 'b2c117aa1ecca315903be925d8553f301d5e5d7fd8e748f632900ab3bdffc188'
READBACK = ASSET.parent/'READBACK_AFTER_RELOAD.json'
READBACK_SHA = '70baebb4994c57a13c145a79627abb0671aafb161f4837e793ac869e6fd9c62c'


def require(ok,reason):
    if not ok:
        raise ValueError(reason)


def git(*args):
    return subprocess.check_output(['git','-C',str(ROOT),*args])


def probe(entry,*args):
    return json.loads(subprocess.check_output([sys.executable,'-IB',str(NS/entry),*args],cwd=ROOT,timeout=45))


def freeze():
    namespace = NS.relative_to(ROOT).as_posix()+'/'
    delta = git('diff','--name-only',HISTORY).decode().splitlines()
    require(not EXTERNAL.exists() and not (NS/'FROZEN.json').exists()
            and git('merge-base','HEAD',HISTORY).decode().strip()==HISTORY
            and all(path.startswith(namespace) for path in delta),
            'fresh_isolated_evidence_tree_required')
    require((NS/'PLAN.md').read_bytes()==git('show',PLAN),'frozen_plan_changed')
    pins = {}

    def pin(path,expected=None,size=None):
        path = Path(path).resolve(strict=True)
        if path not in pins:
            pins[path] = {'path':str(path),'bytes':path.stat().st_size,'sha256':sha(path)}
        row = pins[path]
        require((expected is None or row['sha256']==expected) and (size is None or row['bytes']==size),
                'frozen_input_changed/' + str(path))
        return row

    pin(ASSET,ASSET_SHA256)
    pin(READBACK,READBACK_SHA)
    pin(NS/'inputs/PROMPT.txt',PROMPT,610)
    pin(sys.executable)
    pin(BLENDER)
    products = {label:admission.registered_product(label) for label in ORDER}
    for label in ('QA','QB'):
        spec = product_for(label)
        for field in ('binding','schema','catalogue'):
            pin(spec[field])
        binding = read(spec['binding'])
        wheel = Path(pin(binding['wheel_path'],spec['wheel_sha256'])['path'])
        with ZipFile(wheel) as package:
            for source in binding['source_manifest']:
                name,digest = source['path'],source['sha256']
                pin(Path(binding['install_root'])/name,digest)
                require(sha256(git('show',spec['commit']+':'+name)).hexdigest()==digest
                        and sha256(package.read(name)).hexdigest()==digest,'Git_wheel_install_changed/' + name)
    truth = read(NS/'checks/TRUTH.json')
    require(truth['asset_sha256']==ASSET_SHA256 and truth['readback_sha256']==READBACK_SHA
            and truth['counts']=={'objects':11,'vertices':64,'triangles':62}
            and truth['selected_triangles']==[0,1,8,9] and truth['reference_whole']=='Obj_04'
            and [truth['distances'][scope]['squared_exact_m2'] for scope in ('selected','whole')]
            == ['7489/128','14753/256'],'fixed_independent_geometry_did_not_match')
    installed = read(NS/'qualification/PRODUCT_REPLAY.json')
    bridge = read(NS/'qualification/BRIDGE_PREFLIGHT.json')
    consumer = read(NS/'consumer/PREFLIGHT.json')
    require(installed['passed'] and bridge['passed'] and bridge['actual_Blender']==bridge['model']==0
            and consumer['passed'] and consumer['provider_model_launches']==0,'offline_product_bridge_or_consumer_gate_failed')
    for proof in consumer['proofs'].values():
        pin(proof['CLI_path'],proof['CLI_sha256'])
        pin(proof['Python_path'],proof['Python_sha256'])
        for row in proof['execution_sources']:
            pin(row['path'],row['sha256'],row['bytes'])
    for row in read(PRIOR/'FROZEN.json')['direct_inputs']:
        source = Path(row['path']).resolve()
        if source.is_relative_to(ROOT.resolve()):
            pin(source,row['sha256'],row['bytes'])
    dispatch = {}
    for slot in ORDER:
        entry = probe('harness/run_slot.py',slot,'--dispatch-smoke')
        recorder = probe('harness/mcp_entry.py','--dispatch-smoke',slot)
        spec = product_for(slot)
        expected_tools = sorted(row['name'] for row in bridge['arms']['QA' if slot in ('QA','A1') else 'QB']['catalogue'])
        require(entry['slot']==slot and entry['group']=='P' and entry['product']==products[slot]
                and entry['schema']==admission.SCHEMA and entry['tools']==expected_tools
                and Path(entry['asset'])==ASSET and Path(entry['selected_schema'])==spec['schema']
                and Path(entry['selected_binding'])==Path(recorder['current_binding'])==spec['binding']
                and Path(entry['run_root'])==EXTERNAL and
                Path(recorder['absolute_state_file'])==EXTERNAL/'slots'/slot/'product_state.json',
                'actual_slot_entry_differs_from_frozen_arm/' + slot)
        dispatch[slot] = {'launcher':entry,'recorder':recorder}
    for path in NS.rglob('*'):
        if path.is_file():
            if path.suffix=='.py':
                ast.parse(path.read_bytes(),filename=str(path))
            pin(path)
    save(NS/'FROZEN.json',{'schema':admission.SCHEMA,'slots':list(ORDER),'products':products,'asset_sha256':ASSET_SHA256,
        'asset_path':str(ASSET),'prompt_sha256':PROMPT,'prompt_bytes':610,'readback_source_sha256':READBACK_SHA,
        'offline_preflight_passed':True,'dispatch':dispatch,'new_tool_B_only':NARROW_TOOL,
        'max_Blender_starts':4,'max_models':2,'max_business_per_slot':12,'max_raster_per_slot':12,
        'task_seconds':450,'owned_seconds':600,'candidate_builds':0,'candidate_installs':0,'replacements':0,
        'bridge_argument_rewrites':0,'direct_inputs':[pins[key] for key in sorted(pins)]})
    print('Frozen',sha(NS/'FROZEN.json'),len(pins),flush=True)


def reopen(label,result,receipt,frozen):
    proof = result.get('qualification') or {}
    image = proof.get('product_image')
    require(proof.get('passed') is True and image and result['model_consumers']==0,'missing_actual_qualification')
    root = (EXTERNAL/'slots'/label).resolve(strict=True)
    path = Path(image['path'])
    require(str(path.resolve(strict=True))==str(path) and path.is_relative_to(root)
            and path.stat().st_size==image['bytes'] and sha(path)==image['sha256'],'closed_original_same_slot_file_failed')
    save(EXTERNAL/'preflight'/f'{label}_CLOSED_IMAGE.json',{
        'image':image,'freeze_sha256':frozen,'result_sha256':receipt['result_sha256'],'passed':True})


def sequence():
    frozen = admission.verify_freeze()
    require(not EXTERNAL.exists(),'one_fresh_owned_sequence_only')
    journal = EXTERNAL/'preflight/FORMAL_SEQUENCE.jsonl'
    journal.parent.mkdir(parents=True,exist_ok=False)
    journal.touch(exist_ok=False)
    success = True
    for label in ORDER:
        append(journal,{'event':'start','label':label,'started_ns':time.perf_counter_ns(),'freeze_sha256':frozen})
        process = subprocess.run([sys.executable,'-IB',str(NS/'harness/run_slot.py'),label],cwd=ROOT)
        try:
            result,receipt = admission.publication(label,frozen)
            safe = admission.can_continue(result,receipt)
            reopened = False
            if label in admission.QUALIFICATION:
                safe = safe and receipt['status']=='completed' and process.returncode==0
                if safe:
                    reopen(label,result,receipt,frozen)
                    reopened = True
        except Exception as error:
            append(journal,{'event':'unconfirmed','label':label,'error':str(error),'error_type':type(error).__name__,
                            'exit_code':process.returncode})
            return 1
        append(journal,{'event':'publication','label':label,'result_sha256':receipt['result_sha256'],
            'status':receipt['status'],'model_consumers':result['model_consumers'],'exit_code':process.returncode,
            'closed_image_verified':reopened,'safe_to_continue':safe})
        success &= safe and receipt['status']=='completed' and process.returncode==0
        if not safe:
            return 1
    return 0 if success else 1


if __name__=='__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'pinned_interpreter_I_B_required')
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('action',choices=('freeze','sequence'))
    raise SystemExit(globals()[cli.parse_args().action]())
