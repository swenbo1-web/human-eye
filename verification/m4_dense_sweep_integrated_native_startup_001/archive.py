"""Seal startup controls and the actual formal denominator."""

import json
from pathlib import Path
from runpy import run_path
import sys
from zipfile import ZIP_DEFLATED, ZipFile


NS = Path(__file__).resolve().parent
sys.path.insert(0,str(NS/'harness'))
import admission
from admission import require
from common import EXTERNAL, ORDER, read, save, sha


def copy(source,target):
    with target.open('xb') as out:
        out.write(source.read_bytes())


def archive():
    freeze = admission.verify_freeze()
    checked = run_path(str(NS/'experiment.py'))
    checked['checked_prior']()
    cold = EXTERNAL/'preflight/COLD_ENTRY.json'
    journal = EXTERNAL/'preflight/SEQUENCE.jsonl'
    evidence = NS/'evidence'
    evidence.mkdir(exist_ok=True)
    rows = [json.loads(line) for line in journal.read_bytes().splitlines()] if journal.exists() else []
    attempts = [row['label'] for row in rows if row['event']=='start']
    require(attempts==list(ORDER[:len(attempts)]),'one_verified_formal_sequence_required')
    if journal.exists():
        require(all(row['cold_entry_sha256']==checked['verify_cold_entry'](freeze)
                    for row in rows if row['event']=='start'),'formal_entry_detached_from_cold_gate')
        copy(journal,evidence/journal.name)
    if cold.exists():
        copy(cold,evidence/cold.name)
    slots, latest, models = {}, None, 0
    missing = False
    for label in ORDER:
        slot = EXTERNAL/'slots'/label
        if label not in attempts:
            require(not slot.exists(),'unregistered_formal_slot/'+label)
            slots[label] = {'owned':'unrun','models':0}
            continue
        started, result, publication = (slot/name for name in
                                       ('SLOT_STARTED.json','SLOT_RESULT.json','SLOT_PUBLICATION.json'))
        if not all(path.is_file() for path in (started,result,publication)):
            missing = True
            slots[label] = {'owned':'unconfirmed','models':None}
            continue
        raw, receipt = admission.publication(label,freeze)
        for path in (started,result,publication):
            copy(path,evidence/f'{label}_{path.name}')
        models += raw['model_consumers']
        row = {'owned':receipt['status'],'closed':admission.safe_to_continue(raw,receipt),
               'models':raw['model_consumers'],'complete_slot_ns':receipt['complete_slot_ns'],
               'result_sha256':receipt['result_sha256']}
        if raw.get('budget') is not None:
            latest = raw['budget']['counts']
            row['budget_slot'] = raw['budget']['slots'][label]
        elif ({path.name for path in slot.iterdir()}=={p.name for p in (started,result,publication)}
              and raw['status']=='failed' and raw['model_consumers']==0 and raw['actual_model_admitted'] is False
              and all(error.get('stage')=='runtime_start' for error in raw['errors'])):
            row['early_runtime_failure_no_resource'] = True
        else:
            missing = True
        answer = slot/'consumer/PUBLIC_FINAL.txt'
        if answer.is_file():
            require(raw['answer']['sha256']==sha(answer),'raw_consumer_answer_changed/'+label)
            copy(answer,evidence/f'{label}_PUBLIC_FINAL.txt')
        slots[label] = row
    if latest is not None:
        require(latest['qualification_raster_actual']==0
                and latest['business_admissions']==sum(row.get('budget_slot',{}).get('business_admissions',0)
                                                       for row in slots.values())
                and latest['formal_raster_actual']==sum(row.get('budget_slot',{}).get('raster_actual',0)
                                                         for row in slots.values()),
                'actual_split_formal_budget_totals_changed')
        missing |= latest['Blender_spawned_unknown']!=0 or latest['pending_raster_reservations']!=0
    old = read(admission.DERIVED)['evidence']['raster_settlement']['historical_total']
    new = None if missing else {'blender':latest['Blender_spawned_confirmed'] if latest else 0,
                                'rasters':latest['formal_raster_actual'] if latest else 0,
                                'business':latest['business_admissions'] if latest else 0,'models':models}
    checker = run_path(str(NS.parent/'perf050_dense_micro_surface_holdout_recovery_001/archive_evidence.py'))
    inspect,digest = checker['check_named_bytes'],checker['digest']
    index = {}
    target = NS/'ORIGINAL_RUNTIME.zip'
    with ZipFile(target,'x',compression=ZIP_DEFLATED,compresslevel=6) as bundle:
        for path in sorted(p for p in EXTERNAL.rglob('*') if p.is_file()):
            name = 'runtime/'+path.relative_to(EXTERNAL).as_posix()
            data = path.read_bytes()
            inspect(name,data)
            bundle.writestr(name,data)
            index[name] = digest(data)
    with ZipFile(target) as bundle:
        require(len(bundle.namelist())==len(index) and set(bundle.namelist())==index.keys()
                and all(digest(bundle.read(name))==row for name,row in index.items()),'packed_actual_original_mismatch')
    save(NS/'RAW_INDEX.json',{
        'freeze_sha256':freeze,'derived_admission_sha256':sha(admission.DERIVED),
        'archive':{'name':target.name,'bytes':target.stat().st_size,'sha256':sha(target)},
        'cold_entry_sha256':sha(cold) if cold.is_file() else None,
        'older_qualification':{'frozen_passed':1,'frozen_QP_rejected':1,'original_formal_unrun':2},
        'previous_recovery':{'N1':'failed_before_runtime','P1':'unrun','blender':0,'models':0},
        'new_qualifications':0,'slots':slots,'original_qualification_totals':old,'new_formal_totals':new,
        'combined_totals':{k:old[k]+new[k] for k in old} if new is not None else None,
        'member_count':len(index),'members':index,
    })
    print('Sealed',len(index),'members',target.stat().st_size,'bytes',sha(target),flush=True)


if __name__=='__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'pinned_interpreter_I_B_required')
    archive()
