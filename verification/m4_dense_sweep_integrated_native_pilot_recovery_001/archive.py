"""Seal the new formal records with links to the original qualification archive."""

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
    token = admission.verify_freeze()
    derived = read(admission.DERIVED)
    evidence = NS/'evidence'
    evidence.mkdir(exist_ok=True)
    journal = EXTERNAL/'preflight/SEQUENCE.jsonl'
    copy(admission.DERIVED,evidence/'DERIVED_ADMISSION.json')
    copy(journal,evidence/'SEQUENCE.jsonl')
    rows = [json.loads(line) for line in journal.read_bytes().splitlines()]
    attempts = [row['label'] for row in rows if row['event']=='start']
    require(attempts and attempts==list(ORDER[:len(attempts)]),'one_new_formal_sequence_required')
    slots, latest, models = {}, None, 0
    incomplete = False
    for label in ORDER:
        slot = EXTERNAL/'slots'/label
        if label not in attempts:
            require(not slot.exists(),'unregistered_actual_formal_slot/'+label)
            slots[label] = {'owned':'unrun','models':0}
            continue
        if not all((slot/name).is_file() for name in ('SLOT_RESULT.json','SLOT_PUBLICATION.json')):
            incomplete = True
            slots[label] = {'owned':'unconfirmed','models':None}
            continue
        raw, publication = admission.publication(label,token)
        for name in ('SLOT_RESULT.json','SLOT_PUBLICATION.json'):
            copy(slot/name,evidence/f'{label}_{name}')
        latest = raw['budget']['counts']
        models += raw['model_consumers']
        slots[label] = {'owned':publication['status'],'closed':admission.safe_to_continue(raw,publication),
                        'models':raw['model_consumers'],'complete_slot_ns':publication['complete_slot_ns'],
                        'result_sha256':publication['result_sha256'],'budget_slot':raw['budget']['slots'][label]}
        answer = slot/'consumer/PUBLIC_FINAL.txt'
        if answer.is_file():
            require(raw['answer']['sha256']==sha(answer),'raw_answer_changed/'+label)
            copy(answer,evidence/f'{label}_PUBLIC_FINAL.txt')
    old = derived['evidence']['raster_settlement']['historical_total']
    new = (None if incomplete or latest is None else
           {'blender':latest['Blender_spawned_confirmed'], 'rasters':latest['formal_raster_actual'],
            'business':latest['business_admissions'],'models':models})
    if new is not None:
        require(latest['qualification_raster_actual']==0 and latest['Blender_spawned_unknown']==0
                and latest['pending_raster_reservations']==0
                and new['business']==sum(row.get('budget_slot',{}).get('business_admissions',0) for row in slots.values())
                and new['rasters']==sum(row.get('budget_slot',{}).get('raster_actual',0) for row in slots.values()),
                'actual_split_budget_and_per_slot_total_changed')
    checker = run_path(str(NS.parent/'perf050_dense_micro_surface_holdout_recovery_001/archive_evidence.py'))
    inspect,digest = checker['check_named_bytes'],checker['digest']
    index = {}
    target = NS/'ORIGINAL_RUNTIME.zip'
    with ZipFile(target,'x',compression=ZIP_DEFLATED,compresslevel=6) as bundle:
        for path in sorted(EXTERNAL.rglob('*')):
            if path.is_file():
                name = 'runtime/'+path.relative_to(EXTERNAL).as_posix()
                data = path.read_bytes()
                inspect(name,data)
                index[name] = digest(data)
                bundle.writestr(name,data)
    with ZipFile(target) as bundle:
        require(len(bundle.namelist())==len(index) and set(bundle.namelist())==index.keys()
                and all(digest(bundle.read(name))==row for name,row in index.items()),'serialized_archive_changed')
    save(NS/'RAW_INDEX.json',{
        'freeze_sha256':token,'archive':{'name':target.name,'bytes':target.stat().st_size,'sha256':sha(target)},
        'original_qualification_archive':derived['evidence']['original']['archive'],
        'original_qualification_status':{'frozen_passed':1,'frozen_rejected':1,'formal_unrun':2},
        'current_new_qualifications':0,'derived_admission_sha256':sha(admission.DERIVED),
        'slots':slots,'original_qualification_totals':old,'new_formal_totals':new,
        'combined_totals':{key:old[key]+new[key] for key in old} if new is not None else None,
        'member_count':len(index),'members':index,
    })
    print('Sealed',len(index),'members',target.stat().st_size,'bytes',sha(target),flush=True)


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'pinned_interpreter_I_B_required')
    archive()
