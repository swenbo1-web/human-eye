"""Archive the actual pre-runtime failure when a formal budget does not exist."""

import json
from pathlib import Path
from runpy import run_path
import sys
from zipfile import ZIP_DEFLATED, ZipFile


NS = Path(__file__).resolve().parent
sys.path.insert(0,str(NS/'harness'))
import admission
from admission import require
from common import EXTERNAL, read, save, sha


def seal():
    freeze = admission.verify_freeze()
    derived = read(admission.DERIVED)
    root = EXTERNAL/'slots'
    slot = root/'N1'
    verify_only = {'SLOT_STARTED.json','SLOT_RESULT.json','SLOT_PUBLICATION.json'}
    require({p.name for p in root.iterdir()} == {'N1'}
            and {p.name for p in slot.iterdir()} == verify_only
            and not (EXTERNAL/'budget').exists(),'unexpected_live_resource_or_extra_slot_for_early_failure')
    raw, receipt = admission.publication('N1',freeze)
    started = read(slot/'SLOT_STARTED.json')
    error, = raw['errors']
    require(raw['status']==receipt['status']=='failed' and raw['model_consumers']==raw['paid_API_calls']==0
            and raw['actual_model_admitted'] is False and raw['diagnostic_calls']==[]
            and 'budget' not in raw and 'ready_ns' not in raw and 'initial_source' not in raw
            and error['stage']=='runtime_start' and error['type']=='ImportError'
            and "cannot import name 'Budget' from 'budget'" in error['message']
            and str(NS/'qualification/budget.py') in error['message']
            and started['freeze_sha256']==freeze and raw['started_ns']<=raw['cleanup_started_ns']
            <=raw['closed_ns']<=receipt['published_ns']<raw['owned_deadline_ns'],
            'original_early_exit_failure_or_publication_changed')
    journal = EXTERNAL/'preflight/SEQUENCE.jsonl'
    rows = [json.loads(line) for line in journal.read_bytes().splitlines()]
    require([(r['event'],r['label']) for r in rows]==[('start','N1'),('publication','N1'),('blocked','N1')]
            and rows[1]['result_sha256']==receipt['result_sha256'] and rows[2]['remaining']==['P1'],
            'original_single_failed_launch_roster_changed')
    evidence = NS/'evidence'
    evidence.mkdir(exist_ok=True)
    paths = {
        'DERIVED_ADMISSION.json':admission.DERIVED,
        'SEQUENCE.jsonl':journal,
        'N1_SLOT_STARTED.json':slot/'SLOT_STARTED.json',
        'N1_SLOT_RESULT.json':slot/'SLOT_RESULT.json',
        'N1_SLOT_PUBLICATION.json':slot/'SLOT_PUBLICATION.json',
    }
    for name,path in paths.items():
        with (evidence/name).open('xb') as stream:
            stream.write(path.read_bytes())
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
                and all(digest(bundle.read(name))==value for name,value in index.items()),
                'packed_early_failure_original_mismatch')
    old = derived['evidence']['raster_settlement']['historical_total']
    save(NS/'RAW_INDEX.json',{
        'freeze_sha256':freeze,'archive':{'name':target.name,'bytes':target.stat().st_size,'sha256':sha(target)},
        'original_qualification_archive':derived['evidence']['original']['archive'],
        'original_qualification_status':{'frozen_passed':1,'frozen_rejected':1,'formal_unrun':2},
        'derived_admission_sha256':sha(admission.DERIVED),'current_new_qualifications':0,
        'slots':{'N1':{'owned':'failed','failure_before_runtime_construction':True,'models':0,
                       'complete_slot_ns':receipt['complete_slot_ns'],'result_sha256':receipt['result_sha256']},
                 'P1':{'owned':'unrun','models':0}},
        'original_qualification_totals':old,'new_formal_totals':{key:0 for key in old},'combined_totals':old,
        'member_count':len(index),'members':index,
    })
    print('Sealed startup failure',len(index),'members',target.stat().st_size,'bytes',sha(target),flush=True)


if __name__=='__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'pinned_interpreter_I_B_required')
    seal()
