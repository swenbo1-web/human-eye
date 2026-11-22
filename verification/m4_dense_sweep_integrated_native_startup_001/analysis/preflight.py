"""Recheck the original scoring contract and the separately retained startup failure."""

from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
from subprocess import check_output
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
V = HERE.parents[1]
ROOT = V.parent
PILOT = V/'m4_dense_sweep_integrated_native_pilot_001'
RECOVERY = V/'m4_dense_sweep_integrated_native_pilot_recovery_001'
RECOVERY_RUNTIME = Path('D:/he_m4_dense_sweep_integrated_native_pilot_recovery_001')
COMMIT = '62a631344922ddcea57d78b051a37d33629ad3a2'
ARCHIVE_SHA = 'aef290d67a13869ffb643298d10592adb7c48611e22ec19ebc969561741f78c2'
FREEZE_SHA = 'ea4c90e1567ac61d823f97a6d58244ce73e7e85d862a376041730e52f61b4bca'
DERIVED_SHA = '7d37be07327a090741b4ba6bfbfa5229007d8404a14e90938966e8906dd93a56'
FAILED_SHA = '0f09e4e6d1c538877e7b9d713c96b2a7e674f10e24972cb0c2bc458daf48e963'
OLD_TOTAL = {'blender':2,'rasters':5,'business':10,'models':0}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def read(path):
    return json.loads(path.read_bytes())


def digest(data):
    return {'sha256':sha256(data).hexdigest(),'bytes':len(data)}


def pin(path):
    path = path.resolve(strict=True)
    return {'path':str(path),**digest(path.read_bytes())}


def committed(path):
    name = path.relative_to(ROOT).as_posix()
    require(path.read_bytes() == check_output(['git','show',f'{COMMIT}:{name}'],cwd=ROOT),
            'prior_published_Git_member_changed/'+name)
    return pin(path)


def prior_failure():
    index_path = RECOVERY/'RAW_INDEX.json'
    index = read(index_path)
    archive = RECOVERY/'ORIGINAL_RUNTIME.zip'
    freeze = RECOVERY/'FROZEN.json'
    protected = [index_path, archive, freeze,
                 *(RECOVERY/'evidence'/name for name in ('DERIVED_ADMISSION.json','N1_SLOT_RESULT.json',
                   'N1_SLOT_PUBLICATION.json','ACTUAL_DENOMINATOR.json','RUNTIME_IMPORT_ISOLATION.json'))]
    pins = [committed(path) for path in protected]
    require(digest(archive.read_bytes()) == {'sha256':ARCHIVE_SHA,'bytes':28580}
            and digest(freeze.read_bytes())['sha256'] == index['freeze_sha256'] == FREEZE_SHA
            and index['derived_admission_sha256'] == DERIVED_SHA
            and index['original_qualification_totals'] == index['combined_totals'] == OLD_TOTAL
            and index['new_formal_totals'] == dict.fromkeys(OLD_TOTAL,0),
            'prior_published_archive_freeze_or_budgets_changed')
    paths = {'runtime/'+path.relative_to(RECOVERY_RUNTIME).as_posix():path
             for path in RECOVERY_RUNTIME.rglob('*') if path.is_file()}
    with ZipFile(archive) as bundle:
        require(len(bundle.namelist()) == index['member_count'] == 9
                and set(bundle.namelist()) == paths.keys() == index['members'].keys(),
                'prior_failed_recovery_archive_roster_changed')
        for name,path in sorted(paths.items()):
            data = bundle.read(name)
            require(digest(data) == index['members'][name] and path.read_bytes() == data,
                    'prior_failed_recovery_member_changed/'+name)
            pins.append(pin(path))

    folder = RECOVERY_RUNTIME/'slots'
    n1 = folder/'N1'
    require({path.name for path in folder.iterdir()} == {'N1'}
            and {path.name for path in n1.iterdir()} ==
                {'SLOT_STARTED.json','SLOT_RESULT.json','SLOT_PUBLICATION.json'}
            and not (RECOVERY_RUNTIME/'budget').exists(),
            'old_failure_started_resources_or_unspent_P1')
    result_path, pub_path = (n1/name for name in ('SLOT_RESULT.json','SLOT_PUBLICATION.json'))
    result, pub = read(result_path), read(pub_path)
    error, = result['errors']
    require(result['label'] == pub['label'] == 'N1' and result['status'] == pub['status'] == 'failed'
            and result['freeze_sha256'] == FREEZE_SHA
            and digest(result_path.read_bytes())['sha256'] == pub['result_sha256'] == FAILED_SHA
            and result['model_consumers'] == result['paid_API_calls'] == 0
            and result['actual_model_admitted'] is False and result['diagnostic_calls'] == []
            and not any(key in result for key in ('budget','ready_ns','initial_source','consumer'))
            and error['stage'] == 'runtime_start' and error['type'] == 'ImportError'
            and "cannot import name 'Budget'" in error['message']
            and str(RECOVERY/'qualification/budget.py') in error['message']
            and result['started_ns'] <= result['cleanup_started_ns'] <= result['closed_ns']
                <= pub['published_ns'] < result['owned_deadline_ns'],
            'old_N1_original_early_failure_changed')
    journal = [json.loads(row) for row in (RECOVERY_RUNTIME/'preflight/SEQUENCE.jsonl').read_bytes().splitlines()]
    require([(row['event'],row['label']) for row in journal] ==
                [('start','N1'),('publication','N1'),('blocked','N1')]
            and journal[1]['result_sha256']==FAILED_SHA and journal[2]['remaining']==['P1'],
            'original_failed_attempt_or_P1_unrun_changed')
    evidence = read(RECOVERY/'evidence/ACTUAL_DENOMINATOR.json')
    recovered = read(RECOVERY/'evidence/DERIVED_ADMISSION.json')['evidence']
    require(evidence['passed'] and evidence['formal']['N1_start_to_publication_ns']==pub['complete_slot_ns']
            and recovered['raster_settlement']['historical_total']==OLD_TOTAL,
            'prior_failure_denominator_detached_from_closed_sources')
    return {'published_commit':COMMIT,'archive':digest(archive.read_bytes()),'archive_members':len(paths),
            'old_qualification_counted_once':OLD_TOTAL,'old_formal_slots':{'N1':'failed','P1':'unrun'},
            'old_formal_actual_resources':dict.fromkeys(OLD_TOTAL,0),'N1_result_sha256':FAILED_SHA,
            'N1_whole_window_ns':pub['complete_slot_ns'],'old_N1_error':error['message']}, pins


