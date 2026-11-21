"""Run the frozen source-scope comparison on the existing installed product."""

import argparse
import ast
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys
import time


NS = Path(__file__).resolve().parent
V = NS.parent
ROOT = V.parent
REFERENCE = V/'perf050_dense_pair_transfer_001'
ORIGINAL = V/'perf050_source_scope_rank_transfer_001'
ENGINE = V/'m1_joint_full_task_tail_scope_001'
INSTALL = ENGINE/'install'
HISTORY = '5a6bded884fd0869df42a18cfb6fbba5733eaa43'
PLAN = '695ed39361fdc9baf8872c84fd4a1c6a9f6858d7:docs/PERF050_SOURCE_SCOPE_RANK_TRANSFER_RECOVERY_001_PLAN.md'
RUN = Path('D:/he_perf050_source_scope_rank_transfer_recovery_001')
FORMAL = ('N1', 'P1')
QUALIFICATION = ('QN', 'QP')
ORDER = QUALIFICATION + FORMAL

reference = run_path(str(REFERENCE/'experiment.py'))
sha, read, write, git, archive, seal = (reference[name] for name in ('sha','read','write','git','archive','seal'))
archive.__globals__.update(NS=NS, RUN=RUN, HISTORY=HISTORY)
sys.path.insert(0, str(NS/'harness'))
import admission
from common import ASSET, ASSET_SHA256, BLENDER, PRODUCT, PRODUCT_BINDING, PRODUCT_SCHEMA


def require(value, reason):
    if not value:
        raise ValueError(reason)


def smoke(entry, *args):
    return json.loads(subprocess.check_output([sys.executable, '-IB', str(NS/entry), *args], cwd=ROOT, timeout=45))


