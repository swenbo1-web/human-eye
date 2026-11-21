"""Freeze and run the single authorized same-product full/brief model pair."""

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
from common import ASSET, ASSET_SHA256, BLENDER, CATALOGUE, DETAILS, DUAL, EXTERNAL, ORDER, PRODUCT, PRODUCT_BINDING
from common import PRODUCT_SCHEMA, ROOT, append, read, save, sha

ORIGINAL = '53afaf22b41ca8c1ad80f7b1b4e8719fb36a01a6'
PLAN = '7198664498157087716aada2393efcd17bb4fefd:docs/M1_SOURCE_REGION_FIRST_PACKET_CONSUMPTION_001_PLAN.md'
PROMPT_SHA = 'b1a568881b10964a0e70232c0c044f039e61c38900489c4ca9cbe171602a0247'
TOOLS = ['execute_blender_code','execute_python','human_eye_scene_observe','read_images','render_local','render_views']


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def git(*args):
    return subprocess.check_output(['git','-C',str(ROOT),*args])


def probe(entry,*args):
    return json.loads(subprocess.check_output([sys.executable,'-IB',str(NS/entry),*args],cwd=ROOT,timeout=45))


def freeze():
    require(not EXTERNAL.exists() and not (NS/'FROZEN.json').exists()
            and git('rev-parse','HEAD').decode().strip()==ORIGINAL and not git('diff','--name-only',ORIGINAL),
            'fresh_isolated_experiment_with_zero_product_delta_required')
    require((NS/'PLAN.md').read_bytes()==git('show',PLAN),'frozen_plan_changed')
    pins = {}

    def pin(path, expected=None, size=None):
        path = Path(path).resolve(strict=True)
        if path not in pins:
            pins[path] = {'path':str(path),'bytes':path.stat().st_size,'sha256':sha(path)}
        row = pins[path]
        require((expected is None or row['sha256']==expected) and (size is None or row['bytes']==size),
                'frozen_input_mismatch/' + str(path))
        return row

    def bind(rows):
        for row in rows:
            pin(row['path'],row['sha256'],row.get('bytes'))

    pin(ASSET,ASSET_SHA256)
    prompt = pin(NS/'inputs/PROMPT.txt',PROMPT_SHA,475)
    for item in (PRODUCT_BINDING, PRODUCT_SCHEMA, CATALOGUE, BLENDER, sys.executable):
        pin(item)
    binding = read(PRODUCT_BINDING)
    require(admission.registered_product()==PRODUCT,'installed_product_identity_changed')
    wheel = Path(pin(binding['wheel_path'],PRODUCT['wheel_sha256'])['path'])
    with ZipFile(wheel) as package:
        for source in binding['source_manifest']:
            name,digest = source['path'],source['sha256']
            pin(Path(binding['install_root'])/name,digest)
            require(sha256(git('show',PRODUCT['commit']+':'+name)).hexdigest()==digest
                    and sha256(package.read(name)).hexdigest()==digest,'Git_wheel_install_changed/' + name)
    truth = read(NS/'checks/TRUTH.json')
    require(truth['asset_sha256']==ASSET_SHA256 and truth['exact_shortest_distance_m']=='31/16'
            and truth['exact_world_direction']=='-X' and truth['source_triangles']==[0,1]
            and [truth[field] for field in ('object_count','vertex_count','triangle_count')]==[9,54,56],
            'independent_truth_mismatch')
    source_pins = truth['source_pins']
    bind([source_pins['index'],source_pins['archive'],*source_pins['members']])
    offline = read(NS/'qualification/PREFLIGHT.json')
    consumer = read(NS/'consumer/PREFLIGHT.json')
    require(offline['passed'] and offline['offline_software_rasters']==1 and offline['Blender_starts']==offline['model_starts']==0
            and offline['paired_fixed_CLI']['brief_exact_stages']==6 and
            consumer['passed'] and consumer['provider_model_launches']==0 and consumer['arms']['A1']==consumer['arms']['B1'],
            'full_qualification_and_protected_consumer_preflight_required')
    bind(offline['current_fixture_binding_pins'])
    bind(consumer['proof']['execution_sources'])
    pin(consumer['proof']['CLI_path'],consumer['proof']['CLI_sha256'])
    pin(consumer['proof']['Python_path'],consumer['proof']['Python_sha256'])
    old = read(DUAL/'FROZEN.json')
    for row in old['direct_inputs']:
        source = Path(row['path']).resolve()
        if source.is_relative_to(ROOT.resolve()):
            pin(source,row['sha256'],row['bytes'])
    dispatch = {}
    for slot in ORDER:
        entry = probe('harness/run_slot.py',slot,'--dispatch-smoke')
        recorder = probe('harness/mcp_entry.py','--dispatch-smoke',slot)
        require(entry['slot']==slot and entry['group']=='P' and entry['product']==PRODUCT and entry['tools']==TOOLS
                and entry['schema']==admission.SCHEMA and Path(entry['actual_product_schema'])==PRODUCT_SCHEMA
                and Path(entry['asset'])==ASSET and Path(entry['run_root'])==EXTERNAL
                and Path(recorder['current_binding'])==PRODUCT_BINDING
                and Path(recorder['absolute_state_file'])==EXTERNAL/'slots'/slot/'product_state.json',
                'actual_fresh_entry_has_wrong_frozen_arguments/' + slot)
        dispatch[slot] = {'launch':entry,'recorder':recorder}
    for path in NS.rglob('*'):
        if path.is_file():
            if path.suffix=='.py':
                ast.parse(path.read_bytes(),filename=str(path))
            pin(path)
    save(NS/'FROZEN.json',{'schema':admission.SCHEMA,'slots':list(ORDER),'qualification_slots':list(admission.QUALIFICATION),
        'formal_slots':list(admission.FORMAL),'response_detail_by_slot':DETAILS,'product':PRODUCT,'asset_sha256':ASSET_SHA256,
        'asset_path':str(ASSET),'prompt_sha256':prompt['sha256'],'prompt_bytes':prompt['bytes'],'offline_preflight_passed':True,
        'dispatch':dispatch,'max_Blender_starts':4,'max_model_consumers':2,'max_business_per_slot':12,
        'max_raster_per_slot':12,'task_s':450,'owned_s':600,'product_delta_files':0,'product_builds':0,
        'replacements':0,'diagnostic_artifact_publications':0,'direct_inputs':[pins[key] for key in sorted(pins)]})
    print('Frozen',sha(NS/'FROZEN.json'),len(pins),flush=True)