def verify():
    previous = run_path(str(RECOVERY/'analysis/preflight.py'))['verify']()
    current, pins = prior_failure()
    ledger = run_path(str(PILOT/'analysis/ledger.py'))
    truth = ledger['F']['ORIGINAL']/'fixture/TRUTH.json'
    outcome = ledger['analyze'](RECOVERY_RUNTIME,RECOVERY/'FROZEN.json',truth,ledger['F']['BINDING'],{}, {})
    require(outcome['denominator'] == {'planned':2,'actual_created':1,'completed':0,
                                        'unrun':1,'actual_model_launches':0}
            and outcome['slots']['N1']['status']=='failed'
            and outcome['slots']['N1']['cost_evidence_verified'] is True
            and outcome['slots']['N1']['answer_file'] is None
            and outcome['slots']['N1']['raw_CLI_usage'] == []
            and outcome['slots']['P1']['status']=='unrun',
            'original_ledger_did_not_preserve_pre_runtime_failure_denominator')
    required = [Path(__file__), RECOVERY/'analysis/preflight.py', RECOVERY/'analysis/ANALYSIS_PREFLIGHT.json',
                truth, ledger['F']['BINDING'],
                *(PILOT/'analysis'/f'{stem}.py' for stem in ('formal','score','ledger'))]
    previous['source_pins'] = list({Path(item['path']).resolve():item for item in
                                   (*previous['source_pins'],*pins,*(pin(path) for path in required))}.values())
    previous['prior_startup_failure'] = current
    previous['actual_prior_ledger_denominator'] = outcome['denominator']
    return previous


if __name__ == '__main__':
    result = verify()
    with (HERE/'ANALYSIS_PREFLIGHT.json').open('x',encoding='utf8',newline='\n') as stream:
        stream.write(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'passed':result['passed'],'source_pins':len(result['source_pins']),
                      'old_failure':result['actual_prior_ledger_denominator']}))