def freeze():
    require(not RUN.exists() and not (NS/'FROZEN.json').exists(), 'fresh_outputs_required')
    require(git('rev-parse','HEAD').decode().strip() == HISTORY and not git('diff','--name-only',HISTORY),
            'zero_product_delta_required')
    require((NS/'PLAN.md').read_bytes() == git('show',PLAN), 'frozen_plan_changed')
    pins = {}

    def pin(path, expected=None, size=None):
        p = Path(path).resolve(strict=True)
        if p not in pins:
            pins[p] = {'path':str(p), 'bytes':p.stat().st_size, 'sha256':sha(p)}
        row = pins[p]
        require((expected is None or row['sha256'] == expected) and (size is None or row['bytes'] == size),
                'fixed_input_mismatch/' + str(p))
        return row

    def bind(rows):
        for row in rows:
            pin(row['path'], row['sha256'], row.get('bytes'))

    asset = pin(ASSET, ASSET_SHA256)
    previous_freeze = pin(ORIGINAL/'FROZEN.json','573d66fd20866f82d27f89fed648c8713d8f2c1013b35d31144b9a7476656323')
    stop = read(ORIGINAL/'checks/STOPPED.json')
    require(stop['qualification_passed'] is False and [row['status'] for row in stop['slots']] == ['failed','unrun','unrun','unrun'],
            'old_denominator_lost')
    bind(stop['observed_receipts'])
    for item in ('checks/STOPPED.json','RUNTIME_INDEX.json','checks/TRUTH.json','inputs/PROMPT.txt'):
        pin(ORIGINAL/item)
    old_archive = read(ORIGINAL/'RUNTIME_INDEX.json')['archive']
    require(old_archive['sha256'] == '0e7f9dbb5864a999c90730f709b8d5f3ddc8edb263e7d88cc806598bae32e4a8', 'old_archive_identity_lost')
    bind([old_archive])
    prompt = pin(NS/'inputs/PROMPT.txt',read(ORIGINAL/'FROZEN.json')['prompt_sha256'],562)
    install = read(PRODUCT_BINDING)
    build = read(INSTALL/'BUILD_INSTALL.json')
    require(admission.registered_product() == PRODUCT and build['binding'] == install
            and build['passed'] is True and build['wheel_RECORD_verified'] is True, 'fixed_product_qualification_changed')
    pin(install['wheel_path'], PRODUCT['wheel_sha256'])
    bind(build['installed_files'])
    for row in install['source_manifest']:
        digest = row['sha256']
        pin(Path(install['install_root'])/row['path'], digest)
        require(sha256(git('show',f'{PRODUCT["commit"]}:{row["path"]}')).hexdigest() == digest,
                'Git_vs_actual_install_source/' + row['path'])
    for item in ('DECISION.json','checks/TOOLS_LIST.json','install/BUILD_INSTALL.json','install/PRODUCT_RUN_BINDING.json',
                 'install/PRODUCT_SCHEMA.json','install/TOOLS_SCHEMA.json'):
        pin(ENGINE/item)
    require(read(ENGINE/'DECISION.json')['candidate'] == PRODUCT['commit'], 'accepted_candidate_record_differs')

    old = read(REFERENCE/'FROZEN.json')
    for row in old['direct_inputs']:
        path = Path(row['path']).resolve()
        if path.is_relative_to(ROOT.resolve()) and not path.is_relative_to(REFERENCE.resolve()):
            pin(path, row['sha256'], row['bytes'])
    for item in (REFERENCE/'FROZEN.json', reference['previous']['ARCHIVE'], BLENDER, sys.executable):
        pin(item)

    truth_path = NS/'checks/TRUTH.json'
    truth = read(truth_path)
    require(truth_path.read_bytes() == (ORIGINAL/'checks/TRUTH.json').read_bytes(), 'old_truth_bytes_changed')
    oracle = run_path(str(ORIGINAL/'checks/truth.py'))
    meshes, sources = oracle['frozen_meshes']()
    require(oracle['analytical_truth'](meshes, sources, run_path(str(oracle['MEMBERSHIP']))) == truth,
            'independent_arithmetic_replay_differs')
    bind(sources.values())
    consumer = read(NS/'consumer/PREFLIGHT.json')
    bind(consumer['source_pins'])
    require(consumer['passed'] and consumer['exact_common_prompt']['sha256'] == prompt['sha256']
            and consumer['provider_model_launches'] == 0 and consumer['Blender_launches'] == 0, 'current_consumer_preflight_required')
    preflight = read(NS/'qualification/REPLAY_PREFLIGHT.json')
    require(preflight['passed'] is True and preflight['qualification_calls'] == {'QN':3,'QP':8}
            and preflight['rejection_recovery'] is True and preflight['actual_admission_replay'] is True
            and preflight['Blender_starts'] == preflight['model_starts'] == 0, 'full_actual_qualifications_replay_required')
    bind(preflight['pins'])

    launch = {label:smoke('harness/run_slot.py',label,'--dispatch-smoke') for label in ORDER}
    recorder = {label:smoke('harness/mcp_entry.py','--dispatch-smoke',label) for label in ('QP','P1')}
    for label, entry in launch.items():
        group = admission.SLOTS[label][0]
        require(entry['fresh_process_prepared_only'] and entry['slot'] == label and entry['group'] == group
                and entry['schema'] == admission.SCHEMA and entry['product'] == PRODUCT
                and entry['tools'] == old['fresh_dispatch'][group+'1']['tools']
                and Path(entry['asset']) == ASSET and Path(entry['run_root']) == RUN
                and Path(entry['actual_product_schema']) == PRODUCT_SCHEMA
                and Path(entry['mcp_entry']) == NS/'harness/mcp_entry.py', 'actual_entry_binding_changed/' + label)
    for label, entry in recorder.items():
        require(entry['schema'] == admission.SCHEMA and entry['label'] == label
                and entry['fresh_process_prepared_only']
                and Path(entry['absolute_state_file']) == RUN/'slots'/label/'product_state.json'
                and Path(entry['current_binding']) == PRODUCT_BINDING, 'actual_recorder_binding_changed/' + label)
    host = {'passed':True, 'fresh_dispatch':launch, 'fresh_recorder':recorder, 'actual_host_qualification_slots':list(QUALIFICATION),
            'offline_provider_starts':0, 'offline_Blender_starts':0, 'common_tools_identical_by_name_as_retained':True}
    write(NS/'harness/HOST_PREFLIGHT.json',host)
    for path in NS.rglob('*'):
        if path.is_file():
            if path.suffix == '.py':
                ast.parse(path.read_bytes(), filename=str(path))
            pin(path)
    preflights = {path:pin(NS/path)['sha256'] for path in ('consumer/PREFLIGHT.json','checks/TRUTH.json','harness/HOST_PREFLIGHT.json',
                                                         'qualification/REPLAY_PREFLIGHT.json')}
    write(NS/'FROZEN.json', {'schema':admission.SCHEMA, 'slots':list(ORDER), 'formal_slots':list(FORMAL),
        'qualification_slots':list(QUALIFICATION), 'product':PRODUCT, 'asset_path':asset['path'], 'asset_sha256':asset['sha256'],
        'prompt_sha256':prompt['sha256'], 'prompt_bytes':prompt['bytes'], 'passed_offline_preflight':True, 'preflights':preflights,
        'max_model_consumers':2, 'max_Blender_starts':4, 'max_business_per_slot':12, 'max_raster_per_slot':12,
        'task_s':450, 'owned_s':600, 'product_delta_files':0, 'product_builds':0, 'new_assets':0, 'replacements':0,
        'historical_frozen':previous_freeze,'historical_statuses':['failed','unrun','unrun','unrun'],
        'direct_inputs':[pins[p] for p in sorted(pins)]})
    print('Frozen', sha(NS/'FROZEN.json'), len(pins), flush=True)


