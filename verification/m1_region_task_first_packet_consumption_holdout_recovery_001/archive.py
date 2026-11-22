"""Seal the recovery runtime and the unchanged historical admission anchors."""

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
    with target.open('xb') as output:
        output.write(source.read_bytes())


def archive():
    token = admission.verify_freeze()
    derived = admission.derived_qa()
    journal = EXTERNAL/'preflight/SEQUENCE.jsonl'
    events = [json.loads(line) for line in journal.read_bytes().splitlines()]
    launched = [row['label'] for row in events if row['event']=='start']
    require(events[0]['event']=='historical_QA_derived' and events[0]['old_passed'] is False
            and launched == list(ORDER[:len(launched)]) and len(launched)>0
            and not (EXTERNAL/'slots/QA').exists() and not Path(derived['old_gate_path']).exists(),
            'recovery_launch_denominators_changed')
    evidence = NS/'evidence'
    evidence.mkdir(exist_ok=True)
    copy(journal,evidence/'SEQUENCE.jsonl')
    slot_index = {}
    for label in ORDER:
        folder = EXTERNAL/'slots'/label
        if label not in launched:
            require(not folder.exists(),'unregistered_runtime_slot/' + label)
            slot_index[label] = {'owned':'unrun','model_consumers':0,'rasters':0}
            continue
        if not all((folder/key).is_file() for key in ('SLOT_RESULT.json','SLOT_PUBLICATION.json')):
            slot_index[label] = {'owned':'unconfirmed','model_consumers':None,'rasters':None}
            continue
        result, publication = admission.publication(label,token)
        counts = (result.get('budget') or {}).get('counts',{})
        for key in ('SLOT_RESULT.json','SLOT_PUBLICATION.json'):
            copy(folder/key,evidence/f'{label}_{key}')
        slot_index[label] = {'owned':publication['status'],'same_slot_safely_closed':admission.can_continue(result,publication),
                             'model_consumers':result['model_consumers'],'rasters':counts.get('all_raster_actual'),
                             'complete_slot_ns':publication['complete_slot_ns'],'result_sha256':publication['result_sha256'],
                             'qualification_gate':(EXTERNAL/'preflight/QB_CLOSED_GATE.json').is_file() if label=='QB' else None}
    policy = run_path(str(NS.parent/'perf050_dense_micro_surface_holdout_recovery_001/archive_evidence.py'))
    check,digest = policy['check_named_bytes'],policy['digest']
    members = {}
    target = NS/'ORIGINAL_RUNTIME.zip'
    with ZipFile(target,'x',compression=ZIP_DEFLATED,compresslevel=6) as bundle:
        for path in sorted(EXTERNAL.rglob('*')):
            if path.is_file():
                name = 'runtime/' + path.relative_to(EXTERNAL).as_posix()
                data = path.read_bytes()
                check(name,data)
                members[name] = digest(data)
                bundle.writestr(name,data)
    with ZipFile(target) as bundle:
        require(len(bundle.namelist())==len(members) and set(bundle.namelist())==members.keys()
                and all(digest(bundle.read(name))==expected for name,expected in members.items()),
                'sealed_archive_member_or_digest_changed')
    save(NS/'RAW_INDEX.json',{'freeze_sha256':token,'archive':{'name':target.name,'bytes':target.stat().st_size,
         'sha256':sha(target)},'member_count':len(members),'slots':slot_index,'members':members,
         'original_freeze_sha256':derived['old_freeze_sha256'],'original_archive_sha256':derived['old_archive_sha256'],
         'original_QA_derived':True,'original_QA_reopened':False,'original_gate_passed':False})
    print('Sealed',len(members),'members',target.stat().st_size,'bytes',sha(target))


if __name__=='__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'pinned_interpreter_I_B_required')
    archive()
