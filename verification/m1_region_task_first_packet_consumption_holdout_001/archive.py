"""Seal original holdout evidence and preserve the actual failed admission."""

import hashlib
import json
from pathlib import Path
from runpy import run_path
import sys
from zipfile import ZIP_DEFLATED, ZipFile


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS/'harness'))
import admission
from admission import require
from common import EXTERNAL, ORDER, read, save, sha


def copy(source, target):
    with target.open('xb') as stream:
        stream.write(source.read_bytes())


def archive():
    token = admission.verify_freeze()
    evidence = NS/'evidence'
    journal = EXTERNAL/'preflight/SEQUENCE.jsonl'
    events = [json.loads(line) for line in journal.read_bytes().splitlines()]
    require([row['label'] for row in events if row['event']=='start'] == ['QA']
            and events[-1]['event'] == 'blocked' and events[-1]['remaining'] == ['QB','A1','B1']
            and {item.name for item in (EXTERNAL/'slots').iterdir()} == {'QA'},
            'original_frozen_order_or_denominators_changed')
    result, publication = admission.publication('QA',token)
    require(admission.can_continue(result,publication) and result['status'] == 'completed'
            and not (EXTERNAL/'preflight/QA_CLOSED_GATE.json').exists()
            and result['model_consumers'] == 0 and result['budget']['counts']['all_raster_actual'] == 3,
            'original_QA_process_or_failed_admission_changed')
    diagnosis = read(evidence/'QA_READONLY_DIAGNOSIS.json')
    require(diagnosis['freeze_sha256'] == token and diagnosis['original_slot_result_sha256'] == publication['result_sha256'],
            'post_close_diagnosis_not_bound_to_original_failure')
    for filename in ('SLOT_RESULT.json','SLOT_PUBLICATION.json'):
        copy(EXTERNAL/'slots/QA'/filename,evidence/f'QA_{filename}')
    copy(journal,evidence/'SEQUENCE.jsonl')
    policy = run_path(str(NS.parent/'perf050_dense_micro_surface_holdout_recovery_001/archive_evidence.py'))
    check, digest = policy['check_named_bytes'], policy['digest']
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
        require(len(bundle.namelist()) == len(members) and set(bundle.namelist()) == members.keys()
                and all(digest(bundle.read(name)) == expected for name,expected in members.items()),
                'sealed_archive_member_or_digest_changed')
    slots = {}
    for label in ORDER:
        slots[label] = ({'owned':'completed','qualification':'failed','model_consumers':0,'rasters':3,
                         'complete_slot_ns':publication['complete_slot_ns'],'result_sha256':publication['result_sha256']}
                        if label == 'QA' else {'owned':'unrun','model_consumers':0,'rasters':0})
    save(NS/'RAW_INDEX.json',{'freeze_sha256':token,'archive':{'name':target.name,'bytes':target.stat().st_size,
                          'sha256':sha(target)},'member_count':len(members),'slots':slots,'members':members})
    print('Sealed',len(members),'members',target.stat().st_size,'bytes',sha(target))


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'pinned_interpreter_I_B_required')
    archive()