def closed_qualification(label, result):
    from PIL import Image
    proofs = {'common':result['qualification']['common_image']}
    if label == 'QP':
        proofs['product'] = result['qualification']['product_image']
    slot = (RUN/'slots'/label).resolve(strict=True)
    for receipt in proofs.values():
        png = Path(receipt['path']).resolve(strict=True)
        require(str(png) == receipt['path'] and png.is_relative_to(slot)
                and png.stat().st_size == receipt['bytes'] and sha(png) == receipt['sha256'], 'closed_slot_original_image_failed')
        with Image.open(png) as original:
            require(original.format == 'PNG' and original.size == (512,512), 'closed_slot_original_PNG_shape')
            original.load()
    return proofs


def sequence():
    token = admission.verify_freeze()
    require(not RUN.exists(), 'sole_sequence_requires_fresh_run_directory')
    sys.path.insert(0,read(PRODUCT_BINDING)['dependency_root'])
    journal = RUN/'preflight/FORMAL_SEQUENCE.jsonl'
    journal.parent.mkdir(parents=True)
    journal.touch(exist_ok=False)
    all_complete = True
    for label in ORDER:
        write(journal, {'event':'start','label':label,'started_ns':time.perf_counter_ns(),'freeze_sha256':token}, 'a')
        proc = subprocess.run([sys.executable,'-IB',str(NS/'harness/run_slot.py'),label],cwd=ROOT)
        try:
            result, receipt = admission.publication(label,token)
            safe = admission.can_continue(result,receipt)
            closed = None
            if label in QUALIFICATION:
                safe = safe and receipt['status'] == 'completed' and proc.returncode == 0
                if safe:
                    closed = closed_qualification(label,result)
                    write(RUN/'preflight'/f'{label}_CLOSED_IMAGES.json', {'passed':True,'slot':label,
                          'result_sha256':receipt['result_sha256'],'freeze_sha256':token,'reopened':closed})
        except Exception as error:
            write(journal,{'event':'unconfirmed','label':label,'error':str(error),'error_type':type(error).__name__,
                           'exit_code':proc.returncode},'a')
            return 1
        write(journal,{'event':'publication','label':label,'closed_ns':time.perf_counter_ns(),
            'exit_code':proc.returncode,'status':receipt['status'],'safe_to_continue':safe,
            'result_sha256':receipt['result_sha256'],'model_consumers':result['model_consumers'],
            'closed_slot_image_reopens_verified':len(closed) if closed else None},'a')
        all_complete &= receipt['status'] == 'completed' and proc.returncode == 0
        if not safe:
            return 1
    return 0 if all_complete else 1


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'use_the_fixed_interpreter_I_B')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('freeze','sequence','archive','seal'))
    raise SystemExit(globals()[parser.parse_args().action]())
