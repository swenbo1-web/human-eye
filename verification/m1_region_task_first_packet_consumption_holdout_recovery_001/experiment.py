"""Derive QA from immutable evidence and run the sole registered recovery sequence."""

import argparse
import ast
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys
import time
from unittest.mock import patch


NS = Path(__file__).resolve().parent
sys.path[:0] = [str(NS/'harness'), str(NS/'qualification'), str(NS)]
import admission
from admission import DERIVED, OLD_ARCHIVE, OLD_FREEZE, OLD_RESULT, require
from common import (ASSET, EXTERNAL, FORMAL_LABELS, ORDER, PRODUCT_BINDING, PRODUCT_SCHEMA, ROOT, SEAL,
                    SLOTS, append, catalogue_for, read, save, sha)


PLAN = '10469c7389243d41105ba2cf5e95f4fb307efe30:docs/M1_REGION_TASK_FIRST_PACKET_CONSUMPTION_HOLDOUT_RECOVERY_001_PLAN.md'
OLD_COMMIT = '0b754de85f21e1ec12cb74a08211ac19cfd4fa0d'
OLD = NS.parent/'m1_region_task_first_packet_consumption_holdout_001'
OLD_RUN = Path('D:/he_m1_region_task_first_packet_consumption_holdout_001')
CONTROL = NS/'checks/controls.py'


def argv(name,*args):
    return [sys.executable,'-IB','-X','utf8',str(NS/name),*args]


def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT)


def load_checks(source):
    install = read(PRODUCT_BINDING)
    sys.path[:0] = [install['dependency_root'],read(SEAL/'SHARED_DEPENDENCY.json')['dependency_root']]
    return run_path(str(source))


def derive():
    started = time.perf_counter_ns()
    origin = run_path(str(NS/'qualification/origin.py'))['verify_origin']()
    slot = OLD_RUN/'slots/QA'
    result_path = slot/'SLOT_RESULT.json'
    publication_path = slot/'SLOT_PUBLICATION.json'
    publication, raw = read(publication_path), read(result_path)
    require(sha(OLD/'FROZEN.json') == OLD_FREEZE and sha(OLD/'ORIGINAL_RUNTIME.zip') == OLD_ARCHIVE
            and sha(result_path) == publication['result_sha256'] == OLD_RESULT
            and origin['validated_members'] == 1000 and publication['published_ns'] < raw['owned_deadline_ns'],
            'original_frozen_QA_identity_or_window_changed')
    proof = load_checks(CONTROL)['replay'](slot)
    require(proof['passed'] is True,'corrected_original_QA_replay_failed')
    proof_path = NS/'qualification/QA_ORIGINAL_REPLAY.json'
    save(proof_path,proof)
    scope = NS/'checks/evidence.py'
    closed = time.perf_counter_ns()
    save(DERIVED,{'passed':True,'scope':'derived_closed_QA_only','old_gate_passed':False,
                  'old_gate_path':str(OLD_RUN/'preflight/QA_CLOSED_GATE.json'),
                  'old_freeze_path':str(OLD/'FROZEN.json'),'old_freeze_sha256':OLD_FREEZE,
                  'old_archive_path':str(OLD/'ORIGINAL_RUNTIME.zip'),'old_archive_sha256':OLD_ARCHIVE,
                  'old_result_path':str(result_path),'old_result_sha256':OLD_RESULT,
                  'old_publication_sha256':sha(publication_path),'original_published_ns':publication['published_ns'],
                  'original_owned_deadline_ns':raw['owned_deadline_ns'],'review_started_ns':started,
                  'review_closed_ns':closed,'review_duration_ns':closed-started,'review_live_slots':0,
                  'corrected_verifier_path':str(scope),'corrected_verifier_sha256':sha(scope),
                  'qualification_proof_path':str(proof_path),'qualification_proof_sha256':sha(proof_path),
                  'original_evidence':origin})
    admission.derived_qa()
    print('Derived QA',sha(DERIVED),'from',OLD_RESULT,flush=True)
    return 0


