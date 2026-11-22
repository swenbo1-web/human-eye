"""Seal original production, consumer and qualification evidence from the one pair."""

import json
from pathlib import Path
from runpy import run_path
import sys
from zipfile import ZIP_DEFLATED, ZipFile


NS=Path(__file__).resolve().parent
sys.path.insert(0,str(NS/'harness'))
import admission
from admission import require
from common import EXTERNAL, FORMAL_LABELS, ORDER, read, save, sha

QUALIFICATION = ('QN', 'QP')


def copy(source,target):
    with target.open('xb') as out:
        out.write(source.read_bytes())


def archive():
    token=admission.verify_freeze()
    evidence=NS/'evidence'
    evidence.mkdir(exist_ok=True)
    journal=EXTERNAL/'preflight/SEQUENCE.jsonl'
    copy(journal,evidence/'SEQUENCE.jsonl')
    events=[json.loads(line) for line in journal.read_bytes().splitlines()]
    attempts=[row['label'] for row in events if row['event']=='start']
    require(attempts and attempts==list(ORDER[:len(attempts)]),'one_frozen_dense_sweep_sequence_required')
    slots={}
    for label in ORDER:
        slot=EXTERNAL/'slots'/label
        if label not in attempts:
            require(not slot.exists(),'unregistered_actual_slot/'+label)
            slots[label]={'owned':'unrun','models':0}
            continue
        if not all((slot/name).is_file() for name in ('SLOT_RESULT.json','SLOT_PUBLICATION.json')):
            slots[label]={'owned':'unconfirmed','models':None}
            continue
        raw,publication=admission.publication(label,token)
        for name in ('SLOT_RESULT.json','SLOT_PUBLICATION.json'):
            copy(slot/name,evidence/f'{label}_{name}')
        gate=EXTERNAL/'preflight'/f'{label}_CLOSED_GATE.json'
        slots[label]={'owned':publication['status'],'closed':admission.safe_to_continue(raw,publication),
                      'models':raw['model_consumers'],'complete_slot_ns':publication['complete_slot_ns'],
                      'result_sha256':publication['result_sha256'],'qualified':gate.is_file() if label in QUALIFICATION else None}
        if label in FORMAL_LABELS:
            answer=slot/'consumer/PUBLIC_FINAL.txt'
            if answer.is_file():
                require(raw['answer']['sha256']==sha(answer),'public_answer_differs_from_original_slot')
                copy(answer,evidence/f'{label}_PUBLIC_FINAL.txt')
    old=run_path(str(NS.parent/'perf050_dense_micro_surface_holdout_recovery_001/archive_evidence.py'))
    inspect,pin=old['check_named_bytes'],old['digest']
    index={}
    target=NS/'ORIGINAL_RUNTIME.zip'
    with ZipFile(target,'x',compression=ZIP_DEFLATED,compresslevel=6) as bundle:
        for path in sorted(EXTERNAL.rglob('*')):
            if path.is_file():
                name='runtime/'+path.relative_to(EXTERNAL).as_posix()
                raw=path.read_bytes()
                inspect(name,raw)
                index[name]=pin(raw)
                bundle.writestr(name,raw)
    with ZipFile(target) as bundle:
        require(len(bundle.namelist())==len(index) and set(bundle.namelist())==index.keys()
                and all(pin(bundle.read(name))==row for name,row in index.items()),'original_evidence_archive_not_exact')
    save(NS/'RAW_INDEX.json',{'freeze_sha256':token,'archive':{'name':target.name,'bytes':target.stat().st_size,
                             'sha256':sha(target)},'slots':slots,'member_count':len(index),'members':index})
    print('Sealed',len(index),'members',target.stat().st_size,'bytes',sha(target),flush=True)


if __name__=='__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'pinned_interpreter_I_B_required')
    archive()
