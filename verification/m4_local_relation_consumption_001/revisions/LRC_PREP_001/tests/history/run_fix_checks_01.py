"""Finite pure-QA LRC-PREP-001 checks. Never dispatch a real consumer/backend.

The old 231 assertion functions are compiled from their exact archived source.
Only their output directory and expected packager SHA are runtime overrides.
Raw synthetic controls/PIDs live in a new short, marked QA root; originals are
kept there and copied into an indexed ZIP here. No existing cache is removed.
"""
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import traceback
import types
from unittest.mock import patch
import zipfile

TESTS=Path(__file__).resolve().parent
REV=TESTS.parent
BATCH=REV.parent.parent
BASE=BATCH.parent/'m4_observation_baseline_001'
PACK=BATCH/'quality_handoff/pack_quality.py'
EXPECTED='3b960695d5308ac64c5512191d7c0dc4e854a72b5fa07b97ccb5dfe0c0b3c365'
OLD_HARNESS=REV/'original_169b0be0/synthetic/verify_packager.py'
OLD_HARNESS_SHA='0c10a60acb826699b4a51e2cc31110a214686899aa1af5e372d12169a84dbc29'
CYCLE='M4-LOCAL-RELATION-CONSUMPTION-001'
sha=lambda raw:hashlib.sha256(raw).hexdigest()
enc=lambda value:(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode('utf8')
checks=[];cases=[];external={'subprocess':0,'socket':0}


def put(path,raw):
    assert path.resolve().is_relative_to(WORK.resolve())
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(raw)


def check(name,value):checks.append({'check':name,'passed':bool(value)})
def compile_module(name,path,expected=None):
    raw=path.read_bytes()
    if expected is not None:assert sha(raw)==expected,'QA/source pin changed'
    module=types.ModuleType(name);module.__file__=str(path);sys.modules[name]=module
    exec(compile(raw,str(path),'exec',dont_inherit=True),module.__dict__)
    return module


def legacy_regression(module):
    old=compile_module('lrc_original_assertion_functions',OLD_HARNESS,OLD_HARNESS_SHA)
    old.PACKAGER_SHA=EXPECTED;old.OUT=WORK/'r';old.OUT.mkdir()
    sequence=json.loads((BATCH/'SEQUENCE.json').read_bytes())['sequence']
    old.package_case(module,sequence,'a',9)
    old.package_case(module,sequence,'s',5)
    old.cross_binding(module,sequence)
    report={'synthetic':True,'passed':len(old.checks)==231 and all(row['passed'] for row in old.checks),
      'check_count':len(old.checks),'checks':old.checks,'old_source_sha256':OLD_HARNESS_SHA,
      'effective_wrapper_sha256':sha(Path(__file__).read_bytes()),'new_packager_sha256':EXPECTED,
      'reused_functions':['package_case','verify_answer','fixture','cross_binding','check','put'],
      'runtime_overrides':{'PACKAGER_SHA':EXPECTED,'OUT':str(old.OUT)},
      'execution':'Compiled archived assertion functions; old main/old reports were neither run nor rewritten.',
      'model_consumers':0,'product_calls':0,'Blender_sessions':0}
    put(old.OUT/'RESULTS.json',enc(report))
    check('old_231_assertions_on_new_packager',report['passed'])
    return report


def fixture(variant):
    sequence=json.loads((BATCH/'SEQUENCE.json').read_bytes())['sequence']
    mapping={'synthetic':True,'rows':[dict(slot,anonymous_id='answer_'+sha(('fix-only|'+slot['cell']).encode())[:16]) for slot in sequence]}
    image=(BASE/'input/INITIAL.png').read_bytes();prompt=b'SYNTHETIC failure packaging only; no actual answer or consumer.\n'
    plan={'synthetic':True,'cycle_id':CYCLE,'batch':CYCLE,'sequence':sequence,
      'logical_denominator':9,'per_arm':3,'arms':{'N':'synthetic','P0':'synthetic','P1':'synthetic'},
      'image_count':1,'new_images':0,'private_anonymous_map_sha256':sha(enc(mapping)),
      'tasks':{'T1':{}},'inputs':{'image':'i.png','image_sha256':sha(image),'image_bytes':len(image),
        'prompt':'p.txt','prompt_sha256':sha(prompt)}}
    error={'type':'SyntheticFailure','message':'No real process or network operation was attempted'}
    consumer=None
    if variant!='none':
        consumer={**sequence[0],'group':'N','external_group':'N','synthetic':True,
          'status':'failed','valid_completion':False,'consumer_pid':None,'thread_id':None,'final':None,'errors':[error]}
        if variant=='missing_pid':consumer.pop('consumer_pid')
    row={**sequence[0],'synthetic':True,'consumer':consumer,'finish':None,
      'errors':[error] if consumer is None else [],'cell_started_ns':3,'cell_ended_ns':4,
      'full_cell_wall_ns':1,'within_570s':True}
    run={'synthetic':True,'records':[row],'stop':'synthetic preserved failure reason',
      'started_cells':1,'maximum_consumers':9,'all_planned_dispatched':False,'no_replacements':True,
      'batch_started_ns':1,'batch_ended_ns':5,'batch_wall_ns':4}
    digest=sha(enc(plan))
    controls={'PLAN.json':plan,'FREEZE.json':{'plan_sha256':digest},'private/ANON_MAP.json':mapping,
      'RUN_RESULT.json':run,'GO.json':{'synthetic':True,'task':CYCLE,'authorized':True,'max_consumers':9,'plan_sha256':digest},
      'STARTED.json':{'synthetic':True,'started_ns':2,'max_consumers':9,'plan_sha256':digest}}
    return controls,image,prompt


def invoke(module,label,variant='none',mutation=None,expect=None):
    folder=WORK/'z'/label;folder.mkdir(parents=True,exist_ok=False)
    controls,image,prompt=fixture(variant)
    if mutation is not None:mutation(controls)
    before={name:enc(value) for name,value in controls.items()}
    for name,raw in before.items():put(folder/name,raw)
    # Only accepted branches need image/prompt files; all negative gates must
    # fail for their exact control reason, never an unrelated missing input.
    if expect is None:
        put(folder/'i.png',image);put(folder/'p.txt',prompt)
        consumer=controls['RUN_RESULT.json']['records'][0]['consumer']
        if consumer is not None:put(folder/'cells'/controls['PLAN.json']['sequence'][0]['cell']/'CONSUMER.json',enc(consumer))
    module.EVAL=folder;module.HERE=folder/'q';module.HERE.mkdir()
    stream=io.StringIO();exception=None;old_argv=sys.argv
    try:
        sys.argv=['synthetic-failure-packager','h']
        with contextlib.redirect_stdout(stream):module.main()
    except BaseException as exc:
        exception={'type':type(exc).__name__,'message':str(exc),
          'filename':Path(exc.filename).name if isinstance(exc,FileNotFoundError) and exc.filename else None,
          'traceback':traceback.format_exc()}
    finally:sys.argv=old_argv
    put(folder/'STDOUT.txt',stream.getvalue().encode('utf8'))
    record={'synthetic':True,'label':label,'variant':variant,'expected_rejection':expect,'exception':exception,
      'input_sha256':{name:sha(raw) for name,raw in before.items()},'public_INDEX_created':(folder/'q/h/public/INDEX.json').exists()}
    if expect is not None:
        kind,detail=expect
        matched=bool(exception and exception['type']==kind and
          (exception['filename']==detail if kind=='FileNotFoundError' else exception['message']==detail))
        check(label+':exact_rejection',matched)
        check(label+':no_public_success',not record['public_INDEX_created'])
    else:
        check(label+':no_exception',exception is None)
        if exception is None:
            index=json.loads((folder/'q/h/public/INDEX.json').read_bytes())
            receipt=json.loads((folder/'q/h/private/PROVENANCE.json').read_bytes())
            first_id=controls['private/ANON_MAP.json']['rows'][0]['anonymous_id']
            by_id={answer['anonymous_id']:answer for answer in index['answers']}
            first=by_id[first_id];tail=[answer for key,answer in by_id.items() if key!=first_id]
            state='failed_before_consumer' if variant=='none' else 'failed'
            check(label+':one_failed_eight_not_run',len(by_id)==9 and first['execution_record_state']==state
              and len(tail)==8 and all((row['execution_record_state'],row['answer_state'])==('not_run','not_run') for row in tail))
            check(label+':no_fake_answer',all(row['answer_file'] is None for row in by_id.values())
              and not list((folder/'q/h/public').rglob('answer.txt')) and first['answer_state']=='missing')
            check(label+':original_run_bytes_and_null_preserved',(folder/'q/h/private/control/RUN_RESULT.json').read_bytes()==before['RUN_RESULT.json'])
            check(label+':GO_STARTED_bytes_and_hashes_preserved',all(
              (folder/'q/h/private/control'/name).read_bytes()==before[name] and receipt['control_sha256'][name]==sha(before[name]) for name in ('GO.json','STARTED.json')))
            original_consumer=controls['RUN_RESULT.json']['records'][0]['consumer']
            if original_consumer is not None:
                raw=(folder/'cells'/controls['PLAN.json']['sequence'][0]['cell']/'CONSUMER.json').read_bytes()
                audit=next(row for row in receipt['answers'] if row['mapping']['anonymous_id']==first_id)
                check(label+':consumer_null_or_missing_PID_not_fabricated',json.loads(raw)==original_consumer
                  and audit['source_files_sha256']['CONSUMER.json']==sha(raw)
                  and ('consumer_pid' not in original_consumer if variant=='missing_pid' else original_consumer['consumer_pid'] is None))
            check(label+':all_control_sources_unchanged',all((folder/name).read_bytes()==raw for name,raw in before.items()))
    put(folder/'CASE.json',enc(record));cases.append(record)


def additional_checks(module):
    for variant in ('none','null_pid','missing_pid'):invoke(module,'ok_'+variant,variant)
    def setv(file,key,value):return lambda c:c[file].__setitem__(key,value)
    def setrow(key,value):return lambda c:c['RUN_RESULT.json']['records'][0].__setitem__(key,value)
    negative=[
      ('no_go',lambda c:c.pop('GO.json'),('FileNotFoundError','GO.json')),
      ('go_task',setv('GO.json','task','OTHER'),('AssertionError','zero-launch GO binding mismatch')),
      ('go_hash',setv('GO.json','plan_sha256','0'*64),('AssertionError','zero-launch GO binding mismatch')),
      ('go_max',setv('GO.json','max_consumers',8),('AssertionError','zero-launch GO binding mismatch')),
      ('go_unauthorized',setv('GO.json','authorized',False),('AssertionError','zero-launch GO binding mismatch')),
      ('no_started',lambda c:c.pop('STARTED.json'),('FileNotFoundError','STARTED.json')),
      ('started_hash',setv('STARTED.json','plan_sha256','0'*64),('AssertionError','zero-launch STARTED binding mismatch')),
      ('started_max',setv('STARTED.json','max_consumers',8),('AssertionError','zero-launch STARTED binding mismatch')),
      ('started_zero',setv('STARTED.json','started_ns',0),('AssertionError','zero-launch STARTED binding mismatch')),
      ('no_terminal',lambda c:c['RUN_RESULT.json'].pop('batch_ended_ns'),('AssertionError','terminal batch record required')),
      ('empty_stop',setv('RUN_RESULT.json','stop',None),('AssertionError','partial run needs its preserved stop reason')),
      ('whitespace_stop',setv('RUN_RESULT.json','stop','   '),('AssertionError','zero-launch failed prefix required')),
      ('bad_started_count',setv('RUN_RESULT.json','started_cells',2),('AssertionError','zero-launch terminal counts mismatch')),
      ('bad_maximum',setv('RUN_RESULT.json','maximum_consumers',8),('AssertionError','zero-launch terminal counts mismatch')),
      ('bad_all_dispatched',setv('RUN_RESULT.json','all_planned_dispatched',True),('AssertionError','zero-launch terminal counts mismatch')),
      ('replacements_allowed',setv('RUN_RESULT.json','no_replacements',False),('AssertionError','zero-launch terminal counts mismatch')),
      ('start_after_cell',setv('STARTED.json','started_ns',4),('AssertionError','zero-launch timing mismatch')),
      ('bad_batch_wall',setv('RUN_RESULT.json','batch_wall_ns',9),('AssertionError','zero-launch timing mismatch')),
      ('bad_cell_wall',setrow('full_cell_wall_ns',9),('AssertionError','zero-launch timing mismatch')),
      ('bad_570_flag',setrow('within_570s',False),('AssertionError','zero-launch timing mismatch')),
      ('no_error',setrow('errors',[]),('AssertionError','zero-launch failed prefix required')),
      ('prep_only',lambda c:c.pop('RUN_RESULT.json'),('FileNotFoundError','RUN_RESULT.json'))]
    for label,mutation,expect in negative:invoke(module,label,mutation=mutation,expect=expect)
    for key,value in (('errors',[]),('status','completed'),('valid_completion',True),('thread_id','synthetic_unknown_thread'),('final','synthetic_unbound_text'),('consumer_pid',0)):
        def change(c,key=key,value=value):c['RUN_RESULT.json']['records'][0]['consumer'][key]=value
        invoke(module,'bad_consumer_'+key,'null_pid',change,('AssertionError','zero-launch failed prefix required'))


def main():
    global WORK
    sys.dont_write_bytecode=True
    assert not (TESTS/'RESULTS_01.json').exists() and not (TESTS/'OUTPUTS_01.zip').exists()
    WORK=Path(tempfile.mkdtemp(prefix='lrcfix-')).resolve()
    marker={'synthetic':True,'owner_test_script':str(Path(__file__).resolve()),
      'test_script_sha256':sha(Path(__file__).read_bytes()),'real_consumers':0,'product_calls':0,
      'Blender_sessions':0,'GO_files_are_synthetic_only':True,'old_cache_removal':False,
      'cleanup_performed':False,'raw_outputs_retained_here':True}
    put(WORK/'SYNTHETIC_OWNER.json',enc(marker))
    legacy=None;unexpected=None
    try:
        module=compile_module('lrc_fixed_packager_direct_source',PACK,EXPECTED)
        def forbidden(kind):
            def stop(*args,**kwargs):external[kind]+=1;raise AssertionError('forbidden external '+kind)
            return stop
        with patch.object(subprocess,'Popen',side_effect=forbidden('subprocess')),patch.object(socket,'socket',side_effect=forbidden('socket')):
            legacy=legacy_regression(module)
            additional_checks(module)
    except BaseException as exc:unexpected={'type':type(exc).__name__,'traceback':traceback.format_exc()}
    members={path.relative_to(WORK).as_posix():{'bytes':path.stat().st_size,'sha256':sha(path.read_bytes())} for path in WORK.rglob('*') if path.is_file()}
    with zipfile.ZipFile(TESTS/'OUTPUTS_01.zip','x',compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(members):archive.writestr(name,(WORK/name).read_bytes())
    with zipfile.ZipFile(TESTS/'OUTPUTS_01.zip') as archive:
        archive_ok=set(archive.namelist())==set(members) and all(sha(archive.read(name))==meta['sha256'] for name,meta in members.items())
    check('complete_original_output_archive',archive_ok)
    check('external_process_socket_attempts_zero',external=={'subprocess':0,'socket':0})
    report={'synthetic':True,'passed':unexpected is None and all(row['passed'] for row in checks),
      'new_checks':checks,'new_check_count':len(checks),'new_check_failures':sum(not row['passed'] for row in checks),
      'old_231_regression':None if legacy is None else {'passed':legacy['passed'],'check_count':legacy['check_count'],
        'source_sha256':OLD_HARNESS_SHA,'effective_runtime_overrides':legacy['runtime_overrides']},
      'total_assertion_count':(0 if legacy is None else legacy['check_count'])+len(checks),
      'unexpected_error':unexpected,'case_records':cases,'work_root':str(WORK),'owner_marker_sha256':sha((WORK/'SYNTHETIC_OWNER.json').read_bytes()),
      'outputs_archive':'OUTPUTS_01.zip','outputs_archive_sha256':sha((TESTS/'OUTPUTS_01.zip').read_bytes()),
      'archive_member_count':len(members),'test_script_sha256':sha(Path(__file__).read_bytes()),'packager_sha256':EXPECTED,
      'model_consumers':0,'product_calls':0,'CLI_launches':0,'Blender_sessions':0,'external_attempts':external,
      'old_outputs_or_caches_changed':False,'raw_temporary_outputs_deleted':False,
      'scope':'Synthetic failure receipt acceptance and faithful archival only. No recorded positive PID is not a general proof that a real process never started; unknown state and nulls remain as recorded.'}
    for name,value in (('OUTPUT_MANIFEST_01.json',{'work_root':str(WORK),'members':members}),('RESULTS_01.json',report)):
        with (TESTS/name).open('x',encoding='utf8',newline='\n') as stream:json.dump(value,stream,ensure_ascii=False,sort_keys=True,indent=2);stream.write('\n')
    print(json.dumps({'passed':report['passed'],'old_231':None if legacy is None else legacy['passed'],
      'new_checks':len(checks),'new_failures':report['new_check_failures'],'total_assertions':report['total_assertion_count'],
      'unexpected_error':None if unexpected is None else unexpected['type'],'external_attempts':external,
      'report':str(TESTS/'RESULTS_01.json')},ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