def gate_preflight():
    """Exercise the actual order/admission predicates with archived closure evidence."""
    root = EXTERNAL/'gate_preflight'
    root.mkdir(parents=True,exist_ok=False)
    slots = root/'slots'
    slots.mkdir()
    raw = read(OLD_RUN/'slots/QA/SLOT_RESULT.json')
    closure = read(OLD_RUN/'slots/QA/SLOT_PUBLICATION.json')
    gate = admission.derived_qa()
    bad = root/'bad_QA_DERIVED.json'
    save(bad,{**gate,'old_result_sha256':'0'*64})
    outcomes = {}

    def denied(label, call, expected):
        try:
            call()
        except (ValueError,FileNotFoundError) as error:
            require(expected in str(error),'incorrect_preflight_rejection/' + label + '/' + str(error))
            outcomes[label] = str(error)
        else:
            raise ValueError('preflight_admitted_invalid_predecessor/' + label)

    denied('broken_original_QA_binding',lambda:admission.derived_qa(bad),'historical_QA_derived')
    good = {'QB':({**raw,'label':'QB'},closure),'A1':({**raw,'label':'A1'},closure)}
    token = 'offline-preflight'
    with (patch.object(admission,'EXTERNAL',root), patch.object(admission,'verify_freeze',return_value=token),
          patch.object(admission,'publication',side_effect=lambda label,freeze:good[label])):
        admit = lambda label: admission.validate_admission(label,NS/'FROZEN.json')
        denied('old_QA_label',lambda:admit('QA'),'registered_slot_required')
        denied('formal_before_QB_exists',lambda:admit('A1'),'unexpected_slot_order')
        require(admit('QB') == {'freeze_sha256':token},'actual_QB_admission_not_reachable')
        outcomes['QB_after_historical_QA'] = 'allowed'
        (slots/'QB').mkdir()
        denied('formal_without_QB_closed_gate',lambda:admit('A1'),'QB_CLOSED_GATE.json')
        good['QB'] = ({**raw,'label':'QB','closure_verification':None},closure)
        denied('formal_after_QB_early_failure',lambda:admit('A1'),'unexpected_slot_order')
        good['QB'] = ({**raw,'label':'QB'},closure)
        with patch.object(admission,'qualified',return_value={'passed':True}) as qualified:
            require(admit('A1') == {'freeze_sha256':token},'actual_A1_admission_not_reachable')
            outcomes['A1_after_qualified_QB'] = 'allowed'
            denied('B1_before_A1',lambda:admit('B1'),'unexpected_slot_order')
            (slots/'A1').mkdir()
            good['A1'] = ({**raw,'label':'A1','owner_close':{'confirmed':False}},closure)
            denied('B1_after_unconfirmed_A1',lambda:admit('B1'),'unexpected_slot_order')
            good['A1'] = ({**raw,'label':'A1'},closure)
            require(admit('B1') == {'freeze_sha256':token} and qualified.call_count == 2,
                    'actual_B1_admission_or_required_QB_binding_not_reachable')
            outcomes['B1_after_confirmed_A1_and_QB'] = 'allowed'
    save(NS/'qualification/GATE_PREFLIGHT.json',{'passed':True,'outcomes':outcomes,'business_or_model_starts':0,
                   'current_admission_sha256':sha(NS/'harness/admission.py'),'derived_qa_sha256':sha(DERIVED)})
    return 0