def reopen(slot, result, receipt, frozen):
    image = (result.get('qualification') or {}).get('product_image')
    require(image and result['model_consumers']==0,'qualifier_did_not_produce_its_current_original')
    folder = (EXTERNAL/'slots'/slot).resolve(strict=True)
    path = Path(image['path'])
    require(path.is_absolute() and str(path.resolve(strict=True))==str(path)
            and path.is_relative_to(folder) and path.stat().st_size==image['bytes'] and sha(path)==image['sha256'],
            'closed_owned_scene_original_not_readable')
    save(EXTERNAL/'preflight'/f'{slot}_CLOSED_IMAGES.json',{'passed':True,'freeze_sha256':frozen,
         'result_sha256':receipt['result_sha256'],'image':image})


def sequence():
    frozen = admission.verify_freeze()
    require(not EXTERNAL.exists(),'only_one_fresh_owned_sequence_is_authorized')
    journal = EXTERNAL/'preflight/FORMAL_SEQUENCE.jsonl'
    journal.parent.mkdir(parents=True,exist_ok=False)
    journal.touch(exist_ok=False)
    all_complete = True
    for slot in ORDER:
        append(journal,{'event':'start','label':slot,'freeze_sha256':frozen,'started_ns':time.perf_counter_ns()})
        process = subprocess.run([sys.executable,'-IB',str(NS/'harness/run_slot.py'),slot],cwd=ROOT)
        try:
            result,receipt = admission.publication(slot,frozen)
            safe = admission.can_continue(result,receipt)
            closed = False
            if slot in admission.QUALIFICATION:
                safe = safe and process.returncode==0 and receipt['status']=='completed'
                if safe:
                    reopen(slot,result,receipt,frozen)
                    closed = True
        except Exception as error:
            append(journal,{'event':'unconfirmed','label':slot,'error':str(error),'error_type':type(error).__name__,
                            'exit_code':process.returncode})
            return 1
        append(journal,{'event':'publication','label':slot,'result_sha256':receipt['result_sha256'],
                        'status':receipt['status'],'model_consumers':result['model_consumers'],
                        'exit_code':process.returncode,'closed_image_verified':closed,'safe_to_continue':safe})
        all_complete &= safe and process.returncode==0 and receipt['status']=='completed'
        if not safe:
            return 1
    return 0 if all_complete else 1


if __name__=='__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'pinned_interpreter_I_B_required')
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('action',choices=('freeze','sequence'))
    raise SystemExit(globals()[cli.parse_args().action]())