def freeze():
    dest = NS/'FROZEN.json'
    require(not dest.exists() and not (EXTERNAL/'slots').exists(),'one_fresh_recovery_freeze_required')
    prefix = NS.relative_to(ROOT).as_posix() + '/'
    require(git('merge-base',OLD_COMMIT,'HEAD').decode().strip()==OLD_COMMIT
            and all(path.startswith(prefix) for path in git('diff','--name-only',OLD_COMMIT).decode().splitlines()),
            'recovery_must_have_zero_product_delta')
    require((NS/'PLAN.md').read_bytes() == git('show',PLAN),'fixed_recovery_plan_changed')
    require((NS/'inputs/PROMPT.txt').read_bytes() == (OLD/'inputs/PROMPT.txt').read_bytes()
            and sha(ASSET) == read(OLD/'FROZEN.json')['asset_sha256'],'original_holdout_asset_or_prompt_changed')
    require(tuple(ORDER) == ('QB','A1','B1'),'recovery_live_slots_changed')
    derived = admission.derived_qa()
    preflight = read(NS/'qualification/PREFLIGHT.json')
    gate = read(NS/'qualification/GATE_PREFLIGHT.json')
    require(preflight['passed'] is True and read(NS/'harness/HOST_PREFLIGHT.json')['passed'] is True
            and gate['passed'] is True and gate['derived_qa_sha256'] == sha(DERIVED)
            and gate['current_admission_sha256'] == sha(NS/'harness/admission.py'),
            'actual_recovery_entry_or_derived_gate_preflight_absent')
    ports = {}
    for label in ORDER:
        row = json.loads(subprocess.check_output(argv('harness/run_slot.py',label,'--dispatch-smoke'),cwd=ROOT,timeout=30))
        require(row['slot']==label and row['schema']==admission.SCHEMA and row['product']==admission.registered_product()
                and Path(row['asset'])==ASSET.resolve() and Path(row['run_root'])==EXTERNAL.resolve()
                and Path(row['actual_product_schema'])==PRODUCT_SCHEMA.resolve()
                and Path(row['actual_catalogue_path'])==catalogue_for(label).resolve()
                and row['endpoint_flag']==('--region-task-evidence' if label != 'A1' else None),
                'actual_registered_recovery_entry_wrong/' + label)
        ports[label] = row
    require(all(row['tools']==ports['QB']['tools'] and len(row['tools'])==6 for row in ports.values()),
            'recovery_model_tool_directory_roster_changed')
    disabled = subprocess.run(argv('harness/run_slot.py','QA','--dispatch-smoke'),cwd=ROOT,capture_output=True,timeout=30)
    require(disabled.returncode!=0 and b'invalid choice' in disabled.stderr and not (EXTERNAL/'slots').exists(),
            'historical_QA_live_launch_not_disabled')
    pins = {}

    def pin(path,expected=None):
        source = Path(path).resolve(strict=True)
        row = {'path':str(source),'bytes':source.stat().st_size,'sha256':sha(source)}
        require(expected is None or all(row[k]==expected[k] for k in ('bytes','sha256')),
                'fixed_recovery_input_changed/' + str(source))
        pins[source] = row

    original = read(OLD/'FROZEN.json')
    for row in original['direct_inputs']:
        pin(row['path'],row)
    for path in (OLD/'FROZEN.json',OLD/'RAW_INDEX.json',OLD/'ORIGINAL_RUNTIME.zip',OLD/'checks/evidence.py',
                 OLD/'qualification/closed.py',derived['old_result_path'],OLD_RUN/'slots/QA/SLOT_PUBLICATION.json',
                 OLD_RUN/'preflight/SEQUENCE.jsonl',PRODUCT_BINDING,ASSET):
        pin(path)
    for row in preflight.get('source_pins',[]):
        pin(row['path'],row)
    for cell in ports.values():
        for path in cell['workspace_sources']:
            pin(path)
    for path in EXTERNAL.rglob('*'):
        if path.is_file():
            pin(path)
    for path in NS.rglob('*'):
        if path.is_file():
            require(path.suffix!='.pyc','bytecode_cache_must_not_enter_freeze')
            if path.suffix=='.py':
                ast.parse(path.read_bytes(),filename=str(path))
            pin(path)
    save(dest,{'schema':admission.SCHEMA,'plan':PLAN,'slots':list(ORDER),'registered_dispatch':ports,
               'formal_slots':list(FORMAL_LABELS),'qualification_slots':['QB'],'passed_offline_preflight':True,
               'product':admission.registered_product(),'asset_path':str(ASSET),'asset_sha256':original['asset_sha256'],
               'prompt_sha256':sha(NS/'inputs/PROMPT.txt'),'derived_qa_sha256':sha(DERIVED),'old_freeze_sha256':OLD_FREEZE,
               'old_QA_disabled':True,'task_s':450,'owned_s':600,'max_rasters_per_slot':12,'max_business_per_slot':12,
               'asset_builds':0,'product_builds':0,'product_installs':0,'max_qualification_starts':1,
               'max_formal_starts':2,'max_model_starts':2,'replacements':0,'argument_rewrites':0,
               'direct_inputs':[pins[path] for path in sorted(pins)]})
    print('Frozen',admission.verify_freeze(),len(pins),'pins',flush=True)
    return 0


def qualify(token,result,receipt,checks):
    require(admission.can_continue(result,receipt) and result['status']=='completed'
            and result['model_consumers']==0,'actual_owned_QB_incomplete')
    proof = checks['verify_qualification'](EXTERNAL/'slots/QB',result)
    now = time.perf_counter_ns()
    require(proof['passed'] is True and now < result['owned_deadline_ns'],'closed_QB_evidence_or_owned_deadline_failed')
    folder = EXTERNAL/'preflight'
    path = folder/'QB_CLOSED_PROOF.json'
    save(path,proof)
    originals = [{'ref':key,**row['PNG']} for key,row in proof['readback'].items()]
    save(folder/'QB_CLOSED_GATE.json',{'passed':True,'freeze_sha256':token,'result_sha256':receipt['result_sha256'],
         'proof_sha256':sha(path),'derived_qa_sha256':sha(DERIVED),'verified_ns':now,'original_images':originals})
    return admission.qualified('QB',token)


def sequence():
    token = admission.verify_freeze()
    require(not (EXTERNAL/'slots').exists(),'one_frozen_recovery_sequence_required')
    checks = load_checks(NS/'checks/evidence.py')
    journal = EXTERNAL/'preflight/SEQUENCE.jsonl'
    journal.parent.mkdir(exist_ok=False)
    journal.touch(exist_ok=False)
    append(journal,{'event':'historical_QA_derived','derived_qa_sha256':sha(DERIVED),'live_starts':0,'old_passed':False})
    for index,label in enumerate(ORDER):
        append(journal,{'event':'start','label':label,'stamp_ns':time.perf_counter_ns(),'freeze_sha256':token})
        process = subprocess.run(argv('harness/run_slot.py',label),cwd=ROOT)
        try:
            result, receipt = admission.publication(label,token)
            safe = admission.can_continue(result,receipt)
            append(journal,{'event':'publication','label':label,'exit_code':process.returncode,'status':receipt['status'],
                            'result_sha256':receipt['result_sha256'],'safe_to_continue':safe,
                            'model_consumers':result['model_consumers']})
            require(safe and process.returncode==0 and receipt['status']=='completed','owned_slot_failed_or_unconfirmed')
            if label=='QB':
                gate = qualify(token,result,receipt,checks)
                append(journal,{'event':'closed_qualification_passed','label':label,'proof_sha256':gate['proof_sha256']})
                print('QB closed qualification passed',flush=True)
        except Exception as error:
            append(journal,{'event':'blocked','label':label,'exit_code':process.returncode,'type':type(error).__name__,
                            'reason':str(error),'remaining':list(ORDER[index+1:])})
            print(label,'blocked',type(error).__name__,str(error),flush=True)
            return 1
    return 0


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'pinned_interpreter_I_B_required')
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('stage',choices=('derive','gate_preflight','freeze','sequence'))
    raise SystemExit(globals()[cli.parse_args().stage]())
